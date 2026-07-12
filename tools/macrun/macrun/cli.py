# -*- coding: utf-8 -*-
"""macrun CLI: doctor | dump-tree | run"""

from __future__ import annotations

import argparse
import platform
import sys
from pathlib import Path

from macrun import __version__, ax
from macrun.agent import run_goal
from macrun.config import (
    api_key_is_placeholder,
    default_config_path,
    load_config,
    resolve_api_key,
)


def cmd_doctor(args: argparse.Namespace) -> int:
    print(f"macrun {__version__}")
    print(f"platform: {platform.system()} {platform.mac_ver()[0] or platform.release()}")
    print(f"python:   {sys.version.split()[0]} ({sys.executable})")

    if platform.system() != "Darwin":
        print("OS:       FAIL (macrun 仅支持 macOS)")
        return 1
    print("OS:       OK (Darwin)")

    try:
        trusted = ax.is_trusted()
    except Exception as e:
        print(f"Accessibility: ERROR ({e})")
        trusted = False
    else:
        print(f"Accessibility: {'OK (trusted)' if trusted else 'FAIL (未授权)'}")
        if not trusted:
            print(
                "  → 系统设置 → 隐私与安全性 → 辅助功能 → 勾选运行本进程的 App"
                "（Terminal / iTerm / WorkBuddy / Cursor 等）"
            )

    # Screen Recording：尝试截一张到临时文件
    try:
        from macrun import vision

        p = vision.capture_screen_png()
        ok = p.is_file() and p.stat().st_size > 0
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass
        print(f"ScreenCapture: {'OK' if ok else 'FAIL'}")
        if not ok:
            print("  → 系统设置 → 隐私与安全性 → 屏幕录制 → 授权同一 App")
    except Exception as e:
        print(f"ScreenCapture: FAIL ({e})")
        print("  → 系统设置 → 隐私与安全性 → 屏幕录制 → 授权同一 App")

    cfg_path = default_config_path()
    print(f"config:   {cfg_path or '(missing)'}")
    if cfg_path:
        try:
            cfg = load_config(cfg_path)
            key = resolve_api_key(cfg)
            ph = (not key) or any(
                x in key for x in ("YOUR_VOLC", "YOUR_API", "sk-YOUR", "YOUR_KEY")
            )
            print(f"API key:  {'PLACEHOLDER/missing' if ph else 'set'}")
            print(f"model:    {(cfg.get('llm') or {}).get('model')}")
        except Exception as e:
            print(f"config:   ERROR {e}")
    else:
        print("API key:  (no config)")

    try:
        info = ax.frontmost_app_info()
        print(f"frontmost:{info.get('name')} ({info.get('bundle_id')})")
    except Exception as e:
        print(f"frontmost: n/a ({e})")

    return 0 if platform.system() == "Darwin" else 1


def cmd_dump_tree(args: argparse.Namespace) -> int:
    try:
        info = ax.frontmost_app_info()
        nodes = ax.dump_tree(
            pid=info.get("pid"),
            max_nodes=args.max_nodes,
            max_depth=args.max_depth,
        )
        print(ax.tree_to_text(nodes, info))
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _log_factory(log_path: str | None):
    log_file = open(log_path, "a", encoding="utf-8") if log_path else None

    def _log(msg: str) -> None:
        if log_file:
            log_file.write(msg + "\n")
            log_file.flush()
        else:
            print(msg, flush=True)

    return _log, log_file


def _print_result(result: dict, log_path: str | None) -> int:
    status = result.get("status")
    line = (
        f"✅ SUCCESS: {result.get('result')}"
        if status == "success"
        else f"❌ FAIL: {result.get('reason') or result}"
    )
    print(line, flush=True)
    if status == "success" and result.get("clipboard_text"):
        # 读消息时额外打印内容便于 Agent 回复用户
        print(result["clipboard_text"], flush=True)
    if log_path:
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass
    return 0 if status == "success" else 1


def cmd_wechat_send(args: argparse.Namespace) -> int:
    from macrun.wechat import normalize_message, send_message

    _log, log_file = _log_factory(args.log)
    try:
        result = send_message(
            args.contact,
            normalize_message(args.message),
            log=_log,
        )
    finally:
        if log_file:
            log_file.close()
    return _print_result(result, args.log)


def cmd_wechat_read(args: argparse.Namespace) -> int:
    from macrun.wechat import read_messages

    _log, log_file = _log_factory(args.log)
    try:
        result = read_messages(
            args.session,
            last_n=args.last,
            log=_log,
            to_clipboard=not args.no_clipboard,
        )
    finally:
        if log_file:
            log_file.close()
    return _print_result(result, args.log)


def cmd_run(args: argparse.Namespace) -> int:
    goal = args.goal
    if not goal:
        print("Usage: macrun run \"goal text\"", file=sys.stderr)
        return 2
    log_path = args.log
    log_file = None
    if log_path:
        log_file = open(log_path, "a", encoding="utf-8")

    def _log(msg: str) -> None:
        # 有 -l 时只写文件，避免与 shell 重定向到同一文件导致重复行
        if log_file:
            log_file.write(msg + "\n")
            log_file.flush()
        else:
            print(msg, flush=True)

    try:
        result = run_goal(goal, config_path=args.config, log=_log)
    finally:
        if log_file:
            log_file.close()

    status = result.get("status")
    # 结果摘要始终打 stdout（便于 nohup 重定向或前台看）
    if status == "success":
        line = f"✅ SUCCESS: {result.get('result')}"
    else:
        line = f"❌ FAIL: {result.get('reason') or result}"
    print(line, flush=True)
    if log_file is None and log_path:
        pass
    elif log_path:
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass
    return 0 if status == "success" else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="macrun", description="macOS desktop agent runtime")
    p.add_argument("--version", action="version", version=f"macrun {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("doctor", help="Check OS, permissions, config")
    d.set_defaults(func=cmd_doctor)

    t = sub.add_parser("dump-tree", help="Dump frontmost app AX tree")
    t.add_argument("--max-nodes", type=int, default=80)
    t.add_argument("--max-depth", type=int, default=6)
    t.set_defaults(func=cmd_dump_tree)

    r = sub.add_parser("run", help="Run a natural language goal")
    r.add_argument("goal", nargs="?", help="Goal text")
    r.add_argument("-c", "--config", help="Path to config yaml")
    r.add_argument("-l", "--log", help="Append log file path")
    r.set_defaults(func=cmd_run)

    w = sub.add_parser("wechat-send", help="WeChat send with vision gates")
    w.add_argument("--contact", "-t", required=True, help="Contact / session name")
    w.add_argument("--message", "-m", required=True, help="Message text")
    w.add_argument("-l", "--log", help="Append log file path")
    w.set_defaults(func=cmd_wechat_send)

    wr = sub.add_parser("wechat-read", help="WeChat read last N messages + clipboard")
    wr.add_argument("--session", "-s", required=True, help="Chat / group name")
    wr.add_argument("--last", "-n", type=int, default=5, help="How many recent messages")
    wr.add_argument("--no-clipboard", action="store_true", help="Do not write clipboard")
    wr.add_argument("-l", "--log", help="Append log file path")
    wr.set_defaults(func=cmd_wechat_read)

    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    code = args.func(args)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
