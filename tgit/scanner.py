"""File scanner: ``.tgitignore`` parsing, directory walking, file tree.

Builds a tree of ``FileNode`` objects classified as *tar_file* (archive) or
*plain_file*, respecting ignore rules.
"""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

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
    ignored: bool = False

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


# ── Ignore rules ─────────────────────────────────────────────────────────────

class _IgnoreRule:
    """A single ``.tgitignore`` pattern."""

    def __init__(self, pattern: str) -> None:
        self.original = pattern
        self.negated = pattern.startswith("!")
        p = pattern[1:] if self.negated else pattern
        self.dir_only = p.endswith("/")
        p = p.rstrip("/")

        # Normalise: leading ``/`` means anchored to root
        self.anchor = p.startswith("/")
        p = p.lstrip("/")

        # Trailing ``**`` → match anything inside
        if p.endswith("**"):
            p = p[:-2] + "*"

        self.pattern = p

    def match(self, rel_path: str, is_dir: bool) -> bool:
        """Return True if this rule matches *rel_path*, False otherwise."""
        if self.dir_only and not is_dir:
            return False

        path_parts = rel_path.replace("\\", "/").split("/")

        if self.anchor:
            target = "/".join(path_parts)
            return fnmatch.fnmatch(target, self.pattern)

        # Non-anchored: try matching against every suffix of the path
        for i in range(len(path_parts)):
            suffix = "/".join(path_parts[i:])
            if fnmatch.fnmatch(suffix, self.pattern):
                return True
            if fnmatch.fnmatch(path_parts[i], self.pattern):
                return True

        return False


# ── Scanner ──────────────────────────────────────────────────────────────────

class Scanner:
    """Walk the working directory, classify files, build a tree.

    Call ``scan()`` to (re)build.  The result is cached; a rescan is
    triggered automatically when ``.tgitignore`` or ``tgit.toml`` changes.
    """

    IGNORE_FILENAME = ".tgitignore"

    def __init__(self, working_dir: Path, config: Config) -> None:
        self.working_dir = working_dir
        self.config = config
        self.ignore_path = working_dir / self.IGNORE_FILENAME
        self.root = DirNode(path=working_dir)
        self.files: Dict[str, FileNode] = {}  # rel_path → FileNode
        self._rules: List[_IgnoreRule] = []
        self._last_ignore_mtime: float = 0.0
        self._last_config_mtime: float = 0.0
        self._scanned = False

    # ── Public API ───────────────────────────────────────────────────────

    def scan(self, force: bool = False) -> None:
        """Walk the directory tree and populate ``self.files`` / ``self.root``."""
        if not force and self._scanned and not self._dirty():
            return

        self._load_rules()
        self.root = DirNode(path=self.working_dir)
        self.files.clear()
        suffixes = self.config.get_compression_suffixes()

        for dirpath, dirnames, filenames in os.walk(self.working_dir):
            dp = Path(dirpath)

            # Skip internal directories
            dirnames[:] = [
                d for d in dirnames
                if d != ".tgit"
                and d != ".git"
            ]

            rel_dp = dp.relative_to(self.working_dir)
            parent = self._ensure_dir(rel_dp)

            for fname in filenames:
                fpath = dp / fname
                rel = fpath.relative_to(self.working_dir)
                rel_str = rel.as_posix()

                if self._is_ignored(rel_str, is_dir=False):
                    continue

                # Exclude common non-trackable files
                if fname.endswith(".bak") or fname.startswith("~$"):
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
        self._last_ignore_mtime = self._mtime(self.ignore_path)
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
        return (
            self._mtime(self.ignore_path) != self._last_ignore_mtime
            or self._mtime(self.config.config_path) != self._last_config_mtime
        )

    @staticmethod
    def _mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    def _load_rules(self) -> None:
        self._rules.clear()
        if not self.ignore_path.exists():
            return
        with open(self.ignore_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#"):
                    self._rules.append(_IgnoreRule(line))

    def _is_ignored(self, rel_path: str, is_dir: bool) -> bool:
        """Determine whether a path should be ignored (gitignore semantics).

        Default (no rules match) → NOT ignored.
        A non-negated match       → ignored.
        A negated match (!pref)   → un-ignored.
        Last matching rule wins.
        """
        ignored = False
        for rule in self._rules:
            if rule.match(rel_path, is_dir):
                ignored = not rule.negated
        return ignored

    def _ensure_dir(self, rel: Path) -> DirNode:
        node = self.root
        for part in rel.parts:
            if part not in node.children:
                child = DirNode(path=node.path / part)
                node.children[part] = child
            node = node.children[part]
        return node

    @staticmethod
    def _match_suffix(filename: str, suffixes: List[str]) -> Optional[str]:
        """Return the longest matching suffix, or *None*."""
        fl = filename.lower()
        for sfx in suffixes:
            if fl.endswith(f".{sfx}"):
                return sfx
        return None
