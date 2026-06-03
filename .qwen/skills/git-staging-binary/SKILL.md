---
name: git-direct-binary-tracking
description: Track binary/archive files with git directly in the working directory, extracting archives in-place alongside originals
source: auto-skill
extracted_at: '2026-06-03T08:58:00.000Z'
---

## Problem
Git can't meaningfully diff or merge binary files (`.docx`, `.zip`, `.tar.gz`). You want version control for projects containing a mix of text files and archives, with the ability to see what changed inside archives across versions.

## Architecture: `.git/` directly in working directory

```
project/
├── .git/               # Git repo lives directly in working dir
├── .gitignore          # Auto-generated: excludes archive originals
├── hashes.json         # SHA-256 of all tracked files
├── tgit.toml           # Configuration
├── report.docx         # Original archive (gitignored)
├── report_docx/        # Extracted archive (git-tracked!)
│   ├── word/document.xml
│   └── ...
└── readme.txt          # Plain file (git-tracked directly)
```

**No staging directory.** Archives are extracted in-place; plain files are tracked directly by git.

### Key concepts

1. **Extract in-place**: Archives extract to sibling directories using `extract_dir_tpl` (default `{name}_{suffix}`). `test.docx` → `test_docx/`.
2. **Gitignore originals**: `.gitignore` excludes `*.docx`, `*.tar`, etc. Only extracted dirs and plain files are tracked.
3. **Hash tracking** (`hashes.json`): Store SHA-256 of every working-dir file. Enables efficient change detection and rebuild.
4. **Rebuild from git**: Plain files via `git show HEAD:<path>`, archives via `git ls-tree -r` on extracted dir + pack commands.

### Implementation pattern

```python
# Config-driven extraction with placeholders
# {src} = archive file, {dst} = extract dir, {name} = stem, {suffix} = ext
DEFAULTS = {
    "docx": CompressionConfig(
        suffix="docx",
        extract_cmd=["python", "-c", ZIP_EXTRACT_SCRIPT, "{src}", "{dst}"],
        pack_cmd=["python", "-c", ZIP_PACK_SCRIPT, "{src}", "{dst}"],
        extract_dir_tpl="{name}_{suffix}",  # test.docx → test_docx/
    ),
}
```

### Extract path computation

```python
def extract_path(node):
    """report.docx → <parent>/report_docx/"""
    comp = config.get_compression(node.suffix)
    dirname = comp.extract_dir_tpl.format(
        src_name=node.path.name,  # "report.docx"
        name=node.path.stem,      # "report"
        suffix=node.suffix,       # "docx"
    )
    return node.path.parent / dirname
```

### Detecting extracted directories in scanner

The scanner must identify which subdirectories are extracted archives (not user-created dirs). Compute expected names from sibling archive files:

```python
def _find_extracted_dirs(dirpath, filenames, suffixes):
    """Return directory names that are extracted archives."""
    extracted = set()
    for fname in filenames:
        suffix = match_suffix(fname, suffixes)
        if not suffix:
            continue
        comp = config.get_compression(suffix)
        dirname = comp.extract_dir_tpl.format(
            src_name=fname, name=Path(fname).stem, suffix=suffix
        )
        if (dirpath / dirname).is_dir():
            extracted.add(dirname)
    return extracted
```

### Diff strategy

- **Plain files**: `git diff` shows actual content changes directly
- **Archives**: Compare SHA-256 hash against `hashes.json` to detect change; optionally restore old+new extracted dirs from git and run custom diff tool

### Rebuild (restore missing files)

When files are deleted from the working directory:
1. Check `hashes.json` to know what files should exist
2. For plain files: `git show HEAD:<rel>` → write to disk
3. For archives: `git ls-tree -r HEAD:<extract_dir>` → restore to temp → pack via configured commands
4. **Key edge case**: If the archive file is deleted, the scanner won't find a node for it. Fall back to checking the suffix pattern and looking up the extracted dir in git.

```python
# When node is None (archive deleted), detect by suffix:
suffix = match_archive_suffix(rel, config)
if suffix:
    extract_dir = processor.extract_path_simple(fpath, suffix)
    if dir_in_git(extract_rel):
        restore_dir_from_git(extract_rel, extract_dir)
        pack_single(dummy_node)
```

### Reconstructing files from git tree objects

Use `git ls-tree -r` — **not** `git show` — to extract directories from git:

```python
# WRONG: git show HEAD:<dir> returns simplified listing without blob hashes
r = run_git(["show", f"HEAD:{rel}"])

# CORRECT: git ls-tree -r returns flat list with blob hashes
r = run_git(["ls-tree", "-r", f"HEAD:{rel}"])
# Output: "100644 blob abc123...    word/document.xml"

# Extract each blob with git show <hash> (binary mode)
for line in r.stdout.splitlines():
    parts = line.split(None, 3)
    blob_hash = parts[2]
    rel_path = parts[3]
    content = subprocess.run(["git", "show", blob_hash], capture_output=True)
    (output_dir / rel_path).write_bytes(content.stdout)
```

### Hash file must be committed with changes

```python
# CORRECT: hash updated before commit → hashes.json included
awareness.update_hashes()    # write hashes.json
git.commit(message)          # hashes.json is part of the commit
```

### .gitignore generation

Generate `.gitignore` from config to exclude archive originals:

```python
def generate_gitignore(working_dir):
    lines = ["# Auto-generated by tgit", ""]
    for sfx in sorted(compressions.keys()):
        lines.append(f"*.{sfx}")
    if settings.gitignore_ignore:
        lines.extend(settings.gitignore_ignore)
    (working_dir / ".gitignore").write_text("\n".join(lines))
```

### Gotchas

- **`{name}_{suffix}` template is required on Windows** — `{src_name}` (e.g., `test.docx/`) conflicts with the archive file on Windows (can't have file and dir with same name). Always use `{name}_{suffix}` as default.
- **Don't swap src/dst in template expansion** — extract and pack use the same placeholders with reversed source/destination. Use an explicit `is_pack` flag.
- **`hashes.json` is the source of truth for rebuild** — scanner only finds existing files; deleted files are only known from hashes.
- **`git show <dir>` vs `git ls-tree -r <dir>`** — the former gives human-readable listing without hashes; the latter gives machine-parseable output with blob SHAs.
- **Write blobs as bytes, not text** — archived XML/image files contain bytes that break `text=True` decoding.
- **Scanner must exclude `.git/`, `hashes.json`, `tgit.toml`** — these are internal files, not user content.
- **Rebuild must handle deleted archives with no scanner node** — when the archive file is gone, the scanner won't have a node. Detect by suffix pattern and restore extracted dir from git.
