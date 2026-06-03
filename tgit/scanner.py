"""File scanner: directory walking and file classification.

Builds a tree of ``FileNode`` objects classified as *tar_file* (archive) or
*plain_file*.  Ignores ``.git/`` directories and extracted-archive directories.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set

from .config import Config
from .utils import sha256_file


# ── Data structures ──────────────────────────────────────────────────────────

class FileType(Enum):
    TAR = "tar"
    PLAIN = "plain"


@dataclass
class FileNode:
    """A single file in the working directory."""
    path: Path
    file_type: FileType
    suffix: str
    hash: str = ""

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def is_archive(self) -> bool:
        return self.file_type == FileType.TAR


@dataclass
class DirNode:
    """A directory in the working directory."""
    path: Path
    children: Dict[str, "DirNode"] = field(default_factory=dict)
    files: Dict[str, FileNode] = field(default_factory=dict)


# ── Scanner ──────────────────────────────────────────────────────────────────

class Scanner:
    """Walk the working directory, classify files, build a tree.

    Call ``scan()`` to (re)build.  The result is cached; a rescan is
    triggered automatically when ``tgit.toml`` changes.
    """

    def __init__(self, working_dir: Path, config: Config) -> None:
        self.working_dir = working_dir
        self.config = config
        self.root = DirNode(path=working_dir)
        self.files: Dict[str, FileNode] = {}  # rel_path (posix) → FileNode
        self._last_config_mtime: float = 0.0
        self._scanned = False

    # ── Public API ───────────────────────────────────────────────────────

    def scan(self, force: bool = False) -> None:
        """Walk the directory tree and populate ``self.files`` / ``self.root``."""
        if not force and self._scanned and not self._dirty():
            return

        self.root = DirNode(path=self.working_dir)
        self.files.clear()
        suffixes = self.config.get_compression_suffixes()

        for dirpath, dirnames, filenames in os.walk(self.working_dir):
            dp = Path(dirpath)

            # Skip .git directory
            dirnames[:] = [d for d in dirnames if d != ".git"]

            # Identify archive files in this directory to compute
            # which subdirectories are their extracted counterparts.
            extracted_dirs = self._find_extracted_dirs(dp, filenames, suffixes)
            dirnames[:] = [d for d in dirnames if d not in extracted_dirs]

            rel_dp = dp.relative_to(self.working_dir)
            parent = self._ensure_dir(rel_dp)

            for fname in filenames:
                fpath = dp / fname
                rel = fpath.relative_to(self.working_dir)
                rel_str = rel.as_posix()

                # Exclude common non-trackable files
                if fname.endswith(".bak") or fname.startswith("~$"):
                    continue

                # Exclude tgit internal files
                if fname in ("hashes.json", "tgit.toml"):
                    continue

                suffix = self._match_suffix(fname, suffixes)
                node = FileNode(
                    path=fpath,
                    file_type=FileType.TAR if suffix else FileType.PLAIN,
                    suffix=suffix or "",
                    hash=sha256_file(fpath),
                )
                parent.files[fname] = node
                self.files[rel_str] = node

        self._scanned = True
        self._last_config_mtime = self._mtime(self.config.config_path)

    def tar_files(self) -> List[FileNode]:
        return [f for f in self.files.values() if f.is_archive]

    def plain_files(self) -> List[FileNode]:
        return [f for f in self.files.values() if not f.is_archive]

    def get_node(self, rel_path: str) -> Optional[FileNode]:
        return self.files.get(rel_path)

    def needs_rescan(self) -> bool:
        return self._dirty()

    # ── Internal ─────────────────────────────────────────────────────────

    def _dirty(self) -> bool:
        return self._mtime(self.config.config_path) != self._last_config_mtime

    @staticmethod
    def _mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    def _ensure_dir(self, rel: Path) -> DirNode:
        node = self.root
        for part in rel.parts:
            if part not in node.children:
                child = DirNode(path=node.path / part)
                node.children[part] = child
            node = node.children[part]
        return node

    def _find_extracted_dirs(
        self, dirpath: Path, filenames: List[str], suffixes: List[str]
    ) -> Set[str]:
        """Return directory names in *dirpath* that are extracted archives."""
        extracted: Set[str] = set()
        for fname in filenames:
            suffix = self._match_suffix(fname, suffixes)
            if not suffix:
                continue
            comp = self.config.get_compression(suffix)
            if not comp:
                continue
            dirname = comp.extract_dir_tpl.format(
                src_name=fname,
                name=Path(fname).stem,
                suffix=suffix,
            )
            if (dirpath / dirname).is_dir():
                extracted.add(dirname)
        return extracted

    @staticmethod
    def _match_suffix(filename: str, suffixes: List[str]) -> Optional[str]:
        """Return the longest matching suffix, or *None*."""
        fl = filename.lower()
        for sfx in suffixes:
            if fl.endswith(f".{sfx}"):
                return sfx
        return None
