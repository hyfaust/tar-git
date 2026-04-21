#!/usr/bin/env python3
"""
Word 文档差异对比工具

使用 pandoc 将 .docx 文件转换为 Markdown，然后用 diff 对比差异。

用法:
    python word_diff.py file1.docx file2.docx
    python word_diff.py --help
"""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def check_file_exists(filepath: str) -> bool:
    """检查文件是否存在"""
    if not os.path.isfile(filepath):
        print(f"错误：文件不存在：{filepath}", file=sys.stderr)
        return False
    return True


def check_command_available(cmd: str) -> bool:
    """检查命令是否可用"""
    try:
        # 先尝试 --version，如果失败则尝试直接运行看是否能找到命令
        result = subprocess.run(
            [cmd, "--version"],
            capture_output=True,
            timeout=5
        )
        # 某些 diff（如 vim 版）不支持 --version 但命令存在
        if result.returncode == 0:
            return True
        # 尝试用 where/which 检查命令是否存在
        check_cmd = ["where", cmd] if os.name == 'nt' else ["which", cmd]
        result = subprocess.run(
            check_cmd,
            capture_output=True,
            timeout=5
        )
        # 解码 stdout 为字符串
        stdout_text = result.stdout.decode('utf-8', errors='replace').strip()
        if result.returncode == 0 and stdout_text:
            return True
        print(f"错误：未找到命令 '{cmd}'，请确保已安装并添加到 PATH", file=sys.stderr)
        return False
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        # 尝试用 where/which 检查命令是否存在
        try:
            check_cmd = ["where", cmd] if os.name == 'nt' else ["which", cmd]
            result = subprocess.run(
                check_cmd,
                capture_output=True,
                timeout=5
            )
            stdout_text = result.stdout.decode('utf-8', errors='replace').strip()
            if result.returncode == 0 and stdout_text:
                return True
        except:
            pass
        print(f"错误：未找到命令 '{cmd}'，请确保已安装并添加到 PATH", file=sys.stderr)
        return False


def convert_to_markdown(docx_path: str, output_path: str) -> bool:
    """使用 pandoc 将 docx 转换为 markdown"""
    # pandoc 3.x 中 --atx-headers 已移除，ATX 标题现在是默认行为
    # 使用 --from=docx 明确指定输入格式，支持非.docx 扩展名的文件
    # 使用 shell=True 让系统处理编码，与 CMD 版本一致
    cmd = f'pandoc --from=docx --to=markdown --wrap=none --output="{output_path}" "{docx_path}"'
    
    try:
        # 在 Windows 下，使用 shell=True 让系统处理编码
        result = subprocess.run(
            cmd,
            shell=True,
            timeout=60
        )
        
        if result.returncode != 0:
            print(f"错误：pandoc 转换失败：{docx_path}", file=sys.stderr)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            return False
        return True
        
    except subprocess.TimeoutExpired:
        print(f"错误：pandoc 转换超时：{docx_path}", file=sys.stderr)
        return False
    except FileNotFoundError:
        print("错误：未找到 pandoc 命令", file=sys.stderr)
        return False


def run_diff(file1: str, file2: str) -> int:
    """运行 diff 命令，返回 diff 的退出码

    使用 ANSI 转义码为 diff 输出添加颜色：
    - 红色：删除的行（< 开头）
    - 绿色：新增的行（> 开头）
    - 黄色：变化标记行（包含 ---）
    """
    # Windows 下的 diff 可能不支持 --color 选项
    # 使用 shell=True 并设置 chcp 65001 以支持 UTF-8 输出
    # 使用完整路径确保能找到 diff 命令
    diff_cmd = "diff"
    cmd = f'chcp 65001 >nul && {diff_cmd} "{file1}" "{file2}"'

    # ANSI 颜色代码
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    RESET = '\033[0m'

    try:
        # 启用 Windows 终端的 ANSI 颜色支持
        if os.name == 'nt':
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)

        # 捕获 diff 输出
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            shell=True,
            encoding='utf-8',
            errors='replace'
        )
        
        # 处理输出，添加颜色
        output = result.stdout
        if output:
            colored_lines = []
            for line in output.splitlines():
                if line.startswith('<'):
                    colored_lines.append(f'{RED}{line}{RESET}')
                elif line.startswith('>'):
                    colored_lines.append(f'{GREEN}{line}{RESET}')
                elif '---' in line and line.strip().startswith('---'):
                    colored_lines.append(f'{YELLOW}{line}{RESET}')
                else:
                    colored_lines.append(line)
            
            # 打印彩色输出
            for line in colored_lines:
                print(line)
        
        # 打印错误输出（如果有）
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        
        # diff 返回码：0=无差异，1=有差异，2=错误
        return result.returncode
        
    except subprocess.TimeoutExpired:
        print("错误：diff 命令超时", file=sys.stderr)
        return 2
    except FileNotFoundError:
        print("错误：未找到 diff 命令", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"错误：diff 执行失败：{e}", file=sys.stderr)
        return 2


def main() -> int:
    parser = argparse.ArgumentParser(
        description="对比两个 Word (.docx) 文件的文本内容差异",
        epilog="""
示例:
    python word_diff.py document1.docx document2.docx
    python word_diff.py "path/with spaces/file1.docx" "file2.docx"

输出说明:
    - 无输出：两个文件内容相同
    - 显示差异：以 diff 格式显示不同之处（带颜色高亮）
    - 红色：删除的行；绿色：新增的行
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "file1",
        help="第一个 Word 文件路径"
    )
    parser.add_argument(
        "file2",
        help="第二个 Word 文件路径"
    )
    
    args = parser.parse_args()

    # 检查前置命令
    if not check_command_available("pandoc"):
        return 1
    if not check_command_available("diff"):
        return 1
    
    # 检查输入文件
    if not check_file_exists(args.file1) or not check_file_exists(args.file2):
        return 1
    
    # 创建临时文件
    temp1_path = None
    temp2_path = None
    
    try:
        # 创建临时文件（Windows 下需要显式管理）
        fd1, temp1_path = tempfile.mkstemp(suffix=".md", prefix="wdiff_")
        os.close(fd1)
        
        fd2, temp2_path = tempfile.mkstemp(suffix=".md", prefix="wdiff_")
        os.close(fd2)
        
        # 转换为 Markdown
        if not convert_to_markdown(args.file1, temp1_path):
            return 1
        if not convert_to_markdown(args.file2, temp2_path):
            return 1
        
        # 运行 diff
        diff_result = run_diff(temp1_path, temp2_path)
        
        # 返回 diff 的结果（0=相同，1=不同）
        return diff_result
        
    except Exception as e:
        print(f"错误：发生意外异常：{e}", file=sys.stderr)
        return 1
        
    finally:
        # 清理临时文件
        for temp_path in [temp1_path, temp2_path]:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError as e:
                    print(f"警告：无法删除临时文件 {temp_path}: {e}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
