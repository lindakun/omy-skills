---
name: pc-assistant
description: PC 桌面自动化助理（仅 Windows）。基于微软开源 UFO² 框架，将"使用电脑操作XXX"、"用电脑帮我XXX"、"在电脑上XXX"等自然语言指令，转化为 UFO² Agent 可执行的任务，在 Windows 桌面上自动完成 UI 操作（打开应用/点击/输入/读取信息等），并将执行结果在当前对话中回复给用户。
metadata:
  platforms: [windows]
  requires: [python3.11, ufo2, uia]
---

# pc-assistant PC 桌面自动化助理

## 平台硬限制（最先检查）

1. **仅 Windows 10/11**。若当前主机为 macOS / Linux：
   - **停止**，不要安装或运行 UFO²
   - 说明：UFO² 依赖 Windows UI Automation
   - 若用户实际要操作手机 → 改用 `mobile-assistant`
   - 若必须操作 Windows 桌面 → 请在 Windows 机器上运行本技能 / 远程到 Windows 主机
2. 涉及「手机」/「手机上」→ 用 `mobile-assistant`，不用本技能

## 触发条件

当用户说**涉及电脑操作**的指令时启用。典型触发词：
- "使用电脑..." / "用电脑..."
- "在电脑上..." / "电脑上..."
- "帮我操作电脑..."
- "打开电脑端的 XXX..."

## 路径解析（可移植，禁止写死本机盘符）

按顺序解析，使用**第一组同时存在且可用**的路径：

### `REPO_ROOT`（omy-skills 仓库根）

1. 环境变量 `OMY_SKILLS_ROOT`
2. 环境变量 `UFO_ROOT` 的上两级目录（若其以 `tools/ufo2` 或 `tools\ufo2` 结尾）
3. 在常见位置搜索同时包含 `tools/ufo2` 与 `skills/pc-assistant/SKILL.md` 的目录
4. 仍找不到 → **停止执行**，提示用户：`请设置环境变量 OMY_SKILLS_ROOT 为 omy-skills 仓库根目录的绝对路径`

### `UFO_ROOT` / `UFO_PYTHON`

1. 若设置了 `UFO_ROOT` / `UFO_PYTHON`，优先使用
2. 否则：
   - `UFO_ROOT` = `{REPO_ROOT}/tools/ufo2`
   - `UFO_PYTHON` = `{UFO_ROOT}/venv/Scripts/python.exe`（Windows）

### 其他路径

| 用途 | 路径 |
|------|------|
| API 配置 | `{UFO_ROOT}/config/ufo/agents.yaml` |
| 剪贴板脚本 | `{UFO_ROOT}/scripts/set_clipboard.py`（request 中用正斜杠绝对路径） |
| 运行日志 | `{TEMP}/ufo_assistant.log`（Windows：`%TEMP%` / `$env:TEMP`） |

**不要**在指令里写死 `D:\`、`G:\`、某用户名等个人路径。

## 前置条件

执行前必须验证，不满足则直接提示用户去看 `skills/pc-assistant/INSTALL.md` 或运行 `scripts/install-pc.ps1`：

1. 当前系统为 Windows（见上文「平台硬限制」）
2. `UFO_ROOT` 目录存在
3. `UFO_PYTHON` 存在（默认 `{UFO_ROOT}/venv/Scripts/python.exe`）
4. `{UFO_ROOT}/config/ufo/agents.yaml` 存在（可由 `agents.yaml.template` 复制生成），且 API Key **不是**占位符 `YOUR_VOLC_ARK_API_KEY`
5. `agents.yaml` 含四个 agent：`HOST_AGENT`、`APP_AGENT`、`EVALUATION_AGENT`、`BACKUP_AGENT`
6. 微信等场景需要 `{UFO_ROOT}/scripts/set_clipboard.py`

## 工作流

### 步骤 1：用户意图解析

提取：目标应用、具体操作、需要回传的信息。

### 步骤 2：生成 UFO² request

| 规则 | 说明 |
|------|------|
| 应用用正式名 | 如 `微信(WeChat)`、`记事本(Notepad)` |
| 复杂任务用英文 request | 提高选对函数的概率 |
| 预分解 Step 1/2/3 | 跳过冗长 Host 分析 |
| 微信禁止 `set_edit_text` | 必须用剪贴板 + Ctrl+V |
| 标记 `[verify]` / `[no-verify]` | 机械步骤用 no-verify 加速 |

**通用 few-shot（联系人名、文案按用户实际内容替换）：**

```
用户："用电脑打开微信，给联系人小明发消息：你好"
→ request: Complete the following task step by step:
Step 1 [verify]: Use run_shell with wait_for_completion=True to execute: python {UFO_ROOT_POSIX}/scripts/set_clipboard.py 小明
Step 2 [no-verify]: Open WeChat(微信), click search box, keyboard_input Ctrl+V with control_focus=False, press Enter, click the contact.
Step 3 [verify]: Use run_shell with wait_for_completion=True to execute: python {UFO_ROOT_POSIX}/scripts/set_clipboard.py 你好
Step 4 [no-verify]: Click chat input, Ctrl+V (keyboard_input control_focus=False), press Enter to send.
IMPORTANT: Do NOT use set_edit_text. Do NOT use Notepad. All text via set_clipboard.py only.
```

其中 `{UFO_ROOT_POSIX}` = 将 `UFO_ROOT` 转为正斜杠形式，例如 `C:/Users/you/omy-skills/tools/ufo2`。

```
用户："在电脑上打开记事本，写一段关于 UFO 的介绍"
→ request: Open Notepad, type a short introduction about UFO desktop automation, keep the window open when done.
```

### 微信（剪贴板方案）

微信自定义控件导致 `set_edit_text` 失败。流程：

1. `python {UFO_ROOT}/scripts/set_clipboard.py <文本>`
2. 目标窗口 `keyboard_input` + `control_focus=False` 发送 Ctrl+V / Enter

### 步骤 3：执行 UFO²

在 `UFO_ROOT` 下用 `UFO_PYTHON` 后台运行（路径用已解析变量，日志用系统 TEMP）：

**PowerShell 示例：**

```powershell
$log = Join-Path $env:TEMP "ufo_assistant.log"
$task = "pc-" + (Get-Date -Format "yyyyMMdd-HHmmss")
Set-Location $UFO_ROOT
# 后台启动；request 用单引号或转义，避免引号冲突
Start-Process -FilePath $UFO_PYTHON -ArgumentList @("-u","-m","ufo","--task",$task,"-r",$request) `
  -RedirectStandardOutput $log -RedirectStandardError $log -NoNewWindow
```

**Bash / Git Bash 示例：**

```bash
LOG_FILE="${TEMP:-/tmp}/ufo_assistant.log"
cd "$UFO_ROOT" && \
  "$UFO_PYTHON" -u -m ufo \
    --task "pc-$(date +%Y%m%d-%H%M%S)" \
    -r '<request>' \
    > "$LOG_FILE" 2>&1
```

要点：
- request 用单引号包裹（或 PowerShell 安全传参）
- 后台运行并轮询日志
- 向用户说明当前使用的 `UFO_ROOT`

### 步骤 4：监控结果（最多约 10 分钟）

轮询日志，关注：

| 信号 | 含义 |
|------|------|
| `Welcome to use UFO` | 启动成功 |
| `✅ SUCCESS` / `Status: FINISH` | 步骤成功/子任务结束 |
| `Error` / `Exception` / `Traceback` | 失败 |
| `timeout` / `rate limit` | API 问题 |

超时则汇报日志最后约 30 行。

### 步骤 5：回复用户

```
🖥️ 已执行：…
📂 UFO_ROOT: <实际路径>
📋 结果：…
✅ 完成（耗时 …）
```

失败时说明原因，并指向 `INSTALL.md` 中的对应排查项。

## 注意事项

- 模棱两可的指令先确认再执行
- 长任务给进度提示
- UFO² 在真实桌面操作，可能与用户当前操作冲突；需保持解锁、亮屏
- 执行结束后可删除 `{TEMP}/ufo_assistant.log`

## 已踩坑

| 问题 | 处理 |
|------|------|
| AAD / Evaluation 报错 | 确认四 agent 已配置；核心步骤有 `✅ SUCCESS` 可视为业务成功 |
| 微信 `set_edit_text` 失败 | 只用剪贴板方案 |
| `CustomizedAgent (not in config)` | 可忽略 |
| 占位符 API Key | 运行 `scripts/install-pc.ps1 -ApiKey ...` 或编辑 `agents.yaml` |

## 已知限制

- 仅 Windows 10/11
- 需要多模态 LLM API
- 无隔离桌面；敏感操作可能仍有系统级确认
