---
name: mac-assistant
description: Mac 桌面自动化助理（仅 macOS）。将「用电脑…」「在 Mac 上…」「打开备忘录/微信…」等自然语言，转化为 macrun 操作。微信发消息优先 wechat-send 确定性脚本。
metadata:
  platforms: [macos]
  requires: [macrun, accessibility, screen-recording]
---

# mac-assistant Mac 桌面自动化助理

## 平台硬限制（最先检查）

1. **仅 macOS（Darwin）**。Windows → `pc-assistant`；手机 → `mobile-assistant`。
2. 涉及「手机」→ `mobile-assistant`。

## 触发条件

- "用电脑..." / "在电脑上..."（且主机为 Mac）
- "在 Mac 上..." / "用 Mac..."
- "打开备忘录/TextEdit/微信..." / "给某某发微信..."

## 路径解析

| 项 | 解析 |
|----|------|
| `REPO_ROOT` | `OMY_SKILLS_ROOT` 或含 `tools/macrun` + 本 SKILL 的目录 |
| `MACRUN_BIN` | PATH 的 `macrun`，否则 `{REPO_ROOT}/tools/macrun/venv/bin/macrun` |
| 配置 | `MACRUN_CONFIG` 或 `{REPO_ROOT}/tools/macrun/config.local.yaml` |
| 日志 | `/tmp/mac_assistant.log` |

## 前置检查

1. `uname -s` → Darwin  
2. `macrun` 可用  
3. `macrun doctor`（辅助功能建议 trusted；Key 非占位符）  

失败 → `skills/mac-assistant/INSTALL.md` / `./scripts/install-mac.sh`

---

## 工作流（优先快路径）

### A. 微信发消息（推荐，最快最稳）

识别到：**微信 + 联系人 + 消息正文** → **不要**走长 goal + 视觉 Agent，直接：

```bash
LOG_FILE="/tmp/mac_assistant.log"
: > "$LOG_FILE"
MACRUN_BIN="${MACRUN_BIN:-$REPO_ROOT/tools/macrun/venv/bin/macrun}"
CONFIG="${MACRUN_CONFIG:-$REPO_ROOT/tools/macrun/config.local.yaml}"

"$MACRUN_BIN" wechat-send \
  --contact "陈可欣" \
  --message "老婆晚上好" \
  -l "$LOG_FILE"
# 前台跑即可（通常数秒）；也可用 nohup，但不要把 stdout 再重定向到同一日志
```

**从用户话里抽出参数（你来抽，不要让 macrun 再猜）：**

| 用户说法 | `--contact` | `--message` |
|----------|-------------|-------------|
| 给陈可欣发：晚上好 | 陈可欣 | 晚上好 |
| 打开微信找小明说你好 | 小明 | 你好 |
| 微信给老婆发想你了 | 老婆/陈可欣（按用户称呼） | 想你了 |

日志成功信号：`wechat-script start` → `gate1 result matched=True` → `gate2 result sent=True` → `FINISH:` / `✅ SUCCESS`。

- Gate1：搜索后视觉确认目标联系人在列表中的第几行，再按对应次数 ↓ + Enter（**匹配失败直接 FAIL，不盲进**）
- Gate2：发送后视觉确认是否在会话且输入框大致清空（失败会换发送键重试一次，仍失败则 FAIL）

发送键：`wechat.send_mode` = `both` | `enter` | `cmd_enter`。  
可关闸门调试：`wechat.gates_enabled: false`（不推荐）。

### B. 其它桌面任务（备忘录 / TextEdit 等）

用 `macrun run`：

```bash
"$MACRUN_BIN" run -c "$CONFIG" -l "$LOG_FILE" \
  '打开 Notes，用剪贴板粘贴：hello，然后 finish'
```

中文输入一律剪贴板；不要写死用户路径。

### C. 监控与回复

- 微信脚本：通常 **5–15 秒** 内结束；超时（>60s）贴日志  
- 通用 run：最多约 10 分钟  
- 回复格式：

```
🖥️ 已执行：…
📋 结果：…
✅ 完成（耗时 …）
```

---

## 注意事项

- 真实桌面操作会抢焦点；授权给 **WorkBuddy / 终端** 等实际宿主  
- 微信 AX 极弱：发消息路径已脚本化，勿再用 click_xy 猜坐标  
- 危险操作（清空废纸篓等）拒绝  

## 已知限制

- 仅 macOS  
- 搜索同名联系人可能进错会话（脚本会 ↓ + Enter 选第一项）  
- 发送模式因用户微信设置而异 → 调 `wechat.send_mode`  
