# wgit - Word 文档版本管理工具

[English](./README.md) | [中文](./README.zh.md)

[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)

一个轻量级的命令行工具，用于对 `.docx` 文件进行结构化版本管理。利用 Git 作为底层存储引擎，提供简化、自动化的操作接口，让非技术用户也能轻松追踪 Word 文档的修改历史。

## ✨ 特性

- 🚀 **零学习成本** - 简单的命令，无需了解 Git  internals
- 📦 **智能解压** - 自动将 `.docx` 解压为目录纳入版本控制
- 🏷️ **语义化版本** - 自动生成 `v1.00`, `v1.01`, `v2.00` 等版本标签
- 💾 **安全备份** - 所有操作前自动备份，支持一键恢复
- ⏰ **自动保存** - 支持定时自动提交，防止意外丢失
- 🔍 **变更检测** - 基于哈希智能检测文件变化
- 🌐 **跨平台** - Windows / macOS / Linux 全支持

## 📦 安装

### 方式一：直接运行脚本

```bash
# 克隆或下载 wgit.py 到本地
python wgit.py --help
```

### 方式二：全局安装（推荐）

```bash
# 将 wgit.py 复制到系统 PATH 中的某个目录
# Windows: C:\Users\你的用户名\AppData\Local\Programs\Python\Python3x\Scripts\
# 并重命名为 wgit.exe 或创建批处理文件

# 或者使用 pip 安装（如果有 setup.py）
pip install -e .
```

### 方式三：创建别名

**Windows (PowerShell):**
```powershell
# 在 PowerShell 配置文件 ($PROFILE) 中添加
function wgit { python F:\path\to\wgit.py $args }
```

**Linux/macOS (Bash/Zsh):**
```bash
# 在 ~/.bashrc 或 ~/.zshrc 中添加
alias wgit='python /path/to/wgit.py'
```

## 🚀 快速开始

### 1. 初始化仓库

进入包含 `.docx` 文件的目录，运行：

```bash
wgit init
```

这将：
- 创建 Git 仓库
- 将所有 `.docx` 文件解压为对应的 `_docx` 目录
- 创建初始提交和版本标签 `v1.00`

### 2. 提交更改

修改 `.docx` 文件后，运行：

```bash
# 带提交说明
wgit commit -m "更新了报告第三章"

# 交互式输入说明
wgit commit
```

### 3. 查看版本历史

```bash
wgit log
```

### 4. 查看状态

```bash
wgit status
```

### 5. 恢复旧版本

```bash
# 恢复到最新版本
wgit restore

# 恢复到指定版本
wgit restore v1.02
```

## 📖 命令详解

### `wgit init` - 初始化仓库

初始化当前目录为 wgit 仓库。

```bash
wgit init
```

**执行内容：**
1. 创建 `.git` 仓库（如果不存在）
2. 创建 `.wordgit` 元数据目录
3. 将所有 `.docx` 解压为 `xxx_docx/` 目录
4. 创建初始提交和版本标签 `v1.00`

---

### `wgit commit` - 提交更改

检测 `.docx` 文件变化并提交。

```bash
# 带提交说明
wgit commit -m "修改说明"

# 交互式输入说明
wgit commit

# 不自动创建版本标签
wgit commit -m "说明" --no-tag
```

**自动处理：**
- 检测新增、修改、删除的 `.docx` 文件
- 重新解压变化的文件到对应目录
- 自动 `git add` / `git rm`
- 创建版本标签（如 `v1.01`）

---

### `wgit tag` - 创建版本标签

手动创建版本标签。

```bash
# 自动递增次版本（v1.03 → v1.04）
wgit tag

# 创建新的主版本（v2.00）
wgit tag 2
```

**版本格式：** `v{主版本}.{两位次版本}`
- `v1.00`, `v1.01`, `v1.02` ... `v1.99`
- `v2.00`, `v2.01` ...

---

### `wgit restore` - 恢复版本

将 `.docx` 文件恢复到指定版本。

```bash
# 恢复到最新提交
wgit restore

# 恢复到指定版本
wgit restore v1.02

# 跳过确认
wgit restore -y
```

**安全机制：**
- 恢复前自动备份当前文件为 `.bak` 后缀
- 从 Git 恢复对应的解压目录
- 重新打包为 `.docx` 文件

---

### `wgit status` - 查看状态

显示简化的仓库状态信息。

```bash
wgit status
```

**输出示例：**
```
wgit 状态

当前版本：v1.01
HEAD:    05e947f

文档状态:
  共管理 2 个文档
  所有文档已是最新版本

Git 状态:
  工作区干净
```

---

### `wgit log` - 查看版本历史

显示版本提交记录。

```bash
# 显示最近 20 条
wgit log

# 显示最近 5 条
wgit log -n 5

# 图形化显示
wgit log --graph
```

**输出示例：**
```
版本历史:

版本               时间                     说明
-----------------------------------------------------------------
v1.03 <-HEAD  2024-01-15 14:30:00   更新了报告第三章
v1.02        2024-01-15 10:15:00   修改 1 个文件
v1.01        2024-01-14 16:45:00   新增 2 个文件
v1.00        2024-01-14 09:00:00   wgit: 初始提交
```

**说明：**
- `<-HEAD` 标记表示当前所在的版本

---

### `wgit autosave` - 自动保存

立即检测变化并提交（适合绑定快捷键）。

```bash
wgit autosave
```

---

### `wgit daemon` - 守护进程

启动后台定时自动保存。

```bash
# 默认每 5 分钟检查一次
wgit daemon

# 自定义间隔（秒）
wgit daemon --interval=600
```

**注意：** 守护进程在前台运行，按 `Ctrl+C` 停止。

---

## 📝 示例工作流

### 场景一：撰写报告

```bash
# 1. 开始写报告前初始化
cd F:\reports
wgit init
# → 创建仓库，版本 v1.00

# 2. 写完第一章后提交
# （在 Word 中编辑并保存 report.docx）
wgit commit -m "完成第一章"
# → 版本 v1.01

# 3. 继续写第二章
# （继续编辑并保存）
wgit commit -m "完成第二章"
# → 版本 v1.02

# 4. 发现第一章写错了，恢复到第一章完成后的版本
wgit restore v1.01
# → 恢复 report.docx 到 v1.01 状态

# 5. 重新修改并提交
wgit commit -m "修正第一章错误"
# → 版本 v1.03
```

### 场景二：多人协作

```bash
# 小王修改了文档
wgit commit -m "小王：更新市场分析部分"

# 小李继续修改
wgit commit -m "小李：完善财务预测"

# 查看谁改了什么
wgit log --graph

# 发现有问题，恢复到小王的版本
wgit restore v1.01
```

### 场景三：自动备份

```bash
# 启动守护进程，每 5 分钟自动保存
wgit daemon --interval=300

# 或者在写作过程中定期手动保存
# （可以绑定到 Word 宏或快捷键）
wgit autosave
```

### 场景四：多文档管理

```bash
# 目录结构：
# F:\project\
#   ├── 报告.docx
#   ├── 附录.docx
#   └── 参考资料.docx

# 一次性管理所有文档
wgit init
# → 创建 报告_docx/, 附录_docx/, 参考资料_docx/

# 提交所有变化
wgit commit -m "更新所有文档"

# 恢复所有文档到指定版本
wgit restore v1.02
```

## 🗂️ 目录结构

初始化后的目录结构：

```
工作目录/
├── .git/                  # Git 仓库
├── .wordgit/              # wgit 元数据
│   └── hashes.json        # 文件哈希记录
├── .gitignore             # Git 忽略规则（仅管理 .docx 文件）
├── report_docx/           # report.docx 的解压内容
│   ├── _rels/
│   ├── docProps/
│   ├── word/
│   └── [Content_Types].xml
├── doc1_docx/             # doc1.docx 的解压内容
├── report.docx            # 原始 Word 文件
├── doc1.docx              # 原始 Word 文件
└── report.docx.bak        # 备份文件（恢复时创建）
```

**注意：** `.gitignore` 使用排除方式配置，只管理 `.docx` 和 `*_docx/` 目录，其他文件（如 `.txt`, `.pdf`, `.xlsx` 等）会被自动忽略。

## ⚙️ 技术细节

### 解压策略

`.docx` 本质是 ZIP 格式的 Open XML 文件。wgit 使用 Python 标准库 `zipfile` 进行解压/打包：

- **解压**: `report.docx` → `report_docx/`
- **打包**: `report_docx/` → `report.docx`

### 变更检测

通过比对文件 SHA256 哈希值检测变化：

1. 每次提交后记录每个 `.docx` 的哈希值到 `.wordgit/hashes.json`
2. 下次提交前重新计算哈希，比对差异
3. 只处理有变化的文件

### 版本标签

使用 Git 的 annotated tag：

```bash
git tag -a v1.05 -m "wgit 版本 v1.05"
```

版本号格式：`v{主版本}.{次版本:02d}`

### 原子操作

所有文件操作使用原子化策略：

1. 解压到临时目录
2. 验证完整性
3. 删除旧目录
4. 移动新目录到目标位置

## 🔧 高级用法

### 直接使用 Git

wgit 不阻止你直接使用 Git 命令：

```bash
# 查看详细的 Git 历史
git log --oneline

# 创建分支
git branch feature-xxx

# 切换分支
git checkout feature-xxx

# 注意：切换分支后需要手动恢复 .docx 文件
wgit restore
```

### 恢复误删的文件

```bash
# 1. 查看历史
wgit log

# 2. 找到删除前的版本
wgit restore v1.02

# 3. 或者用 Git 恢复解压目录
git checkout v1.02 -- report_docx/
wgit restore  # 重新打包
```

### 迁移现有 Git 仓库

如果目录已有 Git 仓库：

```bash
wgit init
# 会自动检测并使用现有仓库
```

## ❓ 常见问题

### Q: 支持 `.doc` 文件吗？
A: 不支持。wgit 仅支持 `.docx`（Office 2007+ 的 Open XML 格式）。如需使用，请将 `.doc` 另存为 `.docx`。

### Q: 可以在 Word 打开文件时提交吗？
A: 可以，但 Word 会锁定文件，可能导致读取失败。建议先保存并关闭 Word 再提交。

### Q: 如何禁用自动版本标签？
A: 使用 `wgit commit --no-tag`。

### Q: 备份文件在哪里？
A: 与原文件同目录，后缀为 `.bak`，如 `report.docx.bak`。

### Q: 如何彻底删除 wgit 仓库？
A: 删除 `.git` 和 `.wordgit` 目录，以及所有 `*_docx/` 目录和 `.bak` 文件。
