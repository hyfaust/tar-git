"""File awareness: hash tracking, change detection, rebuild.

Provides the synchronisation layer between working directory and staging:
- **detect_changes**: compare working-dir hashes against stored hashes
- **rebuild**: restore missing files from staging (no overwrite)
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .config import Config
from .git_backend import GitBackend
from .processor import Processor
from .scanner import FileNode, Scanner
from .utils import print_err, print_info, print_ok, print_step, print_warn, sha256_file


class FileAwareness:
    """Track file hashes and orchestrate sync operations."""

    HASHES_FILENAME = "hashes.json"

    def __init__(self, working_dir: Path, config: Config) -> None:
        self.working_dir = working_dir
        self.config = config
        self.staging_dir = working_dir / GitBackend.STAGING_DIR
        self.hashes_path = self.staging_dir / self.HASHES_FILENAME
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
        self.staging_dir.mkdir(parents=True, exist_ok=True)
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
        current: Dict[str, str] = {
            rel: node.hash for rel, node in scanner.files.items()
        }

        modified: List[FileNode] = []
        added: List[FileNode] = []
        deleted: List[str] = []

        for rel, node in scanner.files.items():
            old = self.hashes.get(rel, "")
            if old == "":
                added.append(node)
            elif old != node.hash:
                modified.append(node)

        current_rels = set(current.keys())
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

    def rebuild(self, scanner: Scanner, processor: Processor) -> int:
        """Restore missing files from staging to working dir.

        Only creates files that do **not** already exist in the working dir.
        Returns the number of files restored.
        """
        self.load_hashes()
        restored = 0
        for rel, expected_hash in self.hashes.items():
            fpath = self.working_dir / rel
            if fpath.exists():
                continue

            # Find the node from scanner (for staging_path lookup)
            node = scanner.get_node(rel)
            if node is not None:
                staging = processor.staging_path(node)
                if staging.exists():
                    try:
                        fpath.parent.mkdir(parents=True, exist_ok=True)
                        if node.is_archive:
                            processor.pack_single(node)
                        else:
                            shutil.copy2(str(staging), str(fpath))
                        print_ok(f"Restored: {node.name}")
                        restored += 1
                    except Exception as exc:
                        print_err(f"Restore failed ({node.name}): {exc}")
                    continue

            # Node not in scanner (file was deleted from working dir).
            # Try plain file from staging, or archive directory pack.
            staging_file = self.staging_dir / rel
            if staging_file.exists():
                try:
                    fpath.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(staging_file), str(fpath))
                    print_ok(f"Restored: {fpath.name}")
                    restored += 1
                except Exception as exc:
                    print_err(f"Restore failed ({fpath.name}): {exc}")
                continue

            # Archive: staging is a directory derived from the file name
            # Try common extract_dir_tpl patterns: {name}_{suffix}
            stem = fpath.stem
            for comp_config in self.config.compressions.values():
                staging_dir_name = comp_config.extract_dir_tpl.format(
                    name=stem, suffix=comp_config.suffix
                )
                staging_dir = self.staging_dir / fpath.parent.relative_to(self.working_dir) / staging_dir_name
                if staging_dir.exists() and staging_dir.is_dir():
                    # Found staging directory - create a temp node for packing
                    from .scanner import FileNode, FileType
                    temp_node = FileNode(
                        path=fpath,
                        file_type=FileType.TAR,
                        suffix=comp_config.suffix,
                    )
                    try:
                        processor.pack_single(temp_node)
                        if fpath.exists():
                            print_ok(f"Restored: {fpath.name}")
                            restored += 1
                            break
                    except Exception as exc:
                        print_err(f"Restore failed ({fpath.name}): {exc}")
                    continue

        if restored == 0:
            print_info("No missing files to restore")
        else:
            print_ok(f"Restored {restored} file(s)")
        return restored
