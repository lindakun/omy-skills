---
name: mac-assistant
description: Mac 桌面自动化助理（仅 macOS）。微信发消息用 wechat-send，读群/联系人最近消息用 wechat-read；其它桌面任务用 macrun run。
metadata:
  platforms: [macos]
  requires: [macrun, accessibility, screen-recording]
---

# mac-assistant Mac 桌面自动化助理

## 平台硬限制

1. **仅 macOS**。Windows → `pc-assistant`；手机 → `mobile-assistant`。  
2. 权限：辅助功能 + 屏幕录制（WorkBuddy/终端等实际宿主）。

## 路径

| 项 | 值 |
|----|-----|
| `MACRUN_BIN` | `{REPO_ROOT}/tools/macrun/venv/bin/macrun` 或 PATH |
| `MACRUN_CONFIG` | `{REPO_ROOT}/tools/macrun/config.local.yaml` |
| 日志 | `/tmp/mac_assistant.log` |

`REPO_ROOT` = `OMY_SKILLS_ROOT` 或含 `tools/macrun` 的仓库根。

---

## 路由（必读）

| 用户意图 | 命令 | 禁止 |
|----------|------|------|
| **发微信**（给谁发什么） | `wechat-send` | 不要用 `run` 长 goal |
| **读微信消息**（最近 N 条/复制/总结群聊） | `wechat-read` | 不要用 `run` 点坐标 |
| 备忘录/其它 App | `macrun run "..."` | — |

---

## A. 发消息 → `wechat-send`

```bash
LOG=/tmp/mac_assistant.log; : > "$LOG"
"$MACRUN_BIN" wechat-send \
  --contact "陈可欣" \
  --message "晚上好" \
  -l "$LOG"
```

成功日志含：`gate1 result matched=True`、`gate2 result sent=True`、`✅ SUCCESS`。  
Gate 失败会 **FAIL**（不盲进错误会话）。

---

## B. 读消息 → `wechat-read`（本次新增）

```bash
LOG=/tmp/mac_assistant.log; : > "$LOG"
"$MACRUN_BIN" wechat-read \
  --session "LvLLM" \
  --last 5 \
  -l "$LOG"
```

流程：搜索会话 → **Gate1 确认** → 进入 → **截图抽取最近 N 条** → **写入剪贴板**并打印正文。

| 用户说法 | `--session` | `--last` |
|----------|-------------|----------|
| 读群聊 LvLLM 最近 5 条 | LvLLM | 5 |
| 把和文件传输助手最近 3 条复制出来 | 文件传输助手 | 3 |
| 打开微信找到群「xxx」看最近消息 | xxx | 5（默认） |

成功信号：`wechat-read start` → `gate-read in_session=True` → `clipboard set` → `FINISH` / `✅ SUCCESS`。  
stdout 会带消息列表，可直接回复用户。

---

## C. 其它桌面 → `macrun run`

```bash
"$MACRUN_BIN" run -c "$MACRUN_CONFIG" -l "$LOG" '打开 Notes，剪贴板粘贴 hello'
```

**不要**用 `run` 做微信读/写；若误入，运行时也会禁止微信 `click_xy`。

---

## 回复用户

```
🖥️ 已执行：…
📋 结果：…（读消息时贴出 N 条摘要）
✅/❌ 完成（耗时 …）
```

## 配置要点（`config.local.yaml`）

```yaml
wechat:
  gates_enabled: true
  send_mode: both          # enter | cmd_enter
  gate_timeout: 60
  read_scroll_once: true   # 读消息时是否上滚再截一屏
```
