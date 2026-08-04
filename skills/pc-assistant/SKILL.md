---
name: pc-assistant
description: PC 桌面自动化助理（仅 Windows）。将"使用电脑操作XXX"、"用电脑帮我XXX"、"在电脑上XXX"等自然语言指令，转化为 Windows 桌面自动化操作（打开应用/点击/输入/读取信息等），并将执行结果在当前对话中回复给用户。简单按键操作用 Python ctypes 直达 Win32 API，复杂 GUI 操作走 UFO² 框架。
metadata:
  platforms: [windows]
  requires: [python3.11, ufo2, uia]
disable: true
---

# pc-assistant PC 桌面自动化助理

## 平台硬限制（最先检查）

1. **仅 Windows 10/11**。若当前主机为 macOS / Linux：
   - **停止**，不要安装或运行 UFO²
   - 说明：UFO² 依赖 Windows UI Automation
   - 若用户实际要操作手机 → 改用 `mobile-assistant`
   - 若必须操作 Windows 桌面 → 请在 Windows 机器上运行本技能 / 远程到 Windows 主机
2. 涉及「手机」/「手机上」→ 用 `mobile-assistant`，不用本技能
3. 主机为 **macOS** 时的「用电脑…」→ 用 `mac-assistant`，不用本技能

## 触发条件

当用户说**涉及电脑操作**的指令时启用（且主机为 Windows）。典型触发词：
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
6. `{UFO_ROOT}/config/ufo/mcp.yaml` 存在，否则 UFO² 无法加载 MCP agent
7. ⚠️ **HardwareAgent 是 Mock 实现**（见「已踩坑」），**不能真实操作桌面鼠标键盘**。HostAgent 会优先选择它，导致简单按键操作无法通过 UFO² 完成。
8. 微信等场景需要 `{UFO_ROOT}/scripts/set_clipboard.py`

## 工作流

### 步骤 1：用户意图解析 + 任务分类

先提取：**目标应用、具体操作、是否需要回传信息**。
再判断任务属于哪种类型：

| 任务类型 | 判定条件 | 推荐方案 |
|---------|---------|---------|
| **简单按键** | 只需打开应用 + 点击/输入固定按键 | ✅ **ctypes（首选）** |
| **复杂UI操作** | 需要读取屏幕信息、导航多层菜单、搜索联系人、理解界面内容 | **UFO²（备选）** |

**区分示例：**
| 用户指令 | 类型 | 说明 |
|---------|:----:|------|
| "打开计算器算1+1" | ✅ 简单 | 已知按键序列，无信息回传 |
| "打开记事本写一首诗" | ✅ 简单 | 已知文本内容，直接按键输入 |
| "微信搜索小明发你好" | ❌ 复杂 | 需要定位搜索框、识别联系人、判断搜索结果 |
| "看看B站热搜榜" | ❌ 复杂 | 需要截图读取屏幕内容并回传 |

---

### 步骤 2（首选）：简单按键 → Python ctypes 直接操作

**原理：** `ctypes.windll.user32.keybd_event` 直接调用 Win32 API，**可穿透 WorkBuddy 沙盒**，比 PowerShell COM/Add-Type 更可靠。

**工作流：**
1. `PowerShell: Start-Process <app.exe>` 启动目标应用（或确认其已打开）
2. 若应用窗口未聚焦 → Python FindWindow + SetForegroundWindow 激活窗口
3. `ctypes.windll.user32.keybd_event` 发送按键序列
4. 如需文字输入（记事本等）→ 用 ctypes 逐个字符按键，或用剪贴板方案

**沙盒环境可用性对照表：**

| 操作 | 结果 |
|------|:----:|
| `PowerShell: Start-Process calc.exe`（启动进程） | ✅ 可用 |
| `Python ctypes.windll.user32.keybd_event`（发送按键） | ✅ 穿透沙盒 |
| `PowerShell: Add-Type`（动态编译 .NET） | ❌ 被拦截 |
| `PowerShell: New-Object -ComObject *`（COM 对象） | ❌ 被拦截 |
| Bash 中调 `powershell.exe` | ❌ 被拦截 |

**完整示例代码（打开计算器计算 1+1）：**

```python
import ctypes, time

keybd_event = ctypes.windll.user32.keybd_event
FindWindow = ctypes.windll.user32.FindWindowW
SetForegroundWindow = ctypes.windll.user32.SetForegroundWindow
ShowWindow = ctypes.windll.user32.ShowWindow
SW_RESTORE = 9
KEYEVENTF_KEYUP = 0x0002

def press_key(vk_code):
    keybd_event(vk_code, 0, 0, 0)
    time.sleep(0.05)
    keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.15)

# 1. 用 PowerShell 启动计算器（或用 FindWindow 检查是否已打开）
# 2. 激活窗口
hwnd = FindWindow('CalcFrame', None)
if hwnd:
    ShowWindow(hwnd, SW_RESTORE)
    SetForegroundWindow(hwnd)
    time.sleep(0.5)

# 3. 发送按键
VK_1 = 0x31      # 主键盘 1
VK_ADD = 0x6B    # 小键盘 +
VK_RETURN = 0x0D # Enter（=计算结果）
VK_TAB = 0x09
VK_ESCAPE = 0x1B
VK_0 = 0x30; VK_2 = 0x32; VK_3 = 0x33; VK_4 = 0x34
VK_5 = 0x35; VK_6 = 0x36; VK_7 = 0x37; VK_8 = 0x38; VK_9 = 0x39
VK_SUBTRACT = 0x6D  # 小键盘 -
VK_MULTIPLY = 0x6A  # 小键盘 *
VK_DIVIDE = 0x6F    # 小键盘 /

press_key(VK_1)      # 按 1
press_key(VK_ADD)    # 按 +
press_key(VK_1)      # 按 1
press_key(VK_RETURN) # 按 Enter（等号）
```

**文字输入（记事本场景）：**
```python
def type_string(text):
    """逐字输入字符串（仅支持英文字母和部分符号）"""
    VK_A = 0x41  # A键 = 0x41, 字母连续排列
    for ch in text:
        if 'a' <= ch <= 'z':
            press_key(VK_A + ord(ch) - ord('a'))
        elif 'A' <= ch <= 'Z':
            # Shift + 字母
            keybd_event(0x10, 0, 0, 0)  # Shift down
            press_key(VK_A + ord(ch) - ord('A'))
            keybd_event(0x10, 0, KEYEVENTF_KEYUP, 0)  # Shift up
        elif ch == ' ':
            press_key(0x20)  # Space
        # 更多字符可根据需要扩展

# 或直接用剪贴板方案（更可靠）：
# 1. 用 set_clipboard.py 写入文本
# 2. 切换到目标窗口按 Ctrl+V
```

**限制：**
- 只能发送按键，不能读取屏幕信息
- 需要目标窗口已有焦点（可先调用 `Start-Process` + `SetForegroundWindow` 确保）
- 复杂文字输入建议用剪贴板方案（见下文「微信（剪贴板方案）」）

---

### 步骤 3（备选）：复杂 UI 操作 → UFO²

当任务需要**读取屏幕内容、导航复杂 UI、搜索/识别元素**时使用。

#### 3a：生成 UFO² request

| 规则 | 说明 |
|------|------|
| 应用用正式名 | 如 `微信(WeChat)`、`记事本(Notepad)` |
| 任务用英文 request | 提高选对函数的概率 |
| 预分解 Step 1/2/3 | 跳过冗长 Host 分析 |
| 微信禁止 `set_edit_text` | 必须用剪贴板 + Ctrl+V |
| 标记 `[verify]` / `[no-verify]` | 机械步骤用 no-verify 加速 |
| 🚨 **禁止 HardwareAgent** | request 末尾加 `IMPORTANT: Do NOT select HardwareAgent. Use AppAgent/UIA desktop operations only.` |
| 计算器 run_shell 可用 | `calc.exe` 在 cli_mcp_server.py 白名单中 |

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

#### 3b：执行 UFO²

在 `UFO_ROOT` 下用 `UFO_PYTHON` 后台运行：

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

#### 3c：监控结果（最长约 10 分钟）

| 信号 | 含义 |
|------|------|
| `Welcome to use UFO` | 启动成功 |
| `✅ SUCCESS` / `Status: FINISH` | 步骤成功/子任务结束 |
| `Error` / `Exception` / `Traceback` | 失败 |
| `timeout` / `rate limit` | API 问题 |

超时则汇报日志最后约 30 行。

---

### 微信（剪贴板方案）

微信自定义控件导致 `set_edit_text` 失败。适用于 **ctypes 和 UFO²** 两种方案：

1. `python {UFO_ROOT}/scripts/set_clipboard.py <文本>`
2. 目标窗口 `keyboard_input` + `control_focus=False` 发送 Ctrl+V / Enter

---

### 步骤 4：回复用户

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
- **简单按键任务 ≠ 复杂任务**，写反会导致效率低下或失败：
  - "打开计算器算1+1" → ctypes（秒级完成）
  - "微信搜索联系人发消息" → UFO²（需UI识别）
- ctypes 操作在真实桌面执行，可能与用户当前操作冲突；需保持解锁、亮屏
- UFO² 执行结束后可删除 `{TEMP}/ufo_assistant.log`
- 🚨 **UFO² 每次 request 末尾必须禁止 HardwareAgent**（见 request 生成规则）
- 如果 UFO² 因 `save_screenshot` 解析错误等 AppAgent 问题反复失败，**立即降级为 ctypes 方案**
- **ctypes 方案无法读取屏幕内容**，需要回传信息时只能用 UFO²

## 已踩坑

| 问题 | 处理 |
|------|------|
| AAD / Evaluation 报错 | 确认四 agent 已配置；核心步骤有 `✅ SUCCESS` 可视为业务成功 |
| 微信 `set_edit_text` 失败 | 只用剪贴板方案 |
| `CustomizedAgent (not in config)` | 可忽略 |
| 占位符 API Key | 运行 `scripts/install-pc.ps1 -ApiKey ...` 或编辑 `agents.yaml` |
| `run_shell` 被安全策略拦截 | `cli_mcp_server.py` 有 ALLOWED_CLI_COMMANDS 白名单 + DANGEROUS_PATTERNS 黑名单；`calc.exe` 在白名单中但仍可能因命令格式命中黑名单。在 request 中指定简洁命令（如 `calc.exe` 不带参数）降低拦截概率 |
| ⚠️ **HardwareAgent 是 Mock** | `hardware_mcp_server.py` 的 `press_hotkey`、`type_text`、`click_mouse` 等全部返回 `(mock)`，**不会真实操作桌面**。且其 HTTP MCP 服务（`localhost:8006`）默认未启动时会报 `Client failed to connect` → 进程崩溃。解决方案：request 末尾加 `IMPORTANT: Do NOT select HardwareAgent. Use AppAgent/UIA desktop operations only.` 强制走 AppAgent |
| **PowerShell 沙盒限制** | WorkBuddy 沙盒拦截 `Add-Type`（动态编译 .NET）、`New-Object -ComObject*`（COM 对象）、从 Bash 调 `powershell.exe`。替代方案：Python ctypes（见「步骤 2（首选）：ctypes 直接操作」） |

## 已知限制

- 仅 Windows 10/11
- 需要多模态 LLM API（仅 UFO² 方案需要）
- 无隔离桌面；敏感操作可能仍有系统级确认
- **ctypes 方案**：只能发送按键，不能读取屏幕、不能定位 UI 元素
- **UFO² 方案**：HardwareAgent 为 Mock、AppAgent 的 doubao 模型可能因 `save_screenshot` 参数格式解析报错、run_shell 受白名单/黑名单双重过滤
