"""CLI entry point: argument parsing and command routing."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

from . import __tool_name__, __version__
from .config import Config
from .diff_engine import DiffEngine
from .file_awareness import FileAwareness
from .git_backend import GitBackend
from .processor import Processor
from .scanner import Scanner
from .utils import print_err, print_info, print_ok, print_step, print_warn, run_git


# ── Parser construction ──────────────────────────────────────────────────────

_KNOWN_COMMANDS = frozenset({
    "init", "commit", "version", "restore", "tag",
    "log", "status", "diff", "rebuild",
    "autosave", "daemon",
})


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=__tool_name__,
        description="Structured document version management built on Git",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  tgit init                         initialise repository\n"
            '  tgit commit -m "message"          commit changes\n'
            "  tgit version 2                    create major version v2.00\n"
            "  tgit restore --at v1.01           restore to version\n"
            "  tgit diff                         default diff\n"
            "  tgit diff --at v1.01              diff against version\n"
            "  tgit diff --docx test.docx        diff docx with configured tool\n"
            "  tgit rebuild                      restore missing files\n"
            "  tgit daemon --interval 600        timed auto-save\n"
            "  tgit status                       git status in staging\n"
        ),
    )
    parser.add_argument(
        "--show-version",
        action="version",
        version=f"{__tool_name__} {__version__}",
    )

    subs = parser.add_subparsers(dest="command")

    # init
    subs.add_parser("init", help="Initialise tgit repository")

    # commit
    p = subs.add_parser("commit", help="Commit changes")
    p.add_argument("-m", "--message", help="Commit message")
    p.add_argument("--no-tag", action="store_true", help="Skip auto version tag")
    p.add_argument("--tag", dest="tag_major", help="Force major version (e.g. 2)")

    # version
    p = subs.add_parser("version", help="Create major version tag (vN.00)")
    p.add_argument("major", help="Major version number")

    # restore
    p = subs.add_parser("restore", help="Restore to a version")
    p.add_argument("--at", dest="target_version", help="Version tag (e.g. v1.01)")
    p.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")

    # tag
    p = subs.add_parser("tag", help="List or create tags (proxies git tag)")
    p.add_argument("args", nargs=argparse.REMAINDER, help="Arguments for git tag")

    # log
    p = subs.add_parser("log", help="Show commit history")
    p.add_argument("-n", "--limit", type=int, default=20, help="Max entries")
    p.add_argument("--graph", action="store_true", help="Graph view")
    p.add_argument("args", nargs=argparse.REMAINDER, help="Extra args for git log")

    # status
    subs.add_parser("status", help="Show repository status")

    # diff
    p = subs.add_parser("diff", help="Show differences")
    grp = p.add_mutually_exclusive_group()
    for s in _all_suffixes():
        grp.add_argument(
            f"--{s}", dest="suffix", action="store_const", const=s,
            help=f"Diff .{s} files with configured tool",
        )
    p.add_argument("--at", dest="at_version", nargs="?", const="HEAD",
                   help="Compare against a version tag")
    p.add_argument("files", nargs="*", help="Specific files to diff")

    # rebuild
    subs.add_parser("rebuild", help="Restore missing files from staging")

    # autosave
    p = subs.add_parser("autosave", help="Auto-detect changes and commit")
    p.add_argument("filename", nargs="?", help="Open file, commit on close")

    # daemon
    p = subs.add_parser("daemon", help="Timed auto-save loop")
    p.add_argument("--interval", type=int, default=300, help="Seconds between checks")

    return parser


def _all_suffixes() -> List[str]:
    """Return suffixes that might appear as ``--suffix`` flags."""
    return ["docx", "tar", "tar.gz", "tar.bz2", "zip", "rar", "7z"]


# ── Main entry ───────────────────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> int:
    args_list = argv if argv is not None else sys.argv[1:]

    # If first arg is not a known tgit command → git passthrough
    if args_list and args_list[0] not in _KNOWN_COMMANDS and not args_list[0].startswith("-"):
        return _git_passthrough(args_list)

    parser = _build_parser()
    args, unknown = parser.parse_known_args(args_list)

    if args.command is None:
        parser.print_help()
        return 0

    # For log/tag/status, pass unknown args directly to git
    if unknown and args.command in ("log", "tag", "status"):
        git = GitBackend(Path.cwd())
        if not git.staging_exists():
            print_err("tgit not initialised – run 'tgit init' first")
            return 1
        git_args = [args.command] + unknown
        # If log has --graph, insert it before unknown args
        if args.command == "log" and hasattr(args, "graph") and args.graph:
            git_args = ["log", "--oneline", "--graph", "--decorate"] + unknown
        return git.proxy(git_args)

    working_dir = Path.cwd()
    config = Config(working_dir)
    git = GitBackend(working_dir)
    scanner = Scanner(working_dir, config)
    processor = Processor(working_dir, config)
    awareness = FileAwareness(working_dir, config)

    dispatch = {
        "init":      lambda: _cmd_init(config, git, scanner, processor, awareness),
        "commit":    lambda: _cmd_commit(config, git, scanner, processor, awareness,
                                         args.message, args.no_tag, args.tag_major),
        "version":   lambda: _cmd_version(git, args.major),
        "restore":   lambda: _cmd_restore(config, git, scanner, processor, awareness,
                                           args.target_version, args.yes),
        "tag":       lambda: _cmd_tag(git, args.args),
        "log":       lambda: _cmd_log(git, args.limit, args.graph, args.args),
        "status":    lambda: _cmd_status(git),
        "diff":      lambda: _cmd_diff(config, git, scanner, processor, awareness,
                                        args),
        "rebuild":   lambda: _cmd_rebuild(config, scanner, processor),
        "autosave":  lambda: _cmd_autosave(config, git, scanner, processor,
                                            awareness, args.filename),
        "daemon":    lambda: _cmd_daemon(config, git, scanner, processor,
                                         awareness, args.interval),
    }

    handler = dispatch.get(args.command)
    if handler:
        try:
            ok = handler()
            return 0 if ok else 1
        except KeyboardInterrupt:
            print_info("\nCancelled")
            return 130

    parser.print_help()
    return 0


# ── Git passthrough ──────────────────────────────────────────────────────────

def _git_passthrough(args: List[str]) -> int:
    working_dir = Path.cwd()
    staging = working_dir / GitBackend.STAGING_DIR
    if not staging.exists():
        print_err("tgit not initialised – run 'tgit init' first")
        return 1
    try:
        r = subprocess.run(["git"] + args, cwd=str(staging))
        return r.returncode
    except FileNotFoundError:
        print_err("git not found")
        return 1


def _copy_templates(working_dir: Path) -> None:
    """Copy template config files from tgit project to working directory."""
    import shutil

    # tgit project root is one level up from the tgit package
    project_root = Path(__file__).parent.parent

    templates = [".tgitignore", "tgit.toml"]
    for name in templates:
        src = project_root / name
        dst = working_dir / name
        if src.exists() and not dst.exists():
            shutil.copy2(str(src), str(dst))
            print_info(f"Created {name} from template")


# ── Command implementations ──────────────────────────────────────────────────

def _cmd_init(
    config: Config,
    git: GitBackend,
    scanner: Scanner,
    processor: Processor,
    awareness: FileAwareness,
) -> bool:
    print_step("Initialising tgit repository …")

    processor._ensure_staging()

    # Copy template config files from tgit project to working directory
    _copy_templates(git.working_dir)

    # Init git repo inside staging
    if not git.is_repo():
        r = run_git_local(["init"], cwd=str(git.staging_dir))
        if r.returncode != 0:
            print_err(f"Git init failed: {r.stderr.strip()}")
            return False
        print_ok("Git repository created in .tgit/")

    # Scan + extract
    scanner.scan(force=True)
    n_tar = len(scanner.tar_files())
    n_plain = len(scanner.plain_files())
    print_step(f"Found {n_tar} archive(s), {n_plain} plain file(s)")

    processor.sync_to_staging(scanner)

    # Copy config files into staging
    for fname in [Config.CONFIG_FILENAME, Scanner.IGNORE_FILENAME]:
        src = git.working_dir / fname
        dst = git.staging_dir / fname
        if src.exists() and not dst.exists():
            import shutil
            shutil.copy2(str(src), str(dst))

    # Generate hashes before commit so hashes.json is included
    awareness.update_hashes(scanner)

    # Initial commit
    run_git_local(["add", "-A"], cwd=str(git.staging_dir))
    r = run_git_local(
        ["commit", "-m", "tgit: initial commit", "--allow-empty"],
        cwd=str(git.staging_dir),
    )
    if r.returncode == 0:
        print_ok("Initial commit created")

    git.create_version_tag(major="1")
    print_ok("tgit repository initialised")
    return True


def _cmd_commit(
    config: Config,
    git: GitBackend,
    scanner: Scanner,
    processor: Processor,
    awareness: FileAwareness,
    message: Optional[str],
    no_tag: bool,
    tag_major: Optional[str],
) -> bool:
    if not git.staging_exists():
        print_err("Not initialised – run 'tgit init'")
        return False

    scanner.scan(force=True)
    modified, added, deleted = awareness.detect_changes(scanner)

    if not modified and not added and not deleted:
        print_info("No changes detected")
        return True

    # x_operate: unpack changed archives into staging
    for node in modified + added:
        if node.is_archive:
            processor.unpack_single(node)
        else:
            processor.copy_to_staging(node)

    # Remove deleted files from staging
    for rel in deleted:
        staging_file = git.staging_dir / rel
        if staging_file.exists():
            if staging_file.is_dir():
                import shutil
                shutil.rmtree(staging_file)
            else:
                staging_file.unlink()

    # Generate message
    if not message:
        parts = []
        if modified:
            parts.append(f"modified {len(modified)}")
        if added:
            parts.append(f"added {len(added)}")
        if deleted:
            parts.append(f"deleted {len(deleted)}")
        message = f"tgit: {', '.join(parts)}"

    # Update hashes before commit so hashes.json is included
    awareness.update_hashes(scanner)

    ok = git.commit(message)
    if ok:
        if not no_tag:
            git.create_version_tag(major=tag_major)
    return ok


def _cmd_version(git: GitBackend, major: str) -> bool:
    if not git.staging_exists():
        print_err("Not initialised")
        return False
    tag = git.create_version_tag(major=major)
    return tag is not None


def _cmd_restore(
    config: Config,
    git: GitBackend,
    scanner: Scanner,
    processor: Processor,
    awareness: FileAwareness,
    target_version: Optional[str],
    yes: bool,
) -> bool:
    if not git.staging_exists():
        print_err("Not initialised")
        return False

    if not target_version:
        print_err("Version required: tgit restore --at v1.01")
        return False

    if not yes:
        print_warn(f"This will restore files to {target_version}")
        try:
            ans = input("Continue? [y/N]: ").strip().lower()
            if ans not in ("y", "yes"):
                print_info("Cancelled")
                return False
        except (EOFError, KeyboardInterrupt):
            print_info("Cancelled")
            return False

    scanner.scan(force=True)
    ok = git.restore_version(target_version)
    if not ok:
        return False

    # c_operate: pack from staging back to working dir
    processor.sync_to_workdir(scanner)
    awareness.update_hashes(scanner)
    print_ok(f"Restored to {target_version}")
    return True


def _cmd_tag(git: GitBackend, extra_args: List[str]) -> bool:
    if not git.staging_exists():
        print_err("Not initialised")
        return False
    return git.proxy(["tag"] + extra_args) == 0


def _cmd_log(git: GitBackend, limit: int, graph: bool, extra_args: List[str]) -> bool:
    if not git.staging_exists():
        print_err("Not initialised")
        return False

    # Extra args → pass directly to git log
    if extra_args:
        return git.proxy(["log"] + extra_args) == 0

    if graph:
        return git.proxy(["log", "--oneline", "--graph", "--decorate", f"-{limit}"]) == 0

    r = run_git(
        ["log", "--format=%h|%ai|%s", f"-{limit}"],
        cwd=str(git.staging_dir),
    )
    if not r.stdout.strip():
        print_info("No commits")
        return True

    # Build tag map
    tag_map: dict = {}
    tr = run_git(["show-ref", "--tags", "-d"], cwd=str(git.staging_dir))
    for line in tr.stdout.strip().splitlines():
        parts = line.split()
        if len(parts) >= 2:
            h = parts[0][:7]
            tn = parts[1].replace("refs/tags/", "").replace("^{}", "")
            tag_map[h] = tn

    head = run_git(["rev-parse", "HEAD"], cwd=str(git.staging_dir))
    head_h = head.stdout.strip()[:7] if head.stdout.strip() else ""

    print(f"\n{'Version':<16} {'Time':<22} {'Message'}")
    print("-" * 65)
    for line in r.stdout.strip().splitlines():
        parts = line.split("|", 2)
        if len(parts) < 3:
            continue
        h, ts, msg = parts[0][:7], parts[1][:19].replace("T", " "), parts[2]
        tag = tag_map.get(h, "")
        tag_s = f"\033[93m{tag}\033[0m" if h == head_h and tag else (f"\033[92m{tag}\033[0m" if tag else "")
        print(f"{tag_s:<16} {ts:<22} {msg}")
    return True


def _cmd_status(git: GitBackend) -> bool:
    if not git.staging_exists():
        print_err("Not initialised")
        return False
    return git.proxy(["status"]) == 0


def _cmd_diff(
    config: Config,
    git: GitBackend,
    scanner: Scanner,
    processor: Processor,
    awareness: FileAwareness,
    args: argparse.Namespace,
) -> bool:
    if not git.staging_exists():
        print_err("Not initialised")
        return False

    scanner.scan()
    engine = DiffEngine(git.working_dir, config, git, processor, awareness)

    suffix = getattr(args, "suffix", None)
    at_version = getattr(args, "at_version", None)
    files = getattr(args, "files", []) or []

    # Suffix + version
    if suffix and at_version:
        return engine.diff_suffix_version(scanner, suffix, at_version,
                                          files[0] if files else None)

    # Suffix only
    if suffix:
        return engine.diff_suffix(scanner, suffix, files[0] if files else None)

    # Version only (--at)
    if at_version is not None:
        return engine.diff_version(scanner, at_version, files or None)

    # Default
    return engine.diff_default(scanner, files or None)


def _cmd_rebuild(
    config: Config,
    scanner: Scanner,
    processor: Processor,
) -> bool:
    scanner.scan(force=True)
    awareness = FileAwareness(scanner.working_dir, config)
    return awareness.rebuild(scanner, processor) >= 0


def _cmd_autosave(
    config: Config,
    git: GitBackend,
    scanner: Scanner,
    processor: Processor,
    awareness: FileAwareness,
    filename: Optional[str],
) -> bool:
    if not git.staging_exists():
        print_err("Not initialised")
        return False

    if filename:
        return _open_and_watch(config, git, scanner, processor, awareness, filename)

    scanner.scan(force=True)
    modified, added, deleted = awareness.detect_changes(scanner)
    if not modified and not added and not deleted:
        print_info("No changes")
        return True

    parts = []
    if modified:
        parts.append(f"modified {len(modified)}")
    if added:
        parts.append(f"added {len(added)}")
    if deleted:
        parts.append(f"deleted {len(deleted)}")
    msg = f"[autosave] {', '.join(parts)}"

    print_step(f"Auto-saving: {msg}")
    return _cmd_commit(config, git, scanner, processor, awareness, msg, False, None)


def _open_and_watch(
    config: Config,
    git: GitBackend,
    scanner: Scanner,
    processor: Processor,
    awareness: FileAwareness,
    filename: str,
) -> bool:
    """Open *filename* with the system handler and commit when the process exits."""
    fpath = Path(filename).resolve()
    if not fpath.exists():
        print_err(f"File not found: {fpath}")
        return False

    print_step(f"Opening {fpath.name} …")

    try:
        if sys.platform == "win32":
            proc = subprocess.Popen(["cmd", "/c", "start", "", str(fpath)], shell=True)
            # start returns immediately; watch the file for changes
            print_info("Waiting for file to be closed (press Ctrl+C to stop watching) …")
            initial_mtime = fpath.stat().st_mtime
            try:
                while True:
                    time.sleep(2)
                    try:
                        current_mtime = fpath.stat().st_mtime
                        if current_mtime != initial_mtime:
                            # File was modified; wait for it to stabilise
                            time.sleep(3)
                            if fpath.stat().st_mtime == current_mtime:
                                break
                    except OSError:
                        break
            except KeyboardInterrupt:
                pass
        else:
            proc = subprocess.Popen(["xdg-open", str(fpath)])
            proc.wait()
    except FileNotFoundError:
        print_err("Cannot open file – no system handler found")
        return False
    except Exception as exc:
        print_err(f"Open failed: {exc}")
        return False

    print_step("File closed – committing changes …")
    return _cmd_commit(
        config, git, scanner, processor, awareness,
        f"[autosave] {fpath.name}", False, None,
    )


def _cmd_daemon(
    config: Config,
    git: GitBackend,
    scanner: Scanner,
    processor: Processor,
    awareness: FileAwareness,
    interval: int,
) -> bool:
    if not git.staging_exists():
        print_err("Not initialised")
        return False

    print_ok(f"Daemon started (interval: {interval}s). Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(interval)
            _cmd_autosave(config, git, scanner, processor, awareness, None)
    except KeyboardInterrupt:
        print_info("\nDaemon stopped")
    return True


# ── Local git helper (no tgit context needed) ───────────────────────────────

def run_git_local(
    args: List[str],
    cwd: Optional[str] = None,
) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["git"] + args, cwd=cwd,
            capture_output=True, text=True, encoding="utf-8",
        )
    except FileNotFoundError:
        print_err("git not found")
        sys.exit(1)
