"""Diff engine: compare files across working directory and versions.

Three modes:
1. **Plain git diff** – ``git diff`` on plain files (and unpacked archive dirs).
2. **Hash diff** – compare archive hashes (committed vs current).
3. **Custom diff** – run a configured diff tool for a specific suffix.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

from .config import Config
from .file_awareness import FileAwareness
from .git_backend import GitBackend
from .processor import Processor
from .scanner import FileNode, Scanner
from .utils import (
    bold,
    colorize,
    print_err,
    print_info,
    print_ok,
    print_step,
    print_warn,
    run_git,
    sha256_file,
    _C,
)


class DiffEngine:
    """Unified diff interface for tgit."""

    def __init__(
        self,
        working_dir: Path,
        config: Config,
        git: GitBackend,
        processor: Processor,
        awareness: FileAwareness,
    ) -> None:
        self.working_dir = working_dir
        self.config = config
        self.git = git
        self.processor = processor
        self.awareness = awareness

    # ── Mode 1: default diff (plain=git diff, archive=hash) ─────────────

    def diff_default(self, scanner: Scanner, files: Optional[List[str]] = None) -> bool:
        """Diff plain files via ``git diff``; report archive hash changes."""
        changed = False

        # Plain files: git diff
        if files:
            rels = [f for f in files if not self._is_archive(f, scanner)]
        else:
            rels = [rel for rel, n in scanner.files.items() if not n.is_archive]

        if rels:
            self._ensure_x_operate(scanner)
            r = run_git(["diff"] + rels, cwd=str(self.git.staging_dir))
            if r.stdout.strip():
                print(r.stdout)
                changed = True

        # Archive files: hash comparison
        if files:
            archive_files = [f for f in files if self._is_archive(f, scanner)]
        else:
            archive_files = None

        hash_changed = self._diff_hashes(scanner, archive_files)
        changed = changed or hash_changed

        if not changed:
            print_info("No changes")
        return changed

    # ── Mode 2: version diff (--at) ─────────────────────────────────────

    def diff_version(
        self,
        scanner: Scanner,
        version: str,
        files: Optional[List[str]] = None,
    ) -> bool:
        """Compare working directory against a version tag."""
        if not version.startswith("v"):
            version = f"v{version}"

        r = run_git(["rev-parse", "--verify", version], cwd=str(self.git.staging_dir))
        if r.returncode != 0:
            print_err(f"Version not found: {version}")
            return False

        self._ensure_x_operate(scanner)
        targets = self._resolve_files(files, scanner) if files else None
        return self._git_diff_version(scanner, version, targets)

    # ── Mode 3: suffix-specific diff (--docx, --tar, …) ─────────────────

    def diff_suffix(
        self,
        scanner: Scanner,
        suffix: str,
        filename: Optional[str] = None,
    ) -> bool:
        """Diff files of *suffix* using configured diff tool."""
        dc = self.config.get_diff_config(suffix)

        if dc and (dc.cmd or dc.script):
            return self._custom_diff(scanner, suffix, dc.cmd, dc.script, filename)
        else:
            return self._fallback_suffix_diff(scanner, suffix, filename)

    # ── Mode 4: suffix + version ─────────────────────────────────────────

    def diff_suffix_version(
        self,
        scanner: Scanner,
        suffix: str,
        version: str,
        filename: Optional[str] = None,
    ) -> bool:
        """Diff files of *suffix* against *version* using configured tool."""
        if not version.startswith("v"):
            version = f"v{version}"

        dc = self.config.get_diff_config(suffix)
        if dc and (dc.cmd or dc.script):
            return self._custom_diff_version(
                scanner, suffix, version, dc.cmd, dc.script, filename
            )
        else:
            # Fallback: plain git diff for this suffix against version
            suffix_files = self._files_of_suffix(scanner, suffix, filename)
            if not suffix_files:
                print_info(f"No .{suffix} files found")
                return False
            return self._git_diff_version(scanner, version, suffix_files)

    # ── Internal: git diff ───────────────────────────────────────────────

    def _git_diff_version(
        self,
        scanner: Scanner,
        version: str,
        files: Optional[List[str]],
    ) -> bool:
        """Plain ``git diff VERSION [-- files]``."""
        args = ["diff", version]
        if files:
            args.append("--")
            args.extend(files)
        r = run_git(args, cwd=str(self.git.staging_dir))
        if r.stdout.strip():
            print(r.stdout)
            return True
        print_info(f"No differences with {version}")
        return False

    def _ensure_x_operate(self, scanner: Scanner) -> None:
        """Ensure staging is up-to-date before diffing."""
        self.processor.sync_to_staging(scanner)

    # ── Internal: hash diff ──────────────────────────────────────────────

    def _diff_hashes(
        self, scanner: Scanner, files: Optional[List[str]] = None
    ) -> bool:
        """Compare current archive hashes against stored (committed) hashes."""
        self.awareness.load_hashes()
        targets = (
            [scanner.files[f] for f in files if f in scanner.files]
            if files
            else scanner.tar_files()
        )
        changed = False
        for node in targets:
            if not node.is_archive:
                continue
            old_hash = self.awareness.hashes.get(
                node.path.relative_to(self.working_dir).as_posix(), ""
            )
            if not old_hash:
                print_info(f"  New:    {node.name}")
                changed = True
            elif old_hash != node.hash:
                print_warn(f"  Changed: {node.name}")
                changed = True
        return changed

    # ── Internal: custom diff ────────────────────────────────────────────

    def _custom_diff(
        self,
        scanner: Scanner,
        suffix: str,
        cmd: List[str],
        script: Optional[str],
        filename: Optional[str],
    ) -> bool:
        """Run configured diff tool on all matching files (working vs HEAD)."""
        targets = self._files_of_suffix(scanner, suffix, filename)
        if not targets:
            print_info(f"No .{suffix} files found")
            return False

        changed = False
        for node in targets:
            head_file = self._extract_from_head(node)
            if head_file is None:
                print_info(f"  New: {node.name}")
                changed = True
                continue
            ok = self._run_custom(cmd, script, head_file, str(node.path))
            changed = changed or ok
        return changed

    def _custom_diff_version(
        self,
        scanner: Scanner,
        suffix: str,
        version: str,
        cmd: List[str],
        script: Optional[str],
        filename: Optional[str],
    ) -> bool:
        """Run configured diff tool comparing VERSION vs working dir."""
        targets = self._files_of_suffix(scanner, suffix, filename)
        if not targets:
            print_info(f"No .{suffix} files found")
            return False

        changed = False
        for node in targets:
            ver_file = self._extract_from_version(node, version)
            if ver_file is None:
                print_info(f"  Not in {version}: {node.name}")
                continue
            ok = self._run_custom(cmd, script, ver_file, str(node.path))
            changed = changed or ok
            Path(ver_file).unlink(missing_ok=True)
        return changed

    def _run_custom(
        self, cmd: List[str], script: Optional[str], old: str, new: str
    ) -> bool:
        """Execute a custom diff command/script."""
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"

        if script:
            script_path = self.working_dir / script
            if not script_path.exists():
                script_path = Path(script)
            actual_cmd = [sys.executable, str(script_path), old, new]
        else:
            actual_cmd = [
                c.replace("{old}", old).replace("{new}", new) for c in cmd
            ]

        try:
            r = subprocess.run(
                actual_cmd, capture_output=True, text=True, encoding="utf-8",
                errors="replace", env=env, timeout=120,
            )
            if r.stdout.strip():
                print(r.stdout)
                return True
            if r.stderr.strip():
                print(r.stderr, file=sys.stderr)
            return r.returncode != 0
        except Exception as exc:
            print_err(f"Custom diff failed: {exc}")
            return False

    # ── Internal: extract helpers ────────────────────────────────────────

    def _extract_from_head(self, node: FileNode) -> Optional[str]:
        """Extract an archive file from HEAD into a temp file, return its path."""
        staging = self.processor.staging_path(node)
        rel = staging.relative_to(self.git.staging_dir)
        r = run_git(
            ["ls-tree", "-r", f"HEAD:{rel.as_posix()}"],
            cwd=str(self.git.staging_dir),
        )
        if r.returncode != 0:
            return None

        td = tempfile.mkdtemp(prefix="tgit_diff_")
        head_dir = Path(td) / "head"
        head_dir.mkdir(parents=True, exist_ok=True)

        self._restore_from_ls_tree(r.stdout, str(head_dir), str(self.git.staging_dir))

        comp = self.config.get_compression(node.suffix)
        if not comp:
            shutil.rmtree(td, ignore_errors=True)
            return None

        temp_file = Path(td) / f"head.{node.suffix}"
        pack_cmd = [
            c.replace("{src}", str(head_dir)).replace("{dst}", str(temp_file))
            for c in comp.pack_cmd
        ]
        try:
            subprocess.run(pack_cmd, capture_output=True, timeout=60)
            if temp_file.exists():
                return str(temp_file)
        except Exception:
            pass
        shutil.rmtree(td, ignore_errors=True)
        return None

    def _extract_from_version(self, node: FileNode, version: str) -> Optional[str]:
        """Extract an archive file from *version* into a temp file."""
        staging = self.processor.staging_path(node)
        rel = staging.relative_to(self.git.staging_dir)
        r = run_git(
            ["ls-tree", "-r", f"{version}:{rel.as_posix()}"],
            cwd=str(self.git.staging_dir),
        )
        if r.returncode != 0:
            return None

        td = tempfile.mkdtemp(prefix="tgit_diff_")
        ver_dir = Path(td) / "ver"
        ver_dir.mkdir(parents=True, exist_ok=True)
        self._restore_from_ls_tree(r.stdout, str(ver_dir), str(self.git.staging_dir))

        comp = self.config.get_compression(node.suffix)
        if not comp:
            shutil.rmtree(td, ignore_errors=True)
            return None

        temp_file = Path(td) / f"{version}.{node.suffix}"
        pack_cmd = [
            c.replace("{src}", str(ver_dir)).replace("{dst}", str(temp_file))
            for c in comp.pack_cmd
        ]
        try:
            subprocess.run(pack_cmd, capture_output=True, timeout=60)
            if temp_file.exists():
                return str(temp_file)
        except Exception:
            pass
        shutil.rmtree(td, ignore_errors=True)
        return None

    @staticmethod
    def _restore_tree(data: str, base_dir: str, cwd: Optional[str] = None) -> None:
        """Parse ``git show`` tree output and recreate directories and files."""
        for line in data.splitlines():
            line = line.strip()
            if not line or line.startswith("warning:"):
                continue
            parts = line.split()
            if len(parts) < 4:
                continue
            name = " ".join(parts[3:])
            fpath = Path(base_dir) / name
            if line.startswith("040000"):
                fpath.mkdir(parents=True, exist_ok=True)
            elif line.startswith("100") and len(parts) >= 3:
                blob_hash = parts[2]
                try:
                    r = subprocess.run(
                        ["git", "show", blob_hash],
                        cwd=cwd, capture_output=True, timeout=30,
                    )
                    if r.returncode == 0:
                        fpath.parent.mkdir(parents=True, exist_ok=True)
                        fpath.write_bytes(r.stdout)
                except Exception:
                    pass

    @staticmethod
    def _restore_from_ls_tree(data: str, base_dir: str, cwd: str) -> None:
        """Parse ``git ls-tree -r`` output and recreate all files."""
        for line in data.splitlines():
            line = line.strip()
            if not line or line.startswith("warning:"):
                continue
            parts = line.split(None, 3)
            if len(parts) < 4:
                continue
            blob_hash = parts[2]
            rel_path = parts[3]
            fpath = Path(base_dir) / rel_path
            fpath.parent.mkdir(parents=True, exist_ok=True)
            try:
                r = subprocess.run(
                    ["git", "show", blob_hash],
                    cwd=cwd, capture_output=True, timeout=30,
                )
                if r.returncode == 0:
                    fpath.write_bytes(r.stdout)
            except Exception:
                pass

    # ── Internal: helpers ────────────────────────────────────────────────

    def _is_archive(self, rel_path: str, scanner: Scanner) -> bool:
        node = scanner.files.get(rel_path)
        return node.is_archive if node else False

    def _resolve_files(self, files: List[str], scanner: Scanner) -> List[str]:
        return [f for f in files if f in scanner.files]

    def _files_of_suffix(
        self,
        scanner: Scanner,
        suffix: str,
        filename: Optional[str],
    ) -> List[FileNode]:
        if filename:
            node = scanner.files.get(filename)
            if node and node.suffix == suffix:
                return [node]
            return []
        return [n for n in scanner.files.values() if n.suffix == suffix]
