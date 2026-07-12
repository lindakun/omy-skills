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
- click: {"action":"click","id":123} 或 {"action":"click","name":"按钮文字","role":"AXButton"}
- click_xy: {"action":"click_xy","x":100,"y":200}
- type: {"action":"type","text":"..."}  // 中文会自动走剪贴板
- clipboard_paste: {"action":"clipboard_paste","text":"..."}  // 强制 pbcopy+Cmd+V
- hotkey: {"action":"hotkey","keys":["cmd","v"]}
- wait: {"action":"wait","seconds":1.0}
- finish: {"action":"finish","result":"给用户的结果摘要"}
- fail: {"action":"fail","reason":"..."}

规则：
1. 优先用 AX 的 id 点击；不要臆造 id。
2. 中文输入、微信发消息：必须用 clipboard_paste，不要用 type 直接敲中文。
3. 微信：先 open_app WeChat，再用搜索/剪贴板流程；AX 残缺时可 hotkey。
4. 目标完成后立刻 finish。
5. 不要清空废纸篓、抹盘、sudo 删除等危险操作。
6. 若控件树为空或看不懂，可 {"action":"need_screenshot","reason":"..."} 请求截图后再决策。
"""


def _safety_blocked(goal: str, config: dict[str, Any]) -> str | None:
    phrases = (config.get("safety") or {}).get("blocked_phrases") or []
    g = goal.lower()
    for p in phrases:
        if str(p).lower() in g:
            return str(p)
    return None


def _parse_action(text: str) -> dict[str, Any]:
    text = text.strip()
    # 去掉 ```json
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    # 截取第一个 JSON 对象
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
        # 把最后一条 user 改成 multimodal
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
                            "url": f"data:image/png;base64,{image_b64}",
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
    )
    return (resp.choices[0].message.content or "").strip()


def execute_action(
    action: dict[str, Any],
    nodes: list[dict[str, Any]],
    pid: int | None,
) -> str:
    name = str(action.get("action") or "").lower().strip()
    if name == "open_app":
        return act.open_app(str(action.get("app") or action.get("name") or ""))
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
    if not api_key or api_key_is_placeholder({**config, "llm": {**(config.get("llm") or {}), "api_key": api_key}}):
        # resolve may fix env; re-check raw
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
    # OpenAI SDK 期望 base 不含 /chat/completions
    if base_url.endswith("/chat/completions"):
        base_url = base_url[: -len("/chat/completions")]
    model = str(llm.get("model") or "gpt-4o")
    temperature = float(llm.get("temperature") or 0.1)
    max_tokens = int(llm.get("max_tokens") or 1200)
    timeout = float(llm.get("timeout") or 120)

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

    _log(f"macrun start goal={goal!r}")
    _log(f"config={config.get('_config_path')} model={model}")
    if not ax.is_trusted():
        _log("WARN: Accessibility not trusted — actions may fail")

    history: list[dict[str, Any]] = []
    last_error: str | None = None
    force_screenshot = False

    for step in range(1, max_steps + 1):
        app_info = {}
        nodes: list[dict[str, Any]] = []
        tree_text = "(no tree)"
        try:
            app_info = ax.frontmost_app_info()
            nodes = ax.dump_tree(
                pid=app_info.get("pid"),
                max_nodes=max_nodes,
                max_depth=max_depth,
            )
            tree_text = ax.tree_to_text(nodes, app_info)
        except Exception as e:
            last_error = str(e)
            tree_text = f"(AX error: {e})"
            _log(f"STEP {step} AX error: {e}")

        need_shot = force_screenshot
        if shot_when_empty and len(nodes) == 0:
            need_shot = True
        if last_error and shot_on_fail:
            need_shot = True
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
            result = execute_action(action, nodes, app_info.get("pid"))
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
