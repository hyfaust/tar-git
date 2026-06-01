"""Git backend: all git operations run inside ``.tgit/`` staging directory."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .utils import print_err, print_info, print_ok, print_step, print_warn, run_git


class GitBackend:
    """Wraps git commands to operate inside the ``.tgit/`` staging directory."""

    STAGING_DIR = ".tgit"

    def __init__(self, working_dir: Path) -> None:
        self.working_dir = working_dir
        self.staging_dir = working_dir / self.STAGING_DIR

    # ── Low-level helpers ────────────────────────────────────────────────

    def _git(self, args: List[str], **kw) -> subprocess.CompletedProcess:
        return run_git(args, cwd=str(self.staging_dir), **kw)

    def is_repo(self) -> bool:
        return (self.staging_dir / ".git").exists()

    def staging_exists(self) -> bool:
        return self.staging_dir.exists()

    def head_hash(self) -> str:
        r = self._git(["rev-parse", "HEAD"])
        return r.stdout.strip() if r.returncode == 0 else ""

    def head_short(self) -> str:
        r = self._git(["rev-parse", "--short", "HEAD"])
        return r.stdout.strip() if r.returncode == 0 else "unknown"

    def current_branch(self) -> str:
        r = self._git(["rev-parse", "--abbrev-ref", "HEAD"])
        return r.stdout.strip() if r.returncode == 0 else "unknown"

    # ── Tag helpers ──────────────────────────────────────────────────────

    def get_latest_version_tag(self) -> Optional[str]:
        """Return the highest vMAJOR.MINOR tag, or *None*."""
        r = self._git(["tag", "-l", "v*"])
        tags = [t for t in r.stdout.strip().splitlines() if t.strip()]
        if not tags:
            return None

        def _key(tag: str) -> Tuple[int, int]:
            try:
                body = tag.lstrip("v")
                parts = body.split(".")
                return (int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
            except (ValueError, IndexError):
                return (0, 0)

        tags.sort(key=_key, reverse=True)
        return tags[0]

    def create_version_tag(self, major: Optional[str] = None) -> Optional[str]:
        """Create the next version tag (annotated).

        If *major* is given, create ``v{major}.00``.
        Otherwise auto-increment the minor version of the latest tag.
        """
        latest = self.get_latest_version_tag()

        # Remove existing version tags on current HEAD
        head = self.head_hash()
        if head:
            r = self._git(["show-ref", "--tags", "-d"])
            for line in r.stdout.strip().splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[0] == head:
                    tag_name = parts[1].replace("refs/tags/", "").replace("^{}", "")
                    if tag_name.startswith("v"):
                        self._git(["tag", "-d", tag_name])

        if major is not None:
            new_tag = f"v{major}.00"
        elif latest:
            body = latest.lstrip("v")
            maj_s, *rest = body.split(".")
            minor = int(rest[0]) + 1 if rest else 1
            new_tag = f"v{maj_s}.{minor:02d}"
        else:
            new_tag = "v1.00"

        r = self._git(["tag", "-a", new_tag, "-m", f"tgit version {new_tag}", "HEAD"])
        if r.returncode == 0:
            print_ok(f"Version tag created: {new_tag}")
            return new_tag
        print_err(f"Failed to create tag: {r.stderr.strip()}")
        return None

    def list_tags(self) -> None:
        r = self._git(["tag"])
        tags = [t for t in r.stdout.strip().splitlines() if t.strip()]
        if not tags:
            print_info("No tags")
            return
        print_info("Tags:")
        for t in tags:
            print(f"  {t}")

    # ── Commit ───────────────────────────────────────────────────────────

    def commit(self, message: str) -> bool:
        self._git(["add", "-A"])
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        full = f"{message}\n\nTimestamp: {ts}"
        r = self._git(["commit", "-m", full])
        if r.returncode == 0:
            print_ok(f"Committed: {message}")
            return True
        if "nothing to commit" in (r.stdout + r.stderr):
            print_info("Nothing to commit")
            return True
        print_err(f"Commit failed: {r.stderr.strip()}")
        return False

    # ── Restore ──────────────────────────────────────────────────────────

    def restore_version(self, version: str) -> bool:
        """Checkout unpacked archive dirs from *version* into staging."""
        if not version.startswith("v"):
            version = f"v{version}"

        r = self._git(["rev-parse", "--verify", version])
        if r.returncode != 0:
            print_err(f"Version not found: {version}")
            return False

        r = self._git(["checkout", version, "--", "."])
        if r.returncode != 0:
            print_err(f"Checkout failed: {r.stderr.strip()}")
            return False
        return True

    # ── Proxy (direct passthrough) ───────────────────────────────────────

    def proxy(self, args: List[str]) -> int:
        """Forward *args* directly to ``git`` in the staging directory."""
        if not self.staging_exists():
            print_err("tgit not initialised – run 'tgit init' first")
            return 1
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=str(self.staging_dir),
            )
            return result.returncode
        except FileNotFoundError:
            print_err("git not found")
            return 1
