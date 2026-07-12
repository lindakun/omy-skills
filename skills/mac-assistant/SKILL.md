---
name: mac-assistant
description: Mac 桌面自动化助理（仅 macOS）。将「用电脑…」「在 Mac 上…」「打开备忘录/微信…」等自然语言，转化为 macrun 可执行的 goal，在 macOS 桌面上完成 UI 操作（打开应用/点击/输入/读取信息），并把结果回复用户。依赖辅助功能权限与 macrun。
metadata:
  platforms: [macos]
  requires: [macrun, accessibility, screen-recording]
---

# mac-assistant Mac 桌面自动化助理

## 平台硬限制（最先检查）

1. **仅 macOS（Darwin）**。若当前主机为 Windows / Linux：
   - **停止**，不要安装或运行 macrun
   - Windows 桌面 → `pc-assistant`
   - 手机 → `mobile-assistant`
2. 涉及「手机」→ `mobile-assistant`，不用本技能。

## 触发条件

- "用电脑..." / "在电脑上..."（且主机为 Mac）
- "在 Mac 上..." / "用 Mac..."
- "打开备忘录/TextEdit/微信..."（桌面 App 语境）
- "帮我操作电脑..."（Mac）

## 路径解析（可移植）

### `REPO_ROOT`

1. `OMY_SKILLS_ROOT`
2. 搜索含 `tools/macrun` 与 `skills/mac-assistant/SKILL.md` 的目录
3. 找不到 → 提示设置 `OMY_SKILLS_ROOT`

### 运行时

| 项 | 解析 |
|----|------|
| `MACRUN_BIN` | 优先 `PATH` 中的 `macrun`；否则 `{REPO_ROOT}/tools/macrun/venv/bin/macrun` |
| 配置 | `MACRUN_CONFIG` → `{REPO_ROOT}/tools/macrun/config.local.yaml` → template |
| 日志 | `/tmp/mac_assistant.log` |

**不要**写死 `/Users/某用户/...`。

## 前置检查

失败则引导 `skills/mac-assistant/INSTALL.md` 或 `./scripts/install-mac.sh`：

1. `uname -s` 为 `Darwin`
2. `macrun` 可执行（`macrun --version` 或 venv 路径）
3. `macrun doctor`：辅助功能建议为 trusted；API Key 非占位符
4. 配置存在且 `api_key` 不是 `YOUR_VOLC_ARK_API_KEY`（或已设 `VOLC_ARK_API_KEY`）

## 工作流

### 1. 解析意图

目标 App、操作、需回传信息。

### 2. 生成 macrun goal

| 规则 | 说明 |
|------|------|
| App 用常见名 | `Notes`/`备忘录`、`TextEdit`、`WeChat`/`微信`、`Safari` |
| 中文输入 | 在 goal 中写明「用剪贴板粘贴」，禁止依赖直接打字中文 |
| 微信 | 必须剪贴板方案（见下） |
| 要回传的信息 | 写进 goal，便于 finish 摘要 |

**通用 few-shot：**

```
用户：在 Mac 上打开备忘录，写一句「mac-assistant 测试」
→ goal: 打开 Notes（备忘录）。新建或聚焦编辑区。用剪贴板粘贴文本：mac-assistant 测试。完成后在结果中说明已写入。
```

```
用户：用电脑打开 TextEdit 输入 Hello
→ goal: Open TextEdit, focus the document, type or paste "Hello", leave the window open, then finish.
```

### 微信 Mac（剪贴板 + 焦点）

微信控件树常不完整；从 WorkBuddy/Cursor 启动时 **宿主会抢焦点**，macrun 会自动 `activate` 微信，goal 仍应写清楚：

1. `open_app` WeChat **一次**（不要反复打开）  
2. 若界面不对：`activate_app` WeChat  
3. 搜索/输入：**clipboard_paste** + 回车；可用 hotkey（如 Cmd+F）  
4. 禁止在 goal 里要求「只看 WorkBuddy」  

```
用户：用电脑打开微信，给联系人小明发：你好
→ goal: 打开 WeChat 一次并保持最前。Cmd+F 搜索，剪贴板粘贴「小明」后回车选中联系人。剪贴板粘贴正文「你好」后必须用 send 动作发送（Cmd+Enter 再 Enter，不要只按 Enter）。不要反复 open_app。完成后说明是否已发送。
```

### 3. 执行

```bash
LOG_FILE="/tmp/mac_assistant.log"
: > "$LOG_FILE"   # 可选：清空旧日志
MACRUN_BIN="${MACRUN_BIN:-macrun}"
# 若 PATH 无 macrun：
# MACRUN_BIN="$REPO_ROOT/tools/macrun/venv/bin/macrun"
CONFIG="${MACRUN_CONFIG:-$REPO_ROOT/tools/macrun/config.local.yaml}"

# 只用 -l 写日志，不要再把 stdout 重定向到同一文件（会重复行）
nohup "$MACRUN_BIN" run -c "$CONFIG" -l "$LOG_FILE" '<goal>' \
  >/dev/null 2>&1 &
```

### 4. 监控（最多约 10 分钟）

| 信号 | 含义 |
|------|------|
| `macrun start` | 启动 |
| `FINISH:` / `✅ SUCCESS` | 成功 |
| `FAIL:` / `❌ FAIL` | 失败 |
| `Accessibility` / `未授权` | 权限问题 |
| `PLACEHOLDER` / API Key | 配置问题 |
| `Traceback` / `Error` | 异常 |

超时贴日志末尾约 30 行。

### 5. 回复用户

```
🖥️ 已执行：…
📂 MACRUN: <路径>
📋 结果：…
✅ 完成（耗时 …）
```

## 注意事项

- 策略：**AX 控件树为主，失败才截图**（由 macrun 自动处理）
- 真实桌面操作，可能与用户抢鼠标；保持解锁
- 危险操作（清空废纸篓等）应拒绝
- 权限必须授予**实际拉起 macrun 的宿主 App**

## 已知限制

- 仅 macOS
- 部分 Electron/游戏 App AX 残缺 → 依赖截图回退，成功率下降
- 微信发消息受版本/布局影响，需剪贴板 few-shot
- 需要多模态兼容 LLM API（默认火山 Doubao）
