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


def _app_is_front(app_name: str | None) -> bool:
    if not app_name:
        return False
    app = resolve_app_name(app_name)
    try:
        front = ax.frontmost_app_info()
    except Exception:
        return False
    blob = f"{front.get('name', '')} {front.get('bundle_id', '')}".lower()
    app_l = app.lower()
    if app_l in blob or app_l.replace(" ", "") in blob:
        return True
    # 微信中英文名
    if app_l == "wechat":
        return any(m in blob for m in ("wechat", "微信", "tencent.xinwechat"))
    return False


def ensure_front(
    app_name: str | None,
    settle: float = 0.08,
    *,
    retries: int = 1,
    hard: bool = False,
) -> bool:
    """动作前尝试前置目标 App。返回是否确认已成为 frontmost。

    默认轻量（1 次 activate、短 settle）。宿主抢焦点时往往永远 front 不了，
    热路径应依赖 PostToPid 发键，而不是在这里空转重试。
    hard=True 时才走 System Events / open -a（仅失败恢复用）。
    """
    if not app_name:
        return False
    app = resolve_app_name(app_name)
    if _app_is_front(app):
        if settle > 0:
            time.sleep(settle)
        return True
    for attempt in range(max(1, retries)):
        try:
            ax.activate_app(name=app, hard=hard and attempt == 0)
        except Exception:
            activate_app_by_name(app)
        if _app_is_front(app):
            if settle > 0:
                time.sleep(settle)
            return True
        if hard and attempt >= 0:
            subprocess.run(
                ["open", "-a", app],
                capture_output=True,
                text=True,
            )
            time.sleep(0.15)
        else:
            time.sleep(0.04)
    if settle > 0:
        time.sleep(min(settle, 0.06))
    return _app_is_front(app)


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
        ensure_front(app_name, settle=0.06)
    set_clipboard(text)
    time.sleep(0.05)
    pid = _resolve_pid(app_name)
    # 单通道 PostToPid（有 pid 时），避免 Cmd+V 双发导致正文重复
    ax.press_key("cmd", "v", pid=pid)
    time.sleep(0.04)
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
        ensure_front(app_name, settle=0.06)
    ax.type_text_ascii(text)
    return f"typed ascii ({len(text)} chars)"


def hotkey(
    *keys: str,
    app_name: str | None = None,
    ensure: bool = True,
    settle: float = 0.03,
    use_pid: bool = True,
) -> str:
    """发送组合键。默认 PostToPid+HID（快，不依赖 frontmost）。

    use_pid=False 时退回 ax.hotkey（Return 含 System Events，适合个别兼容场景）。
    聊天发送请用 send_chat，勿对输入框 Return 走 ax.hotkey 双发。
    """
    if ensure:
        ensure_front(app_name, settle=0.05)
    if settle > 0:
        time.sleep(settle)
    pid = _resolve_pid(app_name) if use_pid else None
    if use_pid:
        ax.press_key(*keys, pid=pid)
    else:
        ax.hotkey(*keys)
    return f"hotkey {'+'.join(keys)}"


def _resolve_pid(app_name: str | None) -> int | None:
    if not app_name:
        return None
    try:
        info = ax.find_app(name=resolve_app_name(app_name))
        if info and info.get("pid"):
            return int(info["pid"])
    except Exception:
        return None
    return None


def _press_return_once(*, cmd: bool = False, pid: int | None = None) -> None:
    """单次 Return / Cmd+Return（仅进程内 CGEvent，不调 osascript）。"""
    keys = ("cmd", "return") if cmd else ("return",)
    ax.press_key(*keys, pid=pid)
    time.sleep(0.03)


def send_chat(
    app_name: str | None = None,
    mode: str = "enter",
    ensure: bool = True,
) -> str:
    """发送聊天消息。

    mode:
      - enter / return: 仅 Return（本机微信「Enter 发送」推荐）
      - cmd_enter: 仅 Cmd+Return
      - both: 先 Cmd+Return 再 Return（兼容未知设置；Enter 发送时会多插换行，不推荐）
    """
    mode = (mode or "enter").lower().strip()
    if mode in ("cmd+enter",):
        mode = "cmd_enter"
    if mode == "return":
        mode = "enter"
    pid = _resolve_pid(app_name)
    front_ok = True
    if ensure:
        front_ok = ensure_front(app_name, settle=0.05, retries=1, hard=False)
    time.sleep(0.02)
    if mode in ("both", "cmd_enter"):
        _press_return_once(cmd=True, pid=pid)
        time.sleep(0.05)
    if mode in ("both", "enter"):
        _press_return_once(cmd=False, pid=pid)
        time.sleep(0.04)
    return f"send_chat: mode={mode} front_ok={front_ok} pid={pid}"


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
