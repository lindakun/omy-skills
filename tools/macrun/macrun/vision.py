# -*- coding: utf-8 -*-
"""截图（失败时使用）。"""

from __future__ import annotations

import base64
import subprocess
import tempfile
import time
from pathlib import Path


def capture_screen_png(path: str | Path | None = None) -> Path:
    if path is None:
        fd, name = tempfile.mkstemp(prefix="macrun_", suffix=".png")
        import os

        os.close(fd)
        path = Path(name)
    else:
        path = Path(path)
    # -x 静音；全屏
    r = subprocess.run(
        ["screencapture", "-x", str(path)],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0 or not path.is_file():
        raise RuntimeError(f"screencapture failed: {r.stderr or r.stdout}")
    # 极短等待确保文件落盘
    time.sleep(0.05)
    return path


def capture_b64() -> str:
    p = capture_screen_png()
    try:
        data = p.read_bytes()
        return base64.b64encode(data).decode("ascii")
    finally:
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass
