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

## 微信前置：备注后缀（必读）

选人**不用视觉模型**。常联系的人/群请在微信备注末尾统一加后缀（默认 **`-1688`**，见 `wechat.remark_suffix`）。

| 用户说法 | Agent 传入 | 实际搜索 |
|----------|------------|----------|
| LvLLM / 群 LvLLM | `LvLLM` | `LvLLM-1688` |
| 陈可欣 | `陈可欣` | `陈可欣-1688` |
| 文件传输助手 | `文件传输助手` | `文件传输助手`（例外，不拼后缀） |

- Agent **只传口语名**，不要自己拼 `-1688`。  
- 若用户已说全称 `LvLLM-1688`，运行时不会双拼。  
- 未改备注 → 搜索失败 / 进错会话 → **直接 FAIL**，提示把备注改为 `口语名+后缀`。  
- 后缀可在 `config.local.yaml` 的 `wechat.remark_suffix` 修改。

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

### 成功判定（Agent 必读）

日志须**同时**出现（缺一不可当作成功）：

1. `paste verify: ok`
2. `send verify: ok (input cleared)`（或配置关闭校验时的 `FINISH` + `✅ SUCCESS`）
3. 最终行 `✅ SUCCESS`

仅有 `send_chat` / `FINISH` **不够**。失败看 `❌` / `status: fail`，并检查 `/tmp/wechat_send_fail.jpg`（若开启 `fail_screenshot`）。

### 发送流程（默认无视觉）

1. 口语名 → 拼备注后缀搜索 → 进第 1 条会话  
2. **Esc + 点击底部输入带**（避免正文粘进搜索框）  
3. 粘贴正文 → **剪贴板探测**（Cmd+A/C）确认在输入框  
4. **取消全选**（Right + Cmd+Down；全选时按 Enter 会删字不发）  
5. 按配置发送键（默认 **`enter`**，须与本机微信「Enter 发送 / ⌘Enter 发送」一致）  
6. 再探测：输入框应已清空  

| 配置 | 含义 |
|------|------|
| `send_mode: enter` | 本机「Enter 发送」时用（推荐） |
| `send_mode: cmd_enter` | 本机「⌘Enter 发送」时用 |
| `send_mode: both` | 两种都试（兼容未知设置，略慢、副作用多，不推荐） |
| `verify_send: true` | 剪贴板探测粘贴/发送（默认开，不调视觉） |
| `fail_screenshot: true` | **仅失败**时截图 → `/tmp/wechat_send_fail.jpg` |

---

## B. 读消息 → `wechat-read`（只截图，无视觉 OCR）

```bash
LOG=/tmp/mac_assistant.log; : > "$LOG"
"$MACRUN_BIN" wechat-read \
  --session "LvLLM" \
  -l "$LOG"
```

流程：口语名 → 拼后缀搜索 → **脚本进第 1 条** → **截微信聊天窗口** → 保存图片。

| 项 | 值 |
|----|-----|
| 默认截图路径 | `/tmp/wechat_screenshot.jpg`（缩放最长边 1600 + JPEG q80，人工可读） |
| 视觉模型 | **不调用** |
| Agent 后续 | 打开该图片查看/总结后回复用户 |

| 用户说法 | `--session` |
|----------|-------------|
| 读群聊 LvLLM 最近消息 | LvLLM |
| 看文件传输助手聊天 | 文件传输助手 |

成功信号：`resolve query=...` → `select first result` → `screenshot saved` → `SCREENSHOT: /tmp/wechat_screenshot.jpg` → `✅ SUCCESS`。  
**不要**再期待 macrun 输出逐条文字消息；请读截图。

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
📋 结果：…（读消息：说明已截图并给出路径；可基于图片内容总结；对用户用口语名）
✅/❌ 完成（耗时 …）
```

发消息失败时：如实报 FAIL 原因；可提示查看 `/tmp/mac_assistant.log` 与 `/tmp/wechat_send_fail.jpg`。**不要**在校验失败时声称「已发送」。

## 配置要点（`config.local.yaml`）

```yaml
wechat:
  remark_suffix: "-1688"       # 可改
  remark_suffix_enabled: true
  no_suffix_sessions:
    - 文件传输助手
  select_mode: enter           # enter | down_enter
  send_mode: enter             # 与本机微信一致：Enter 发送（⌘Enter 则改 cmd_enter）
  focus_input: true            # Esc+点击底部输入带
  verify_send: true            # 剪贴板探测粘贴/发送（非视觉）
  fail_screenshot: true        # 仅失败时截图 /tmp/wechat_send_fail.jpg
  # gates: { send: true }      # 仅调试时开发送视觉校验
  read_screenshot_path: /tmp/wechat_screenshot.jpg
  read_screenshot_max_side: 1600
  read_screenshot_jpeg_quality: 80
  read_scroll_once: false
```

## 常见失败

| 现象 | 处理 |
|------|------|
| `paste verify: FAIL` | 焦点未进输入框；看 fail 截图；检查窗口布局 / `input_click_*` |
| 输入框有字一发送就空、无气泡 | 多为全选后 Enter 删字；须有 collapse 日志；升级 macrun |
| `send verify` 仍残留正文 | `send_mode` 与微信设置不一致（enter ↔ cmd_enter） |
| 进错会话 | 备注未加后缀，或后缀配置不一致 |
