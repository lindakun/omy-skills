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

SYSTEM_PROMPT = """你是 macOS 桌面自动化控制器。根据用户 goal 与当前 Accessibility(AX) 控件树，每步只输出 **一个** JSON 动作（不要 markdown 围栏）。

可用 action：
- open_app: {"action":"open_app","app":"Notes|TextEdit|WeChat|Safari|..."}
- activate_app: {"action":"activate_app","app":"WeChat"}  // 强制前置已打开的 App（宿主抢焦点时必用）
- click: {"action":"click","id":123} 或 {"action":"click","name":"按钮文字","role":"AXButton"}
- click_xy: {"action":"click_xy","x":100,"y":200}  // 仅截图后且无可靠 id 时使用
- type: {"action":"type","text":"..."}
- clipboard_paste: {"action":"clipboard_paste","text":"..."}  // 中文/微信必须用这个
- hotkey: {"action":"hotkey","keys":["cmd","f"]}  // 微信搜索常用 cmd+f 或 cmd+k 视版本
- wait: {"action":"wait","seconds":1.0}
- finish: {"action":"finish","result":"给用户的结果摘要"}
- fail: {"action":"fail","reason":"..."}
- need_screenshot: {"action":"need_screenshot","reason":"..."}

规则：
1. 优先用 AX 的 id 点击；不要臆造 id。
2. 中文输入、微信发消息：必须用 clipboard_paste，不要 type 直接敲中文。
3. 微信：open_app WeChat 一次即可；若 ax_tree 显示 WorkBuddy/Cursor/Terminal 等宿主，先 activate_app WeChat，不要反复 open_app。
4. 不要连续多次 open_app 同一应用；打开后应 click/clipboard_paste/hotkey 推进任务。
5. 目标完成后立刻 finish。
6. 禁止危险操作（清空废纸篓、抹盘、sudo rm 等）。
7. 控件树为空或明显是错误应用时，先 activate_app 目标，再 need_screenshot。
8. 观察上下文里的 target_app / observed_app / running_hint 很重要。
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
                        "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                    },
                ],
            }
            msgs = msgs[:-1] + [last]
    resp = client.chat.completions.create(
        model=model,
        messages=msgs,
        temperature=temperature,
        max_tokens=max_tokens,
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
    if name == "open_app":
        app = str(action.get("app") or action.get("name") or "")
        result = act.open_app(app)
        # 从结果解析 pid
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
        state["target_app"] = app
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
        return act.click_xy(float(action["x"]), float(action["y"]))
    if name == "type":
        return act.type_text(str(action.get("text") or ""), prefer_clipboard=True)
    if name in ("clipboard_paste", "clipboard_type"):
        return act.clipboard_type(str(action.get("text") or ""))
    if name == "hotkey":
        keys = action.get("keys") or []
        if isinstance(keys, str):
            keys = keys.replace("+", " ").split()
        return act.hotkey(*[str(k) for k in keys])
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

    base_url = str(llm.get("api_base") or "https://api.openai.com/v1").rstrip("/")
    if base_url.endswith("/chat/completions"):
        base_url = base_url[: -len("/chat/completions")]
    model = str(llm.get("model") or "gpt-4o")
    temperature = float(llm.get("temperature") or 0.1)
    max_tokens = int(llm.get("max_tokens") or 1200)
    timeout = float(llm.get("timeout") or 120)

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

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

    history: list[dict[str, Any]] = []
    last_error: str | None = None
    force_screenshot = False
    open_counts: dict[str, int] = {}

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
        # 微信等 AX 极稀疏：节点过少视为「树不可用」，自动截图（仍非每步全量截图策略的例外）
        tname = str(state.get("target_app") or app_info.get("name") or "").lower()
        if any(k in tname for k in ("wechat", "微信")) and len(nodes) < 12:
            need_shot = True
            if step == 1 or len(nodes) < 12:
                _log(f"STEP {step} sparse AX for WeChat (nodes={len(nodes)}), attach screenshot")
        force_screenshot = False

        image_b64 = None
        if need_shot:
            try:
                image_b64 = vision.capture_b64()
                _log(f"STEP {step} screenshot attached (failure/empty tree path)")
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
            raw = _llm_decide(
                client,
                model,
                messages,
                temperature,
                max_tokens,
                image_b64=image_b64,
            )
            action = _parse_action(raw)
        except Exception as e:
            last_error = f"LLM/parse error: {e}"
            _log(f"STEP {step} {last_error}")
            if shot_on_fail:
                force_screenshot = True
            time.sleep(step_delay)
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
