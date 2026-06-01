# tgit - Structured Document Version Manager

[English](./README.md) | [中文](./README.zh.md)

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

A lightweight command-line tool for version management of structured documents (`.docx`, `.xlsx`, `.pptx`) and archives (`.tar`, `.tar.gz`, `.zip`). Built on Git as the storage engine, it provides a simplified interface so non-technical users can easily track document change history.

## 📦 Installation

```bash
# Clone the project and run from the directory
python -m tgit --help

# Or use the convenience scripts (Windows / Linux)
tgit.bat --help
tgit.sh --help
```

## 🚀 Quick Start

### 1. Initialize a repository

Navigate to a directory containing documents and run:

```bash
tgit init
```

This automatically:
- Creates the `.tgit/` staging directory with an internal Git repository
- Copies default `.tgitignore` and `tgit.toml` configuration
- Extracts archives and copies plain files into the staging area
- Creates the initial commit and version tag `v1.00`

### 2. Commit changes

After modifying documents, run:

```bash
tgit commit -m "Updated chapter 3 of the report"
```

### 3. View history and status

```bash
tgit log
tgit status
```

### 4. Restore an older version

```bash
tgit restore --at v1.02
tgit restore --at v1.02 -y   # Skip confirmation
```

### 5. View differences

```bash
tgit diff                        # Compare with the previous version
tgit diff --at v1.01             # Compare with a specific version
tgit diff --docx report.docx     # Use a custom diff tool
```

## 📖 Command Reference

| Command | Description |
|---------|-------------|
| `tgit init` | Initialize repository, auto-create config files |
| `tgit commit [-m MSG]` | Commit changes, auto-detect and tag |
| `tgit version N` | Create major version tag `vN.00` |
| `tgit restore --at VER [-y]` | Restore to a specific version |
| `tgit diff [--at VER] [--docx]` | View differences |
| `tgit rebuild` | Rebuild missing files from staging |
| `tgit autosave [FILE]` | Auto-detect changes and commit |
| `tgit daemon [--interval N]` | Timed auto-save daemon |
| `tgit log [-n N] [--graph]` | View version history |
| `tgit tag` | List tags (proxies git tag) |
| `tgit status` | View repository status |

**Common flags:**
- `-y, --yes` — Skip interactive confirmation (for `restore`)

## ⚙️ Configuration

### `.tgitignore`

Uses gitignore syntax to control which files are tracked:

```gitignore
# Ignore backup files
*.bak
*.bak*
*.tmp
~$*

# Ignore the tgit staging directory
.tgit/
```

### `tgit.toml`

Configure archive formats and custom diff tools:

```toml
# .xlsx extract/pack (zip-based)
[compression.xlsx]
extract_cmd = ["python", "-c", "import zipfile,sys,os; ...", "{src}", "{dst}"]
pack_cmd    = ["python", "-c", "import zipfile,sys,os; ...", "{src}", "{dst}"]
extract_to  = "{name}_{suffix}"

# .docx custom diff
[diff.docx]
script = "word_diff.py"
```

**Placeholders:**
- `{src}` — Source file path
- `{dst}` — Destination path
- `{name}` — Filename without extension
- `{suffix}` — File extension

## 🗂️ Directory Structure

```
working-directory/
├── .tgit/                 # tgit staging directory (internal Git repo)
│   ├── .git/              # Git repository
│   ├── hashes.json        # File hash records
│   ├── report_docx/       # Extracted contents of report.docx
│   └── doc1.xlsx          # Plain file copy
├── .tgitignore            # tgit ignore rules
├── tgit.toml              # tgit configuration
├── report.docx            # Original document
└── doc1.xlsx              # Original document
```

## ⚙️ Technical Details

- **Change detection**: SHA-256 hash comparison; only changed files are processed
- **Version tags**: Git annotated tags, format `v{major}.{minor:02d}`
- **Extraction**: `.docx`/`.xlsx`/`.pptx` use Python `zipfile`; `.tar`/`.tar.gz` use system `tar`
- **Custom diff**: Configure per-format diff tools via `tgit.toml`

## 🔧 Advanced Usage

### Use Git directly

tgit does not prevent direct Git usage:

```bash
tgit log --oneline
tgit git branch feature-xxx
tgit git checkout feature-xxx
```

### Recover deleted files

```bash
tgit log                    # View history
tgit restore --at v1.02     # Restore to before deletion
```

### Auto-save

```bash
# Auto-commit after editing
tgit autosave report.docx

# Background timed save (every 10 minutes)
tgit daemon --interval 600
```
