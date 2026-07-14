# -*- coding: utf-8 -*-
"""读消息截图路径命名单测。"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macrun.wechat import (  # noqa: E402
    _safe_filename_part,
    build_read_screenshot_path,
)


class TestReadScreenshotPath(unittest.TestCase):
    def test_safe_keeps_chinese(self) -> None:
        self.assertEqual(_safe_filename_part("达达助手"), "达达助手")

    def test_safe_strips_path_chars(self) -> None:
        self.assertEqual(_safe_filename_part("a/b:c"), "a_b_c")

    def test_default_pattern(self) -> None:
        when = datetime(2026, 7, 14, 16, 52, 3)
        path = build_read_screenshot_path("达达助手", {}, when=when)
        self.assertEqual(
            path,
            "/tmp/wechat_screenshot_达达助手_20260714_165203.jpg",
        )

    def test_dir_config(self) -> None:
        when = datetime(2026, 7, 14, 16, 52, 3)
        path = build_read_screenshot_path(
            "LvLLM",
            {"read_screenshot_dir": "/tmp"},
            when=when,
        )
        self.assertTrue(path.endswith("wechat_screenshot_LvLLM_20260714_165203.jpg"))

    def test_legacy_fixed_path_uses_parent_dir(self) -> None:
        when = datetime(2026, 1, 2, 3, 4, 5)
        path = build_read_screenshot_path(
            "文件传输助手",
            {"read_screenshot_path": "/tmp/wechat_screenshot.jpg"},
            when=when,
        )
        self.assertEqual(
            path,
            "/tmp/wechat_screenshot_文件传输助手_20260102_030405.jpg",
        )

    def test_template_path(self) -> None:
        when = datetime(2026, 7, 14, 16, 52, 3)
        path = build_read_screenshot_path(
            "达达助手",
            {"read_screenshot_path": "/tmp/shot_{session}_{time}.jpg"},
            when=when,
        )
        self.assertEqual(path, "/tmp/shot_达达助手_20260714_165203.jpg")


if __name__ == "__main__":
    unittest.main()
