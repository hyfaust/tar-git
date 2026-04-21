# wgit - Word Document Version Manager

[English](./README.md) | [中文](./README.zh.md)

[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)

A lightweight command-line tool for structured version management of `.docx` files. It uses Git as the storage engine and provides a simplified, automated interface so non-technical users can easily track the history of Word document changes.

## ✨ Features

- 🚀 **Zero learning curve** - simple commands, no need to understand Git internals
- 📦 **Smart unpacking** - automatically extracts `.docx` files into directories for version control
- 🏷️ **Semantic versioning** - automatically generates tags such as `v1.00`, `v1.01`, `v2.00`
- 💾 **Safe backups** - automatic backups before every operation, with one-click recovery
- ⏰ **Auto-save** - supports scheduled auto-commits to prevent accidental loss
- 🔍 **Change detection** - intelligently detects file changes by hash
- 🌐 **Cross-platform** - full support for Windows, macOS, and Linux

## 📦 Installation

### Option 1: Run the script directly

```bash
# Clone or download wgit.py locally
python wgit.py --help
```

### Option 2: Global installation (recommended)

```bash
# Copy wgit.py to a directory on your system PATH
# Windows: C:\Users\YourName\AppData\Local\Programs\Python\Python3x\Scripts\
# and rename it to wgit.exe or create a batch file

# Or install with pip (if setup.py is available)
pip install -e .
```

### Option 3: Create an alias

**Windows (PowerShell):**
```powershell
# Add this to your PowerShell profile ($PROFILE)
function wgit { python F:\path\to\wgit.py $args }
```

**Linux/macOS (Bash/Zsh):**
```bash
# Add this to ~/.bashrc or ~/.zshrc
alias wgit='python /path/to/wgit.py'
```

## 🚀 Quick Start

### 1. Initialize a repository

Go to a directory that contains `.docx` files and run:

```bash
wgit init
```

This will:
- create a Git repository
- extract all `.docx` files into corresponding `_docx` directories
- create the initial commit and version tag `v1.00`

### 2. Commit changes

After modifying a `.docx` file, run:

```bash
# With a commit message
wgit commit -m "Updated chapter 3"

# Interactive message input
wgit commit
```

### 3. View version history

```bash
wgit log
```

### 4. Check status

```bash
wgit status
```

### 5. Restore an older version

```bash
# Restore to the latest version
wgit restore

# Restore to a specific version
wgit restore v1.02
```

## 📖 Command Reference

### `wgit init` - Initialize a repository

Initialize the current directory as a wgit repository.

```bash
wgit init
```

**What it does:**
1. Creates a `.git` repository if one does not already exist
2. Creates the `.wordgit` metadata directory
3. Extracts all `.docx` files into `xxx_docx/` directories
4. Creates the initial commit and version tag `v1.00`

---

### `wgit commit` - Commit changes

Detect `.docx` file changes and commit them.

```bash
# With a commit message
wgit commit -m "Description"

# Interactive message input
wgit commit

# Do not create a version tag automatically
wgit commit -m "Description" --no-tag
```

**Automatic processing:**
- detects added, modified, and deleted `.docx` files
- re-extracts changed files into the corresponding directories
- automatically runs `git add` / `git rm`
- creates a version tag (for example, `v1.01`)

---

### `wgit tag` - Create a version tag

Manually create a version tag.

```bash
# Auto-increment the minor version (v1.03 → v1.04)
wgit tag

# Create a new major version (v2.00)
wgit tag 2
```

**Version format:** `v{major}.{two-digit-minor}`
- `v1.00`, `v1.01`, `v1.02` ...
- `v2.00`, `v2.01` ...

---

### `wgit restore` - Restore a version

Restore `.docx` files to a specified version.

```bash
# Restore to the latest commit
wgit restore

# Restore to a specific version
wgit restore v1.02

# Skip confirmation
wgit restore -y
```

**Safety mechanism:**
- creates a `.bak` backup before restoring
- restores the extracted directory from Git
- repacks the result into a `.docx` file

---

### `wgit status` - Show status

Display simplified repository status information.

```bash
wgit status
```

**Example output:**
```
wgit status

Current version: v1.01
HEAD:    05e947f

Document status:
  2 documents tracked
  All documents are up to date

Git status:
  Working tree clean
```

---

### `wgit log` - Show version history

Display commit history.

```bash
# Show the latest 20 entries
wgit log

# Show the latest 5 entries
wgit log -n 5

# Graph view
wgit log --graph
```

**Example output:**
```
Version history:

Version               Time                     Message
-----------------------------------------------------------------
v1.03 <-HEAD  2024-01-15 14:30:00   Updated chapter 3
v1.02        2024-01-15 10:15:00   Modified 1 file
v1.01        2024-01-14 16:45:00   Added 2 files
v1.00        2024-01-14 09:00:00   wgit: initial commit
```

**Note:**
- the `<-HEAD` marker indicates the current version

---

### `wgit autosave` - Auto-save

Detect changes immediately and commit them (good for keyboard shortcuts).

```bash
wgit autosave
```

---

### `wgit daemon` - Daemon process

Start a background scheduled auto-save loop.

```bash
# Check every 5 minutes by default
wgit daemon

# Custom interval in seconds
wgit daemon --interval=600
```

**Note:** the daemon runs in the foreground; press `Ctrl+C` to stop it.

---

## 📝 Example Workflows

### Scenario 1: Writing a report

```bash
# 1. Initialize before starting the report
cd F:\reports
wgit init
# → creates a repository, version v1.00

# 2. Commit after finishing chapter 1
# (edit and save report.docx in Word)
wgit commit -m "Finished chapter 1"
# → version v1.01

# 3. Continue writing chapter 2
# (keep editing and saving)
wgit commit -m "Finished chapter 2"
# → version v1.02

# 4. Realize chapter 1 needs fixing, restore the version after it was completed
wgit restore v1.01
# → restores report.docx to the v1.01 state

# 5. Revise and commit again
wgit commit -m "Fixed chapter 1"
# → version v1.03
```

### Scenario 2: Collaboration

```bash
# Xiao Wang modified the document
wgit commit -m "Xiao Wang: updated the market analysis section"

# Xiao Li continued editing
wgit commit -m "Xiao Li: improved the financial forecast"

# See who changed what
wgit log --graph

# Find a problem and restore Xiao Wang's version
wgit restore v1.01
```

### Scenario 3: Automatic backups

```bash
# Start the daemon, auto-save every 5 minutes
wgit daemon --interval=300

# Or manually save at intervals while writing
# (can be bound to a Word macro or shortcut)
wgit autosave
```

### Scenario 4: Multiple document management

```bash
# Directory structure:
# F:\project\
#   ├── Report.docx
#   ├── Appendix.docx
#   └── References.docx

# Manage all documents at once
wgit init
# → creates Report_docx/, Appendix_docx/, References_docx/

# Commit all changes
wgit commit -m "Updated all documents"

# Restore all documents to a specific version
wgit restore v1.02
```

## 🗂️ Directory Structure

After initialization:

```
Working directory/
├── .git/                  # Git repository
├── .wordgit/              # wgit metadata
│   └── hashes.json        # File hash records
├── .gitignore             # Git ignore rules (only manages .docx files)
├── report_docx/           # Unpacked contents of report.docx
│   ├── _rels/
│   ├── docProps/
│   ├── word/
│   └── [Content_Types].xml
├── doc1_docx/             # Unpacked contents of doc1.docx
├── report.docx            # Original Word file
├── doc1.docx              # Original Word file
└── report.docx.bak        # Backup file (created during restore)
```

**Note:** `.gitignore` uses an exclusion-based setup. It only manages `.docx` files and `*_docx/` directories; other files such as `.txt`, `.pdf`, and `.xlsx` are automatically ignored.

## ⚙️ Technical Details

### Unpacking strategy

`.docx` files are ZIP-based Open XML documents. wgit uses Python's standard `zipfile` library for unpacking and repacking:

- **Unpack**: `report.docx` → `report_docx/`
- **Pack**: `report_docx/` → `report.docx`

### Change detection

Changes are detected by comparing SHA256 hashes:

1. After each commit, wgit records the hash of every `.docx` file in `.wordgit/hashes.json`
2. Before the next commit, it recomputes the hashes and compares the differences
3. Only changed files are processed

### Version tags

Uses Git annotated tags:

```bash
git tag -a v1.05 -m "wgit version v1.05"
```

Version format: `v{major}.{minor:02d}`

### Atomic operations

All file operations use an atomic strategy:

1. Unpack to a temporary directory
2. Verify integrity
3. Remove the old directory
4. Move the new directory into place

## 🔧 Advanced Usage

### Use Git directly

wgit does not prevent you from using Git commands directly:

```bash
# View detailed Git history
git log --oneline

# Create a branch
git branch feature-xxx

# Switch branches
git checkout feature-xxx

# Note: after switching branches, you need to restore the .docx files manually
wgit restore
```

### Recover deleted files

```bash
# 1. View history
wgit log

# 2. Find the version before deletion
wgit restore v1.02

# 3. Or use Git to restore the unpacked directory
git checkout v1.02 -- report_docx/
wgit restore  # repack the file
```

### Migrate an existing Git repository

If the directory already has a Git repository:

```bash
wgit init
# It will automatically detect and use the existing repository
```

## ❓ FAQ

### Q: Does it support `.doc` files?
A: No. wgit only supports `.docx` (the Office 2007+ Open XML format). If needed, save the `.doc` file as `.docx` first.

### Q: Can I commit while the file is open in Word?
A: Yes, but Word may lock the file and cause read failures. It is recommended to save and close Word first.

### Q: How do I disable automatic version tags?
A: Use `wgit commit --no-tag`.

### Q: Where are backup files stored?
A: In the same directory as the original file, with the `.bak` suffix, for example `report.docx.bak`.

### Q: How do I completely remove a wgit repository?
A: Delete the `.git` and `.wordgit` directories, plus all `*_docx/` directories and `.bak` files.
