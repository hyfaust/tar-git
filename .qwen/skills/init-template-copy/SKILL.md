---
name: init-template-copy
description: Auto-copy template config files from tool project to user's working directory during init, then generate derived files
source: auto-skill
extracted_at: '2026-06-03T08:58:00.000Z'
---

## Problem
CLI tools often need to scaffold default config files (`.gitignore`, `pyproject.toml`, etc.) in the user's project when they run `tool init`. Hardcoding these in Python is fragile — duplicating content that already exists as template files in the repo.

## Solution
Store template files in the tool's project root and copy them during `init` if they don't already exist. For derived files (like `.gitignore`), generate them programmatically from config.

## Implementation pattern

```python
from pathlib import Path
import shutil

def _copy_templates(working_dir: Path) -> None:
    """Copy template config files from tool project to working directory."""
    project_root = Path(__file__).parent.parent

    templates = ["tgit.toml"]  # Only copy tgit.toml; .gitignore is generated
    for name in templates:
        src = project_root / name
        dst = working_dir / name
        if src.exists() and not dst.exists():
            shutil.copy2(str(src), str(dst))
            print_info(f"Created {name} from template")
```

## Key design decisions

1. **Don't overwrite** — only copy if `not dst.exists()`. User's customized configs are preserved.
2. **`Path(__file__).parent.parent`** — resolves to project root regardless of how the tool is installed.
3. **Template files live in project root** — easy to edit, version-controlled, visible to users.
4. **Log what was created** — user sees what was scaffolded.
5. **Generate derived files** — `.gitignore` is generated from `tgit.toml` config, not copied as a template.

## Integration in `_cmd_init`

```python
def _cmd_init(...):
    print_step("Initialising …")

    # 1. Copy template tgit.toml if missing
    _copy_templates(working_dir)

    # 2. Reload config after template copy
    config.__init__(working_dir)

    # 3. Init git repo
    if not git.is_repo():
        run_git_local(["init"], cwd=str(working_dir))

    # 4. Generate .gitignore from config (not from template!)
    config.generate_gitignore(working_dir)

    # 5. Scan, extract, commit...
    scanner.scan(force=True)
    processor.extract_all(scanner)
    awareness.update_hashes(scanner)
    git.commit("tgit: initial commit")
```

**Order matters:**
- Copy `tgit.toml` before generating `.gitignore` (gitignore is derived from config)
- Generate `.gitignore` before scanning (scanner respects gitignore patterns)
- Update hashes before commit (hashes.json must be in the commit)

## When to use this pattern

- Tool has a `init` command that sets up a project directory
- Default config files exist as templates in the tool's source repo
- Some files are derived from config (generated, not copied)
- You want users to get sensible defaults without manual file creation
