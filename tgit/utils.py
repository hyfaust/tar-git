"""Common utilities: subprocess helpers, hashing, colored output."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


# ── Git helper ───────────────────────────────────────────────────────────────

def run_git(
    args: List[str],
    cwd: Optional[str] = None,
    capture: bool = True,
) -> subprocess.CompletedProcess:
    """Execute a git command and return the result."""
    try:
        return subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=capture,
            text=True,
            encoding="utf-8",
        )
    except FileNotFoundError:
        print_err("git command not found. Please install Git and add it to PATH.")
        sys.exit(1)


# ── Hashing ──────────────────────────────────────────────────────────────────

def sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest of *path*, or "" on error."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError as exc:
        print_err(f"Cannot read {path}: {exc}")
        return ""


# ── Platform helpers ─────────────────────────────────────────────────────────

def set_hidden(path: Path) -> None:
    """Mark *path* as hidden on Windows (no-op elsewhere)."""
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["attrib", "+h", str(path)],
                capture_output=True,
                timeout=5,
            )
        except Exception:
            pass


# ── Coloured output ─────────────────────────────────────────────────────────

class _C:
    """ANSI colour escape codes."""

    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


# Enable ANSI on Windows terminals
if sys.platform == "win32":
    try:
        import colorama
        colorama.init()
    except ImportError:
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass


def print_ok(msg: str) -> None:
    print(f"{_C.GREEN}\u2713{_C.RESET} {msg}")


def print_err(msg: str) -> None:
    print(f"{_C.RED}\u2717{_C.RESET} {msg}")


def print_warn(msg: str) -> None:
    print(f"{_C.YELLOW}\u26A0{_C.RESET} {msg}")


def print_info(msg: str) -> None:
    print(f"{_C.BLUE}\u2139{_C.RESET} {msg}")


def print_step(msg: str) -> None:
    print(f"{_C.CYAN}\u2192{_C.RESET} {msg}")


def bold(text: str) -> str:
    return f"{_C.BOLD}{text}{_C.RESET}"


def colorize(text: str, color: str) -> str:
    return f"{color}{text}{_C.RESET}"
