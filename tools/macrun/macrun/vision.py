# -*- coding: utf-8 -*-
"""截图（失败时使用）；压缩后上传，避免视觉 API 超时。"""

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
    r = subprocess.run(
        ["screencapture", "-x", str(path)],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0 or not path.is_file():
        raise RuntimeError(f"screencapture failed: {r.stderr or r.stdout}")
    time.sleep(0.05)
    return path


def _compress_for_llm(src: Path, max_side: int = 1280, quality: int = 55) -> Path:
    """用 macOS sips 缩成 JPEG，显著减小 base64 体积与上传时间。"""
    out = src.with_suffix(".jpg")
    r = subprocess.run(
        [
            "sips",
            "-Z",
            str(max_side),
            "-s",
            "format",
            "jpeg",
            "-s",
            "formatOptions",
            str(quality),
            str(src),
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0 or not out.is_file() or out.stat().st_size == 0:
        # 压缩失败则退回原 PNG
        return src
    return out


def capture_b64(max_side: int = 1280, quality: int = 55) -> tuple[str, str]:
    """返回 (base64, mime_subtype) 如 ('...','jpeg')。"""
    p = capture_screen_png()
    try:
        compressed = _compress_for_llm(p, max_side=max_side, quality=quality)
        data = compressed.read_bytes()
        mime = "jpeg" if compressed.suffix.lower() in (".jpg", ".jpeg") else "png"
        if compressed != p:
            try:
                compressed.unlink(missing_ok=True)
            except Exception:
                pass
        return base64.b64encode(data).decode("ascii"), mime
    finally:
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass
