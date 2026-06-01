"""File processor: extract/copy files into ``.tgit/`` staging, and reverse.

Handles both directions:
- **x_operate** (working → staging): unpack archives + copy plain files
- **c_operate** (staging → working): pack archives + copy plain files
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import List

from .config import Config
from .git_backend import GitBackend
from .scanner import FileNode, FileType, Scanner
from .utils import print_err, print_info, print_ok, print_step, print_warn


class Processor:
    """Move files between working directory and ``.tgit/`` staging area."""

    def __init__(self, working_dir: Path, config: Config) -> None:
        self.working_dir = working_dir
        self.config = config
        self.staging_dir = working_dir / GitBackend.STAGING_DIR

    # ── x_operate: working → staging ─────────────────────────────────────

    def sync_to_staging(self, scanner: Scanner) -> None:
        """Extract / copy all tracked files into ``.tgit/``."""
        self._ensure_staging()
        for node in scanner.files.values():
            if node.is_archive:
                self._unpack(node)
            else:
                self._copy_to_staging(node)

    def unpack_single(self, node: FileNode) -> bool:
        """Extract one archive into staging."""
        self._ensure_staging()
        return self._unpack(node)

    def copy_to_staging(self, node: FileNode) -> bool:
        """Copy one plain file into staging."""
        self._ensure_staging()
        return self._copy_to_staging(node)

    # ── c_operate: staging → working ─────────────────────────────────────

    def sync_to_workdir(self, scanner: Scanner) -> None:
        """Pack / copy files from ``.tgit/`` back to working directory."""
        for node in scanner.files.values():
            if node.is_archive:
                self._pack(node)
            else:
                self._copy_to_workdir(node)

    def pack_single(self, node: FileNode) -> bool:
        """Pack one archive from staging back to working dir."""
        return self._pack(node)

    def copy_to_workdir(self, node: FileNode) -> bool:
        """Copy one plain file from staging back to working dir."""
        return self._copy_to_workdir(node)

    # ── Staging setup ────────────────────────────────────────────────────

    def _ensure_staging(self) -> None:
        """Create ``.tgit/`` and its internal ``.gitignore`` if missing."""
        if not self.staging_dir.exists():
            self.staging_dir.mkdir(parents=True)
            from .utils import set_hidden
            set_hidden(self.staging_dir)

        ig = self.staging_dir / ".gitignore"
        if not ig.exists():
            with open(ig, "w", encoding="utf-8") as fh:
                fh.write("# tgit internal .gitignore\n")
                fh.write("# Track everything inside staging\n")
                fh.write("!.gitignore\n")

    # ── Archive operations ───────────────────────────────────────────────

    def _unpack(self, node: FileNode) -> bool:
        """Extract an archive into the corresponding staging sub-directory."""
        comp = self.config.get_compression(node.suffix)
        if not comp:
            print_warn(f"No compression config for .{node.suffix}: {node.name}")
            return False

        dst = self.staging_path(node)
        if dst.exists():
            shutil.rmtree(dst)
        dst.mkdir(parents=True, exist_ok=True)

        cmd = self._expand(comp.extract_cmd, node, is_pack=False)
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if r.returncode == 0:
                return True
            print_err(f"Extract failed ({node.name}): {r.stderr.strip()}")
            return False
        except Exception as exc:
            print_err(f"Extract error ({node.name}): {exc}")
            return False

    def _pack(self, node: FileNode) -> bool:
        """Pack a staging sub-directory back into the archive file."""
        comp = self.config.get_compression(node.suffix)
        if not comp:
            return False

        src = self.staging_path(node)
        if not src.exists():
            print_warn(f"Staging missing for {node.name}")
            return False

        cmd = self._expand(comp.pack_cmd, node, is_pack=True)
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if r.returncode == 0:
                return True
            print_err(f"Pack failed ({node.name}): {r.stderr.strip()}")
            return False
        except Exception as exc:
            print_err(f"Pack error ({node.name}): {exc}")
            return False

    def _expand(self, cmd: List[str], node: FileNode, is_pack: bool) -> List[str]:
        """Substitute ``{src}``, ``{dst}``, ``{name}``, ``{suffix}`` placeholders."""
        if is_pack:
            src = str(self.staging_path(node))
            dst = str(node.path)
        else:
            src = str(node.path)
            dst = str(self.staging_path(node))

        result = []
        for part in cmd:
            part = part.replace("{src}", src)
            part = part.replace("{dst}", dst)
            part = part.replace("{name}", node.path.stem)
            part = part.replace("{suffix}", node.suffix)
            result.append(part)
        return result

    # ── Plain file operations ────────────────────────────────────────────

    def _copy_to_staging(self, node: FileNode) -> bool:
        dst = self.staging_path(node)
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(str(node.path), str(dst))
            return True
        except OSError as exc:
            print_err(f"Copy to staging failed ({node.name}): {exc}")
            return False

    def _copy_to_workdir(self, node: FileNode) -> bool:
        src = self.staging_path(node)
        if not src.exists():
            return False
        node.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(str(src), str(node.path))
            return True
        except OSError as exc:
            print_err(f"Copy to workdir failed ({node.name}): {exc}")
            return False

    # ── Path mapping ─────────────────────────────────────────────────────

    def staging_path(self, node: FileNode) -> Path:
        """Return the path inside ``.tgit/`` that corresponds to *node*."""
        rel = node.path.relative_to(self.working_dir)
        if node.is_archive:
            comp = self.config.get_compression(node.suffix)
            if comp:
                dirname = comp.extract_dir_tpl.format(
                    name=node.path.stem, suffix=node.suffix
                )
                return self.staging_dir / rel.parent / dirname
        return self.staging_dir / rel
