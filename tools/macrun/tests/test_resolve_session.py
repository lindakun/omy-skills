# -*- coding: utf-8 -*-
"""resolve_session_query 纯函数单测（不依赖微信 GUI）。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

# 允许直接 python tests/test_resolve_session.py
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macrun.wechat import resolve_session_query  # noqa: E402


class TestResolveSessionQuery(unittest.TestCase):
    def test_default_suffix(self) -> None:
        r = resolve_session_query("LvLLM", {})
        self.assertEqual(r["display"], "LvLLM")
        self.assertEqual(r["query"], "LvLLM-1688")
        self.assertTrue(r["used_suffix"])
        self.assertFalse(r["exception"])

    def test_already_has_suffix(self) -> None:
        r = resolve_session_query("LvLLM-1688", {"remark_suffix": "-1688"})
        self.assertEqual(r["query"], "LvLLM-1688")
        self.assertFalse(r["used_suffix"])

    def test_file_transfer_exception(self) -> None:
        r = resolve_session_query("文件传输助手", {})
        self.assertEqual(r["query"], "文件传输助手")
        self.assertTrue(r["exception"])
        self.assertFalse(r["used_suffix"])

    def test_custom_suffix(self) -> None:
        r = resolve_session_query("陈可欣", {"remark_suffix": "_x"})
        self.assertEqual(r["query"], "陈可欣_x")

    def test_suffix_disabled(self) -> None:
        r = resolve_session_query("LvLLM", {"remark_suffix_enabled": False})
        self.assertEqual(r["query"], "LvLLM")
        self.assertFalse(r["used_suffix"])

    def test_empty_suffix(self) -> None:
        r = resolve_session_query("LvLLM", {"remark_suffix": ""})
        self.assertEqual(r["query"], "LvLLM")

    def test_custom_no_suffix_list(self) -> None:
        r = resolve_session_query(
            "系统通知",
            {"no_suffix_sessions": ["系统通知", "文件传输助手"]},
        )
        self.assertEqual(r["query"], "系统通知")
        self.assertTrue(r["exception"])

    def test_empty_name(self) -> None:
        r = resolve_session_query("  ", {})
        self.assertEqual(r["query"], "")


if __name__ == "__main__":
    unittest.main()
