# -*- coding: utf-8 -*-
"""微信 Mac：备注后缀脚本选人/发送；读消息只截图。默认全流程不调视觉。"""

from __future__ import annotations

import re
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from macrun import act, ax, vision
from macrun.config import load_config

# 默认备注后缀；可用 config wechat.remark_suffix 覆盖
DEFAULT_REMARK_SUFFIX = "-1688"
DEFAULT_NO_SUFFIX_SESSIONS = ("文件传输助手",)
DEFAULT_READ_SCREENSHOT_DIR = "/tmp"
# 兼容旧配置键默认值（固定文件名已废弃，仅作目录推断）
DEFAULT_READ_SCREENSHOT = "/tmp/wechat_screenshot.jpg"
# 剪贴板探测用标记（不应与正常聊天正文冲突）
_PROBE_CANARY_PREFIX = "__macrun_probe__"


def _safe_filename_part(name: str, max_len: int = 48) -> str:
    """会话名 → 文件名安全片段（保留中文，去掉路径非法字符）。"""
    text = (name or "").strip()
    if not text:
        return "session"
    bad = '\\/:*?"<>|\n\r\t'
    out = "".join("_" if ch in bad else ch for ch in text)
    out = out.strip(" ._") or "session"
    if len(out) > max_len:
        out = out[:max_len].rstrip(" ._") or "session"
    return out


def build_read_screenshot_path(
    session_display: str,
    wcfg: dict[str, Any] | None = None,
    *,
    when: datetime | None = None,
) -> str:
    """读消息截图路径：/tmp/wechat_screenshot_{会话}_{YYYYMMDD_HHMMSS}.jpg

    配置：
    - read_screenshot_dir: 目录（优先）
    - read_screenshot_path: 若为目录或旧固定 .jpg，取其父目录；支持模板
      {session}/{display}/{time}
    """
    cfg = wcfg or {}
    ts = (when or datetime.now()).strftime("%Y%m%d_%H%M%S")
    safe = _safe_filename_part(session_display)
    default_name = f"wechat_screenshot_{safe}_{ts}.jpg"

    raw_dir = str(cfg.get("read_screenshot_dir") or "").strip()
    raw_path = str(cfg.get("read_screenshot_path") or "").strip()

    # 显式模板：含 {session} / {display} / {time}
    if raw_path and ("{" in raw_path and "}" in raw_path):
        path = raw_path.format(session=safe, display=safe, time=ts)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        return str(Path(path))

    if raw_dir:
        dest_dir = Path(raw_dir).expanduser()
    elif raw_path:
        p = Path(raw_path).expanduser()
        # 旧配置 /tmp/wechat_screenshot.jpg → 目录 /tmp
        if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
            dest_dir = p.parent if str(p.parent) not in ("", ".") else Path(DEFAULT_READ_SCREENSHOT_DIR)
        else:
            dest_dir = p
    else:
        dest_dir = Path(DEFAULT_READ_SCREENSHOT_DIR)

    dest_dir.mkdir(parents=True, exist_ok=True)
    return str(dest_dir / default_name)


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


def resolve_session_query(
    raw: str,
    wcfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """将用户口语名解析为微信搜索串。

    规则：
    - 默认在备注后拼 remark_suffix（默认 -1688）保证唯一
    - no_suffix_sessions（默认含「文件传输助手」）不拼
    - 已以后缀结尾则不双拼
    - remark_suffix_enabled=false 或 suffix 为空则原样

    返回：
      display: 用户原始名
      query: 实际搜索串
      used_suffix: 是否本次拼接了后缀
      exception: 是否命中免后缀白名单
      suffix: 当前配置的后缀
    """
    cfg = wcfg if wcfg is not None else _wechat_cfg()
    display = (raw or "").strip()
    suffix = cfg.get("remark_suffix", DEFAULT_REMARK_SUFFIX)
    if suffix is None:
        suffix = DEFAULT_REMARK_SUFFIX
    suffix = str(suffix)
    enabled = bool(cfg.get("remark_suffix_enabled", True))

    no_suffix = cfg.get("no_suffix_sessions")
    if no_suffix is None:
        no_list = list(DEFAULT_NO_SUFFIX_SESSIONS)
    elif isinstance(no_suffix, str):
        no_list = [no_suffix]
    else:
        no_list = [str(x).strip() for x in no_suffix if str(x).strip()]

    if not display:
        return {
            "display": "",
            "query": "",
            "used_suffix": False,
            "exception": False,
            "suffix": suffix,
        }

    # 白名单：精确匹配（忽略首尾空白）
    for name in no_list:
        if display == name:
            return {
                "display": display,
                "query": display,
                "used_suffix": False,
                "exception": True,
                "suffix": suffix,
            }

    if not enabled or not suffix:
        return {
            "display": display,
            "query": display,
            "used_suffix": False,
            "exception": False,
            "suffix": suffix,
        }

    if display.endswith(suffix):
        return {
            "display": display,
            "query": display,
            "used_suffix": False,
            "exception": False,
            "suffix": suffix,
        }

    return {
        "display": display,
        "query": f"{display}{suffix}",
        "used_suffix": True,
        "exception": False,
        "suffix": suffix,
    }


def _gates_flags(wcfg: dict[str, Any]) -> dict[str, bool]:
    """视觉关卡开关。默认全关（备注后缀 + 纯脚本）。

    仅当显式 gates.send: true 时开启发送后视觉校验（调试用）。
    """
    gates = wcfg.get("gates")
    if isinstance(gates, dict):
        return {
            "search": bool(gates.get("search", False)),
            "enter": bool(gates.get("enter", False)),
            "send": bool(gates.get("send", False)),
            "read": bool(gates.get("read", False)),
        }
    # 旧 gates_enabled 不再默认打开任何视觉；需显式 gates.send
    return {"search": False, "enter": False, "send": False, "read": False}


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
    """关键按键：轻量前置 + PostToPid。

    宿主抢焦点时 frontmost 检查几乎总失败；不再因此双倍重试（可省数秒）。
    真正失败由上层粘贴/发送校验兜底。
    """
    act.ensure_front("WeChat", settle=0.04, retries=1, hard=False)
    act.hotkey(*keys, app_name="WeChat", ensure=False, settle=0.02, use_pid=True)


def _critical_paste(
    text: str,
    log: Callable[[str], None],
    t0: float,
    label: str,
) -> None:
    act.ensure_front("WeChat", settle=0.04, retries=1, hard=False)
    act.clipboard_type(text, app_name="WeChat", ensure=False)


def _clipboard_get() -> str:
    r = subprocess.run(["pbpaste"], capture_output=True, check=False)
    if r.returncode != 0:
        return ""
    return (r.stdout or b"").decode("utf-8", errors="replace")


def _clipboard_set(text: str) -> None:
    subprocess.run(["pbcopy"], input=(text or "").encode("utf-8"), check=False)


def _norm_probe_text(text: str) -> str:
    """探测比对用：统一换行与首尾空白。"""
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _wechat_window_bounds() -> tuple[tuple[float, float], tuple[float, float]] | None:
    """返回微信主窗口 (position, size)；失败返回 None。"""
    found = ax.find_app(name="WeChat")
    if not found or not found.get("pid"):
        return None
    try:
        nodes = ax.dump_tree(pid=int(found["pid"]), max_nodes=20, max_depth=3)
    except Exception:
        return None
    for n in nodes:
        if "window" not in str(n.get("role") or "").lower():
            continue
        pos, size = n.get("position"), n.get("size")
        if pos and size and size[0] > 200 and size[1] > 200:
            return (float(pos[0]), float(pos[1])), (float(size[0]), float(size[1]))
    return None


def _focus_chat_input(
    log: Callable[[str], None],
    t0: float,
    wcfg: dict[str, Any],
    *,
    attempt: int = 1,
) -> dict[str, Any]:
    """选人后把焦点落到底部输入框。

    微信 Mac AX 树几乎无控件，无法靠 Accessibility 找输入框。
    策略：Esc 收起搜索 → 按主窗口几何点击聊天区底部输入带。
    attempt>1 时微调点击坐标（几乎不增加成功路径耗时）。
    """
    x_ratio = float(wcfg.get("input_click_x_ratio") or 0.58)
    bottom_inset = float(wcfg.get("input_click_bottom_inset") or 70)
    # 重试：略上移/右移，避开工具栏或点偏
    nudge_y = 0.0
    nudge_x = 0.0
    if attempt >= 2:
        nudge_y = -18.0
        nudge_x = 24.0
    if attempt >= 3:
        nudge_y = -36.0
        nudge_x = -20.0

    act.ensure_front("WeChat", settle=0.04, retries=1, hard=False)
    # 关闭仍停留在搜索框的焦点
    _critical_hotkey("escape", log=log, t0=t0, label="focus-esc")
    time.sleep(0.04)

    bounds = _wechat_window_bounds()
    if not bounds:
        _log_step(log, t0, "focus input: no window bounds, skip click")
        return {"ok": False, "reason": "no_window_bounds"}

    (px, py), (sw, sh) = bounds
    x = px + sw * x_ratio + nudge_x
    y = py + sh - bottom_inset + nudge_y
    _log_step(
        log,
        t0,
        f"focus input: click ({x:.0f},{y:.0f}) attempt={attempt} "
        f"win=({px:.0f},{py:.0f},{sw:.0f}x{sh:.0f})",
    )
    act.ensure_front("WeChat", settle=0.03, retries=1, hard=False)
    ax.click_xy(x, y)
    time.sleep(0.06)
    return {"ok": True, "x": x, "y": y, "bounds": bounds, "attempt": attempt}


def _clear_chat_input(log: Callable[[str], None], t0: float) -> None:
    """清空当前焦点处文本（假定已在输入框）。"""
    _critical_hotkey("cmd", "a", log=log, t0=t0, label="clear-select")
    time.sleep(0.03)
    _critical_hotkey("delete", log=log, t0=t0, label="clear-delete")
    time.sleep(0.03)


def _collapse_input_selection(
    log: Callable[[str], None] | None,
    t0: float,
) -> None:
    """取消输入框内全选，把光标收到文末。

    粘贴校验会 Cmd+A；若保持全选再按 Return，微信常把选中正文直接删掉
    （输入框变空但消息未发出），导致假成功。
    Right 取消选区；Cmd+Down 跳到文末（多行更稳，几乎不耗时）。
    """
    act.ensure_front("WeChat", settle=0.02, retries=1, hard=False)
    act.hotkey("right", app_name="WeChat", ensure=False, settle=0.01, use_pid=True)
    time.sleep(0.015)
    act.hotkey("cmd", "down", app_name="WeChat", ensure=False, settle=0.01, use_pid=True)
    time.sleep(0.02)
    if log:
        _log_step(log, t0, "collapse selection (right+cmd+down)")


def _snapshot_on_fail(
    log: Callable[[str], None],
    t0: float,
    wcfg: dict[str, Any],
    tag: str,
) -> str | None:
    """仅失败时截一张微信窗口图，便于排障（成功路径零开销）。"""
    if not bool(wcfg.get("fail_screenshot", True)):
        return None
    path = str(wcfg.get("fail_screenshot_path") or "/tmp/wechat_send_fail.jpg")
    try:
        act.ensure_front("WeChat", settle=0.06)
        saved = vision.capture_front_window_to(
            path,
            owner_names=["WeChat", "微信", "xinWeChat"],
            compress=True,
            max_side=int(wcfg.get("fail_screenshot_max_side") or 1280),
            quality=int(wcfg.get("fail_screenshot_jpeg_quality") or 70),
        )
        _log_step(log, t0, f"fail snapshot [{tag}]: {saved}")
        return str(saved)
    except Exception as e:
        _log_step(log, t0, f"fail snapshot skip: {e}")
        return None


def _probe_input_text(
    log: Callable[[str], None],
    t0: float,
    *,
    collapse_after: bool = False,
) -> str:
    """用 Cmd+A / Cmd+C 探测当前焦点文本（不依赖 AX Value）。

    先写入 canary 再复制：若焦点处无选中内容，剪贴板仍为 canary。
    collapse_after=True 时取消全选，避免紧接着发送时把正文删掉。
    """
    canary = f"{_PROBE_CANARY_PREFIX}{uuid.uuid4().hex[:10]}"
    act.ensure_front("WeChat", settle=0.03, retries=1, hard=False)
    _clipboard_set(canary)
    time.sleep(0.025)
    act.hotkey("cmd", "a", app_name="WeChat", ensure=False, settle=0.015, use_pid=True)
    time.sleep(0.025)
    act.hotkey("cmd", "c", app_name="WeChat", ensure=False, settle=0.015, use_pid=True)
    time.sleep(0.05)
    got = _clipboard_get()
    if got == canary:
        _log_step(log, t0, "probe input: empty (canary unchanged)")
        return ""
    preview = got.replace("\n", "\\n")
    if len(preview) > 60:
        preview = preview[:60] + "…"
    _log_step(log, t0, f"probe input: {len(got)} chars preview={preview!r}")
    if collapse_after and got:
        _collapse_input_selection(log, t0)
    return got


def _input_matches_message(probed: str, message: str) -> bool:
    """粘贴后：探测文本应与正文一致（允许首尾空白/换行差异）。"""
    a, b = _norm_probe_text(probed), _norm_probe_text(message)
    if not b:
        return False
    if a == b:
        return True
    # 个别版本粘贴后末尾多一个换行已在 strip 处理；再容忍全等失败时的包含
    return a.replace("\n", "") == b.replace("\n", "")


def _input_still_has_message(probed: str, message: str) -> bool:
    """发送后：若输入框仍基本等于正文，视为未发出。"""
    return _input_matches_message(probed, message)


def _select_first_result(
    select_mode: str,
    log: Callable[[str], None],
    t0: float,
) -> None:
    """备注后缀搜索后固定选第 1 条。默认 enter（更快）。"""
    mode = (select_mode or "enter").lower().strip()
    if mode in ("down_enter", "down+enter", "down"):
        _critical_hotkey("down", log=log, t0=t0, label="select-down")
        time.sleep(0.06)
        _critical_hotkey("return", log=log, t0=t0, label="select-enter")
    else:
        # enter：焦点在搜索框时微信通常直接打开第一条最佳匹配
        _critical_hotkey("return", log=log, t0=t0, label="select-enter")


def open_session(
    session: str,
    log: Callable[[str], None],
    t0: float,
    wcfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """打开微信并用备注后缀搜索进入会话（无视觉选人）。

    成功：{status:ok, display, query, ...}
    失败：status:fail（如微信未运行）。未设备注时可能进错会话，由用户侧备注约定保证。
    """
    wcfg = wcfg if wcfg is not None else _wechat_cfg()
    session = (session or "").strip()
    if not session:
        return {"status": "fail", "reason": "session name empty"}

    resolved = resolve_session_query(session, wcfg)
    display = resolved["display"]
    query = resolved["query"]
    if not query:
        return {"status": "fail", "reason": "session name empty"}

    search_keys = wcfg.get("search_hotkey") or ["cmd", "f"]
    if isinstance(search_keys, str):
        search_keys = search_keys.replace("+", " ").split()
    search_keys = [str(k) for k in search_keys]
    open_sleep = float(wcfg.get("open_sleep") or 0.35)
    search_sleep = float(wcfg.get("search_sleep") or 0.35)
    after_contact_sleep = float(wcfg.get("after_contact_sleep") or 0.40)
    after_select_sleep = float(wcfg.get("after_select_sleep") or 0.45)
    select_mode = str(wcfg.get("select_mode") or "enter").lower().strip()

    _log_step(
        log,
        t0,
        f"resolve display={display!r} query={query!r} "
        f"used_suffix={resolved.get('used_suffix')} "
        f"exception={resolved.get('exception')} suffix={resolved.get('suffix')!r}",
    )

    found = ax.find_app(name="WeChat")
    if found:
        _log_step(log, t0, f"hot-start activate pid={found.get('pid')}")
        # 热启动：一次轻量 activate 即可，宿主抢焦点时硬重试只浪费时间
        act.ensure_front("WeChat", settle=0.06, retries=1, hard=False)
    else:
        _log_step(log, t0, "cold-start open WeChat")
        try:
            r = act.open_app("WeChat")
            _log_step(log, t0, str(r))
        except Exception as e:
            _log_step(log, t0, f"open_app warn {e}")
            act.ensure_front("WeChat", settle=0.12, retries=2, hard=True)
        time.sleep(open_sleep)

    if not ax.find_app(name="WeChat"):
        return {"status": "fail", "reason": "WeChat not running after open/activate"}

    front = ax.frontmost_app_info()
    _log_step(log, t0, f"frontmost={front.get('name')} active_ok={_is_wechat_front()}")

    _log_step(log, t0, f"search hotkey {'+'.join(search_keys)}")
    _critical_hotkey(*search_keys, log=log, t0=t0, label="search")
    time.sleep(search_sleep)

    # 清空搜索框再粘贴，避免残留关键字
    _critical_hotkey("cmd", "a", log=log, t0=t0, label="select-all")
    time.sleep(0.03)
    _log_step(log, t0, f"paste query {query!r}")
    _critical_paste(query, log=log, t0=t0, label="session")
    time.sleep(after_contact_sleep)

    _log_step(log, t0, f"select first result mode={select_mode} (no vision)")
    _select_first_result(select_mode, log=log, t0=t0)
    time.sleep(after_select_sleep)

    return {
        "status": "ok",
        "display": display,
        "query": query,
        "session": display,
        "resolved": resolved,
        "select_mode": select_mode,
        "mode": "remark-suffix",
    }


def send_message(
    contact: str,
    message: str,
    log: Callable[[str], None] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """备注后缀脚本选人并发送。

    默认：Esc+点击聚焦输入框，剪贴板探测校验粘贴/发送是否成功（不调视觉）。
    gates.send=true 时额外做视觉 Gate2。
    """

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
    # 默认 enter：对应本机常见「Enter 发送」；both 仅作兼容
    send_mode = str(wcfg.get("send_mode") or "enter").lower().strip()
    if send_mode not in ("both", "enter", "cmd_enter", "cmd+enter", "return"):
        send_mode = "enter"
    if send_mode == "cmd+enter":
        send_mode = "cmd_enter"
    if send_mode == "return":
        send_mode = "enter"

    gflags = _gates_flags(wcfg)
    after_message_sleep = float(wcfg.get("after_message_sleep") or 0.22)
    # 默认开启：聚焦输入框 + 剪贴板探测（修「假 SUCCESS」）
    focus_input = bool(wcfg.get("focus_input", True))
    verify_send = bool(wcfg.get("verify_send", True))

    _log(
        f"wechat-script start contact={contact!r} message_len={len(message)} "
        f"send_mode={send_mode} focus_input={focus_input} "
        f"verify_send={verify_send} vision={'on' if gflags['send'] else 'off'}"
    )

    opened = open_session(contact, _log, t0, wcfg)
    if opened.get("status") != "ok":
        opened["elapsed_s"] = round(time.perf_counter() - t0, 2)
        snap = _snapshot_on_fail(_log, t0, wcfg, "open_session")
        if snap:
            opened["fail_screenshot"] = snap
        return opened
    display = str(opened.get("display") or contact)
    query = str(opened.get("query") or contact)

    def _paste_with_focus(attempt: int) -> bool:
        if focus_input:
            _log_step(_log, t0, f"focus chat input (attempt {attempt})")
            _focus_chat_input(_log, t0, wcfg, attempt=attempt)
            _clear_chat_input(_log, t0)
        _log_step(_log, t0, f"paste message ({len(message)} chars, attempt {attempt})")
        _critical_paste(message, log=_log, t0=t0, label="message")
        time.sleep(after_message_sleep)
        if not verify_send:
            _collapse_input_selection(_log, t0)
            return True
        # collapse_after：必须在发送前取消全选，否则 Return 会删掉正文
        probed = _probe_input_text(_log, t0, collapse_after=True)
        ok = _input_matches_message(probed, message)
        _log_step(
            _log,
            t0,
            f"paste verify: {'ok' if ok else 'FAIL'} "
            f"probed_len={len(probed)} expect_len={len(message)}",
        )
        return ok

    # 粘贴 + 校验（失败则换坐标再试一次）
    paste_ok = _paste_with_focus(1)
    if not paste_ok:
        _log_step(_log, t0, "paste verify failed, retry with click nudge")
        paste_ok = _paste_with_focus(2)
    if verify_send and not paste_ok:
        try:
            if focus_input:
                _focus_chat_input(_log, t0, wcfg, attempt=3)
            _clear_chat_input(_log, t0)
        except Exception:
            pass
        snap = _snapshot_on_fail(_log, t0, wcfg, "paste_verify")
        out = {
            "status": "fail",
            "reason": (
                f"粘贴校验失败：正文未进入「{display}」输入框"
                f"（搜索「{query}」）。可能焦点仍在搜索框。"
            ),
            "display": display,
            "query": query,
            "elapsed_s": round(time.perf_counter() - t0, 2),
        }
        if snap:
            out["fail_screenshot"] = snap
        return out

    def _do_send(attempt: int, *, collapse: bool = True) -> str:
        # 粘贴校验已 collapse；首次发送可跳过二次 collapse
        if collapse:
            _collapse_input_selection(_log, t0)
        _log_step(_log, t0, f"send mode={send_mode} (attempt {attempt})")
        # 成功路径：轻量前置 + 点输入 + PostToPid 发键（不因 frontmost 失败而空转重试）
        # 真正没发出去由 verify_send 检测后再 hard 重试
        act.ensure_front("WeChat", settle=0.04, retries=1, hard=(attempt > 1))
        if focus_input:
            bounds = _wechat_window_bounds()
            if bounds:
                (px, py), (sw, sh) = bounds
                x = px + sw * float(wcfg.get("input_click_x_ratio") or 0.58)
                y = py + sh - float(wcfg.get("input_click_bottom_inset") or 70)
                ax.click_xy(x, y)
                time.sleep(0.04)
                if attempt == 1:
                    _log_step(_log, t0, f"send: re-click input ({x:.0f},{y:.0f})")
        send_result = act.send_chat(app_name="WeChat", mode=send_mode, ensure=False)
        _log_step(_log, t0, str(send_result))
        time.sleep(0.18)
        return str(send_result)

    # 粘贴探测刚 collapse 过，首次发送不再重复
    _do_send(1, collapse=False)

    send_verified = not verify_send
    if verify_send:
        probed_after = _probe_input_text(_log, t0, collapse_after=False)
        if _input_still_has_message(probed_after, message):
            _log_step(_log, t0, "send verify: input still has message, resend once")
            # 轻量重试：先 collapse 再发；仍在则点输入框，丢字才重贴
            _collapse_input_selection(_log, t0)
            _do_send(2, collapse=False)
            probed_after = _probe_input_text(_log, t0, collapse_after=False)
            if _input_still_has_message(probed_after, message) and focus_input:
                _focus_chat_input(_log, t0, wcfg, attempt=2)
                re_probe = _probe_input_text(_log, t0, collapse_after=True)
                if not _input_matches_message(re_probe, message):
                    _log_step(_log, t0, "resend: re-paste message before final try")
                    _clear_chat_input(_log, t0)
                    _critical_paste(message, log=_log, t0=t0, label="message-retry")
                    time.sleep(after_message_sleep)
                    _collapse_input_selection(_log, t0)
                _do_send(3, collapse=False)
                probed_after = _probe_input_text(_log, t0, collapse_after=False)
        if _input_still_has_message(probed_after, message):
            snap = _snapshot_on_fail(_log, t0, wcfg, "send_verify")
            out = {
                "status": "fail",
                "reason": (
                    f"发送校验失败：输入框仍残留正文，未能确认发给「{display}」"
                    f"（搜索「{query}」，mode={send_mode}）。"
                ),
                "display": display,
                "query": query,
                "elapsed_s": round(time.perf_counter() - t0, 2),
            }
            if snap:
                out["fail_screenshot"] = snap
            return out
        send_verified = True
        _log_step(_log, t0, "send verify: ok (input cleared)")

    # 可选：仅 gates.send=true 时做视觉校验（默认关闭）
    if gflags["send"]:
        from macrun.gate import gate2_send_verify

        _log_step(_log, t0, "gate2: vision verify send (optional)")
        try:
            gate2 = gate2_send_verify(display, message, log=_log)
            _log_step(
                _log,
                t0,
                f"gate2 sent={gate2.get('sent')} reason={gate2.get('reason')}",
            )
            if not gate2.get("sent"):
                return {
                    "status": "fail",
                    "reason": (
                        f"Gate2 判定未成功发送给「{display}」（搜索「{query}」）"
                        f"（{gate2.get('reason') or 'unverified'}）"
                    ),
                    "display": display,
                    "query": query,
                    "gate2": gate2,
                    "elapsed_s": round(time.perf_counter() - t0, 2),
                }
        except Exception as e:
            return {
                "status": "fail",
                "reason": f"Gate2 视觉验收失败：{e}",
                "display": display,
                "query": query,
                "elapsed_s": round(time.perf_counter() - t0, 2),
            }

    elapsed = time.perf_counter() - t0
    verify_note = "剪贴板校验" if send_verified and verify_send else "未校验"
    if gflags["send"]:
        verify_note = f"{verify_note}+视觉"
    result = (
        f"已向「{display}」发送消息（搜索「{query}」，{len(message)} 字，"
        f"{elapsed:.1f}s，mode={send_mode}，{verify_note}）。"
    )
    _log(f"FINISH: {result}")
    return {
        "status": "success",
        "result": result,
        "contact": display,
        "display": display,
        "query": query,
        "message": message,
        "mode": "wechat-remark-suffix",
        "send_mode": send_mode,
        "verify_send": verify_send,
        "paste_verified": bool(verify_send and paste_ok),
        "send_verified": bool(send_verified and verify_send),
        "elapsed_s": round(elapsed, 2),
    }


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
    """备注后缀打开会话 + 截图落盘（不调视觉模型）。

    last_n 保留兼容 CLI，当前不解析消息条数，仅截当前可见聊天窗口。
    默认保存到 /tmp/wechat_screenshot_{会话}_{YYYYMMDD_HHMMSS}.jpg（缩放+JPEG）。
    """

    def _log(msg: str) -> None:
        if log:
            log(msg)
        else:
            print(msg, flush=True)

    t0 = _ts()
    session = (session or "").strip()
    # 兼容旧 CLI 参数，读消息截图模式不再按条数 OCR
    _ = max(1, min(int(last_n or 5), 30))
    if not session:
        return {"status": "fail", "reason": "session empty"}

    wcfg = config if config is not None else _wechat_cfg()
    scroll = bool(wcfg.get("read_scroll_once", False))
    # 人工识别优先：默认最长边 1600、JPEG 质量 80
    max_side = int(wcfg.get("read_screenshot_max_side") or 1600)
    jpeg_q = int(wcfg.get("read_screenshot_jpeg_quality") or 80)
    compress = bool(wcfg.get("read_screenshot_compress", True))
    _log(f"wechat-read start session={session!r} mode=screenshot-only")

    opened = open_session(session, _log, t0, wcfg)
    if opened.get("status") != "ok":
        opened["elapsed_s"] = round(time.perf_counter() - t0, 2)
        return opened
    display = str(opened.get("display") or session)
    query = str(opened.get("query") or session)
    # 用口语展示名（非搜索 query）生成唯一文件名，避免覆盖
    shot_path = build_read_screenshot_path(display, wcfg)

    act.ensure_front("WeChat", settle=0.25)
    time.sleep(0.15)
    if not _is_wechat_front():
        act.ensure_front("WeChat", settle=0.3)
        time.sleep(0.12)

    # 可选轻微上滚，露出更多历史后再截（默认关，更快）
    if scroll:
        _log_step(_log, t0, "scroll up once before screenshot")
        for _ in range(3):
            act.hotkey("up", app_name="WeChat", ensure=False, settle=0.02)
            time.sleep(0.05)
        time.sleep(0.2)

    _log_step(
        _log,
        t0,
        f"screenshot chat window → {shot_path} "
        f"(compress={compress} max_side={max_side} q={jpeg_q})",
    )
    try:
        saved = vision.capture_front_window_to(
            dest=shot_path,
            owner_names=["WeChat", "微信", "Weixin"],
            max_side=max_side,
            quality=jpeg_q,
            compress=compress,
        )
    except Exception as e:
        return {
            "status": "fail",
            "reason": (
                f"截取「{display}」聊天窗口失败：{e}。"
                f"请确认已进入会话（备注「{query}」）且已授权屏幕录制。"
            ),
            "display": display,
            "query": query,
            "elapsed_s": round(time.perf_counter() - t0, 2),
        }

    size = Path(saved).stat().st_size
    _log_step(_log, t0, f"screenshot saved bytes={size} path={saved}")

    note = (
        f"微信会话「{display}」聊天窗口截图已保存：\n"
        f"{saved}\n"
        f"（搜索「{query}」，无视觉 OCR；请打开图片查看记录）\n"
    )
    if to_clipboard:
        act.set_clipboard(note)
        _log_step(_log, t0, f"clipboard set path note ({len(note)} chars)")

    elapsed = time.perf_counter() - t0
    summary = (
        f"已打开「{display}」并截图保存到 {saved}"
        f"（搜索「{query}」，{elapsed:.1f}s，无视觉模型）。"
    )
    _log(f"FINISH: {summary}")
    return {
        "status": "success",
        "result": summary,
        "session": display,
        "display": display,
        "query": query,
        "screenshot_path": str(saved),
        "clipboard_text": note if to_clipboard else "",
        "messages": [],
        "elapsed_s": round(elapsed, 2),
        "mode": "wechat-read-screenshot",
    }
