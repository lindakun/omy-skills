# -*- coding: utf-8 -*-
"""截图（失败时使用）；压缩后上传，避免视觉 API 超时。"""

from __future__ import annotations

import base64
import shutil
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


def _sips_to_jpeg(
    src: Path,
    out: Path,
    max_side: int = 1600,
    quality: int = 80,
) -> Path | None:
    """用 macOS sips 缩放 + JPEG。失败返回 None。"""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "sips",
        "-s",
        "format",
        "jpeg",
        "-s",
        "formatOptions",
        str(max(1, min(int(quality), 100))),
        str(src),
        "--out",
        str(out),
    ]
    # -Z：最长边不超过 max_side；<=0 表示不缩放
    if max_side and int(max_side) > 0:
        cmd = ["sips", "-Z", str(int(max_side))] + cmd[1:]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not out.is_file() or out.stat().st_size == 0:
        return None
    return out


def _compress_for_llm(src: Path, max_side: int = 1280, quality: int = 55) -> Path:
    """用 macOS sips 缩成 JPEG，显著减小 base64 体积与上传时间。"""
    out = src.with_suffix(".jpg")
    result = _sips_to_jpeg(src, out, max_side=max_side, quality=quality)
    return result if result is not None else src


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


# 读微信聊天记录默认落盘（JPEG，兼顾人工可读与体积）
DEFAULT_WECHAT_SCREENSHOT = Path("/tmp/wechat_screenshot.jpg")
# 人工识别：约 1600 边长 + q80，Retina 聊天文字仍清晰，体积远小于原 PNG
DEFAULT_READ_MAX_SIDE = 1600
DEFAULT_READ_JPEG_QUALITY = 80


def capture_front_window_to(
    dest: str | Path | None = None,
    owner_names: list[str] | None = None,
    max_side: int | None = DEFAULT_READ_MAX_SIDE,
    quality: int | None = DEFAULT_READ_JPEG_QUALITY,
    compress: bool = True,
) -> Path:
    """截取目标 App 前台窗口并保存到 dest。

    默认：缩放最长边 + JPEG 压缩，便于人工查看、体积可控。
    compress=False 时保存原始 PNG（体积大）。
    """
    dest_path = Path(dest) if dest else DEFAULT_WECHAT_SCREENSHOT
    # 压缩时统一落成 .jpg（配置若仍写 .png 也自动改后缀，避免 JPEG 内容却叫 png）
    if compress and dest_path.suffix.lower() not in (".jpg", ".jpeg"):
        dest_path = dest_path.with_suffix(".jpg")
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    tmp = capture_front_window_png(owner_names=owner_names)
    try:
        if compress:
            side = DEFAULT_READ_MAX_SIDE if max_side is None else int(max_side)
            q = DEFAULT_READ_JPEG_QUALITY if quality is None else int(quality)
            # 写到临时 jpg 再替换目标，避免半截文件
            fd, tmp_jpg_name = tempfile.mkstemp(prefix="macrun_chat_", suffix=".jpg")
            import os

            os.close(fd)
            tmp_jpg = Path(tmp_jpg_name)
            try:
                result = _sips_to_jpeg(tmp, tmp_jpg, max_side=side, quality=q)
                if result is not None:
                    shutil.move(str(result), str(dest_path))
                else:
                    # 压缩失败：退回原 PNG 路径旁路
                    fallback = dest_path.with_suffix(".png")
                    shutil.copy2(tmp, fallback)
                    dest_path = fallback
            finally:
                try:
                    tmp_jpg.unlink(missing_ok=True)
                except Exception:
                    pass
        else:
            if dest_path.suffix.lower() not in (".png",):
                dest_path = dest_path.with_suffix(".png")
            shutil.copy2(tmp, dest_path)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass

    if not dest_path.is_file() or dest_path.stat().st_size == 0:
        raise RuntimeError(f"screenshot empty: {dest_path}")
    return dest_path.resolve()


def capture_b64(
    max_side: int = 1280,
    quality: int = 55,
    app_window: bool = False,
    owner_names: list[str] | None = None,
) -> tuple[str, str]:
    """返回 (base64, mime_subtype) 如 ('...','jpeg')。

    app_window=True 时优先截微信等目标窗口，避免 IDE 抢镜。
    仅用于 Gate2 等视觉校验；读消息请用 capture_front_window_to。
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
