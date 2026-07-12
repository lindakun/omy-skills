# -*- coding: utf-8 -*-
"""加载 macrun 配置。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

PLACEHOLDER_KEYS = (
    "YOUR_VOLC_ARK_API_KEY",
    "sk-YOUR_KEY_HERE",
    "YOUR_API_KEY",
)


def default_config_path() -> Path | None:
    env = os.environ.get("MACRUN_CONFIG")
    if env and Path(env).is_file():
        return Path(env)

    here = Path(__file__).resolve().parent.parent  # tools/macrun
    local = here / "config.local.yaml"
    if local.is_file():
        return local

    template = here / "config.template.yaml"
    if template.is_file():
        return template
    return None


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    p = Path(path) if path else default_config_path()
    if not p or not p.is_file():
        raise FileNotFoundError(
            "找不到配置文件。请设置 MACRUN_CONFIG 或运行 scripts/install-mac.sh"
        )
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    data["_config_path"] = str(p.resolve())
    return data


def api_key_is_placeholder(config: dict[str, Any]) -> bool:
    key = str((config.get("llm") or {}).get("api_key") or "")
    if not key.strip():
        return True
    return any(ph in key for ph in PLACEHOLDER_KEYS)


def resolve_api_key(config: dict[str, Any]) -> str:
    llm = config.get("llm") or {}
    key = str(llm.get("api_key") or "")
    if api_key_is_placeholder(config):
        env_key = os.environ.get("VOLC_ARK_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if env_key:
            return env_key
    return key
