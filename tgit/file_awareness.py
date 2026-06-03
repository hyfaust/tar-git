"""File awareness: hash tracking, change detection, rebuild.

- **detect_changes**: compare working-dir hashes against stored hashes
- **rebuild**: restore missing files from git (plain files directly,
  archives via extracted-directory restore + pack)
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .config import Config
from .git_backend import GitBackend
from .processor import Processor
from .scanner import FileNode, Scanner
from .utils import print_err, print_info, print_ok, print_step, print_warn, sha256_file, run_git


class FileAwareness:
    """Track file hashes and orchestrate restore operations."""

    HASHES_FILENAME = "hashes.json"

    def __init__(self, working_dir: Path, config: Config) -> None:
        self.working_dir = working_dir
        self.config = config
        self.hashes_path = working_dir / self.HASHES_FILENAME
        self.hashes: Dict[str, str] = {}

    # ── Hash persistence ─────────────────────────────────────────────────

    def load_hashes(self) -> None:
        if self.hashes_path.exists():
            try:
                with open(self.hashes_path, "r", encoding="utf-8") as fh:
                    self.hashes = json.load(fh)
            except (json.JSONDecodeError, OSError):
                self.hashes = {}
        else:
            self.hashes = {}

    def save_hashes(self) -> None:
        with open(self.hashes_path, "w", encoding="utf-8") as fh:
            json.dump(self.hashes, fh, indent=2, ensure_ascii=False)

    # ── Change detection ─────────────────────────────────────────────────

    def detect_changes(
        self, scanner: Scanner
    ) -> Tuple[List[FileNode], List[FileNode], List[str]]:
        """Compare current working-dir hashes against stored hashes.

        Returns (modified, added, deleted_names).
        """
        self.load_hashes()

        modified: List[FileNode] = []
        added: List[FileNode] = []
        deleted: List[str] = []

        for rel, node in scanner.files.items():
            old = self.hashes.get(rel, "")
            if old == "":
                added.append(node)
            elif old != node.hash:
                modified.append(node)

        current_rels = set(scanner.files.keys())
        for rel in self.hashes:
            if rel not in current_rels:
                deleted.append(rel)

        return modified, added, deleted

    def update_hashes(self, scanner: Scanner) -> None:
        """Refresh stored hashes to match current working-dir state."""
        self.load_hashes()
        for rel, node in scanner.files.items():
            self.hashes[rel] = node.hash
        self.save_hashes()

    # ── Rebuild ──────────────────────────────────────────────────────────

    def rebuild(
        self,
        scanner: Scanner,
        processor: Processor,
        git: GitBackend,
    ) -> int:
        """Restore missing files from git.

        - **Plain files**: restored directly via ``git show HEAD:<path>``.
        - **Archives**: extracted directory restored from git, then packed.

        Only creates files that do **not** already exist in the working dir.
        Returns the number of files restored.
        """
        self.load_hashes()
        restored = 0

        # Get the list of tracked files from HEAD
        r = run_git(["ls-tree", "-r", "--name-only", "HEAD"], cwd=str(self.working_dir))
        tracked_files = set()
        if r.returncode == 0:
            tracked_files = set(r.stdout.strip().splitlines())

        for rel, expected_hash in self.hashes.items():
            fpath = self.working_dir / rel
            if fpath.exists():
                continue

            node = scanner.get_node(rel)

            if node is not None and not node.is_archive:
                # Plain file: restore from git
                if rel in tracked_files:
                    ok = self._restore_plain_from_git(rel, fpath)
                    if ok:
                        print_ok(f"Restored: {node.name}")
                        restored += 1
                continue

            if node is not None and node.is_archive:
                # Archive: restore extracted dir from git, then pack
                extract_dir = processor.extract_path(node)
                extract_rel = extract_dir.relative_to(self.working_dir).as_posix()
                if self._restore_dir_from_git(extract_rel, extract_dir):
                    ok = processor.pack_single(node)
                    if ok and fpath.exists():
                        print_ok(f"Restored: {node.name}")
                        restored += 1
                continue

            # Node not in scanner — check if it's a deleted archive
            suffix = self._match_archive_suffix(rel, scanner)
            if suffix:
                # Archive file deleted but extracted dir may be in git
                extract_dir = processor.extract_path_simple(fpath, suffix)
                extract_rel = extract_dir.relative_to(self.working_dir).as_posix()
                if extract_rel in tracked_files or self._dir_in_git(extract_rel):
                    if self._restore_dir_from_git(extract_rel, extract_dir):
                        # Create a dummy node for packing
                        from .scanner import FileNode, FileType
                        dummy = FileNode(path=fpath, file_type=FileType.TAR, suffix=suffix)
                        ok = processor.pack_single(dummy)
                        if ok and fpath.exists():
                            print_ok(f"Restored: {fpath.name}")
                            restored += 1
                continue

            # Plain file: restore from git
            if rel in tracked_files:
                ok = self._restore_plain_from_git(rel, fpath)
                if ok:
                    print_ok(f"Restored: {fpath.name}")
                    restored += 1

        if restored == 0:
            print_info("No missing files to restore")
        else:
            print_ok(f"Restored {restored} file(s)")
        return restored

    def _match_archive_suffix(self, rel: str, scanner: Scanner) -> Optional[str]:
        """Return the archive suffix if *rel* looks like an archive file."""
        name = Path(rel).name.lower()
        for sfx in scanner.config.get_compression_suffixes():
            if name.endswith(f".{sfx}"):
                return sfx
        return None

    def _dir_in_git(self, rel_dir: str) -> bool:
        """Check if a directory exists in git HEAD."""
        r = run_git(
            ["ls-tree", "--name-only", f"HEAD:{rel_dir}"],
            cwd=str(self.working_dir),
        )
        return r.returncode == 0

    # ── Git restore helpers ──────────────────────────────────────────────

    def _restore_plain_from_git(self, rel: str, target: Path) -> bool:
        """Restore a single file from ``git show HEAD:<rel>``."""
        r = run_git(["show", f"HEAD:{rel}"], cwd=str(self.working_dir))
        if r.returncode != 0:
            return False
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(r.stdout.encode("utf-8") if isinstance(r.stdout, str) else r.stdout)
            return True
        except OSError as exc:
            print_err(f"Restore failed ({target.name}): {exc}")
            return False

    def _restore_dir_from_git(self, rel_dir: str, target: Path) -> bool:
        """Restore a directory tree from ``git ls-tree -r HEAD:<dir>``."""
        r = run_git(
            ["ls-tree", "-r", f"HEAD:{rel_dir}"],
            cwd=str(self.working_dir),
        )
        if r.returncode != 0:
            return False

        try:
            if target.exists():
                import shutil
                shutil.rmtree(target)
            target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print_err(f"Restore dir failed: {exc}")
            return False

        for line in r.stdout.strip().splitlines():
            parts = line.split(None, 3)
            if len(parts) < 4:
                continue
            blob_hash = parts[2]
            file_rel = parts[3]
            fpath = target / file_rel
            fpath.parent.mkdir(parents=True, exist_ok=True)
            br = run_git(["show", blob_hash], cwd=str(self.working_dir))
            if br.returncode == 0:
                try:
                    fpath.write_bytes(
                        br.stdout.encode("utf-8") if isinstance(br.stdout, str) else br.stdout
                    )
                except OSError:
                    pass

        return True
