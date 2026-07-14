# -*- coding: utf-8 -*-
"""AX 为主的 LLM 桌面 agent 闭环。"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Callable

from openai import OpenAI

from macrun import act, ax, vision
from macrun.config import api_key_is_placeholder, load_config, resolve_api_key
from macrun.wechat import (
    is_wechat_read_goal,
    is_wechat_send_goal,
    parse_contact_and_message,
    parse_read_session,
    read_messages,
    send_message,
)

SYSTEM_PROMPT = """你是 macOS 桌面自动化控制器。根据用户 goal 与当前 Accessibility(AX) 控件树，每步只输出 **一个** JSON 动作（不要 markdown 围栏）。

可用 action：
- open_app / activate_app
- click（按 AX id/name）
- type / clipboard_paste / hotkey / wait
- finish / fail / need_screenshot

规则：
1. 优先 AX id；不要臆造 id。
2. 中文用 clipboard_paste。
3. **微信相关任务禁止 click_xy**（坐标乱点几乎必错）。微信发消息/读消息应由专用脚本处理；若你仍在处理微信，只用 hotkey/clipboard_paste/activate_app。
4. 非微信且无可靠 id 时才可用 click_xy。
5. 禁止危险操作。
"""

# goal 里提到的应用线索 → 规范名
_GOAL_APP_HINTS = [
    (["wechat", "微信"], "WeChat"),
    (["备忘录", "notes"], "Notes"),
    (["textedit", "文本编辑"], "TextEdit"),
    (["safari"], "Safari"),
    (["finder", "访达"], "Finder"),
    (["chrome"], "Google Chrome"),
    (["messages", "信息"], "Messages"),
]


def _infer_target_app(goal: str) -> str | None:
    g = goal.lower()
    for keys, app in _GOAL_APP_HINTS:
        for k in keys:
            if k.lower() in g or k in goal:
                return app
    return None


def _safety_blocked(goal: str, config: dict[str, Any]) -> str | None:
    phrases = (config.get("safety") or {}).get("blocked_phrases") or []
    g = goal.lower()
    for p in phrases:
        if str(p).lower() in g:
            return str(p)
    return None


def _parse_action(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise ValueError(f"LLM 未返回 JSON: {text[:200]}")
    return json.loads(m.group(0))


def _llm_decide(
    client: OpenAI,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float,
    max_tokens: int,
    image_b64: str | None = None,
    image_mime: str = "jpeg",
    timeout: float = 30,
) -> str:
    msgs = list(messages)
    if image_b64:
        last = msgs[-1]
        content = last.get("content", "")
        if isinstance(content, str):
            last = {
                "role": "user",
                "content": [
                    {"type": "text", "text": content},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/{image_mime};base64,{image_b64}",
                        },
                    },
                ],
            }
            msgs = msgs[:-1] + [last]
    resp = client.chat.completions.create(
        model=model,
        messages=msgs,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )
    return (resp.choices[0].message.content or "").strip()


def _observe(
    target_app: str | None,
    target_pid: int | None,
    max_nodes: int,
    max_depth: int,
    log: Callable[[str], None],
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    """
    观察策略：
    1) 若有 target_pid / target_app → 先 activate 再 dump 该 App
    2) 若 frontmost 是宿主（WorkBuddy 等）且目标 App 在运行 → 切到目标
    3) 否则 dump frontmost
    """
    front = {}
    try:
        front = ax.frontmost_app_info()
    except Exception as e:
        log(f"frontmost error: {e}")

    observed: dict[str, Any] = {}
    pid: int | None = target_pid

    # 解析目标
    if target_app and not pid:
        found = ax.find_app(name=target_app)
        if found:
            pid = int(found["pid"])
            observed = found

    # frontmost 是宿主且目标在跑 → 强制切目标
    if target_app and ax.is_host_app(front):
        try:
            observed = ax.activate_app(pid=pid, name=target_app)
            pid = int(observed["pid"])
            log(f"observe: host frontmost={front.get('name')}, activated target={observed.get('name')} pid={pid}")
        except Exception as e:
            log(f"observe: activate target failed: {e}")

    # 有 pid 则 dump 该进程；否则 frontmost
    if pid:
        try:
            # 再激活一次保证窗口前置
            if target_app:
                try:
                    ax.activate_app(pid=pid, name=target_app)
                except Exception:
                    pass
            nodes = ax.dump_tree(pid=pid, max_nodes=max_nodes, max_depth=max_depth)
            if not observed:
                observed = ax.find_app(name=target_app) or {"pid": pid, "name": target_app or ""}
            # 若树为空，fallback frontmost
            if not nodes and front.get("pid") and front.get("pid") != pid:
                log("observe: target tree empty, also noting frontmost")
            tree = ax.tree_to_text(nodes, observed or {"pid": pid})
            hint = ""
            if ax.is_host_app(front) and target_app:
                hint = f"\nNOTE: frontmost was host app {front.get('name')}; AX dumped target {target_app}."
            running = ax.find_app(name=target_app) if target_app else None
            if target_app:
                hint += f"\nrunning_hint: {running or 'target not in running regular apps'}"
            return observed or {"pid": pid}, nodes, tree + hint
        except Exception as e:
            log(f"observe target pid={pid} error: {e}")

    # fallback frontmost
    nodes = ax.dump_tree(
        pid=front.get("pid"),
        max_nodes=max_nodes,
        max_depth=max_depth,
    )
    tree = ax.tree_to_text(nodes, front)
    if target_app and ax.is_host_app(front):
        tree += (
            f"\nWARNING: observing host app {front.get('name')}. "
            f"Call activate_app {target_app} or open_app {target_app}."
        )
    return front, nodes, tree


def execute_action(
    action: dict[str, Any],
    nodes: list[dict[str, Any]],
    pid: int | None,
    state: dict[str, Any],
) -> str:
    name = str(action.get("action") or "").lower().strip()
    target = state.get("target_app")

    # 除 wait/finish 外，执行前再抢一次焦点（LLM 耗时内宿主常抢回前台）
    if name not in ("finish", "fail", "need_screenshot", "wait", "open_app", "activate_app"):
        if target:
            act.ensure_front(str(target))

    if name == "open_app":
        app = str(action.get("app") or action.get("name") or "")
        result = act.open_app(app)
        m = re.search(r"pid=(\d+)", result)
        if m:
            state["target_pid"] = int(m.group(1))
        state["target_app"] = act.resolve_app_name(app)
        found = ax.find_app(name=state["target_app"])
        if found:
            state["target_pid"] = int(found["pid"])
        return result
    if name == "activate_app":
        app = str(action.get("app") or action.get("name") or state.get("target_app") or "")
        info = ax.activate_app(name=app)
        state["target_app"] = act.resolve_app_name(app)
        state["target_pid"] = int(info["pid"])
        return f"activated {info.get('name')} pid={info.get('pid')}"
    if name == "click":
        node = None
        if action.get("id") is not None:
            node = ax.find_node(nodes, node_id=int(action["id"]))
        if node is None:
            node = ax.find_node(
                nodes,
                name=action.get("name"),
                role=action.get("role"),
            )
        if node is None:
            raise RuntimeError(f"click target not found: {action}")
        return act.click_node(node, pid=pid)
    if name == "click_xy":
        # 微信禁止坐标乱点
        t = str(state.get("target_app") or "").lower()
        if "wechat" in t or "微信" in t:
            raise RuntimeError("WeChat: click_xy forbidden; use wechat-send/wechat-read scripts")
        return act.click_xy(float(action["x"]), float(action["y"]))
    if name == "type":
        return act.type_text(
            str(action.get("text") or ""),
            prefer_clipboard=True,
            app_name=target,
        )
    if name in ("clipboard_paste", "clipboard_type"):
        return act.clipboard_type(str(action.get("text") or ""), app_name=target)
    if name == "send":
        mode = "both"
        try:
            mode = str((load_config().get("wechat") or {}).get("send_mode") or "enter")
        except Exception:
            pass
        return act.send_chat(app_name=target, mode=mode)
    if name == "hotkey":
        keys = action.get("keys") or []
        if isinstance(keys, str):
            keys = keys.replace("+", " ").split()
        keys = [str(k) for k in keys]
        keys_l = [k.lower() for k in keys]
        if keys_l in (["enter"], ["return"]) and state.get("pending_send"):
            state["pending_send"] = False
            mode = "both"
            try:
                mode = str((load_config().get("wechat") or {}).get("send_mode") or "enter")
            except Exception:
                pass
            return act.send_chat(app_name=target, mode=mode)
        return act.hotkey(*keys, app_name=target)
    if name == "wait":
        sec = float(action.get("seconds") or 1.0)
        time.sleep(sec)
        return f"waited {sec}s"
    if name in ("finish", "fail", "need_screenshot"):
        return name
    raise RuntimeError(f"unknown action: {name}")


def run_goal(
    goal: str,
    config_path: str | None = None,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    def _log(msg: str) -> None:
        if log:
            log(msg)
        else:
            print(msg, flush=True)

    config = load_config(config_path)
    blocked = _safety_blocked(goal, config)
    if blocked:
        _log(f"BLOCKED phrase: {blocked}")
        return {"status": "fail", "reason": f"blocked phrase: {blocked}"}

    api_key = resolve_api_key(config)
    if not api_key or any(p in api_key for p in ("YOUR_VOLC", "YOUR_API", "sk-YOUR")):
        return {
            "status": "fail",
            "reason": "API Key 仍是占位符。请配置 config.local.yaml 或 VOLC_ARK_API_KEY",
        }

    llm = config.get("llm") or {}
    agent_cfg = config.get("agent") or {}
    max_steps = int(agent_cfg.get("max_steps") or 20)
    max_nodes = int(agent_cfg.get("ax_max_nodes") or 80)
    max_depth = int(agent_cfg.get("ax_max_depth") or 6)
    step_delay = float(agent_cfg.get("step_delay") or 0.35)
    shot_on_fail = bool(agent_cfg.get("screenshot_on_failure", True))
    shot_when_empty = bool(agent_cfg.get("screenshot_when_tree_empty", True))
    sparse_every = int(agent_cfg.get("sparse_ax_screenshot_every") or 3)
    shot_max_side = int(agent_cfg.get("screenshot_max_side") or 1280)
    shot_quality = int(agent_cfg.get("screenshot_jpeg_quality") or 55)

    base_url = str(llm.get("api_base") or "https://api.openai.com/v1").rstrip("/")
    if base_url.endswith("/chat/completions"):
        base_url = base_url[: -len("/chat/completions")]
    model = str(llm.get("model") or "gpt-4o")
    temperature = float(llm.get("temperature") or 0.1)
    max_tokens = int(llm.get("max_tokens") or 1200)
    timeout = float(llm.get("timeout") or 30)
    vision_timeout = float(llm.get("vision_timeout") or 90)

    # 客户端默认用较长上限；单次请求再按是否带图覆盖
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=max(timeout, vision_timeout))

    state: dict[str, Any] = {
        "target_app": _infer_target_app(goal),
        "target_pid": None,
    }
    if state["target_app"]:
        found = ax.find_app(name=state["target_app"])
        if found:
            state["target_pid"] = int(found["pid"])

    _log(f"macrun start goal={goal!r}")
    _log(f"config={config.get('_config_path')} model={model}")
    _log(f"inferred target_app={state.get('target_app')} pid={state.get('target_pid')}")
    if not ax.is_trusted():
        _log("WARN: Accessibility not trusted — actions may fail")

    # 微信读消息 / 发消息：专用脚本，不走通用 click_xy Agent
    if is_wechat_read_goal(goal):
        session, last_n = parse_read_session(goal)
        _log(f"wechat-read mode session={session!r} last_n={last_n}")
        if session:
            return read_messages(session, last_n=last_n, log=_log)
        _log("wechat-read: parse session failed, fallback to LLM agent")

    if is_wechat_send_goal(goal):
        contact, message = parse_contact_and_message(goal)
        _log(f"wechat-script mode contact={contact!r} message_len={len(message or '')}")
        if contact and message:
            return send_message(contact, message, log=_log)
        _log("wechat-script: parse failed, fallback to LLM agent")

    history: list[dict[str, Any]] = []
    last_error: str | None = None
    force_screenshot = False
    open_counts: dict[str, int] = {}
    wechat_goal = state.get("target_app") == "WeChat" or ("微信" in goal)

    for step in range(1, max_steps + 1):
        app_info: dict[str, Any] = {}
        nodes: list[dict[str, Any]] = []
        tree_text = "(no tree)"
        try:
            app_info, nodes, tree_text = _observe(
                state.get("target_app"),
                state.get("target_pid"),
                max_nodes,
                max_depth,
                _log,
            )
            if app_info.get("pid") and state.get("target_app"):
                # 同步 pid
                if not ax.is_host_app(app_info):
                    state["target_pid"] = int(app_info["pid"])
        except Exception as e:
            last_error = str(e)
            tree_text = f"(AX error: {e})"
            _log(f"STEP {step} AX error: {e}")

        need_shot = force_screenshot
        if shot_when_empty and len(nodes) == 0:
            need_shot = True
        if last_error and shot_on_fail:
            need_shot = True
        # 微信等 AX 极稀疏：通用 Agent 兜底时**每步截图**（禁止盲开）；专用脚本不走这里
        tname = str(state.get("target_app") or app_info.get("name") or "").lower()
        sparse_app = any(k in tname for k in ("wechat", "微信")) or wechat_goal
        if sparse_app and len(nodes) < 12:
            need_shot = True
            _log(
                f"STEP {step} sparse AX (nodes={len(nodes)}), "
                f"force screenshot (WeChat fallback agent)"
            )
        force_screenshot = False

        image_b64 = None
        image_mime = "jpeg"
        if need_shot:
            try:
                image_b64, image_mime = vision.capture_b64(
                    max_side=shot_max_side,
                    quality=shot_quality,
                )
                _log(
                    f"STEP {step} screenshot attached "
                    f"(mime={image_mime}, timeout={vision_timeout}s)"
                )
            except Exception as e:
                _log(f"STEP {step} screenshot failed: {e}")

        user_blob = {
            "goal": goal,
            "step": step,
            "max_steps": max_steps,
            "target_app": state.get("target_app"),
            "target_pid": state.get("target_pid"),
            "observed_app": app_info,
            "last_error": last_error,
            "history": history[-6:],
            "ax_tree": tree_text,
        }
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(user_blob, ensure_ascii=False),
            },
        ]

        try:
            req_timeout = vision_timeout if image_b64 else timeout
            _log(
                f"STEP {step} calling LLM "
                f"(vision={'yes' if image_b64 else 'no'}, timeout={req_timeout}s)"
            )
            raw = _llm_decide(
                client,
                model,
                messages,
                temperature,
                max_tokens,
                image_b64=image_b64,
                image_mime=image_mime,
                timeout=req_timeout,
            )
            action = _parse_action(raw)
        except Exception as e:
            last_error = f"LLM/parse error: {e}"
            _log(f"STEP {step} {last_error}")
            if shot_on_fail:
                force_screenshot = True
            # 超时后稍等再试，避免连打
            time.sleep(max(step_delay, 0.8))
            continue

        _log(f"STEP {step} action={json.dumps(action, ensure_ascii=False)}")
        aname = str(action.get("action") or "").lower()

        # 防止 open_app 死循环
        if aname == "open_app":
            app_key = str(action.get("app") or action.get("name") or "").lower()
            open_counts[app_key] = open_counts.get(app_key, 0) + 1
            if open_counts[app_key] > 2:
                _log(f"STEP {step} coerce open_app -> activate_app (opened {open_counts[app_key]} times)")
                action = {"action": "activate_app", "app": action.get("app") or action.get("name")}
                aname = "activate_app"

        # 微信：模型若在 pending_send 时直接 finish，先强制 send 一次
        if aname == "finish" and state.get("pending_send") and state.get("target_app"):
            tname = str(state.get("target_app") or "").lower()
            if "wechat" in tname or "微信" in tname:
                _log(f"STEP {step} coerce finish -> send first (message may still be in input)")
                try:
                    send_result = act.send_chat(app_name=state.get("target_app"))
                    history.append(
                        {"action": {"action": "send"}, "result": send_result}
                    )
                    _log(f"STEP {step} ok: {send_result}")
                    state["pending_send"] = False
                except Exception as e:
                    _log(f"STEP {step} auto-send error: {e}")

        if aname == "finish":
            result = action.get("result") or action.get("message") or "done"
            _log(f"FINISH: {result}")
            return {"status": "success", "result": result, "steps": step}

        if aname == "fail":
            reason = action.get("reason") or "failed"
            _log(f"FAIL: {reason}")
            return {"status": "fail", "reason": reason, "steps": step}

        if aname == "need_screenshot":
            force_screenshot = True
            history.append({"action": action, "result": "will_screenshot"})
            last_error = action.get("reason") or "need_screenshot"
            continue

        try:
            result = execute_action(
                action,
                nodes,
                state.get("target_pid") or app_info.get("pid"),
                state,
            )
            history.append({"action": action, "result": result})
            last_error = None
            _log(f"STEP {step} ok: {result}")

            # 粘贴正文成功后：下一次裸 enter / 误 finish 应走 send
            if aname in ("clipboard_paste", "clipboard_type", "type"):
                text = str(action.get("text") or "")
                if len(text) >= 4 or any(ch in text for ch in "。！？~～!?😊👋嗨"):
                    state["pending_send"] = True
                    _log(f"STEP {step} mark pending_send after paste body")
            if aname == "send" or (
                aname == "hotkey" and "send_chat" in str(result)
            ):
                state["pending_send"] = False
        except Exception as e:
            last_error = str(e)
            history.append({"action": action, "result": f"error: {e}"})
            _log(f"STEP {step} error: {e}")
            if shot_on_fail:
                force_screenshot = True

        time.sleep(step_delay)

    _log("TIMEOUT: max steps reached")
    return {
        "status": "fail",
        "reason": "max steps reached",
        "last_error": last_error,
        "history": history[-5:],
    }
