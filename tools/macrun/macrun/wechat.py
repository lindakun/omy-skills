# -*- coding: utf-8 -*-
"""微信 Mac 确定性发送流程（不依赖逐步视觉 LLM）。"""

from __future__ import annotations

import re
import time
from typing import Any, Callable

from macrun import act, ax
from macrun.config import load_config


def parse_contact_and_message(goal: str) -> tuple[str | None, str | None]:
    """从 goal 文本提取联系人与正文。"""
    contact = None
    message = None

    m = re.search(r"联系人[「『\"'](.+?)[」』\"']", goal)
    if m:
        contact = m.group(1).strip()
    if not contact:
        m = re.search(r"搜索(?:联系人)?[「『\"'](.+?)[」』\"']", goal)
        if m:
            contact = m.group(1).strip()
    if not contact:
        m = re.search(r"(?:给|发给|找到)([^\s，,。发]{2,12})(?:发|：|:)", goal)
        if m:
            contact = m.group(1).strip()

    m = re.search(r"正文[「『\"'](.+?)[」』\"']", goal, re.S)
    if m:
        message = m.group(1).strip()
    if not message:
        m = re.search(r"粘贴正文[「『\"'](.+?)[」』\"']", goal, re.S)
        if m:
            message = m.group(1).strip()
    if not message:
        pairs = re.findall(r"[「『\"'](.+?)[」』\"']", goal, re.S)
        if contact and len(pairs) >= 2:
            rest = [p for p in pairs if p.strip() != contact]
            if rest:
                message = rest[-1].strip()
        elif not contact and len(pairs) >= 2:
            contact, message = pairs[0].strip(), pairs[1].strip()
        elif len(pairs) == 1 and not message:
            message = pairs[0].strip()

    if not message:
        m = re.search(r"(?:发(?:送)?(?:消息|信息)?|问好)[：:]\s*(.+)$", goal)
        if m:
            message = m.group(1).strip()

    return contact, message


def is_wechat_send_goal(goal: str) -> bool:
    g = goal.lower()
    has_wechat = ("wechat" in g) or ("微信" in goal)
    has_send = any(k in goal for k in ("发", "消息", "信息", "问好", "发送", "paste", "粘贴"))
    contact, message = parse_contact_and_message(goal)
    return has_wechat and has_send and bool(contact and message)


def _wechat_cfg() -> dict[str, Any]:
    try:
        cfg = load_config()
        return dict(cfg.get("wechat") or {})
    except Exception:
        return {}


def _ts() -> float:
    return time.perf_counter()


def _log_step(
    log: Callable[[str], None],
    t0: float,
    msg: str,
) -> None:
    log(f"+{time.perf_counter() - t0:.2f}s {msg}")


def _is_wechat_front() -> bool:
    try:
        front = ax.frontmost_app_info()
        blob = f"{front.get('name','')} {front.get('bundle_id','')}".lower()
        return "wechat" in blob or "微信" in blob or "tencent.xinwechat" in blob
    except Exception:
        return False


def _critical_hotkey(
    *keys: str,
    log: Callable[[str], None],
    t0: float,
    label: str,
) -> None:
    """关键热键：前置 + 发送；若焦点被抢则重试一次。"""
    act.ensure_front("WeChat", settle=0.12)
    act.hotkey(*keys, app_name="WeChat", ensure=False, settle=0.04)
    if not _is_wechat_front():
        _log_step(log, t0, f"{label}: focus lost, retry")
        act.ensure_front("WeChat", settle=0.15)
        act.hotkey(*keys, app_name="WeChat", ensure=False, settle=0.04)


def _critical_paste(
    text: str,
    log: Callable[[str], None],
    t0: float,
    label: str,
) -> None:
    act.ensure_front("WeChat", settle=0.12)
    act.clipboard_type(text, app_name="WeChat", ensure=False)
    if not _is_wechat_front():
        _log_step(log, t0, f"{label}: focus lost after paste, re-front")
        act.ensure_front("WeChat", settle=0.12)


def send_message(
    contact: str,
    message: str,
    log: Callable[[str], None] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """固定快捷键流程发微信消息（热启动加速 + 可配置发送键 + 焦点重试）。"""

    def _log(msg: str) -> None:
        if log:
            log(msg)
        else:
            print(msg, flush=True)

    t0 = _ts()
    wcfg = config if config is not None else _wechat_cfg()
    send_mode = str(wcfg.get("send_mode") or "both").lower().strip()
    # both | enter | cmd_enter
    if send_mode not in ("both", "enter", "cmd_enter", "cmd+enter", "return"):
        send_mode = "both"
    if send_mode in ("cmd+enter",):
        send_mode = "cmd_enter"
    if send_mode == "return":
        send_mode = "enter"

    search_keys = wcfg.get("search_hotkey") or ["cmd", "f"]
    if isinstance(search_keys, str):
        search_keys = search_keys.replace("+", " ").split()
    search_keys = [str(k) for k in search_keys]

    select_extra_enter = bool(wcfg.get("select_extra_enter", True))
    open_sleep = float(wcfg.get("open_sleep") or 0.35)
    search_sleep = float(wcfg.get("search_sleep") or 0.28)
    after_contact_sleep = float(wcfg.get("after_contact_sleep") or 0.28)
    after_select_sleep = float(wcfg.get("after_select_sleep") or 0.40)
    after_message_sleep = float(wcfg.get("after_message_sleep") or 0.22)

    _log(f"wechat-script start contact={contact!r} message={message!r} send_mode={send_mode}")

    # 1) 热启动：已在跑则只 activate
    found = ax.find_app(name="WeChat")
    if found:
        _log_step(_log, t0, f"hot-start activate pid={found.get('pid')}")
        act.ensure_front("WeChat", settle=0.15)
        time.sleep(0.12)
    else:
        _log_step(_log, t0, "cold-start open WeChat")
        try:
            r = act.open_app("WeChat")
            _log_step(_log, t0, str(r))
        except Exception as e:
            _log_step(_log, t0, f"open_app warn {e}")
            act.ensure_front("WeChat", settle=0.2)
        time.sleep(open_sleep)

    if not ax.find_app(name="WeChat"):
        return {"status": "fail", "reason": "WeChat not running after open/activate"}

    if not _is_wechat_front():
        act.ensure_front("WeChat", settle=0.18)

    front = ax.frontmost_app_info()
    _log_step(_log, t0, f"frontmost={front.get('name')} active_ok={_is_wechat_front()}")

    # 2) 搜索
    _log_step(_log, t0, f"search hotkey {'+'.join(search_keys)}")
    _critical_hotkey(*search_keys, log=_log, t0=t0, label="search")
    time.sleep(search_sleep)

    # 3) 粘贴联系人 + 选中（Down 更稳可选，默认 Enter；可二次 Enter）
    _log_step(_log, t0, f"paste contact {contact!r}")
    _critical_paste(contact, log=_log, t0=t0, label="contact")
    time.sleep(after_contact_sleep)

    # 先 ↓ 再 Enter，降低停在搜索框的概率
    if bool(wcfg.get("select_with_down", True)):
        _critical_hotkey("down", log=_log, t0=t0, label="select-down")
        time.sleep(0.08)
    _critical_hotkey("return", log=_log, t0=t0, label="select-enter")
    time.sleep(after_select_sleep)

    if select_extra_enter:
        _critical_hotkey("return", log=_log, t0=t0, label="select-enter-2")
        time.sleep(0.22)

    # 4) 正文
    _log_step(_log, t0, f"paste message ({len(message)} chars)")
    _critical_paste(message, log=_log, t0=t0, label="message")
    time.sleep(after_message_sleep)

    # 5) 发送
    _log_step(_log, t0, f"send mode={send_mode}")
    act.ensure_front("WeChat", settle=0.12)
    send_result = act.send_chat(app_name="WeChat", mode=send_mode, ensure=False)
    if not _is_wechat_front():
        _log_step(_log, t0, "send: focus lost, resend")
        act.ensure_front("WeChat", settle=0.15)
        send_result = act.send_chat(app_name="WeChat", mode=send_mode, ensure=False)
    _log_step(_log, t0, str(send_result))

    elapsed = time.perf_counter() - t0
    result = (
        f"已向「{contact}」发送消息（{len(message)} 字，脚本 {elapsed:.1f}s，mode={send_mode}）。"
        f"请在微信确认气泡；若仍在输入框，把 config wechat.send_mode 改为 enter 或 cmd_enter。"
    )
    _log(f"FINISH: {result}")
    return {
        "status": "success",
        "result": result,
        "contact": contact,
        "message": message,
        "mode": "wechat-script",
        "send_mode": send_mode,
        "elapsed_s": round(elapsed, 2),
    }
