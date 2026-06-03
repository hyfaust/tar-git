"""Git operations wrapper.

Provides a thin layer around ``git`` CLI for tgit-specific workflows.
All git operations run directly in the working directory (``.git/`` is at the
project root, not inside a staging sub-directory).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from .utils import print_err, print_info, print_ok, run_git


class GitBackend:
    """Git interface that operates in the working directory."""

    def __init__(self, working_dir: Path) -> None:
        self.working_dir = working_dir

    # ── Repo state ───────────────────────────────────────────────────────

    def is_repo(self) -> bool:
        """Check if ``.git/`` exists in the working directory."""
        return (self.working_dir / ".git").exists()

    def staging_exists(self) -> bool:
        """Alias for ``is_repo()`` — kept for backward compat."""
        return self.is_repo()

    def head_hash(self) -> str:
        r = run_git(["rev-parse", "HEAD"], cwd=str(self.working_dir))
        return r.stdout.strip() if r.returncode == 0 else ""

    def head_short(self) -> str:
        r = run_git(["rev-parse", "--short", "HEAD"], cwd=str(self.working_dir))
        return r.stdout.strip() if r.returncode == 0 else "unknown"

    def current_branch(self) -> str:
        r = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=str(self.working_dir))
        return r.stdout.strip() if r.returncode == 0 else "unknown"

    # ── Commit ───────────────────────────────────────────────────────────

    def commit(self, message: str) -> bool:
        """Stage all changes and commit."""
        r = run_git(["add", "-A"], cwd=str(self.working_dir))
        if r.returncode != 0:
            print_err(f"Git add failed: {r.stderr.strip()}")
            return False

        r = run_git(["commit", "-m", message], cwd=str(self.working_dir))
        if r.returncode != 0:
            if "nothing to commit" in (r.stdout + r.stderr):
                print_info("Nothing to commit")
                return True
            print_err(f"Commit failed: {r.stderr.strip()}")
            return False

        print_ok(f"Committed: {message}")
        return True

    # ── Tagging ──────────────────────────────────────────────────────────

    def get_latest_version_tag(self) -> Optional[str]:
        """Return the highest ``vMAJOR.MINOR`` tag, or *None*."""
        r = run_git(
            ["tag", "-l", "v*", "--sort=-v:refname"],
            cwd=str(self.working_dir),
        )
        tags = [t.strip() for t in r.stdout.strip().splitlines() if t.strip()]
        return tags[0] if tags else None

    def create_version_tag(
        self, major: Optional[str] = None
    ) -> Optional[str]:
        """Create the next version tag (``v{major}.{minor:02d}``).

        If *major* is given, start at ``v{major}.00`` (or increment from
        the latest tag with the same major).  Otherwise auto-increment.
        """
        latest = self.get_latest_version_tag()

        if major is not None:
            major_n = int(major)
            if latest and latest.startswith(f"v{major_n}."):
                minor = int(latest.split(".")[1]) + 1
            else:
                minor = 0
        elif latest:
            parts = latest.lstrip("v").split(".")
            major_n = int(parts[0])
            minor = int(parts[1]) + 1 if len(parts) > 1 else 1
        else:
            major_n, minor = 1, 0

        tag = f"v{major_n}.{minor:02d}"
        r = run_git(
            ["tag", "-a", tag, "-m", f"tgit version {tag}"],
            cwd=str(self.working_dir),
        )
        if r.returncode != 0:
            print_err(f"Tag creation failed: {r.stderr.strip()}")
            return None
        print_ok(f"Version tag created: {tag}")
        return tag

    # ── Restore ──────────────────────────────────────────────────────────

    def restore_version(self, version: str) -> bool:
        """Restore the working directory to *version*.

        Checks out all tracked files from the target version.
        """
        if not version.startswith("v"):
            version = f"v{version}"

        r = run_git(["rev-parse", "--verify", version], cwd=str(self.working_dir))
        if r.returncode != 0:
            print_err(f"Version not found: {version}")
            return False

        r = run_git(["checkout", version, "--", "."], cwd=str(self.working_dir))
        if r.returncode != 0:
            print_err(f"Checkout failed: {r.stderr.strip()}")
            return False

        print_ok(f"Restored to {version}")
        return True

    # ── Proxy ────────────────────────────────────────────────────────────

    def proxy(self, args: List[str]) -> int:
        """Run ``git <args>`` directly in the working directory."""
        r = run_git(args, cwd=str(self.working_dir), capture=False)
        return r.returncode
