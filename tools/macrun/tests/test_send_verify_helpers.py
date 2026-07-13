# -*- coding: utf-8 -*-
"""send 剪贴板探测相关纯函数单测（不依赖微信 GUI）。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macrun.wechat import (  # noqa: E402
    _input_matches_message,
    _input_still_has_message,
    _norm_probe_text,
)


class TestSendVerifyHelpers(unittest.TestCase):
    def test_norm_strips_and_newlines(self) -> None:
        self.assertEqual(_norm_probe_text("  hi\r\n"), "hi")
        self.assertEqual(_norm_probe_text("a\rb"), "a\nb")

    def test_match_exact(self) -> None:
        self.assertTrue(_input_matches_message("晚上好", "晚上好"))
        self.assertTrue(_input_matches_message("  晚上好\n", "晚上好"))

    def test_match_reject_wrong_field(self) -> None:
        # 误粘进搜索框时常见：探测到的是联系人备注
        self.assertFalse(_input_matches_message("陈可欣-1688", "哈哈看完了"))
        self.assertFalse(_input_matches_message("", "哈哈"))

    def test_still_has_message_after_failed_send(self) -> None:
        msg = "幽默回复测试"
        self.assertTrue(_input_still_has_message(msg, msg))
        self.assertFalse(_input_still_has_message("", msg))
        self.assertFalse(_input_still_has_message("别的内容", msg))


if __name__ == "__main__":
    unittest.main()
