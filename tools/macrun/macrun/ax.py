# -*- coding: utf-8 -*-
"""macOS Accessibility 树读取与元素查找。"""

from __future__ import annotations

import platform
import sys
from typing import Any

_AX_OK = False
_ERR: str | None = None

try:
    if platform.system() == "Darwin":
        from AppKit import NSWorkspace  # type: ignore
        from ApplicationServices import (  # type: ignore
            AXIsProcessTrusted,
            AXUIElementCopyAttributeValue,
            AXUIElementCreateApplication,
            AXUIElementCreateSystemWide,
            AXUIElementPerformAction,
            AXUIElementSetAttributeValue,
            AXValueGetType,
            AXValueGetValue,
            kAXChildrenAttribute,
            kAXDescriptionAttribute,
            kAXErrorSuccess,
            kAXFocusedUIElementAttribute,
            kAXIdentifierAttribute,
            kAXPositionAttribute,
            kAXPressAction,
            kAXRoleAttribute,
            kAXSizeAttribute,
            kAXTitleAttribute,
            kAXValueAttribute,
            kAXWindowsAttribute,
        )
        from Quartz import (  # type: ignore
            CGEventCreateKeyboardEvent,
            CGEventCreateMouseEvent,
            CGEventPost,
            CGEventSetFlags,
            CGEventKeyboardSetUnicodeString,
            CGPoint,
            kCGEventFlagMaskCommand,
            kCGEventFlagMaskControl,
            kCGEventFlagMaskAlternate,
            kCGEventFlagMaskShift,
            kCGEventKeyDown,
            kCGEventKeyUp,
            kCGEventLeftMouseDown,
            kCGEventLeftMouseUp,
            kCGHIDEventTap,
            kCGMouseButtonLeft,
        )

        # CGEventPostToPid：把键鼠事件直接投递给目标进程，不依赖 frontmost。
        # WorkBuddy 等宿主抢焦点时，HID 全局键常打到宿主；PostToPid 可绕过。
        try:
            from Quartz import CGEventPostToPid  # type: ignore
        except Exception:  # pragma: no cover
            CGEventPostToPid = None  # type: ignore

        _AX_OK = True
    else:
        _ERR = f"macrun 仅支持 macOS，当前: {platform.system()}"
except Exception as e:  # pragma: no cover
    _ERR = f"导入 Accessibility/AppKit 失败: {e}"


def require_darwin() -> None:
    if platform.system() != "Darwin":
        raise RuntimeError(_ERR or "macrun 仅支持 macOS")


def is_trusted() -> bool:
    if not _AX_OK:
        return False
    try:
        return bool(AXIsProcessTrusted())
    except Exception:
        return False


def frontmost_app_info() -> dict[str, Any]:
    require_darwin()
    if not _AX_OK:
        raise RuntimeError(_ERR)
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    if app is None:
        return {}
    return {
        "name": str(app.localizedName() or ""),
        "bundle_id": str(app.bundleIdentifier() or ""),
        "pid": int(app.processIdentifier()),
    }


# 宿主 IDE / Agent 名：观察时应避免误当成目标桌面 App
HOST_APP_MARKERS = (
    "workbuddy",
    "cursor",
    "code",
    "visual studio code",
    "terminal",
    "iterm",
    "warp",
    "claude",
    "electron",  # 部分壳
)


def list_running_apps() -> list[dict[str, Any]]:
    """列出前台可激活的运行中 App。"""
    require_darwin()
    if not _AX_OK:
        raise RuntimeError(_ERR)
    out: list[dict[str, Any]] = []
    for app in NSWorkspace.sharedWorkspace().runningApplications():
        try:
            if app.isTerminated():
                continue
            # 0 = regular, 1 = accessory, 2 = prohibited
            pol = int(app.activationPolicy()) if hasattr(app, "activationPolicy") else 0
            if pol != 0:
                continue
            name = str(app.localizedName() or "")
            bid = str(app.bundleIdentifier() or "")
            if not name and not bid:
                continue
            out.append(
                {
                    "name": name,
                    "bundle_id": bid,
                    "pid": int(app.processIdentifier()),
                    "active": bool(app.isActive()),
                }
            )
        except Exception:
            continue
    return out


def find_app(
    name: str | None = None,
    bundle_id: str | None = None,
) -> dict[str, Any] | None:
    """按名称/bundle 模糊查找运行中 App。"""
    name_l = (name or "").lower().strip()
    bid_l = (bundle_id or "").lower().strip()
    # 别名
    aliases = {
        "wechat": ["wechat", "微信", "com.tencent.xinwechat"],
        "微信": ["wechat", "微信", "com.tencent.xinwechat"],
        "notes": ["notes", "备忘录", "com.apple.notes"],
        "备忘录": ["notes", "备忘录", "com.apple.notes"],
        "textedit": ["textedit", "文本编辑", "com.apple.textedit"],
    }
    keys = aliases.get(name_l, [name_l] if name_l else [])
    if bid_l:
        keys.append(bid_l)

    apps = list_running_apps()
    for app in apps:
        blob = f"{app.get('name','')} {app.get('bundle_id','')}".lower()
        for k in keys:
            if k and k in blob:
                return app
        if name_l and name_l in blob:
            return app
    return None


def activate_app(
    pid: int | None = None,
    name: str | None = None,
    *,
    hard: bool = False,
) -> dict[str, Any]:
    """前置指定 App。

    hard=False（默认）：只做 NSRunningApplication.activate，约 50ms，适合热路径。
    hard=True：额外 System Events set frontmost（osascript，慢，仅冷启动/发送失败重试用）。
    """
    require_darwin()
    if not _AX_OK:
        raise RuntimeError(_ERR)

    target = None
    if pid is not None:
        for app in NSWorkspace.sharedWorkspace().runningApplications():
            if int(app.processIdentifier()) == int(pid):
                target = app
                break
    if target is None and name:
        info = find_app(name=name)
        if info:
            for app in NSWorkspace.sharedWorkspace().runningApplications():
                if int(app.processIdentifier()) == int(info["pid"]):
                    target = app
                    break
    if target is None:
        raise RuntimeError(f"activate_app: not found pid={pid} name={name}")

    import time

    try:
        target.unhide()
    except Exception:
        pass
    # 1=AllWindows, 2=IgnoringOtherApps → 3
    ok = target.activateWithOptions_(3)
    time.sleep(0.05 if not hard else 0.08)

    if hard:
        front_ok = False
        try:
            front = frontmost_app_info()
            front_ok = int(front.get("pid") or 0) == int(target.processIdentifier())
        except Exception:
            front_ok = False
        if not front_ok:
            try:
                import subprocess

                bid = str(target.bundleIdentifier() or "")
                if bid:
                    subprocess.run(
                        [
                            "osascript",
                            "-e",
                            "tell application \"System Events\" to set frontmost of "
                            f"first process whose bundle identifier is \"{bid}\" to true",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    time.sleep(0.08)
            except Exception:
                pass

    return {
        "name": str(target.localizedName() or ""),
        "bundle_id": str(target.bundleIdentifier() or ""),
        "pid": int(target.processIdentifier()),
        "activated": bool(ok),
    }


def is_host_app(info: dict[str, Any] | None) -> bool:
    if not info:
        return False
    blob = f"{info.get('name','')} {info.get('bundle_id','')}".lower()
    return any(m in blob for m in HOST_APP_MARKERS)


def _copy_attr(element, attr) -> Any:
    err, value = AXUIElementCopyAttributeValue(element, attr, None)
    if err != kAXErrorSuccess:
        return None
    return value


def _ax_point(value) -> tuple[float, float] | None:
    if value is None:
        return None
    try:
        # AXValue CGPoint
        import ctypes

        class CGPointStruct(ctypes.Structure):
            _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

        pt = CGPointStruct()
        # Prefer high-level if available
        try:
            from ApplicationServices import kAXValueCGPointType  # type: ignore

            if AXValueGetType(value) == kAXValueCGPointType:
                ok = AXValueGetValue(value, kAXValueCGPointType, ctypes.byref(pt))
                if ok:
                    return float(pt.x), float(pt.y)
        except Exception:
            pass
        # Fallback: string parse
        s = str(value)
        if "x:" in s and "y:" in s:
            # e.g. x:12.000000 y:34.000000
            parts = s.replace(",", " ").split()
            xs = [p for p in parts if p.startswith("x:")]
            ys = [p for p in parts if p.startswith("y:")]
            if xs and ys:
                return float(xs[0].split(":")[1]), float(ys[0].split(":")[1])
    except Exception:
        return None
    return None


def _ax_size(value) -> tuple[float, float] | None:
    if value is None:
        return None
    try:
        import ctypes

        class CGSizeStruct(ctypes.Structure):
            _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]

        sz = CGSizeStruct()
        try:
            from ApplicationServices import kAXValueCGSizeType  # type: ignore

            if AXValueGetType(value) == kAXValueCGSizeType:
                ok = AXValueGetValue(value, kAXValueCGSizeType, ctypes.byref(sz))
                if ok:
                    return float(sz.width), float(sz.height)
        except Exception:
            pass
        s = str(value)
        if "w:" in s and "h:" in s:
            parts = s.replace(",", " ").split()
            ws = [p for p in parts if p.startswith("w:")]
            hs = [p for p in parts if p.startswith("h:")]
            if ws and hs:
                return float(ws[0].split(":")[1]), float(hs[0].split(":")[1])
    except Exception:
        return None
    return None


def _node_label(element) -> dict[str, Any]:
    role = _copy_attr(element, kAXRoleAttribute)
    title = _copy_attr(element, kAXTitleAttribute)
    value = _copy_attr(element, kAXValueAttribute)
    desc = _copy_attr(element, kAXDescriptionAttribute)
    ident = _copy_attr(element, kAXIdentifierAttribute)
    pos = _ax_point(_copy_attr(element, kAXPositionAttribute))
    size = _ax_size(_copy_attr(element, kAXSizeAttribute))
    center = None
    if pos and size:
        center = (pos[0] + size[0] / 2.0, pos[1] + size[1] / 2.0)
    return {
        "role": str(role) if role is not None else "",
        "title": str(title) if title is not None else "",
        "value": str(value)[:120] if value is not None else "",
        "description": str(desc) if desc is not None else "",
        "identifier": str(ident) if ident is not None else "",
        "position": pos,
        "size": size,
        "center": center,
    }


def dump_tree(
    pid: int | None = None,
    max_nodes: int = 80,
    max_depth: int = 6,
) -> list[dict[str, Any]]:
    """扁平化可操作节点列表（带 id）。"""
    require_darwin()
    if not _AX_OK:
        raise RuntimeError(_ERR)
    if not is_trusted():
        raise PermissionError(
            "进程未获「辅助功能」权限。请到 系统设置 → 隐私与安全性 → 辅助功能 中授权当前终端/Agent 宿主。"
        )

    if pid is None:
        info = frontmost_app_info()
        pid = info.get("pid")
        if not pid:
            return []

    app_el = AXUIElementCreateApplication(pid)
    nodes: list[dict[str, Any]] = []
    counter = {"n": 0}

    def walk(el, depth: int) -> None:
        if depth > max_depth or counter["n"] >= max_nodes:
            return
        meta = _node_label(el)
        # 过滤无意义节点
        if meta["role"] or meta["title"] or meta["value"] or meta["description"]:
            item = {"id": counter["n"], **meta}
            nodes.append(item)
            counter["n"] += 1
        children = _copy_attr(el, kAXChildrenAttribute) or []
        try:
            for child in children:
                if counter["n"] >= max_nodes:
                    break
                walk(child, depth + 1)
        except TypeError:
            pass

    # 优先窗口
    windows = _copy_attr(app_el, kAXWindowsAttribute) or []
    if windows:
        for w in windows:
            walk(w, 0)
    else:
        walk(app_el, 0)
    return nodes


def tree_to_text(nodes: list[dict[str, Any]], app_info: dict[str, Any] | None = None) -> str:
    lines = []
    if app_info:
        lines.append(
            f"Frontmost app: {app_info.get('name')} ({app_info.get('bundle_id')}) pid={app_info.get('pid')}"
        )
    lines.append(f"AX nodes ({len(nodes)}):")
    for n in nodes:
        bits = [f"id={n['id']}", f"role={n.get('role')}"]
        if n.get("title"):
            bits.append(f"title={n['title']!r}")
        if n.get("value"):
            bits.append(f"value={n['value']!r}")
        if n.get("description"):
            bits.append(f"desc={n['description']!r}")
        if n.get("center"):
            bits.append(f"center=({n['center'][0]:.0f},{n['center'][1]:.0f})")
        lines.append("  " + " ".join(bits))
    return "\n".join(lines)


def find_node(
    nodes: list[dict[str, Any]],
    *,
    name: str | None = None,
    role: str | None = None,
    node_id: int | None = None,
) -> dict[str, Any] | None:
    if node_id is not None:
        for n in nodes:
            if n.get("id") == node_id:
                return n
        return None
    name_l = (name or "").lower().strip()
    role_l = (role or "").lower().strip()
    for n in nodes:
        if role_l and role_l not in str(n.get("role", "")).lower():
            continue
        blob = " ".join(
            [
                str(n.get("title") or ""),
                str(n.get("value") or ""),
                str(n.get("description") or ""),
                str(n.get("identifier") or ""),
            ]
        ).lower()
        if name_l and name_l not in blob:
            continue
        return n
    return None


def press_element_by_id(pid: int, node_id: int, max_nodes: int = 80, max_depth: int = 6) -> bool:
    """尝试对匹配 id 的元素执行 AXPress（通过重新遍历定位 element）。"""
    require_darwin()
    if not is_trusted():
        raise PermissionError("需要辅助功能权限")

    app_el = AXUIElementCreateApplication(pid)
    counter = {"n": 0}
    target = {"el": None}

    def walk(el, depth: int) -> None:
        if depth > max_depth or counter["n"] > max_nodes:
            return
        meta = _node_label(el)
        if meta["role"] or meta["title"] or meta["value"] or meta["description"]:
            if counter["n"] == node_id:
                target["el"] = el
                return
            counter["n"] += 1
        if target["el"] is not None:
            return
        children = _copy_attr(el, kAXChildrenAttribute) or []
        try:
            for child in children:
                walk(child, depth + 1)
                if target["el"] is not None:
                    return
        except TypeError:
            pass

    windows = _copy_attr(app_el, kAXWindowsAttribute) or []
    if windows:
        for w in windows:
            walk(w, 0)
            if target["el"] is not None:
                break
    else:
        walk(app_el, 0)

    el = target["el"]
    if el is None:
        return False
    err = AXUIElementPerformAction(el, kAXPressAction)
    return err == kAXErrorSuccess


def click_xy(x: float, y: float) -> None:
    require_darwin()
    if not _AX_OK:
        raise RuntimeError(_ERR)
    point = CGPoint(x, y)
    down = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, point, kCGMouseButtonLeft)
    up = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, point, kCGMouseButtonLeft)
    CGEventPost(kCGHIDEventTap, down)
    CGEventPost(kCGHIDEventTap, up)


# 常用虚拟键码（美式键盘布局）
_KEYCODES = {
    "a": 0x00,
    "s": 0x01,
    "d": 0x02,
    "f": 0x03,
    "h": 0x04,
    "g": 0x05,
    "z": 0x06,
    "x": 0x07,
    "c": 0x08,
    "v": 0x09,
    "b": 0x0B,
    "q": 0x0C,
    "w": 0x0D,
    "e": 0x0E,
    "r": 0x0F,
    "y": 0x10,
    "t": 0x11,
    "1": 0x12,
    "2": 0x13,
    "3": 0x14,
    "4": 0x15,
    "6": 0x16,
    "5": 0x17,
    "9": 0x19,
    "7": 0x1A,
    "8": 0x1C,
    "0": 0x1D,
    "o": 0x1F,
    "u": 0x20,
    "i": 0x22,
    "p": 0x23,
    "l": 0x25,
    "j": 0x26,
    "k": 0x28,
    "n": 0x2D,
    "m": 0x2E,
    "return": 0x24,
    "enter": 0x24,
    "tab": 0x30,
    "space": 0x31,
    "delete": 0x33,
    "escape": 0x35,
    "esc": 0x35,
    "command": 0x37,
    "cmd": 0x37,
    "shift": 0x38,
    "option": 0x3A,
    "alt": 0x3A,
    "control": 0x3B,
    "ctrl": 0x3B,
    "right": 0x7C,
    "left": 0x7B,
    "down": 0x7D,
    "up": 0x7E,
    "f": 0x03,  # already
}


def _keycode_and_flags(keys: list[str]) -> tuple[int | None, int, str | None]:
    """解析组合键 → (keycode, flags, main_key)。"""
    keys_l = [k.lower().strip() for k in keys if k]
    if not keys_l:
        return None, 0, None
    flags = 0
    main = None
    for k in keys_l:
        if k in ("cmd", "command", "meta"):
            flags |= kCGEventFlagMaskCommand
        elif k in ("shift",):
            flags |= kCGEventFlagMaskShift
        elif k in ("alt", "option"):
            flags |= kCGEventFlagMaskAlternate
        elif k in ("ctrl", "control"):
            flags |= kCGEventFlagMaskControl
        else:
            main = k
    if main is None:
        main = keys_l[-1]
    code = _KEYCODES.get(main)
    if code is None and len(main) == 1:
        code = _KEYCODES.get(main.lower())
    return code, flags, main


def post_key_to_pid(pid: int, *keys: str) -> bool:
    """向指定 PID 投递按键（不依赖 frontmost）。失败返回 False。"""
    import time

    require_darwin()
    if not _AX_OK or CGEventPostToPid is None:
        return False
    code, flags, main = _keycode_and_flags([k for k in keys if k])
    if code is None or main is None:
        return False
    try:
        down = CGEventCreateKeyboardEvent(None, code, True)
        up = CGEventCreateKeyboardEvent(None, code, False)
        CGEventSetFlags(down, flags)
        CGEventSetFlags(up, flags)
        CGEventPostToPid(int(pid), down)
        time.sleep(0.03)
        CGEventPostToPid(int(pid), up)
        return True
    except Exception:
        return False


def press_key(*keys: str, pid: int | None = None, also_hid: bool | None = None) -> None:
    """进程内按键。

    默认策略（避免双发）：
    - 有 pid 且 PostToPid 可用 → 只投递给目标进程（宿主抢焦点时仍能进微信）
    - 否则 → 只走 HID 全局
    also_hid=True 可强制双通道（不推荐，Cmd+V/Return 可能执行两次）。
    """
    import time

    require_darwin()
    if not _AX_OK:
        raise RuntimeError(_ERR)
    code, flags, main = _keycode_and_flags([k for k in keys if k])
    if main is None:
        return
    if code is None:
        _type_unicode(main)
        return

    use_pid = pid is not None and CGEventPostToPid is not None
    # 默认单通道：有 pid 用 PostToPid，否则 HID。显式 also_hid=True 才双发。
    if also_hid is None:
        also_hid = not use_pid

    if use_pid:
        try:
            down = CGEventCreateKeyboardEvent(None, code, True)
            up = CGEventCreateKeyboardEvent(None, code, False)
            CGEventSetFlags(down, flags)
            CGEventSetFlags(up, flags)
            CGEventPostToPid(int(pid), down)
            time.sleep(0.02)
            CGEventPostToPid(int(pid), up)
        except Exception:
            # PostToPid 失败则回退 HID
            also_hid = True

    if also_hid:
        down2 = CGEventCreateKeyboardEvent(None, code, True)
        up2 = CGEventCreateKeyboardEvent(None, code, False)
        CGEventSetFlags(down2, flags)
        CGEventSetFlags(up2, flags)
        CGEventPost(kCGHIDEventTap, down2)
        time.sleep(0.025)
        CGEventPost(kCGHIDEventTap, up2)


def hotkey(*keys: str) -> None:
    """组合键，如 hotkey('cmd', 'v') / hotkey('return')。

    常规路径用 HID CGEvent。Return/Enter 额外走 System Events 双保险
    （搜索选人等场景）；聊天发送请用 act.send_chat / press_key，避免双发。
    """
    import time

    require_darwin()
    if not _AX_OK:
        raise RuntimeError(_ERR)
    code, flags, main = _keycode_and_flags([k for k in keys if k])
    if main is None:
        return
    if code is None:
        _type_unicode(main)
        return

    # CGEvent：必须显式写 flags（含 0），down/up 间稍作间隔
    down = CGEventCreateKeyboardEvent(None, code, True)
    up = CGEventCreateKeyboardEvent(None, code, False)
    CGEventSetFlags(down, flags)
    CGEventSetFlags(up, flags)
    CGEventPost(kCGHIDEventTap, down)
    time.sleep(0.03)
    CGEventPost(kCGHIDEventTap, up)

    # Return/Enter：System Events 双保险（选搜索结果等）
    if main in ("return", "enter"):
        time.sleep(0.04)
        try:
            import subprocess

            if flags & kCGEventFlagMaskCommand:
                script = (
                    'tell application "System Events" to '
                    "keystroke return using command down"
                )
            elif flags & kCGEventFlagMaskShift:
                script = (
                    'tell application "System Events" to '
                    "keystroke return using shift down"
                )
            else:
                # key code 36 = Return
                script = 'tell application "System Events" to key code 36'
            subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except Exception:
            pass


def _type_unicode(text: str) -> None:
    """逐字发送 unicode（英文短串可用；中文请用剪贴板）。"""
    for ch in text:
        down = CGEventCreateKeyboardEvent(None, 0, True)
        CGEventKeyboardSetUnicodeString(down, len(ch), ch)
        up = CGEventCreateKeyboardEvent(None, 0, False)
        CGEventKeyboardSetUnicodeString(up, len(ch), ch)
        CGEventPost(kCGHIDEventTap, down)
        CGEventPost(kCGHIDEventTap, up)


def type_text_ascii(text: str) -> None:
    _type_unicode(text)
