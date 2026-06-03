"""TOML configuration parsing for tgit.

Reads ``tgit.toml`` from the working directory and exposes structured
config objects for compression formats, diff tools, and general settings.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class CompressionConfig:
    """Configuration for a single archive format."""
    suffix: str
    extract_cmd: List[str]
    pack_cmd: List[str]
    extract_dir_tpl: str = "{name}_{suffix}"


@dataclass
class DiffConfig:
    """Configuration for a custom diff tool on a specific suffix."""
    suffix: str
    cmd: List[str] = field(default_factory=list)
    script: Optional[str] = None


@dataclass
class TgitSettings:
    """General tgit settings."""
    autosave_interval: int = 300
    gitignore_ignore: List[str] = field(default_factory=list)


# ── Default configs ──────────────────────────────────────────────────────────

_DOCX_EXTRACT = (
    "import zipfile, sys, os; "
    "src, dst = sys.argv[1], sys.argv[2]; "
    "os.makedirs(dst, exist_ok=True); "
    "zipfile.ZipFile(src).extractall(dst)"
)
_DOCX_PACK = (
    "import zipfile, sys, os; "
    "src, dst = sys.argv[1], sys.argv[2]; "
    "z = zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED); "
    "[z.write(os.path.join(r,f), os.path.relpath(os.path.join(r,f), src)) "
    "for r,_,fs in os.walk(src) for f in fs]; z.close()"
)


def _default_compressions() -> Dict[str, CompressionConfig]:
    """Built-in compression definitions (docx + common archives)."""
    return {
        "docx": CompressionConfig(
            suffix="docx",
            extract_cmd=[sys.executable, "-c", _DOCX_EXTRACT, "{src}", "{dst}"],
            pack_cmd=[sys.executable, "-c", _DOCX_PACK, "{src}", "{dst}"],
        ),
        "tar": CompressionConfig(
            suffix="tar",
            extract_cmd=["tar", "xf", "{src}", "-C", "{dst}"],
            pack_cmd=["tar", "cf", "{dst}", "-C", "{src}", "."],
        ),
        "tar.gz": CompressionConfig(
            suffix="tar.gz",
            extract_cmd=["tar", "xzf", "{src}", "-C", "{dst}"],
            pack_cmd=["tar", "czf", "{dst}", "-C", "{src}", "."],
        ),
        "tar.bz2": CompressionConfig(
            suffix="tar.bz2",
            extract_cmd=["tar", "xjf", "{src}", "-C", "{dst}"],
            pack_cmd=["tar", "cjf", "{dst}", "-C", "{src}", "."],
        ),
        "zip": CompressionConfig(
            suffix="zip",
            extract_cmd=[sys.executable, "-c", _DOCX_EXTRACT, "{src}", "{dst}"],
            pack_cmd=[sys.executable, "-c", _DOCX_PACK, "{src}", "{dst}"],
        ),
    }


# ── Main config class ────────────────────────────────────────────────────────

class Config:
    """Load and query tgit configuration from ``tgit.toml``."""

    CONFIG_FILENAME = "tgit.toml"

    def __init__(self, working_dir: Path) -> None:
        self.working_dir = working_dir
        self.config_path = working_dir / self.CONFIG_FILENAME

        self.compressions: Dict[str, CompressionConfig] = _default_compressions()
        self.diffs: Dict[str, DiffConfig] = {
            "docx": DiffConfig(suffix="docx"),
        }
        self.settings = TgitSettings()

        if self.config_path.exists():
            self._load()

    # ── Internal ─────────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            with open(self.config_path, "rb") as fh:
                data = tomllib.load(fh)
        except Exception as exc:
            from .utils import print_warn
            print_warn(f"Failed to parse {self.CONFIG_FILENAME}: {exc}")
            return

        # [compression.<suffix>]
        for suffix, raw in data.get("compression", {}).items():
            if not isinstance(raw, dict):
                continue
            self.compressions[suffix] = CompressionConfig(
                suffix=suffix,
                extract_cmd=raw.get("extract_cmd", []),
                pack_cmd=raw.get("pack_cmd", []),
                extract_dir_tpl=raw.get("extract_to", "{name}_{suffix}"),
            )

        # [diff.<suffix>]
        for suffix, raw in data.get("diff", {}).items():
            if not isinstance(raw, dict):
                continue
            self.diffs[suffix] = DiffConfig(
                suffix=suffix,
                cmd=raw.get("cmd", []),
                script=raw.get("script"),
            )

        # [tgit]
        tg = data.get("tgit", {})
        if isinstance(tg, dict):
            self.settings = TgitSettings(
                autosave_interval=tg.get("autosave_interval", 300),
                gitignore_ignore=tg.get("gitignore_ignore", []),
            )

    # ── Public API ───────────────────────────────────────────────────────

    def get_compression(self, suffix: str) -> Optional[CompressionConfig]:
        return self.compressions.get(suffix)

    def get_compression_suffixes(self) -> List[str]:
        """All configured archive suffixes, longest first."""
        return sorted(self.compressions.keys(), key=len, reverse=True)

    def get_diff_config(self, suffix: str) -> Optional[DiffConfig]:
        return self.diffs.get(suffix)

    def get_diff_suffixes(self) -> List[str]:
        return list(self.diffs.keys())

    def get_archive_suffixes_for_gitignore(self) -> List[str]:
        """Return suffixes that should be added to ``.gitignore`` as ``*.ext``."""
        return sorted(self.compressions.keys())

    def generate_gitignore(self, working_dir: Path) -> Path:
        """Generate ``.gitignore`` from compression config and settings.

        Returns the path to the generated file.
        """
        lines = [
            "# Auto-generated by tgit — do not edit manually",
            "# Re-run 'tgit init' to regenerate",
            "",
            "# ── Archive originals (extracted dirs are tracked) ──",
        ]
        for sfx in self.get_archive_suffixes_for_gitignore():
            lines.append(f"*.{sfx}")

        if self.settings.gitignore_ignore:
            lines.append("")
            lines.append("# ── User-defined ignores ──")
            for pattern in self.settings.gitignore_ignore:
                lines.append(pattern)

        lines.append("")
        content = "\n".join(lines)
        gitignore_path = working_dir / ".gitignore"
        gitignore_path.write_text(content, encoding="utf-8")
        return gitignore_path
