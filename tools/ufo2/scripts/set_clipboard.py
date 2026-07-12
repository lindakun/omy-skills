#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将命令行参数写入 Windows 系统剪贴板。

供 pc-assistant / UFO² 微信等场景使用：无法 set_edit_text 时，
先运行本脚本写剪贴板，再 keyboard_input 发送 Ctrl+V。

依赖：pywin32（requirements.txt 在 win32 下已声明）

用法：
  python set_clipboard.py 要写入的文本
"""

from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python set_clipboard.py <text>", file=sys.stderr)
        return 2

    text = " ".join(sys.argv[1:])
    if text == "":
        print("Error: empty clipboard text", file=sys.stderr)
        return 2

    try:
        import win32clipboard  # type: ignore
        import win32con  # type: ignore
    except ImportError:
        print(
            "Error: pywin32 is required (pip install pywin32). Windows only.",
            file=sys.stderr,
        )
        return 1

    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
    finally:
        # 必须关闭，否则其他进程无法访问剪贴板
        win32clipboard.CloseClipboard()

    print(f"OK: clipboard set ({len(text)} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
