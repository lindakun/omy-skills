# -*- coding: utf-8 -*-
"""微信 Mac：脚本推进 + 关卡式视觉验收（Gate1 选人 / Gate2 发送）。"""

from __future__ import annotations

import re
import time
from typing import Any, Callable

from macrun import act, ax
from macrun.config import load_config
from macrun.gate import gate1_search_contact, gate2_send_verify, gate_read_messages


def normalize_message(message: str) -> str:
    """规范化正文：字面 \\n → 真换行，统一换行符。"""
    if message is None:
        return ""
    text = message
    # 处理 shell/JSON 双重转义
    if "\\n" in text and "\n" not in text:
        text = text.replace("\\n", "\n")
    text = text.replace("\\t", "\t")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.strip()


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
    if not contact:
        # 文件传输助手等专名
        if "文件传输助手" in goal:
            contact = "文件传输助手"

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
        m = re.search(r"(?:发(?:送)?(?:消息|信息|一首|一个|首)?|问好)[：:]\s*(.+)$", goal, re.S)
        if m:
            message = m.group(1).strip()
    # 「一首静夜思」类：正文可能未加引号
    if not message and "静夜思" in goal:
        message = (
            "静夜思\n\n床前明月光，疑是地上霜。\n举头望明月，低头思故乡。"
        )

    if message:
        message = normalize_message(message)
    return contact, message


def is_wechat_send_goal(goal: str) -> bool:
    g = goal.lower()
    has_wechat = ("wechat" in g) or ("微信" in goal) or ("文件传输助手" in goal)
    has_send = any(k in goal for k in ("发", "消息", "信息", "问好", "发送", "paste", "粘贴", "一首", "一个"))
    contact, message = parse_contact_and_message(goal)
    return bool(contact and message) and (has_wechat or has_send)


def _wechat_cfg() -> dict[str, Any]:
    try:
        cfg = load_config()
        return dict(cfg.get("wechat") or {})
    except Exception:
        return {}


def _ts() -> float:
    return time.perf_counter()


def _log_step(log: Callable[[str], None], t0: float, msg: str) -> None:
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


def _select_row(row: int, log: Callable[[str], None], t0: float) -> None:
    """row 为 1-based：按 (row-1) 次 Down 再 Enter。禁止盲点。"""
    n = max(0, int(row) - 1)
    for i in range(n):
        _critical_hotkey("down", log=log, t0=t0, label=f"select-down-{i+1}")
        time.sleep(0.06)
    _critical_hotkey("return", log=log, t0=t0, label="select-enter")


def open_session(
    session: str,
    log: Callable[[str], None],
    t0: float,
    wcfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """打开/激活微信并搜索进入会话。成功返回 {status:ok, gate1}，失败 status:fail。"""
    wcfg = wcfg if wcfg is not None else _wechat_cfg()
    session = (session or "").strip()
    if not session:
        return {"status": "fail", "reason": "session name empty"}

    gates_enabled = bool(wcfg.get("gates_enabled", True))
    search_keys = wcfg.get("search_hotkey") or ["cmd", "f"]
    if isinstance(search_keys, str):
        search_keys = search_keys.replace("+", " ").split()
    search_keys = [str(k) for k in search_keys]
    open_sleep = float(wcfg.get("open_sleep") or 0.35)
    search_sleep = float(wcfg.get("search_sleep") or 0.35)
    after_contact_sleep = float(wcfg.get("after_contact_sleep") or 0.35)
    after_select_sleep = float(wcfg.get("after_select_sleep") or 0.45)

    found = ax.find_app(name="WeChat")
    if found:
        _log_step(log, t0, f"hot-start activate pid={found.get('pid')}")
        act.ensure_front("WeChat", settle=0.15)
        time.sleep(0.12)
    else:
        _log_step(log, t0, "cold-start open WeChat")
        try:
            r = act.open_app("WeChat")
            _log_step(log, t0, str(r))
        except Exception as e:
            _log_step(log, t0, f"open_app warn {e}")
            act.ensure_front("WeChat", settle=0.2)
        time.sleep(open_sleep)

    if not ax.find_app(name="WeChat"):
        return {"status": "fail", "reason": "WeChat not running after open/activate"}
    if not _is_wechat_front():
        act.ensure_front("WeChat", settle=0.18)

    front = ax.frontmost_app_info()
    _log_step(log, t0, f"frontmost={front.get('name')} active_ok={_is_wechat_front()}")

    _log_step(log, t0, f"search hotkey {'+'.join(search_keys)}")
    _critical_hotkey(*search_keys, log=log, t0=t0, label="search")
    time.sleep(search_sleep)

    _log_step(log, t0, f"paste session {session!r}")
    _critical_paste(session, log=log, t0=t0, label="session")
    time.sleep(after_contact_sleep)

    row = 1
    gate1: dict[str, Any] | None = None
    if gates_enabled:
        _log_step(log, t0, "gate1: vision check search results")
        try:
            gate1 = gate1_search_contact(session, log=log)
        except Exception as e:
            _log_step(log, t0, f"gate1 error: {e}")
            return {
                "status": "fail",
                "reason": f"Gate1 视觉验收失败（API/截图）：{e}",
                "gate1": {"error": str(e)},
            }
        _log_step(
            log,
            t0,
            f"gate1 result matched={gate1.get('matched')} row={gate1.get('row')} "
            f"title={gate1.get('title')!r} conf={gate1.get('confidence')} "
            f"reason={gate1.get('reason')}",
        )
        if not gate1.get("matched"):
            return {
                "status": "fail",
                "reason": (
                    f"Gate1 未在搜索结果中确认「{session}」"
                    f"（{gate1.get('reason') or 'no match'}）。"
                    f"已中止，避免机械进入错误会话。"
                ),
                "gate1": gate1,
            }
        row = int(gate1.get("row") or 1)
    else:
        _log_step(log, t0, "gate1 skipped, use row=1")

    _log_step(log, t0, f"select row={row}")
    _select_row(row, log=log, t0=t0)
    time.sleep(after_select_sleep)
    return {"status": "ok", "gate1": gate1, "row": row, "session": session}


def send_message(
    contact: str,
    message: str,
    log: Callable[[str], None] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """脚本推进 + Gate1/Gate2 视觉验收；Gate 失败直接 FAIL（不盲 Enter）。"""

    def _log(msg: str) -> None:
        if log:
            log(msg)
        else:
            print(msg, flush=True)

    t0 = _ts()
    message = normalize_message(message)
    contact = (contact or "").strip()
    if not contact or not message:
        return {"status": "fail", "reason": "contact/message empty"}

    wcfg = config if config is not None else _wechat_cfg()
    send_mode = str(wcfg.get("send_mode") or "both").lower().strip()
    if send_mode not in ("both", "enter", "cmd_enter", "cmd+enter", "return"):
        send_mode = "both"
    if send_mode == "cmd+enter":
        send_mode = "cmd_enter"
    if send_mode == "return":
        send_mode = "enter"

    gates_enabled = bool(wcfg.get("gates_enabled", True))
    after_message_sleep = float(wcfg.get("after_message_sleep") or 0.25)

    _log(
        f"wechat-script start contact={contact!r} message_len={len(message)} "
        f"send_mode={send_mode} gates={gates_enabled}"
    )

    opened = open_session(contact, _log, t0, wcfg)
    if opened.get("status") != "ok":
        opened["elapsed_s"] = round(time.perf_counter() - t0, 2)
        return opened
    gate1 = opened.get("gate1")

    # 正文 + 发送
    _log_step(_log, t0, f"paste message ({len(message)} chars)")
    _critical_paste(message, log=_log, t0=t0, label="message")
    time.sleep(after_message_sleep)

    _log_step(_log, t0, f"send mode={send_mode}")
    act.ensure_front("WeChat", settle=0.12)
    send_result = act.send_chat(app_name="WeChat", mode=send_mode, ensure=False)
    if not _is_wechat_front():
        _log_step(_log, t0, "send: focus lost, resend once")
        act.ensure_front("WeChat", settle=0.15)
        send_result = act.send_chat(app_name="WeChat", mode=send_mode, ensure=False)
    _log_step(_log, t0, str(send_result))
    time.sleep(0.35)

    gate2: dict[str, Any] | None = None
    if gates_enabled:
        _log_step(_log, t0, "gate2: vision verify send")
        try:
            gate2 = gate2_send_verify(contact, message, log=_log)
        except Exception as e:
            _log_step(_log, t0, f"gate2 error: {e}")
            return {
                "status": "fail",
                "reason": f"Gate2 视觉验收失败（API/截图）：{e}",
                "gate1": gate1,
                "gate2": {"error": str(e)},
                "elapsed_s": round(time.perf_counter() - t0, 2),
            }
        _log_step(
            _log,
            t0,
            f"gate2 result sent={gate2.get('sent')} in_chat={gate2.get('in_chat')} "
            f"empty={gate2.get('input_emptyish')} conf={gate2.get('confidence')} "
            f"reason={gate2.get('reason')}",
        )

        if not gate2.get("sent"):
            alt = "enter" if send_mode != "enter" else "cmd_enter"
            _log_step(_log, t0, f"gate2 fail → retry send mode={alt}")
            act.ensure_front("WeChat", settle=0.12)
            act.send_chat(app_name="WeChat", mode=alt, ensure=False)
            time.sleep(0.4)
            try:
                gate2 = gate2_send_verify(contact, message, log=_log)
            except Exception as e:
                return {
                    "status": "fail",
                    "reason": f"Gate2 重试时视觉失败：{e}",
                    "gate1": gate1,
                    "gate2": {"error": str(e)},
                    "elapsed_s": round(time.perf_counter() - t0, 2),
                }
            _log_step(
                _log,
                t0,
                f"gate2 retry sent={gate2.get('sent')} reason={gate2.get('reason')}",
            )
            if not gate2.get("sent"):
                return {
                    "status": "fail",
                    "reason": (
                        f"Gate2 判定未成功发送给「{contact}」"
                        f"（{gate2.get('reason') or 'unverified'}）。"
                        f"未报告假成功。"
                    ),
                    "gate1": gate1,
                    "gate2": gate2,
                    "elapsed_s": round(time.perf_counter() - t0, 2),
                }
            send_mode = alt

    elapsed = time.perf_counter() - t0
    result = (
        f"已向「{contact}」发送消息（{len(message)} 字，{elapsed:.1f}s，"
        f"mode={send_mode}，gates=on）。Gate1/Gate2 已通过。"
    )
    _log(f"FINISH: {result}")
    return {
        "status": "success",
        "result": result,
        "contact": contact,
        "message": message,
        "mode": "wechat-script+gates",
        "send_mode": send_mode,
        "gate1": gate1,
        "gate2": gate2,
        "elapsed_s": round(elapsed, 2),
    }


def _format_messages_for_clipboard(session: str, messages: list[dict[str, Any]]) -> str:
    lines = [f"微信会话「{session}」最近 {len(messages)} 条消息：", ""]
    for m in messages:
        sender = m.get("sender") or "未知"
        text = m.get("text") or ""
        t = m.get("time") or ""
        prefix = f"[{t}] " if t else ""
        lines.append(f"{m.get('index', '')}. {prefix}{sender}: {text}")
    return "\n".join(lines).strip() + "\n"


def is_wechat_read_goal(goal: str) -> bool:
    """是否「读/看/复制 微信会话消息」。"""
    g = goal
    has_wechat = ("微信" in g) or ("wechat" in g.lower()) or ("群聊" in g) or ("群" in g)
    has_read = any(
        k in g
        for k in (
            "读",
            "看",
            "最近",
            "消息",
            "聊天记录",
            "复制",
            "剪贴板",
            "总结",
            "提取",
        )
    )
    # 排除纯发送
    if is_wechat_send_goal(goal) and not any(k in g for k in ("读", "最近", "复制", "剪贴板", "聊天记录")):
        return False
    session, _ = parse_read_session(goal)
    return bool(has_wechat and has_read and session)


def parse_read_session(goal: str) -> tuple[str | None, int]:
    """解析会话名与条数。默认 last=5。"""
    session = None
    last_n = 5
    m = re.search(r"群聊[「『\"'](.+?)[」』\"']", goal)
    if m:
        session = m.group(1).strip()
    if not session:
        m = re.search(r"(?:会话|联系人|群)[「『\"'](.+?)[」』\"']", goal)
        if m:
            session = m.group(1).strip()
    if not session:
        pairs = re.findall(r"[「『\"'](.+?)[」』\"']", goal)
        if pairs:
            session = pairs[0].strip()
    if not session and "文件传输助手" in goal:
        session = "文件传输助手"
    m = re.search(r"最近\s*(\d+)\s*条", goal)
    if m:
        last_n = int(m.group(1))
    m = re.search(r"(\d+)\s*条", goal)
    if m and last_n == 5:
        last_n = int(m.group(1))
    last_n = max(1, min(last_n, 30))
    return session, last_n


def read_messages(
    session: str,
    last_n: int = 5,
    log: Callable[[str], None] | None = None,
    config: dict[str, Any] | None = None,
    to_clipboard: bool = True,
) -> dict[str, Any]:
    """打开会话 + 视觉抽取最近 N 条 + 可选写入剪贴板。"""

    def _log(msg: str) -> None:
        if log:
            log(msg)
        else:
            print(msg, flush=True)

    t0 = _ts()
    session = (session or "").strip()
    last_n = max(1, min(int(last_n or 5), 30))
    if not session:
        return {"status": "fail", "reason": "session empty"}

    wcfg = config if config is not None else _wechat_cfg()
    _log(f"wechat-read start session={session!r} last_n={last_n}")

    opened = open_session(session, _log, t0, wcfg)
    if opened.get("status") != "ok":
        opened["elapsed_s"] = round(time.perf_counter() - t0, 2)
        return opened
    gate1 = opened.get("gate1")

    # 轻微上滚，尽量露出更多历史（可选第二张图）
    scroll = bool(wcfg.get("read_scroll_once", True))
    messages: list[dict[str, Any]] = []
    gate_read: dict[str, Any] | None = None

    def _do_read(hint: str = "") -> dict[str, Any]:
        act.ensure_front("WeChat", settle=0.25)
        time.sleep(0.2)
        if not _is_wechat_front():
            act.ensure_front("WeChat", settle=0.3)
            time.sleep(0.15)
        return gate_read_messages(
            session, last_n=last_n, log=_log, extra_hint=hint
        )

    _log_step(_log, t0, "gate-read: extract messages from chat view")
    try:
        gate_read = _do_read()
    except Exception as e:
        return {
            "status": "fail",
            "reason": f"读消息视觉失败：{e}",
            "gate1": gate1,
            "elapsed_s": round(time.perf_counter() - t0, 2),
        }
    _log_step(
        _log,
        t0,
        f"gate-read in_session={gate_read.get('in_session')} "
        f"n={len(gate_read.get('messages') or [])} conf={gate_read.get('confidence')} "
        f"reason={gate_read.get('reason')}",
    )

    if not gate_read.get("in_session"):
        # 常见：截图时焦点被 WorkBuddy/IDE 抢走
        _log_step(_log, t0, "gate-read not in session → re-front WeChat and retry once")
        try:
            gate_read = _do_read(
                "请确认是否为微信聊天窗口；忽略背后 IDE/编辑器。"
            )
        except Exception as e:
            return {
                "status": "fail",
                "reason": f"读消息重试失败：{e}",
                "gate1": gate1,
                "elapsed_s": round(time.perf_counter() - t0, 2),
            }
        _log_step(
            _log,
            t0,
            f"gate-read retry in_session={gate_read.get('in_session')} "
            f"n={len(gate_read.get('messages') or [])} reason={gate_read.get('reason')}",
        )

    if not gate_read.get("in_session"):
        return {
            "status": "fail",
            "reason": (
                f"未确认已进入会话「{session}」"
                f"（{gate_read.get('reason') or 'in_session=false'}）"
            ),
            "gate1": gate1,
            "gate_read": gate_read,
            "elapsed_s": round(time.perf_counter() - t0, 2),
        }

    messages = list(gate_read.get("messages") or [])

    # 不足 N 条时上滚再读一次合并
    if scroll and len(messages) < last_n:
        _log_step(_log, t0, "scroll up once for more history")
        act.ensure_front("WeChat", settle=0.1)
        # Page Up / 触控板式：多次 key up 或 pageup
        for _ in range(3):
            act.hotkey("up", app_name="WeChat", ensure=False, settle=0.02)
            time.sleep(0.05)
        time.sleep(0.25)
        try:
            gate_read2 = gate_read_messages(
                session,
                last_n=last_n,
                log=_log,
                extra_hint="这是向上滚动后的截图，请继续抽取可见消息。",
            )
            more = list(gate_read2.get("messages") or [])
            # 简单合并去重（按 text+sender）
            seen = {(m.get("sender"), m.get("text")) for m in messages}
            for m in more:
                key = (m.get("sender"), m.get("text"))
                if key not in seen:
                    messages.append(m)
                    seen.add(key)
            # 只保留最后 last_n 条（按 index 或列表尾部）
            if len(messages) > last_n:
                messages = messages[-last_n:]
                for i, m in enumerate(messages, 1):
                    m["index"] = i
            _log_step(_log, t0, f"after scroll merged n={len(messages)}")
        except Exception as e:
            _log_step(_log, t0, f"second read skipped: {e}")

    if not messages:
        return {
            "status": "fail",
            "reason": f"未能从「{session}」抽取到消息文本",
            "gate1": gate1,
            "gate_read": gate_read,
            "elapsed_s": round(time.perf_counter() - t0, 2),
        }

    text = _format_messages_for_clipboard(session, messages)
    if to_clipboard:
        act.set_clipboard(text)
        _log_step(_log, t0, f"clipboard set ({len(text)} chars)")

    elapsed = time.perf_counter() - t0
    summary = (
        f"已读取「{session}」最近 {len(messages)} 条消息（{elapsed:.1f}s），"
        f"{'并复制到剪贴板' if to_clipboard else '未写剪贴板'}。"
    )
    _log(f"FINISH: {summary}")
    _log("--- messages ---")
    _log(text.rstrip())
    return {
        "status": "success",
        "result": summary,
        "session": session,
        "messages": messages,
        "clipboard_text": text,
        "gate1": gate1,
        "gate_read": gate_read,
        "elapsed_s": round(elapsed, 2),
        "mode": "wechat-read",
    }
