# -*- coding: utf-8 -*-
"""桌面动作：打开 App、点击、键入、剪贴板。"""

from __future__ import annotations

import subprocess
import time
from typing import Any

from macrun import ax


def open_app(name: str) -> str:
    """用 open -a 打开应用（支持中文名如「微信」「备忘录」）。"""
    name = name.strip()
    if not name:
        raise ValueError("open_app: empty name")
    # 常见别名
    aliases = {
        "wechat": "WeChat",
        "微信": "WeChat",
        "notes": "Notes",
        "备忘录": "Notes",
        "textedit": "TextEdit",
        "文本编辑": "TextEdit",
        "safari": "Safari",
        "finder": "Finder",
        "访达": "Finder",
        "terminal": "Terminal",
        "终端": "Terminal",
    }
    app = aliases.get(name.lower(), aliases.get(name, name))
    r = subprocess.run(
        ["open", "-a", app],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        # 再试原始名
        r2 = subprocess.run(["open", "-a", name], capture_output=True, text=True)
        if r2.returncode != 0:
            raise RuntimeError(
                f"open_app failed: {r.stderr or r2.stderr or r.stdout or 'unknown'}"
            )
        app = name
    time.sleep(0.8)
    return f"opened {app}"


def set_clipboard(text: str) -> str:
    p = subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=False)
    if p.returncode != 0:
        raise RuntimeError("pbcopy failed")
    return f"clipboard set ({len(text)} chars)"


def paste_clipboard() -> str:
    ax.hotkey("cmd", "v")
    return "pasted clipboard (cmd+v)"


def clipboard_type(text: str) -> str:
    """中文/复杂文本：写入剪贴板并粘贴。"""
    set_clipboard(text)
    time.sleep(0.1)
    paste_clipboard()
    return f"clipboard_typed ({len(text)} chars)"


def type_text(text: str, prefer_clipboard: bool = True) -> str:
    if not text:
        return "empty type"
    # 含非 ascii 或 prefer → 剪贴板
    if prefer_clipboard or any(ord(c) > 127 for c in text):
        return clipboard_type(text)
    ax.type_text_ascii(text)
    return f"typed ascii ({len(text)} chars)"


def hotkey(*keys: str) -> str:
    ax.hotkey(*keys)
    return f"hotkey {'+'.join(keys)}"


def click_node(node: dict[str, Any], pid: int | None = None) -> str:
    """优先 AXPress，失败则坐标点击。"""
    nid = node.get("id")
    if pid is not None and nid is not None:
        try:
            if ax.press_element_by_id(int(pid), int(nid)):
                return f"ax_press id={nid}"
        except Exception:
            pass
    center = node.get("center")
    if center:
        ax.click_xy(float(center[0]), float(center[1]))
        return f"click_xy ({center[0]:.0f},{center[1]:.0f}) id={nid}"
    raise RuntimeError(f"cannot click node id={nid}: no center/press")


def click_xy(x: float, y: float) -> str:
    ax.click_xy(x, y)
    return f"click_xy ({x:.0f},{y:.0f})"


def activate_app_by_name(name: str) -> None:
    """用 AppleScript 前置应用。"""
    script = f'tell application "{name}" to activate'
    subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
