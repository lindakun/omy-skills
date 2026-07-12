# -*- coding: utf-8 -*-
"""桌面动作：打开 App、点击、键入、剪贴板。"""

from __future__ import annotations

import subprocess
import time
from typing import Any

from macrun import ax


APP_ALIASES = {
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


def resolve_app_name(name: str) -> str:
    name = name.strip()
    return APP_ALIASES.get(name.lower(), APP_ALIASES.get(name, name))


def open_app(name: str) -> str:
    """用 open -a 打开并强制激活应用（避免 WorkBuddy 等宿主抢焦点）。"""
    name = name.strip()
    if not name:
        raise ValueError("open_app: empty name")
    app = resolve_app_name(name)
    r = subprocess.run(
        ["open", "-a", app],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        r2 = subprocess.run(["open", "-a", name], capture_output=True, text=True)
        if r2.returncode != 0:
            raise RuntimeError(
                f"open_app failed: {r.stderr or r2.stderr or r.stdout or 'unknown'}"
            )
        app = name
    time.sleep(0.9)
    # 强制前置：open 后宿主进程常仍是 frontmost，导致 AX 只看到 WorkBuddy
    info = None
    try:
        info = ax.activate_app(name=app)
    except Exception:
        try:
            activate_app_by_name(app)
            time.sleep(0.4)
            info = ax.find_app(name=app)
        except Exception:
            info = ax.find_app(name=app)
    if info:
        return (
            f"opened+activated {info.get('name') or app} "
            f"pid={info.get('pid')} bundle={info.get('bundle_id')}"
        )
    return f"opened {app} (activate pending; app may still be launching)"


def set_clipboard(text: str) -> str:
    p = subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=False)
    if p.returncode != 0:
        raise RuntimeError("pbcopy failed")
    return f"clipboard set ({len(text)} chars)"


def ensure_front(app_name: str | None, settle: float = 0.15) -> bool:
    """动作前强制前置目标 App。返回是否调用了 activate。"""
    if not app_name:
        return False
    app = resolve_app_name(app_name)
    try:
        ax.activate_app(name=app)
    except Exception:
        activate_app_by_name(app)
    if settle > 0:
        time.sleep(settle)
    return True


def paste_clipboard() -> str:
    ax.hotkey("cmd", "v")
    return "pasted clipboard (cmd+v)"


def clipboard_type(
    text: str,
    app_name: str | None = None,
    ensure: bool = True,
) -> str:
    """中文/复杂文本：写入剪贴板并粘贴。"""
    if ensure:
        ensure_front(app_name, settle=0.12)
    set_clipboard(text)
    time.sleep(0.08)
    paste_clipboard()
    time.sleep(0.05)
    return f"clipboard_typed ({len(text)} chars)"


def type_text(
    text: str,
    prefer_clipboard: bool = True,
    app_name: str | None = None,
    ensure: bool = True,
) -> str:
    if not text:
        return "empty type"
    if prefer_clipboard or any(ord(c) > 127 for c in text):
        return clipboard_type(text, app_name=app_name, ensure=ensure)
    if ensure:
        ensure_front(app_name, settle=0.12)
    ax.type_text_ascii(text)
    return f"typed ascii ({len(text)} chars)"


def hotkey(
    *keys: str,
    app_name: str | None = None,
    ensure: bool = True,
    settle: float = 0.05,
) -> str:
    if ensure:
        ensure_front(app_name, settle=0.12)
    if settle > 0:
        time.sleep(settle)
    ax.hotkey(*keys)
    return f"hotkey {'+'.join(keys)}"


def send_chat(
    app_name: str | None = None,
    mode: str = "both",
    ensure: bool = True,
) -> str:
    """发送聊天消息。

    mode:
      - both: 先 Cmd+Return 再 Return（默认，兼容两种微信设置）
      - enter / return: 仅 Return
      - cmd_enter: 仅 Cmd+Return
    """
    mode = (mode or "both").lower().strip()
    if mode in ("cmd+enter",):
        mode = "cmd_enter"
    if mode == "return":
        mode = "enter"
    if ensure:
        ensure_front(app_name, settle=0.12)
    time.sleep(0.08)
    if mode in ("both", "cmd_enter"):
        ax.hotkey("cmd", "return")
        time.sleep(0.10)
    if mode in ("both", "enter"):
        ax.hotkey("return")
        time.sleep(0.06)
    return f"send_chat: mode={mode}"


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
