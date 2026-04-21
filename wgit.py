#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wgit - Word 文档版本管理工具
基于 Git 的 .docx 文件结构化版本管理系统
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 获取 wgit.py 所在目录，用于查找 word_diff.py
SCRIPT_DIR = Path(__file__).parent.resolve()
WORD_DIFF_SCRIPT = SCRIPT_DIR / "word_diff.py"

# ============================================================================
# 常量定义
# ============================================================================

VERSION = "1.0.0"
TOOL_NAME = "wgit"
METADATA_DIR = ".wordgit"
HASHES_FILE = "hashes.json"
DOCX_EXTENSION = ".docx"
UNPACK_SUFFIX = "_docx"

# 颜色输出
class Colors:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    RESET = "\033[0m"
    BOLD = "\033[1m"

# Windows 兼容性
if sys.platform == "win32":
    try:
        import colorama
        colorama.init()
    except ImportError:
        pass  # 如果没有安装 colorama，则不使用颜色


# ============================================================================
# 工具函数
# ============================================================================

def print_success(msg: str):
    print(f"{Colors.GREEN}✓{Colors.RESET} {msg}")


def print_error(msg: str):
    print(f"{Colors.RED}✗{Colors.RESET} {msg}")


def print_warning(msg: str):
    print(f"{Colors.YELLOW}⚠{Colors.RESET} {msg}")


def print_info(msg: str):
    print(f"{Colors.BLUE}ℹ{Colors.RESET} {msg}")


def print_step(msg: str):
    print(f"{Colors.CYAN}→{Colors.RESET} {msg}")


def set_hidden_attr(path: Path):
    """设置目录为隐藏属性（Windows）"""
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["attrib", "+h", str(path)],
                capture_output=True,
                timeout=5
            )
        except Exception:
            pass  # 如果失败则忽略


def run_git(args: List[str], cwd: Optional[str] = None, capture: bool = True) -> subprocess.CompletedProcess:
    """执行 git 命令"""
    cmd = ["git"] + args
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=capture,
            text=True,
            encoding="utf-8"
        )
        return result
    except FileNotFoundError:
        print_error("未找到 git 命令，请确保已安装 Git")
        sys.exit(1)


def calculate_file_hash(filepath: Path) -> str:
    """计算文件的 SHA256 哈希值"""
    sha256 = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except (IOError, OSError) as e:
        print_error(f"无法读取文件 {filepath}: {e}")
        return ""


def unpack_docx(docx_path: Path, output_dir: Path) -> bool:
    """
    将 .docx 文件解压到指定目录
    使用原子操作：先解压到临时目录，再移动
    """
    if not docx_path.exists():
        print_error(f"文件不存在：{docx_path}")
        return False
    
    if not zipfile.is_zipfile(docx_path):
        print_error(f"不是有效的 .docx 文件：{docx_path}")
        return False
    
    try:
        # 创建临时目录
        temp_dir = tempfile.mkdtemp(prefix="wgit_unpack_")
        temp_path = Path(temp_dir)
        
        # 解压
        with zipfile.ZipFile(docx_path, 'r') as zip_ref:
            zip_ref.extractall(temp_path)
        
        # 原子移动：先删除旧目录，再移动新目录
        if output_dir.exists():
            shutil.rmtree(output_dir)
        shutil.move(str(temp_path), str(output_dir))
        
        return True
    except Exception as e:
        print_error(f"解压失败：{e}")
        # 清理临时目录
        if 'temp_dir' in locals() and Path(temp_dir).exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        return False


def pack_docx(source_dir: Path, output_path: Path) -> bool:
    """
    将目录打包为 .docx 文件
    使用原子操作：先打包到临时文件，再替换
    """
    if not source_dir.exists():
        print_error(f"源目录不存在：{source_dir}")
        return False

    try:
        # 创建临时文件
        fd, temp_path = tempfile.mkstemp(suffix=".docx", prefix="wgit_pack_")
        os.close(fd)
        temp_file = Path(temp_path)

        # 打包（保持 ZIP 格式，_docx 扩展名）
        with zipfile.ZipFile(temp_file, 'w', zipfile.ZIP_DEFLATED) as zip_ref:
            for root, dirs, files in os.walk(source_dir):
                for file in files:
                    file_path = Path(root) / file
                    arcname = file_path.relative_to(source_dir)
                    zip_ref.write(file_path, arcname)

        # 原子替换：直接移动临时文件到目标位置
        if output_path.exists():
            output_path.unlink()

        shutil.move(str(temp_file), str(output_path))

        return True
    except Exception as e:
        print_error(f"打包失败：{e}")
        # 清理临时文件
        if 'temp_file' in locals() and temp_file.exists():
            temp_file.unlink(missing_ok=True)
        return False


# 已弃用：backup_file 函数已移除，不再使用 .bak 备份文件


# ============================================================================
# WGit 核心类
# ============================================================================

class WGit:
    """WGit 核心功能类"""
    
    def __init__(self, working_dir: Optional[Path] = None):
        self.working_dir = working_dir or Path.cwd()
        self.metadata_dir = self.working_dir / METADATA_DIR
        self.hashes_file = self.metadata_dir / HASHES_FILE
        self.hashes: Dict[str, str] = {}
        
    def load_hashes(self):
        """加载哈希记录"""
        if self.hashes_file.exists():
            try:
                with open(self.hashes_file, 'r', encoding='utf-8') as f:
                    self.hashes = json.load(f)
            except (json.JSONDecodeError, IOError):
                self.hashes = {}
        else:
            self.hashes = {}
    
    def save_hashes(self):
        """保存哈希记录"""
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        with open(self.hashes_file, 'w', encoding='utf-8') as f:
            json.dump(self.hashes, f, indent=2, ensure_ascii=False)
    
    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        git_dir = self.working_dir / ".git"
        return git_dir.exists() and self.metadata_dir.exists()
    
    def get_docx_files(self) -> List[Path]:
        """获取当前目录下所有 .docx 文件（排除备份文件和临时文件）"""
        docx_files = []
        for f in self.working_dir.glob(f"*{DOCX_EXTENSION}"):
            # 排除备份文件、临时文件和隐藏文件
            if (not f.name.endswith(".bak") and 
                not ".bak" in f.name and
                not f.name.startswith("~$")):
                docx_files.append(f)
        return sorted(docx_files)
    
    def get_unpack_dir(self, docx_path: Path) -> Path:
        """获取 .docx 对应的解压目录"""
        # report.docx -> report_docx
        base_name = docx_path.stem  # 不含扩展名
        return self.working_dir / f"{base_name}{UNPACK_SUFFIX}"
    
    def init(self) -> bool:
        """初始化仓库"""
        print_step(f"在 {self.working_dir} 初始化 wgit 仓库...")
        
        # 检查是否已有 git 仓库
        git_dir = self.working_dir / ".git"
        if not git_dir.exists():
            print_step("创建 Git 仓库...")
            result = run_git(["init"], cwd=str(self.working_dir))
            if result.returncode != 0:
                print_error(f"Git 初始化失败：{result.stderr}")
                return False
            print_success("Git 仓库创建成功")
        
        # 创建 .gitignore（仅跟踪解压目录，不跟踪 .docx 二进制文件）
        gitignore_path = self.working_dir / ".gitignore"
        ignore_patterns = [
            "# wgit - Word 文档版本管理",
            "# 仅跟踪解压后的 _docx 目录，不跟踪 .docx 二进制文件",
            "",
            "# 忽略所有文件",
            "/*",
            "",
            "# 强制添加解压后的目录（用于版本对比和 diff）",
            "!*_docx/",
            "!*_docx/**",
            "",
            "# 排除 .docx 二进制文件（通过解压目录追踪变化）",
            "*.docx",
            "",
            "# 排除 wgit 元数据",
            f"{METADATA_DIR}/",
            "",
            "# 排除临时文件",
            "*.tmp",
            "~$*",
            "*.part",
        ]

        # 如果 .gitignore 不存在或没有 wgit 相关规则，则重写
        existing_patterns = []
        if gitignore_path.exists():
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                existing_patterns = f.read()

        # 只有当文件中没有 wgit 标记时才重写
        if "# wgit" not in existing_patterns:
            with open(gitignore_path, 'w', encoding='utf-8') as f:
                f.write("\n".join(ignore_patterns) + "\n")
            print_success("创建 .gitignore（仅管理 .docx 文件）")
        else:
            print_info(".gitignore 已存在")
        
        # 创建元数据目录
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        print_success(f"创建 {METADATA_DIR} 目录")
        # 设置隐藏属性
        set_hidden_attr(self.metadata_dir)

        # 加载并解压现有 .docx 文件
        self.load_hashes()
        docx_files = self.get_docx_files()

        if docx_files:
            print_step(f"发现 {len(docx_files)} 个 .docx 文件，开始解压...")
            for docx_path in docx_files:
                unpack_dir = self.get_unpack_dir(docx_path)
                if unpack_docx(docx_path, unpack_dir):
                    # 记录哈希
                    file_hash = calculate_file_hash(docx_path)
                    self.hashes[docx_path.name] = file_hash
                    print_success(f"解压：{docx_path.name} → {unpack_dir.name}/")
                    # 设置隐藏属性
                    set_hidden_attr(unpack_dir)
                else:
                    print_warning(f"跳过：{docx_path.name}")
            self.save_hashes()
        
        # 初始提交
        print_step("创建初始提交...")
        run_git(["add", "-A"], cwd=str(self.working_dir))
        result = run_git(
            ["commit", "-m", "wgit: 初始提交"],
            cwd=str(self.working_dir)
        )
        if result.returncode == 0:
            print_success("初始提交完成")
        else:
            if "nothing to commit" in result.stdout or "nothing to commit" in result.stderr:
                print_info("没有需要提交的内容")
            else:
                print_warning(f"提交可能失败：{result.stderr}")
        
        # 创建初始标签
        self.create_tag("1", force_major=True)
        
        print_success(f"wgit 仓库初始化完成！")
        print_info(f"使用 'wgit commit -m \"说明\"' 提交更改")
        return True
    
    def ensure_workspace_clean(self, operation: str = "操作", allow_backup: bool = False) -> bool:
        """
        确保工作区干净，检测未提交的更改
        :param operation: 操作名称，用于提示信息
        :param allow_backup: 是否允许创建备份分支（restore 命令为 False）
        :return: True 如果工作区干净或用户选择提交，False 如果用户取消
        """
        modified, added, deleted = self.detect_changes(auto_unpack=False)

        if not modified and not added and not deleted:
            return True

        # 有未提交的更改
        print_warning("检测到未提交的更改：")
        if modified:
            for f in modified:
                print(f"  M {f.name}")
        if added:
            for f in added:
                print(f"  A {f.name}")
        if deleted:
            for name in deleted:
                print(f"  D {name}")

        print()
        try:
            response = input("是否先提交？(y/n): ").strip().lower()
            if response in ('y', 'yes'):
                # 用户选择提交
                message = input("请输入提交说明（直接回车使用默认说明）: ").strip()
                if not message:
                    message = f"[{operation} 前自动提交]"
                success = self.commit(message=message, auto_version=True)
                return success
            else:
                # 用户选择不提交
                if allow_backup:
                    # 创建临时备份分支
                    print_info("将创建临时备份分支保存当前状态...")
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    backup_branch = f"wgit_backup_{timestamp}"
                    result = run_git(["checkout", "-b", backup_branch], cwd=str(self.working_dir))
                    if result.returncode == 0:
                        print_success(f"已创建临时备份分支：{backup_branch}")
                        print_info(f"操作完成后可运行 'git checkout {backup_branch}' 恢复")
                else:
                    # 直接丢弃更改
                    print_warning("将丢弃未提交的更改...")
                return True
        except (EOFError, KeyboardInterrupt):
            print_info("\n已取消")
            return False

    def detect_changes(self, auto_unpack: bool = True) -> Tuple[List[Path], List[Path], List[str]]:
        """
        检测文件变化（基于 .docx 文件的哈希值）
        如果检测到变化，自动解压到 _docx 目录
        :param auto_unpack: 检测到变化时是否自动解压
        :return: (修改的文件，新增的文件，删除的文件)
        """
        self.load_hashes()
        current_docx = self.get_docx_files()
        current_names = {f.name for f in current_docx}
        recorded_names = set(self.hashes.keys())

        modified = []
        added = []
        deleted = []

        # 检查修改和新增
        for docx_path in current_docx:
            current_hash = calculate_file_hash(docx_path)
            recorded_hash = self.hashes.get(docx_path.name, "")

            if recorded_hash == "":
                added.append(docx_path)
                # 自动解压新文件
                if auto_unpack:
                    unpack_dir = self.get_unpack_dir(docx_path)
                    if unpack_docx(docx_path, unpack_dir):
                        print_success(f"新增并解压：{docx_path.name}")
                        # 设置隐藏属性
                        set_hidden_attr(unpack_dir)
                    # 记录哈希
                    self.hashes[docx_path.name] = current_hash
            elif current_hash != recorded_hash:
                modified.append(docx_path)
                # 自动解压修改的文件
                if auto_unpack:
                    unpack_dir = self.get_unpack_dir(docx_path)
                    if unpack_docx(docx_path, unpack_dir):
                        print_success(f"检测到变更并解压：{docx_path.name}")
                        # 设置隐藏属性
                        set_hidden_attr(unpack_dir)
                    # 更新哈希
                    self.hashes[docx_path.name] = current_hash

        # 检查删除
        for name in recorded_names:
            if name not in current_names:
                deleted.append(name)
                # 移除解压目录
                if auto_unpack:
                    unpack_dir = self.get_unpack_dir(self.working_dir / name)
                    if unpack_dir.exists():
                        shutil.rmtree(unpack_dir)
                        print_success(f"删除解压目录：{name}")
                    # 从哈希记录中移除
                    del self.hashes[name]

        # 保存更新后的哈希记录
        if auto_unpack and (modified or added or deleted):
            self.save_hashes()

        return modified, added, deleted
    
    def commit(self, message: Optional[str] = None, auto_version: bool = True, tag_major: Optional[str] = None) -> bool:
        """提交更改"""
        if not self.is_initialized():
            print_error("当前目录不是 wgit 仓库，请先运行 'wgit init'")
            return False

        # 检测变化（自动解压变更的文件到 _docx 目录）
        modified, added, deleted = self.detect_changes(auto_unpack=True)

        if not modified and not added and not deleted:
            print_info("没有检测到更改")
            return True

        print_step("提交更改...")

        # Git add：只添加 _docx 目录（.gitignore 已排除 .docx 文件）
        run_git(["add", "-A"], cwd=str(self.working_dir))

        # 获取提交信息
        if not message:
            # 使用 Git 默认编辑器
            editor_result = run_git(["var", "GIT_EDITOR"])
            if editor_result.returncode == 0:
                editor = editor_result.stdout.strip()
            else:
                # 默认使用 vim 或记事本
                editor = "vim" if os.name != "nt" else "notepad"

            # 创建临时文件
            import tempfile
            fd, temp_file = tempfile.mkstemp(suffix=".txt", prefix="wgit_commit_")
            os.close(fd)
            temp_path = Path(temp_file)

            # 写入提示信息
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.write("\n# 请输入提交说明，保存退出后提交。以 # 开头的行将被忽略。\n")
                f.write("#\n")
                if modified:
                    f.write(f"# 修改的文件 ({len(modified)}):\n")
                    for f_path in modified:
                        f.write(f"#   M {f_path.name}\n")
                if added:
                    f.write(f"# 新增的文件 ({len(added)}):\n")
                    for f_path in added:
                        f.write(f"#   A {f_path.name}\n")
                if deleted:
                    f.write(f"# 删除的文件 ({len(deleted)}):\n")
                    for name in deleted:
                        f.write(f"#   D {name}\n")

            # 打开编辑器
            print_info(f"打开编辑器：{editor}")
            try:
                subprocess.run([editor, temp_path])
            except FileNotFoundError:
                print_error(f"无法打开编辑器：{editor}")
                temp_path.unlink(missing_ok=True)
                return False

            # 读取提交信息
            with open(temp_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            message = ''.join([line for line in lines if not line.startswith('#')]).strip()

            # 清理临时文件
            temp_path.unlink(missing_ok=True)

            if not message:
                print_info("提交信息为空，取消提交")
                return False

        # 执行提交
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        full_message = f"{message}\n\n时间：{timestamp}"

        result = run_git(
            ["commit", "-m", full_message],
            cwd=str(self.working_dir)
        )

        if result.returncode != 0:
            print_error(f"提交失败：{result.stderr}")
            return False

        print_success(f"提交成功：{message}")

        # 自动创建版本标签
        if auto_version:
            self.create_tag(major=tag_major, force_major=(tag_major is not None))

        return True
    
    def get_latest_tag(self) -> Optional[str]:
        """获取最新的版本标签"""
        result = run_git(
            ["tag", "-l", "v*"],
            cwd=str(self.working_dir)
        )
        tags = result.stdout.strip().split('\n') if result.stdout.strip() else []
        
        if not tags:
            return None
        
        # 按版本号排序
        def parse_version(tag: str) -> Tuple[int, int]:
            # v1.05 -> (1, 5)
            try:
                tag = tag.lstrip('v')
                parts = tag.split('.')
                major = int(parts[0])
                minor = int(parts[1]) if len(parts) > 1 else 0
                return (major, minor)
            except (ValueError, IndexError):
                return (0, 0)
        
        tags.sort(key=parse_version, reverse=True)
        return tags[0] if tags else None
    
    def parse_version(self, version: str) -> Tuple[int, int]:
        """解析版本号"""
        version = version.lstrip('v')
        parts = version.split('.')
        major = int(parts[0]) if parts else 1
        minor = int(parts[1]) if len(parts) > 1 else 0
        return (major, minor)
    
    def create_tag(self, major: Optional[str] = None, force_major: bool = False) -> Optional[str]:
        """
        创建版本标签
        :param major: 指定主版本号（可选）
        :param force_major: 是否强制使用指定的主版本号
        :return: 创建的标签名
        """
        latest_tag = self.get_latest_tag()
        
        # 获取 HEAD 指向的所有标签
        head_result = run_git(["rev-parse", "HEAD"], cwd=str(self.working_dir))
        head_hash = head_result.stdout.strip() if head_result.stdout.strip() else ""
        
        # 删除 HEAD 指向的所有现有标签（保证一次提交只有一个 tag）
        if head_hash:
            tag_result = run_git(
                ["show-ref", "--tags", "-d"],
                cwd=str(self.working_dir)
            )
            for line in tag_result.stdout.strip().split('\n'):
                if line:
                    parts = line.split()
                    if len(parts) >= 2:
                        commit_hash = parts[0]
                        tag_ref = parts[1]
                        if commit_hash == head_hash:
                            # 删除这个标签
                            tag_name = tag_ref.replace('refs/tags/', '').replace('^{}', '')
                            del_result = run_git(["tag", "-d", tag_name], cwd=str(self.working_dir))
                            if del_result.returncode == 0:
                                print_info(f"删除旧标签：{tag_name}")

        if major is not None and force_major:
            # 强制创建新的主版本
            new_tag = f"v{major}.00"
        elif latest_tag:
            current_major, current_minor = self.parse_version(latest_tag)

            if major is not None:
                # 指定主版本，次版本从 0 开始
                new_major = int(major)
                new_minor = 0
            else:
                # 自动递增次版本
                new_major = current_major
                new_minor = current_minor + 1

            new_tag = f"v{new_major}.{new_minor:02d}"
        else:
            # 没有现有标签，从 v1.00 开始
            new_tag = "v1.00" if major is None else f"v{major}.00"

        # 创建标签（指向 HEAD）
        result = run_git(
            ["tag", "-a", new_tag, "-m", f"wgit 版本 {new_tag}", "HEAD"],
            cwd=str(self.working_dir)
        )

        if result.returncode == 0:
            print_success(f"创建版本标签：{new_tag}")
            return new_tag
        else:
            print_error(f"创建标签失败：{result.stderr}")
            return None
    
    def restore(self, version: Optional[str] = None, force: bool = False) -> bool:
        """
        恢复指定版本
        :param version: 版本号（如 v1.02），None 表示最新版本
        :param force: 是否跳过确认
        """
        if not self.is_initialized():
            print_error("当前目录不是 wgit 仓库")
            return False

        # 前置工作区检测（restore 不创建备份分支）
        if not force and not self.ensure_workspace_clean("restore", allow_backup=False):
            return False

        # 确定要恢复的版本
        if version is None:
            # 恢复到最新提交（HEAD）
            print_step("恢复到最新提交...")
            target = "HEAD"
            version = "最新提交"
        else:
            # 确保版本号格式
            if not version.startswith('v'):
                version = f"v{version}"
            target = version
            # 验证标签是否存在
            result = run_git(["rev-parse", "--verify", target], cwd=str(self.working_dir))
            if result.returncode != 0:
                print_error(f"版本不存在：{version}")
                # 列出可用版本
                self.list_tags()
                return False

        # 从 Git 历史中获取要恢复的 .docx 文件列表（从解压目录推断）
        # 即使当前工作区没有 .docx 文件，也能从 Git 存储中恢复
        print_step(f"从 {target} 获取文件列表...")
        
        # 获取目标版本中所有的 _docx 目录（使用 -z 避免特殊字符转义）
        if target == "HEAD":
            ls_result = run_git(["ls-tree", "-r", "--name-only", "-z", "HEAD"], cwd=str(self.working_dir))
        else:
            ls_result = run_git(["ls-tree", "-r", "--name-only", "-z", target], cwd=str(self.working_dir))
        
        unpack_dirs = set()
        # 使用 \0 分割
        for line in ls_result.stdout.split('\0'):
            line = line.strip()
            if line:
                # 提取 _docx 目录名（如：作业封皮 _docx/word/document.xml -> 作业封皮 _docx）
                parts = line.split('/')
                if parts and parts[0].endswith('_docx'):
                    unpack_dirs.add(parts[0])
        
        # 从 _docx 目录推断 .docx 文件名
        restore_files = []
        for unpack_dir_name in unpack_dirs:
            # doc1_docx -> doc1.docx
            docx_name = unpack_dir_name[:-5] + '.docx'  # 去掉 '_docx' 加上 '.docx'
            restore_files.append(docx_name)

        if not restore_files:
            print_error(f"版本 {version} 中没有找到 .docx 文件")
            return False

        print_info(f"将恢复 {len(restore_files)} 个文件：{', '.join(restore_files)}")

        # 恢复解压目录和 .docx 文件
        print_step(f"从 {target} 恢复文件...")

        for docx_name in restore_files:
            docx_path = self.working_dir / docx_name
            unpack_dir = self.get_unpack_dir(docx_path)
            rel_path = unpack_dir.relative_to(self.working_dir)

            # 从 git 恢复解压目录
            if target == "HEAD":
                result = run_git(
                    ["checkout", "HEAD", "--", str(rel_path)],
                    cwd=str(self.working_dir)
                )
            else:
                result = run_git(
                    ["checkout", target, "--", str(rel_path)],
                    cwd=str(self.working_dir)
                )

            if result.returncode != 0:
                print_warning(f"无法恢复 {unpack_dir.name}（可能在该版本中不存在）")
                continue

            # 重新打包为 .docx
            if pack_docx(unpack_dir, docx_path):
                print_success(f"恢复：{docx_name}")
            else:
                print_error(f"打包失败：{docx_name}")

        # 更新哈希记录
        self.load_hashes()
        for docx_name in restore_files:
            docx_path = self.working_dir / docx_name
            if docx_path.exists():
                self.hashes[docx_path.name] = calculate_file_hash(docx_path)
        self.save_hashes()

        print_success(f"已恢复到 {version}")

        return True

    def branch(self, branch_name: Optional[str] = None, delete: bool = False) -> bool:
        """
        创建、删除或列出分支
        :param branch_name: 分支名，None 表示列出所有分支
        :param delete: 是否删除分支
        """
        if not self.is_initialized():
            print_error("当前目录不是 wgit 仓库")
            return False

        if branch_name is None:
            # 列出所有分支
            result = run_git(["branch"], cwd=str(self.working_dir))
            if result.returncode == 0:
                print(result.stdout)
            return True

        if delete:
            # 删除分支
            # 检查是否是当前分支
            current_result = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=str(self.working_dir))
            current_branch = current_result.stdout.strip()
            if current_branch == branch_name:
                print_error(f"不能删除当前分支，请先切换到其他分支")
                return False
            
            result = run_git(["branch", "-d", branch_name], cwd=str(self.working_dir))
            if result.returncode == 0:
                print_success(f"已删除分支：{branch_name}")
                return True
            else:
                print_error(f"删除失败：{result.stderr}")
                return False

        # 创建新分支
        # 前置工作区检测（直接丢弃更改）
        if not self.ensure_workspace_clean("branch", allow_backup=False):
            return False

        # 检查分支是否已存在
        check_result = run_git(["rev-parse", "--verify", branch_name], cwd=str(self.working_dir))
        if check_result.returncode == 0:
            print_error(f"分支 '{branch_name}' 已存在")
            return False

        # 创建并切换到新分支
        result = run_git(["checkout", "-b", branch_name], cwd=str(self.working_dir))
        if result.returncode == 0:
            print_success(f"创建并切换到新分支：{branch_name}")
            # 新分支的版本号从 v1.00 开始，需要重置 hashes.json 中的版本记录
            # 但保留文件哈希，以便检测变化
            print_info(f"新分支的版本号将从 v1.00 开始")
            return True
        else:
            print_error(f"创建分支失败：{result.stderr}")
            return False

    def checkout(self, branch_name: str) -> bool:
        """
        切换到指定分支
        :param branch_name: 分支名
        """
        if not self.is_initialized():
            print_error("当前目录不是 wgit 仓库")
            return False

        # 检查分支是否存在
        result = run_git(["rev-parse", "--verify", branch_name], cwd=str(self.working_dir))
        if result.returncode != 0:
            print_error(f"分支 '{branch_name}' 不存在")
            return False

        # 前置工作区检测（直接丢弃更改）
        if not self.ensure_workspace_clean("checkout", allow_backup=False):
            return False

        # 获取当前分支
        current_result = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=str(self.working_dir))
        current_branch = current_result.stdout.strip()
        if current_branch == branch_name:
            print_info(f"已在分支 '{branch_name}' 上")
            return True

        # 保存当前 .docx 文件列表，用于切换后重新打包
        docx_files = self.get_docx_files()

        # 切换分支
        result = run_git(["checkout", branch_name], cwd=str(self.working_dir))
        if result.returncode != 0:
            print_error(f"切换分支失败：{result.stderr}")
            return False

        # 重新生成 .docx 文件
        print_step("重新生成 .docx 文件...")
        self.load_hashes()
        for docx_path in docx_files:
            unpack_dir = self.get_unpack_dir(docx_path)
            if unpack_dir.exists():
                if pack_docx(unpack_dir, docx_path):
                    print_success(f"生成：{docx_path.name}")
                else:
                    print_warning(f"生成失败：{docx_path.name}")

        print_success(f"已切换到 {branch_name} 分支")
        return True

    def override(self, branch_name: str) -> bool:
        """
        将当前工作区状态覆盖式地提交到指定分支
        :param branch_name: 目标分支名
        """
        if not self.is_initialized():
            print_error("当前目录不是 wgit 仓库")
            return False

        # 检查目标分支是否存在
        result = run_git(["rev-parse", "--verify", branch_name], cwd=str(self.working_dir))
        if result.returncode != 0:
            print_error(f"分支 '{branch_name}' 不存在")
            return False

        # 前置工作区检测（直接丢弃更改）
        if not self.ensure_workspace_clean("override", allow_backup=False):
            return False

        # 获取当前分支
        current_result = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=str(self.working_dir))
        current_branch = current_result.stdout.strip()
        if current_branch == branch_name:
            print_error(f"已在分支 '{branch_name}' 上，无需覆盖")
            return False

        # 保存当前工作区的 _docx 目录到临时位置
        import tempfile
        temp_dir = tempfile.mkdtemp(prefix="wgit_override_")
        print_step(f"保存当前工作区状态到临时目录...")
        
        docx_files = self.get_docx_files()
        for docx_path in docx_files:
            unpack_dir = self.get_unpack_dir(docx_path)
            if unpack_dir.exists():
                temp_unpack = Path(temp_dir) / unpack_dir.name
                shutil.copytree(str(unpack_dir), str(temp_unpack))

        # 切换到目标分支
        print_step(f"切换到分支 {branch_name}...")
        result = run_git(["checkout", branch_name], cwd=str(self.working_dir))
        if result.returncode != 0:
            print_error(f"切换分支失败：{result.stderr}")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return False

        # 复制临时目录内容到工作区
        print_step(f"应用工作区状态到 {branch_name}...")
        for docx_path in docx_files:
            unpack_dir = self.get_unpack_dir(docx_path)
            temp_unpack = Path(temp_dir) / unpack_dir.name
            if temp_unpack.exists():
                # 移除现有的解压目录
                if unpack_dir.exists():
                    shutil.rmtree(unpack_dir)
                # 复制新的解压目录
                shutil.copytree(str(temp_unpack), str(unpack_dir))
                # 重新生成 .docx 文件
                if pack_docx(unpack_dir, docx_path):
                    print_success(f"生成：{docx_path.name}")

        # Git add 并提交
        run_git(["add", "-A"], cwd=str(self.working_dir))
        result = run_git(["status", "--short"], cwd=str(self.working_dir))
        if result.stdout.strip():
            # 有变更，提交
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            message = f"[override] 从 {current_branch} 覆盖\n\n时间：{timestamp}"
            result = run_git(["commit", "-m", message], cwd=str(self.working_dir))
            if result.returncode == 0:
                print_success(f"提交完成：{message.split()[0]}")
                # 创建版本标签
                self.create_tag()
        else:
            print_info("没有变更")

        # 清理临时目录
        shutil.rmtree(temp_dir, ignore_errors=True)

        print_success(f"已完成覆盖并切换到 {branch_name} 分支")
        return True

    def tag(self, tag_name: Optional[str] = None) -> bool:
        """
        创建或列出版本标签
        :param tag_name: 标签名（主版本号），None 表示列出所有标签
        """
        if not self.is_initialized():
            print_error("当前目录不是 wgit 仓库")
            return False

        if tag_name is None:
            # 列出所有版本标签
            self.list_tags()
            return True

        # 创建标签
        tag = self.create_tag(major=tag_name, force_major=True)
        return tag is not None

    def list_tags(self):
        """列出所有版本标签"""
        result = run_git(
            ["tag", "-l", "v*"],
            cwd=str(self.working_dir)
        )
        tags = result.stdout.strip().split('\n') if result.stdout.strip() else []

        if not tags:
            print_info("没有版本标签")
            return

        # 按版本号排序
        def parse_version(tag: str) -> Tuple[int, int]:
            try:
                tag = tag.lstrip('v')
                parts = tag.split('.')
                major = int(parts[0])
                minor = int(parts[1]) if len(parts) > 1 else 0
                return (major, minor)
            except (ValueError, IndexError):
                return (0, 0)

        tags.sort(key=parse_version)

        print_info("版本标签:")
        for tag in tags:
            print(f"  {tag}")
    
    def log(self, limit: int = 20, show_graph: bool = False):
        """显示版本日志"""
        if not self.is_initialized():
            print_error("当前目录不是 wgit 仓库")
            return

        # 获取当前分支名
        branch_result = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=str(self.working_dir))
        current_branch = branch_result.stdout.strip() if branch_result.stdout.strip() else "未知"

        if show_graph:
            # 使用 git log --graph
            result = subprocess.run(
                ["git", "log", "--oneline", "--graph", "--decorate", f"-{limit}"],
                cwd=str(self.working_dir),
                text=True
            )
            print(f"\n{Colors.BOLD}当前分支：{Colors.CYAN}{current_branch}{Colors.RESET}\n")
            print(result.stdout)
        else:
            # 自定义格式
            result = run_git(
                ["log", "--format=%h|%ai|%s", f"-{limit}"],
                cwd=str(self.working_dir)
            )

            if not result.stdout.strip():
                print_info("没有提交记录")
                return

            print(f"\n{Colors.BOLD}当前分支：{Colors.CYAN}{current_branch}{Colors.RESET}\n")
            print(f"{'版本':<16} {'时间':<22} {'说明'}")
            print("-" * 65)

            # 获取 HEAD commit hash
            head_result = run_git(["rev-parse", "HEAD"], cwd=str(self.working_dir))
            head_hash = head_result.stdout.strip()[:7] if head_result.stdout.strip() else ""

            # 获取标签到 commit 的映射
            tag_map = {}
            tag_result = run_git(
                ["show-ref", "--tags", "-d"],
                cwd=str(self.working_dir)
            )
            for line in tag_result.stdout.strip().split('\n'):
                if line:
                    parts = line.split()
                    if len(parts) >= 2:
                        commit_hash = parts[0][:7]
                        # refs/tags/v1.00^{} -> v1.00
                        tag_name = parts[1].replace('refs/tags/', '').replace('^{}', '')
                        tag_map[commit_hash] = tag_name

            for line in result.stdout.strip().split('\n'):
                parts = line.split('|')
                if len(parts) >= 3:
                    commit_hash = parts[0][:7]
                    timestamp = parts[1][:19].replace('T', ' ')
                    message = parts[2]

                    # 查找对应的版本标签
                    version = tag_map.get(commit_hash, "")

                    # 构建版本显示字符串
                    if version:
                        # 如果当前 HEAD 有这个标签，使用黄色高亮
                        if commit_hash == head_hash:
                            version_str = f"{Colors.YELLOW}{version}{Colors.RESET}"
                        else:
                            version_str = f"{Colors.GREEN}{version}{Colors.RESET}"
                    else:
                        version_str = ""

                    print(f"{version_str:<16} {timestamp:<22} {message}")
    
    def status(self) -> bool:
        """显示简化的状态信息"""
        if not self.is_initialized():
            print_error("当前目录不是 wgit 仓库")
            return False

        # 获取最新版本
        latest_tag = self.get_latest_tag()
        version_str = f"{Colors.GREEN}{latest_tag}{Colors.RESET}" if latest_tag else "无版本"

        # 获取 HEAD commit 信息
        head_result = run_git(["rev-parse", "--short", "HEAD"], cwd=str(self.working_dir))
        head_short = head_result.stdout.strip() if head_result.stdout.strip() else "未知"

        print(f"\n{Colors.BOLD}wgit 状态{Colors.RESET}\n")
        print(f"当前版本：{version_str}")
        print(f"HEAD:    {Colors.CYAN}{head_short}{Colors.RESET}")

        # 检测 .docx 文件变化（不自动解压，仅检测）
        modified, added, deleted = self.detect_changes(auto_unpack=False)

        print(f"\n{Colors.BOLD}文档状态:{Colors.RESET}")

        docx_files = self.get_docx_files()
        if not docx_files:
            print_info("当前目录没有 .docx 文件")
        else:
            print(f"  共管理 {len(docx_files)} 个文档")

            if modified:
                print(f"\n{Colors.YELLOW}修改的文档 ({len(modified)}):{Colors.RESET}")
                for f in modified:
                    print(f"  {Colors.YELLOW}M{Colors.RESET} {f.name}")

            if added:
                print(f"\n{Colors.GREEN}新增的文档 ({len(added)}):{Colors.RESET}")
                for f in added:
                    print(f"  {Colors.GREEN}A{Colors.RESET} {f.name}")

            if deleted:
                print(f"\n{Colors.RED}删除的文档 ({len(deleted)}):{Colors.RESET}")
                for name in deleted:
                    print(f"  {Colors.RED}D{Colors.RESET} {name}")

            if not modified and not added and not deleted:
                print(f"  {Colors.GREEN}所有文档已是最新版本{Colors.RESET}")

        # 获取 git 状态（简化）
        git_result = run_git(["status", "--short"], cwd=str(self.working_dir))
        git_status = git_result.stdout.strip()

        if git_status:
            print(f"\n{Colors.BOLD}Git 状态:{Colors.RESET}")
            lines = git_status.split('\n')
            # 只显示非 .docx/_docx 相关的变化（如果有）
            other_changes = [l for l in lines if l and '.docx' not in l and '_docx' not in l]
            if other_changes:
                for line in other_changes[:10]:  # 最多显示 10 行
                    print(f"  {line}")
            else:
                print(f"  {Colors.GREEN}工作区干净{Colors.RESET}")
        else:
            print(f"\n{Colors.BOLD}Git 状态:{Colors.RESET}")
            print(f"  {Colors.GREEN}工作区干净{Colors.RESET}")

        print()
        return True

    def diff(self, version1: Optional[str] = None, version2: Optional[str] = None) -> bool:
        """
        对比文档差异（调用 word_diff 工具）
        :param version1: 第一个版本号（可选，None 表示当前工作区）
        :param version2: 第二个版本号（可选，None 表示最近一次提交）
        """
        if not self.is_initialized():
            print_error("当前目录不是 wgit 仓库")
            return False

        # 先检测变化并自动解压（确保 _docx 目录与 .docx 同步）
        self.detect_changes(auto_unpack=True)

        docx_files = self.get_docx_files()

        if not docx_files:
            print_info("当前目录没有 .docx 文件")
            return True

        # 确定对比模式
        if version1 is None and version2 is None:
            # 模式 1：工作区 vs HEAD
            print_step("对比工作区文件与最近提交...")
            for docx_path in docx_files:
                # 从 HEAD 恢复临时文件进行对比
                unpack_dir = self.get_unpack_dir(docx_path)
                rel_path = unpack_dir.relative_to(self.working_dir)

                # 创建临时目录存放打包的文件
                import tempfile
                temp_dir = tempfile.mkdtemp(prefix="wgit_diff_")
                temp_head_path = Path(temp_dir) / f"head_{docx_path.name}"

                # 从 HEAD 恢复解压目录
                head_result = run_git(
                    ["checkout", "HEAD", "--", str(rel_path)],
                    cwd=str(self.working_dir)
                )
                if head_result.returncode == 0:
                    # 打包 HEAD 版本
                    pack_docx(unpack_dir, temp_head_path)

                    # 调用 word_diff.py 脚本，直接对比 HEAD 打包文件与工作区 .docx 文件
                    # 使用 PYTHONUTF8 环境变量确保 UTF-8 处理
                    env = os.environ.copy()
                    env['PYTHONUTF8'] = '1'

                    result = subprocess.run(
                        [sys.executable, str(WORD_DIFF_SCRIPT), str(temp_head_path), str(docx_path)],
                        capture_output=True,
                        text=True,
                        encoding='utf-8',
                        errors='replace',
                        env=env
                    )
                    # 只有当有差异时才输出
                    if result.stdout.strip():
                        print(f"\n{Colors.BOLD}文档：{docx_path.name}{Colors.RESET}")
                        print(result.stdout)
                    # 恢复解压目录到 HEAD（保持 Git 状态干净）
                    run_git(["checkout", "HEAD", "--", str(rel_path)], cwd=str(self.working_dir))
                else:
                    print_warning(f"无法从 HEAD 恢复 {docx_path.name}")
                # 清理临时文件
                if Path(temp_dir).exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    
        elif version2 is None:
            # 模式 2：工作区 vs 指定版本
            print_step(f"对比工作区文件与版本 {version1}...")
            # 确保版本号格式
            if not version1.startswith('v'):
                version1 = f"v{version1}"

            for docx_path in docx_files:
                unpack_dir = self.get_unpack_dir(docx_path)

                # 创建临时目录存放打包的文件
                import tempfile
                temp_dir = tempfile.mkdtemp(prefix="wgit_diff_")
                temp_version_path = Path(temp_dir) / f"v_{docx_path.name}"

                # 从指定版本恢复解压目录
                rel_path = unpack_dir.relative_to(self.working_dir)
                version_result = run_git(
                    ["checkout", version1, "--", str(rel_path)],
                    cwd=str(self.working_dir)
                )
                if version_result.returncode == 0:
                    # 打包指定版本
                    pack_docx(unpack_dir, temp_version_path)
                    
                    # 调用 word_diff.py 脚本，直接对比指定版本打包文件与工作区 .docx 文件
                    # 使用 PYTHONUTF8 环境变量确保 UTF-8 处理
                    env = os.environ.copy()
                    env['PYTHONUTF8'] = '1'

                    result = subprocess.run(
                        [sys.executable, str(WORD_DIFF_SCRIPT), str(temp_version_path), str(docx_path)],
                        capture_output=True,
                        text=True,
                        encoding='utf-8',
                        errors='replace',
                        env=env
                    )
                    if result.stdout.strip():
                        print(f"\n{Colors.BOLD}文档：{docx_path.name}{Colors.RESET}")
                        print(result.stdout)
                    # 恢复解压目录到 HEAD
                    run_git(["checkout", "HEAD", "--", str(rel_path)], cwd=str(self.working_dir))
                else:
                    print_warning(f"无法从 {version1} 恢复 {docx_path.name}")
                # 清理临时文件
                if Path(temp_dir).exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)
        else:
            # 模式 3：两个版本之间对比
            # 确保版本号格式
            if not version1.startswith('v'):
                version1 = f"v{version1}"
            if not version2.startswith('v'):
                version2 = f"v{version2}"

            print_step(f"对比版本 {version1} 与 {version2}...")

            for docx_path in docx_files:
                unpack_dir = self.get_unpack_dir(docx_path)

                # 创建临时目录
                import tempfile
                temp_dir = tempfile.mkdtemp(prefix="wgit_diff_")
                temp_path1 = Path(temp_dir) / f"v1_{docx_path.name}"
                temp_path2 = Path(temp_dir) / f"v2_{docx_path.name}"

                # 从 version1 恢复
                rel_path = unpack_dir.relative_to(self.working_dir)
                v1_result = run_git(
                    ["checkout", version1, "--", str(rel_path)],
                    cwd=str(self.working_dir)
                )
                if v1_result.returncode == 0:
                    pack_docx(unpack_dir, temp_path1)
                else:
                    print_warning(f"无法从 {version1} 恢复 {docx_path.name}")
                    continue

                # 从 version2 恢复
                v2_result = run_git(
                    ["checkout", version2, "--", str(rel_path)],
                    cwd=str(self.working_dir)
                )
                if v2_result.returncode == 0:
                    pack_docx(unpack_dir, temp_path2)
                else:
                    print_warning(f"无法从 {version2} 恢复 {docx_path.name}")
                    continue

                # 调用 word_diff.py 脚本
                # 使用 PYTHONUTF8 环境变量确保 UTF-8 处理
                env = os.environ.copy()
                env['PYTHONUTF8'] = '1'
                
                result = subprocess.run(
                    [sys.executable, str(WORD_DIFF_SCRIPT), str(temp_path1), str(temp_path2)],
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    env=env
                )
                if result.stdout.strip():
                    print(f"\n{Colors.BOLD}文档：{docx_path.name}{Colors.RESET}")
                    print(result.stdout)

                # 恢复解压目录到 HEAD
                run_git(["checkout", "HEAD", "--", str(rel_path)], cwd=str(self.working_dir))

                # 清理临时文件
                if temp_path1.exists():
                    temp_path1.unlink()
                if temp_path2.exists():
                    temp_path2.unlink()
                if Path(temp_dir).exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)
        
        return True

    def autosave(self) -> bool:
        """自动保存：检测变化并提交"""
        if not self.is_initialized():
            print_error("当前目录不是 wgit 仓库")
            return False
        
        modified, added, deleted = self.detect_changes()
        
        if not modified and not added and not deleted:
            print_info("没有检测到更改，无需保存")
            return True
        
        # 自动生成提交信息
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        parts = []
        if modified:
            parts.append(f"修改 {len(modified)} 个文件")
        if added:
            parts.append(f"新增 {len(added)} 个文件")
        if deleted:
            parts.append(f"删除 {len(deleted)} 个文件")
        message = f"[自动保存] {', '.join(parts)}"
        
        print_step(f"自动保存：{message}")
        return self.commit(message=message, auto_version=True)
    
    def daemon(self, interval: int = 300):
        """
        守护进程：定时自动保存
        :param interval: 检查间隔（秒），默认 300 秒（5 分钟）
        """
        if not self.is_initialized():
            print_error("当前目录不是 wgit 仓库")
            return
        
        print_success(f"启动自动保存守护进程，间隔：{interval}秒")
        print_info("按 Ctrl+C 停止")
        
        try:
            while True:
                time.sleep(interval)
                self.autosave()
        except KeyboardInterrupt:
            print_info("\n守护进程已停止")


# ============================================================================
# 命令行接口
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="Word 文档版本管理工具 - 基于 Git 的 .docx 文件版本控制系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  wgit init                      初始化仓库
  wgit commit -m "修改说明"      提交更改
  wgit tag                       创建新版本
  wgit tag 2                     创建主版本 2.00
  wgit restore                   恢复到最新版本
  wgit restore v1.02             恢复到指定版本
  wgit log                       查看版本历史
  wgit status                    显示简化状态
  wgit diff                      对比工作区与 HEAD
  wgit diff v1.02                对比工作区与 v1.02
  wgit diff v1.00 v1.01          对比两个版本
  wgit autosave                  立即自动保存
  wgit daemon --interval=300     启动定时保存（5 分钟）
        """
    )
    
    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"{TOOL_NAME} {VERSION}"
    )
    
    parser.add_argument(
        "-d", "--directory",
        type=Path,
        default=None,
        help="工作目录（默认：当前目录）"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # init 命令
    subparsers.add_parser("init", help="初始化 wgit 仓库")

    # commit 命令
    commit_parser = subparsers.add_parser("commit", help="提交更改")
    commit_parser.add_argument("-m", "--message", type=str, help="提交说明")
    commit_parser.add_argument(
        "--no-tag",
        action="store_true",
        help="不自动创建版本标签"
    )
    commit_parser.add_argument(
        "--tag",
        type=str,
        dest="tag_major",
        help="指定主版本号（如 2 表示创建 v2.00）"
    )

    # tag 命令
    tag_parser = subparsers.add_parser("tag", help="创建或列出版本标签")
    tag_parser.add_argument(
        "major",
        nargs="?",
        type=str,
        default=None,
        help="主版本号（可选，如 2 表示创建 v2.00；不指定则列出所有标签）"
    )

    # branch 命令
    branch_parser = subparsers.add_parser("branch", help="创建、删除或列出分支")
    branch_parser.add_argument(
        "name",
        nargs="?",
        type=str,
        default=None,
        help="分支名（不指定则列出所有分支）"
    )
    branch_parser.add_argument(
        "-d", "--delete",
        action="store_true",
        help="删除分支"
    )

    # checkout 命令
    checkout_parser = subparsers.add_parser("checkout", help="切换分支")
    checkout_parser.add_argument(
        "branch",
        type=str,
        help="要切换到的分支名"
    )

    # override 命令
    override_parser = subparsers.add_parser("override", help="将当前工作区覆盖到指定分支")
    override_parser.add_argument(
        "branch",
        type=str,
        help="目标分支名"
    )

    # restore 命令
    restore_parser = subparsers.add_parser("restore", help="恢复版本")
    restore_parser.add_argument(
        "version",
        nargs="?",
        type=str,
        default=None,
        help="版本号（如 v1.02），不指定则恢复最新"
    )
    restore_parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="跳过确认"
    )

    # log 命令
    log_parser = subparsers.add_parser("log", help="查看版本历史")
    log_parser.add_argument(
        "-n", "--limit",
        type=int,
        default=20,
        help="显示条目数（默认：20）"
    )
    log_parser.add_argument(
        "--graph",
        action="store_true",
        help="显示图形化历史"
    )

    # status 命令
    subparsers.add_parser("status", help="显示简化状态")

    # diff 命令
    diff_parser = subparsers.add_parser("diff", help="对比文档差异")
    diff_parser.add_argument(
        "version1",
        nargs="?",
        type=str,
        default=None,
        help="第一个版本号（可选，不指定则对比工作区与 HEAD）"
    )
    diff_parser.add_argument(
        "version2",
        nargs="?",
        type=str,
        default=None,
        help="第二个版本号（可选）"
    )

    # autosave 命令
    subparsers.add_parser("autosave", help="立即自动保存")

    # daemon 命令
    daemon_parser = subparsers.add_parser("daemon", help="启动定时自动保存")
    daemon_parser.add_argument(
        "--interval",
        type=int,
        default=300,
        help="检查间隔（秒），默认 300"
    )

    args = parser.parse_args()

    # 确定工作目录
    working_dir = args.directory or Path.cwd()
    if not working_dir.exists():
        print_error(f"目录不存在：{working_dir}")
        sys.exit(1)

    wgit = WGit(working_dir)

    # 执行命令
    if args.command == "init":
        success = wgit.init()
        sys.exit(0 if success else 1)

    elif args.command == "commit":
        success = wgit.commit(
            message=args.message,
            auto_version=not args.no_tag,
            tag_major=args.tag_major
        )
        sys.exit(0 if success else 1)

    elif args.command == "tag":
        if not wgit.is_initialized():
            print_error("当前目录不是 wgit 仓库")
            sys.exit(1)
        success = wgit.tag(tag_name=args.major)
        sys.exit(0 if success else 1)

    elif args.command == "branch":
        if not wgit.is_initialized():
            print_error("当前目录不是 wgit 仓库")
            sys.exit(1)
        success = wgit.branch(branch_name=args.name, delete=args.delete)
        sys.exit(0 if success else 1)

    elif args.command == "checkout":
        if not wgit.is_initialized():
            print_error("当前目录不是 wgit 仓库")
            sys.exit(1)
        success = wgit.checkout(branch_name=args.branch)
        sys.exit(0 if success else 1)

    elif args.command == "override":
        if not wgit.is_initialized():
            print_error("当前目录不是 wgit 仓库")
            sys.exit(1)
        success = wgit.override(branch_name=args.branch)
        sys.exit(0 if success else 1)

    elif args.command == "restore":
        # 恢复前确认
        if args.version is None and not args.yes:
            print_warning("这将恢复到最新提交，当前文件将被覆盖并备份")
            try:
                response = input("继续吗？[y/N]: ").strip().lower()
                if response not in ('y', 'yes'):
                    print_info("已取消")
                    sys.exit(0)
            except (EOFError, KeyboardInterrupt):
                print_info("已取消")
                sys.exit(0)

        success = wgit.restore(version=args.version, force=args.yes)
        sys.exit(0 if success else 1)

    elif args.command == "log":
        wgit.log(limit=args.limit, show_graph=args.graph)
        sys.exit(0)

    elif args.command == "status":
        success = wgit.status()
        sys.exit(0 if success else 1)

    elif args.command == "diff":
        success = wgit.diff(version1=args.version1, version2=args.version2)
        sys.exit(0 if success else 1)

    elif args.command == "autosave":
        success = wgit.autosave()
        sys.exit(0 if success else 1)

    elif args.command == "daemon":
        wgit.daemon(interval=args.interval)
        sys.exit(0)

    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
