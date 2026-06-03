# tgit - 结构化文档版本管理工具

[English](./README.md) | [中文](./README.zh.md)

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

一个轻量级命令行工具，用于对结构化文档（`.docx`、`.xlsx`、`.pptx`）和压缩包（`.tar`、`.tar.gz`、`.zip`）进行版本管理。基于 Git 存储引擎，提供简化的操作接口，让非技术用户也能轻松追踪文档修改历史。

## 📦 安装

```bash
# 克隆项目后进入目录运行
python -m tgit --help

# 或使用快捷脚本（Windows / Linux）
tgit.bat --help
tgit.sh --help
```

## 🚀 快速开始

### 1. 初始化仓库

进入包含文档的目录，运行：

```bash
tgit init
```

自动完成：
- 在工作目录中创建 Git 仓库（`.git/`）
- 根据 `tgit.toml` 配置生成 `.gitignore`，排除归档原文件
- 就地解压归档文件（如 `report.docx` → `report_docx/`）
- 创建初始提交和版本标签 `v1.00`

### 2. 提交更改

修改文档后运行：

```bash
tgit commit -m "更新了报告第三章"
```

### 3. 查看历史与状态

```bash
tgit log
tgit status
```

### 4. 恢复旧版本

```bash
tgit restore --at v1.02
tgit restore --at v1.02 -y   # 跳过确认
```

### 5. 查看差异

```bash
tgit diff                        # 与上一版本比较
tgit diff --at v1.01             # 与指定版本比较
tgit diff --docx report.docx     # 使用自定义 diff 工具
```

## 📖 命令参考

| 命令 | 说明 |
|------|------|
| `tgit init` | 初始化仓库，根据配置生成 `.gitignore` |
| `tgit commit [-m MSG]` | 提交更改，自动检测变化并打标签 |
| `tgit version N` | 创建主版本标签 `vN.00` |
| `tgit restore --at VER [-y]` | 恢复到指定版本 |
| `tgit diff [--at VER] [--docx]` | 查看差异 |
| `tgit rebuild` | 从 git 重建缺失的归档文件 |
| `tgit autosave [FILE]` | 自动检测变化并提交 |
| `tgit daemon [--interval N]` | 定时自动保存守护进程 |
| `tgit log [-n N] [--graph]` | 查看版本历史 |
| `tgit tag` | 列出标签（代理 git tag） |
| `tgit status` | 查看仓库状态 |

**通用参数：**
- `-y, --yes` — 跳过交互确认（适用于 `restore`）

## ⚙️ 配置

### `tgit.toml`

配置压缩包格式、自定义 diff 工具和通用设置：

```toml
# .docx 解压/打包（内置，无需外部工具）
[compression.docx]
extract_cmd = ["python", "-c", "import zipfile,sys,os; ...", "{src}", "{dst}"]
pack_cmd    = ["python", "-c", "import zipfile,sys,os; ...", "{src}", "{dst}"]
extract_to  = "{name}_{suffix}"   # test.docx → test_docx/

# .docx 自定义 diff
[diff.docx]
script = "word_diff.py"

# 通用设置
[tgit]
autosave_interval = 300
gitignore_ignore = ["*.bak", "*.tmp", "~$*"]
```

**解压目录命名（`extract_to`）：**

| 模板 | 示例 | 说明 |
|------|------|------|
| `{name}_{suffix}`（默认） | `test.docx` → `test_docx/` | 所有平台安全 |
| `{src_name}` | `test.docx` → `test.docx/` | ⚠️ Windows：与归档文件冲突 |

**占位符：**
- `{src}` — 源文件路径（解压时为归档文件，打包时为目录）
- `{dst}` — 目标路径（解压时为目录，打包时为归档文件）
- `{name}` — 文件名主干（如 `test.docx` 中的 `test`）
- `{suffix}` — 扩展名（如 `docx`）
- `{src_name}` — 完整源文件名（如 `test.docx`）

### `.gitignore`

由 `tgit init` 根据 `tgit.toml` 自动生成，排除归档原文件，只跟踪解压目录。重新运行 `tgit init` 可重新生成。

## 🗂️ 目录结构

```
工作目录/
├── .git/                  # Git 仓库（直接在工作目录中）
├── .gitignore             # 自动生成，排除归档原文件
├── hashes.json            # 文件哈希记录，用于变更检测
├── tgit.toml              # tgit 配置文件
├── report.docx            # 原始归档（被 gitignore）
├── report_docx/           # 解压内容（由 git 跟踪）
│   ├── word/
│   └── [Content_Types].xml
├── data.xlsx              # 原始归档（被 gitignore）
├── data_xlsx/             # 解压内容（由 git 跟踪）
└── notes.txt              # 普通文件（直接由 git 跟踪）
```

**核心设计原则：**
- `.git/` 直接在工作目录中，无中间暂存层
- 归档文件就地解压，与原文件并存
- 归档原文件被 gitignore，解压目录被 git 跟踪
- 普通文件直接由 Git 跟踪，无需复制
- `hashes.json` 实现高效的变更检测

## ⚙️ 技术细节

- **变更检测**：通过 SHA-256 哈希值检测文件变化，只处理有变化的文件
- **版本标签**：使用 Git annotated tag，格式 `v{主版本}.{次版本:02d}`
- **解压策略**：`.docx`/`.xlsx`/`.pptx` 使用 Python `zipfile`；`.tar`/`.tar.gz` 使用系统 `tar` 命令
- **自定义 diff**：可通过 `tgit.toml` 配置各格式的 diff 工具
- **重建机制**：通过 `git show` 恢复普通文件，通过 `git ls-tree` + 打包命令恢复归档文件

## 🔧 高级用法

### 直接使用 Git

tgit 不阻止直接使用 Git 命令：

```bash
tgit log --oneline
tgit git branch feature-xxx
tgit git checkout feature-xxx
```

### 恢复误删文件

```bash
tgit log                    # 查看历史
tgit restore --at v1.02     # 恢复到删除前的版本
```

### 重建缺失归档

如果归档文件被删除但其解压目录存在于 git 中：

```bash
tgit rebuild    # 从 git 历史恢复缺失文件
```

### 自动保存

```bash
# 编辑完成后自动提交
tgit autosave report.docx

# 后台定时保存（每 10 分钟）
tgit daemon --interval 600
```
