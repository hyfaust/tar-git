---
name: argparse-git-passthrough
description: Build a CLI wrapper around git (or any tool) using argparse, forwarding unknown arguments transparently
source: auto-skill
extracted_at: '2026-06-01T05:35:49.540Z'
---

## Problem
You're building a CLI tool that wraps an existing command (like `git`). Some subcommands are handled natively by your tool, but others (or extra flags on native subcommands) should be forwarded to the underlying tool. `argparse` rejects unknown arguments by default.

## Approach: `parse_known_args` + passthrough set

### Step 1: Define known commands as a frozenset

```python
_KNOWN_COMMANDS = frozenset({"init", "commit", "diff", "rebuild"})
```

### Step 2: Route unknown top-level commands before argparse

```python
def main(argv=None):
    args_list = argv if argv is not None else sys.argv[1:]

    # First arg not a known command and not a flag → passthrough
    if args_list and args_list[0] not in _KNOWN_COMMANDS and not args_list[0].startswith("-"):
        return _git_passthrough(args_list)
    ...
```

### Step 3: Use `parse_known_args` instead of `parse_args`

```python
parser = _build_parser()
args, unknown = parser.parse_known_args(args_list)
```

This captures unrecognized flags in `unknown` instead of erroring.

### Step 4: Forward unknowns for specific subcommands

For subcommands that should transparently forward extra args to the underlying tool:

```python
if unknown and args.command in ("log", "status", "tag"):
    git_args = [args.command] + unknown
    return subprocess.run(["git"] + git_args, cwd=staging_dir).returncode
```

### Step 5: Handle subcommand-specific flags normally

For subcommands your tool handles natively, use standard argparse subparsers. `parse_known_args` still parses them correctly — only truly unknown flags end up in `unknown`.

### Gotchas

- **`nargs=REMAINDER` doesn't work for `-` prefixed args** — argparse tries to parse them as options before the REMAINDER captures them. Use `parse_known_args` instead.
- **Order matters** — check `unknown` AFTER parsing, not before, so argparse can extract what it knows first.
- **Help text** — add `args` (REMAINDER) positional to subparsers that accept passthrough args, even though `parse_known_args` does the real work. This improves `--help` output.
