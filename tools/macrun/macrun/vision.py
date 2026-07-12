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


def capture_front_window_png(
    owner_names: list[str] | None = None,
    path: str | Path | None = None,
) -> Path:
    """截取指定 App 前台窗口（避免把 IDE/WorkBuddy 全屏截进去）。

    owner_names: 窗口所属进程名子串列表，默认微信。
    """
    import os

    owner_names = owner_names or ["WeChat", "微信", "Weixin"]
    if path is None:
        fd, name = tempfile.mkstemp(prefix="macrun_win_", suffix=".png")
        os.close(fd)
        path = Path(name)
    else:
        path = Path(path)

    wid = None
    try:
        from Quartz import (  # type: ignore
            CGWindowListCopyWindowInfo,
            kCGNullWindowID,
            kCGWindowListExcludeDesktopElements,
            kCGWindowListOptionOnScreenOnly,
        )

        opts = kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements
        windows = CGWindowListCopyWindowInfo(opts, kCGNullWindowID) or []
        best = None
        for w in windows:
            owner = str(w.get("kCGWindowOwnerName") or "")
            layer = int(w.get("kCGWindowLayer") or 0)
            bounds = w.get("kCGWindowBounds") or {}
            w_h = float(bounds.get("Height") or 0)
            w_w = float(bounds.get("Width") or 0)
            if layer != 0:
                continue
            if w_h < 80 or w_w < 80:
                continue
            if any(n.lower() in owner.lower() for n in owner_names):
                # 优先面积最大的窗口
                area = w_h * w_w
                if best is None or area > best[0]:
                    best = (area, int(w.get("kCGWindowNumber")))
        if best:
            wid = best[1]
    except Exception:
        wid = None

    if wid is not None:
        r = subprocess.run(
            ["screencapture", "-x", f"-l{wid}", str(path)],
            capture_output=True,
            text=True,
        )
        if r.returncode == 0 and path.is_file() and path.stat().st_size > 0:
            time.sleep(0.05)
            return path

    # fallback 全屏
    return capture_screen_png(path)


def capture_b64(
    max_side: int = 1280,
    quality: int = 55,
    app_window: bool = False,
    owner_names: list[str] | None = None,
) -> tuple[str, str]:
    """返回 (base64, mime_subtype) 如 ('...','jpeg')。

    app_window=True 时优先截微信等目标窗口，避免 IDE 抢镜。
    """
    if app_window:
        p = capture_front_window_png(owner_names=owner_names)
    else:
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
