"""File processor: in-place archive extraction and packing.

Archives are extracted next to their original files (e.g. ``test.tar`` →
``test.tar/``).  Plain files are tracked directly by git — no copying needed.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import List

from .config import Config
from .scanner import FileNode, Scanner
from .utils import print_err, print_info, print_ok, print_step, print_warn


class Processor:
    """Extract / pack archives in the working directory."""

    def __init__(self, working_dir: Path, config: Config) -> None:
        self.working_dir = working_dir
        self.config = config

    # ── Batch operations ─────────────────────────────────────────────────

    def extract_all(self, scanner: Scanner) -> None:
        """Extract all tracked archives in-place."""
        for node in scanner.tar_files():
            self.extract_single(node)

    def pack_all(self, scanner: Scanner) -> None:
        """Pack all extracted archives back to their original files."""
        for node in scanner.tar_files():
            self.pack_single(node)

    # ── Single file operations ───────────────────────────────────────────

    def extract_single(self, node: FileNode) -> bool:
        """Extract one archive in-place (next to the original file)."""
        comp = self.config.get_compression(node.suffix)
        if not comp:
            print_warn(f"No compression config for .{node.suffix}: {node.name}")
            return False

        dst = self.extract_path(node)
        if dst.exists():
            shutil.rmtree(dst)
        dst.mkdir(parents=True, exist_ok=True)

        cmd = self._expand_cmd(comp.extract_cmd, node, dst)
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if r.returncode == 0:
                return True
            print_err(f"Extract failed ({node.name}): {r.stderr.strip()}")
            return False
        except Exception as exc:
            print_err(f"Extract error ({node.name}): {exc}")
            return False

    def pack_single(self, node: FileNode) -> bool:
        """Pack an extracted directory back into the archive file."""
        comp = self.config.get_compression(node.suffix)
        if not comp:
            return False

        src = self.extract_path(node)
        if not src.exists():
            print_warn(f"Extracted dir missing for {node.name}")
            return False

        cmd = self._expand_cmd(comp.pack_cmd, node, src, is_pack=True)
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if r.returncode == 0:
                return True
            print_err(f"Pack failed ({node.name}): {r.stderr.strip()}")
            return False
        except Exception as exc:
            print_err(f"Pack error ({node.name}): {exc}")
            return False

    # ── Path helpers ─────────────────────────────────────────────────────

    def extract_path(self, node: FileNode) -> Path:
        """Return the directory where *node*'s archive is extracted."""
        comp = self.config.get_compression(node.suffix)
        if not comp:
            raise ValueError(f"No compression config for .{node.suffix}")
        dirname = comp.extract_dir_tpl.format(
            src_name=node.path.name,
            name=node.path.stem,
            suffix=node.suffix,
        )
        return node.path.parent / dirname

    def extract_path_simple(self, archive_path: Path, suffix: str) -> Path:
        """Return the extract directory for an archive path and suffix."""
        comp = self.config.get_compression(suffix)
        if not comp:
            raise ValueError(f"No compression config for .{suffix}")
        dirname = comp.extract_dir_tpl.format(
            src_name=archive_path.name,
            name=archive_path.stem,
            suffix=suffix,
        )
        return archive_path.parent / dirname

    # ── Internal ─────────────────────────────────────────────────────────

    def _expand_cmd(
        self,
        cmd: List[str],
        node: FileNode,
        dst: Path,
        is_pack: bool = False,
    ) -> List[str]:
        """Substitute placeholders in a command template.

        For extract: ``{src}`` = archive file, ``{dst}`` = extract directory.
        For pack:    ``{src}`` = extract directory, ``{dst}`` = archive file.
        """
        if is_pack:
            src_str = str(dst)   # the extracted directory
            dst_str = str(node.path)  # the archive file to create
        else:
            src_str = str(node.path)  # the archive file
            dst_str = str(dst)   # the directory to extract into

        result = []
        for part in cmd:
            part = part.replace("{src}", src_str)
            part = part.replace("{dst}", dst_str)
            part = part.replace("{name}", node.path.stem)
            part = part.replace("{suffix}", node.suffix)
            result.append(part)
        return result
