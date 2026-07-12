# -*- coding: utf-8 -*-
"""微信 Mac 确定性发送流程（不依赖逐步视觉 LLM）。"""

from __future__ import annotations

import re
import time
from typing import Any, Callable

from macrun import act, ax


def parse_contact_and_message(goal: str) -> tuple[str | None, str | None]:
    """从 goal 文本提取联系人与正文。

    支持：
    - 联系人「张三」…正文「你好」
    - 搜索「张三」…粘贴「你好」
    - 给张三发：你好 / 发给张三：你好
    """
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
        # 第二个书名号/引号对常为正文
        pairs = re.findall(r"[「『\"'](.+?)[」』\"']", goal, re.S)
        if contact and len(pairs) >= 2:
            # 去掉已识别的联系人
            rest = [p for p in pairs if p.strip() != contact]
            if rest:
                message = rest[-1].strip()
        elif not contact and len(pairs) >= 2:
            contact, message = pairs[0].strip(), pairs[1].strip()
        elif len(pairs) == 1 and not message:
            # 仅一段引号且像正文
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


def send_message(
    contact: str,
    message: str,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """固定快捷键流程发微信消息。"""

    def _log(msg: str) -> None:
        if log:
            log(msg)
        else:
            print(msg, flush=True)

    _log(f"wechat-script start contact={contact!r} message={message!r}")

    # 1) 打开并前置
    _log("wechat-script: open/activate WeChat")
    try:
        r = act.open_app("WeChat")
        _log(f"wechat-script: {r}")
    except Exception as e:
        _log(f"wechat-script: open_app warn {e}, try activate")
        act.ensure_front("WeChat")
    time.sleep(0.6)

    front = ax.frontmost_app_info()
    found = ax.find_app(name="WeChat")
    _log(f"wechat-script: frontmost={front} found={found}")
    if not found:
        return {"status": "fail", "reason": "WeChat not running after open"}

    # 2) 搜索联系人 Cmd+F（部分版本是 Cmd+F，失败可再试）
    _log("wechat-script: Cmd+F search")
    act.hotkey("cmd", "f", app_name="WeChat")
    time.sleep(0.45)

    # 3) 粘贴联系人 + 回车选中
    _log(f"wechat-script: paste contact {contact!r}")
    act.clipboard_type(contact, app_name="WeChat")
    time.sleep(0.35)
    act.hotkey("return", app_name="WeChat")
    time.sleep(0.7)

    # 再回车一次，防止停在搜索结果列表
    act.hotkey("return", app_name="WeChat")
    time.sleep(0.5)

    # 4) 粘贴正文
    _log(f"wechat-script: paste message ({len(message)} chars)")
    act.clipboard_type(message, app_name="WeChat")
    time.sleep(0.35)

    # 5) 发送（Cmd+Enter + Enter）
    _log("wechat-script: send")
    r = act.send_chat(app_name="WeChat")
    _log(f"wechat-script: {r}")
    time.sleep(0.3)

    result = (
        f"已按脚本流程向「{contact}」发送消息（{len(message)} 字）。"
        f"请在微信中确认气泡是否出现；若仍在输入框，可能是发送快捷键设置不同。"
    )
    _log(f"FINISH: {result}")
    return {
        "status": "success",
        "result": result,
        "contact": contact,
        "message": message,
        "mode": "wechat-script",
    }
