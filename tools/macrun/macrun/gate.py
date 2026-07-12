# -*- coding: utf-8 -*-
"""关卡式视觉验收：只判断、不自由点击。"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from openai import OpenAI

from macrun import vision
from macrun.config import load_config, resolve_api_key


def _client_and_model(
    *,
    max_side_override: int | None = None,
    quality_override: int | None = None,
) -> tuple[OpenAI, str, float, int, int, int]:
    cfg = load_config()
    llm = cfg.get("llm") or {}
    agent = cfg.get("agent") or {}
    wcfg = cfg.get("wechat") or {}
    key = resolve_api_key(cfg)
    if not key or any(p in key for p in ("YOUR_VOLC", "YOUR_API", "sk-YOUR")):
        raise RuntimeError("API Key 无效，无法做视觉 Gate")
    base = str(llm.get("api_base") or "https://api.openai.com/v1").rstrip("/")
    if base.endswith("/chat/completions"):
        base = base[: -len("/chat/completions")]
    model = str(llm.get("model") or "gpt-4o")
    # Gate 专用超时（默认 60，避免 90s×重试拖到数分钟）
    vision_timeout = float(
        wcfg.get("gate_timeout") or llm.get("vision_timeout") or 60
    )
    max_side = int(
        max_side_override
        or wcfg.get("gate_max_side")
        or agent.get("screenshot_max_side")
        or 960
    )
    quality = int(
        quality_override
        or wcfg.get("gate_jpeg_quality")
        or agent.get("screenshot_jpeg_quality")
        or 45
    )
    # 禁止 SDK 自动重试，否则一次超时会乘 2～3
    client = OpenAI(
        api_key=key,
        base_url=base,
        timeout=vision_timeout,
        max_retries=0,
    )
    return client, model, vision_timeout, max_side, quality, int(llm.get("max_tokens") or 300)


def _parse_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise ValueError(f"Gate 未返回 JSON: {text[:200]}")
    return json.loads(m.group(0))


def _ask_vision(
    prompt: str,
    log: Callable[[str], None] | None = None,
    *,
    max_side: int | None = None,
    quality: int | None = None,
) -> dict[str, Any]:
    client, model, timeout, side, q, max_tokens = _client_and_model(
        max_side_override=max_side,
        quality_override=quality,
    )
    b64, mime = vision.capture_b64(max_side=side, quality=q)
    if log:
        log(f"gate: screenshot mime={mime} side={side} q={q} timeout={timeout}s")
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "你是 UI 验收器。只根据截图判断，只输出一个 JSON 对象，不要 markdown。"
                    "不要建议点击坐标。用最短 JSON。"
                ),
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/{mime};base64,{b64}"},
                    },
                ],
            },
        ],
        temperature=0.0,
        max_tokens=max_tokens,
        timeout=timeout,
    )
    raw = (resp.choices[0].message.content or "").strip()
    if log:
        log(f"gate: raw={raw[:300]}")
    return _parse_json(raw)


def gate1_search_contact(
    contact: str,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Gate1：搜索后是否出现目标联系人/会话。

    返回：
      matched: bool
      row: int  # 1-based，从结果列表顶部往下数
      title: str
      confidence: float 0-1
      reason: str
    """
    prompt = f"""当前是 macOS 微信界面截图，用户刚搜索联系人/会话。
目标名称：「{contact}」

请判断搜索结果/会话列表中是否出现可匹配的目标（允许简称，如「文件传输助手」）。
若匹配，给出从上往下第几项（第一项 row=1，仅计可见结果行，不含搜索框本身）。

只输出 JSON：
{{
  "matched": true/false,
  "row": 1,
  "title": "你看到的名称",
  "confidence": 0.0到1.0,
  "reason": "一句话"
}}
若完全看不到微信或搜索 UI，matched=false。
"""
    try:
        data = _ask_vision(prompt, log=log)
    except Exception as e:
        # 一次缩小图重试
        if log:
            log(f"gate1: vision error {e}, retry smaller")
        data = _ask_vision(prompt, log=log, max_side=720, quality=40)
    matched = bool(data.get("matched"))
    try:
        row = int(data.get("row") or 0)
    except Exception:
        row = 0
    conf = float(data.get("confidence") or 0.0)
    # 低置信度视为失败（按用户要求：失败直接 FAIL，不盲进）
    if matched and conf < 0.55:
        matched = False
        data["reason"] = f"confidence too low ({conf}): {data.get('reason')}"
    if matched and row < 1:
        row = 1
    return {
        "matched": matched,
        "row": row if matched else 0,
        "title": str(data.get("title") or ""),
        "confidence": conf,
        "reason": str(data.get("reason") or ""),
        "gate": "gate1_search",
    }


def gate2_send_verify(
    contact: str,
    message: str,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Gate2：发送后是否像已发出。

    返回：
      sent: bool
      in_chat: bool  # 是否像在目标会话
      input_emptyish: bool  # 输入框是否大致清空
      confidence: float
      reason: str
    """
    preview = message.replace("\n", " ").strip()
    if len(preview) > 40:
        preview = preview[:40] + "…"
    prompt = f"""当前是 macOS 微信界面截图，用户刚尝试向「{contact}」发送消息。
消息预览：「{preview}」

请判断：
1) 是否已进入与目标相关的聊天会话（标题/头像区域像该联系人或文件传输助手等）
2) 底部输入框是否大致为空（消息已发出），还是仍残留刚输入的正文
3) 综合是否认为发送成功

只输出 JSON：
{{
  "sent": true/false,
  "in_chat": true/false,
  "input_emptyish": true/false,
  "confidence": 0.0到1.0,
  "reason": "一句话"
}}
若截图不是微信或无法判断，sent=false。
"""
    try:
        data = _ask_vision(prompt, log=log)
    except Exception as e:
        if log:
            log(f"gate2: vision error {e}, retry smaller")
        data = _ask_vision(prompt, log=log, max_side=720, quality=40)
    sent = bool(data.get("sent"))
    conf = float(data.get("confidence") or 0.0)
    in_chat = bool(data.get("in_chat"))
    empty = bool(data.get("input_emptyish"))
    # 收紧：低置信度或明显未在会话/输入框仍有内容 → 失败
    if sent and conf < 0.55:
        sent = False
        data["reason"] = f"confidence too low ({conf}): {data.get('reason')}"
    if sent and not in_chat:
        sent = False
        data["reason"] = f"not in target chat: {data.get('reason')}"
    if sent and not empty:
        # 输入框仍像有字，大概率没发出
        sent = False
        data["reason"] = f"input still has text: {data.get('reason')}"
    return {
        "sent": sent,
        "in_chat": in_chat,
        "input_emptyish": empty,
        "confidence": conf,
        "reason": str(data.get("reason") or ""),
        "gate": "gate2_send",
    }
