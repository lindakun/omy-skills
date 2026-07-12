---
name: pc-assistant
description: PC 桌面自动化助理。基于微软开源 UFO² 框架，将"使用电脑操作XXX"、"用电脑帮我XXX"、"在电脑上XXX"等自然语言指令，转化为 UFO² Agent 可执行的任务，在 Windows 桌面上自动完成 UI 操作（打开应用/点击/输入/读取信息等），并将执行结果在当前对话中回复给用户。
agent_created: true
---

# pc-assistant PC 桌面自动化助理

## 触发条件

当用户说**涉及电脑操作**的指令时启用。典型触发词：
- "使用电脑..." / "用电脑..."
- "在电脑上..." / "电脑上..."
- "帮我操作电脑..."
- "打开电脑端的 XXX..."

**注意**：凡是涉及 "手机"/"手机上" 的操作，应使用 `mobile-assistant` 技能，而非本技能。

## 路径约定（与 INSTALL.md 对齐）

UFO² **源码以本仓库 `tools/ufo2` 为准**。本机执行前按下列顺序解析路径，使用**第一个同时满足**的组合：

| 优先级 | `UFO_ROOT`（源码） | `UFO_PYTHON`（解释器） | 说明 |
|--------|-------------------|------------------------|------|
| 1 | 环境变量 `UFO_ROOT` | 环境变量 `UFO_PYTHON` | 显式覆盖，优先 |
| 2 | `G:\github_pj\omy-skills\tools\ufo2` | `{UFO_ROOT}\venv\Scripts\python.exe` | 与 INSTALL 一致：仓库内源码 + 仓库内 venv |
| 3 | `D:\tools\ufo2` | `D:\tools\ufo_venv\Scripts\python.exe` | 本机已有独立运行环境时的回退 |

`set_clipboard.py` 路径一律为：`{UFO_ROOT}/scripts/set_clipboard.py`（在 request 里写正斜杠，如 `G:/github_pj/omy-skills/tools/ufo2/scripts/set_clipboard.py`）。

**API 配置**：`{UFO_ROOT}/config/ufo/agents.yaml`  
仓库内该文件仅为占位符 `YOUR_VOLC_ARK_API_KEY`。真实 Key 只应写在本地运行副本中，**禁止提交到 git**。

## 前置条件

执行前必须验证，不满足则直接提示用户：

1. **UFO_ROOT 存在**（按上表解析后的目录）
2. **UFO_PYTHON 存在**，且该环境已安装 UFO² 依赖（`pip install -r requirements.txt`）
3. **API 配置**：`{UFO_ROOT}/config/ufo/agents.yaml` 存在，且 API Key **不是** `YOUR_VOLC_ARK_API_KEY` 占位符
4. **配置完整性**：`agents.yaml` 中**必须有**以下 4 个 agent，否则会回落到默认 `azure_ad` 导致 AAD 报错：
   - `HOST_AGENT`
   - `APP_AGENT`
   - `EVALUATION_AGENT`
   - `BACKUP_AGENT`

若优先级 2（仓库路径）缺少 venv 或 Key，而优先级 3（`D:\tools\...`）可用，则使用优先级 3，并在执行前简要告知用户当前选用的 `UFO_ROOT`。

## 工作流

### 步骤 1：用户意图解析

解析用户自然语言指令，提取关键信息：
- **目标应用**：要在电脑上打开什么软件（如"微信"、"记事本"、"浏览器"）
- **操作**：具体做什么（搜索、发送消息、创建文件、截屏等）
- **回传内容**：最终要告诉用户什么信息（如"操作结果"、"截图"）

### 步骤 2：生成 UFO² request 提示词

将用户指令整理为 UFO² 可执行的清晰 request。核心规则：

| 规则 | 说明 | 示例 |
|------|------|------|
| 应用用正式名 | 使用 Windows 上应用的实际名称 | "微信(WeChat)"、"记事本(Notepad)" |
| 操作清晰化 | 明确描述每一步操作，避免歧义 | "打开微信，找到联系人孙振易，发送消息" |
| 回传结果 | 如果用户需要看到结果，要求 UFO² 在任务完成后报告结果 | "操作完成后，告诉我是否成功" |
| **request 用英文编写** | 实测英文指令让 LLM 更准确选对函数，中文长指令可能导致选错函数 | 复杂多步任务必须用英文 |
| **预分解任务为 Step 1/2/3** | 直接在 request 中给出分解后的步骤，跳过 HostAgent 的分析阶段，省 1-2 分钟 | "Step 1: Open Notepad... Step 2: Open WeChat..." |
| **指定函数名** | 对微信等特殊应用，明确指定用哪个函数 | "use keyboard_input with control_focus=False" |
| **禁止错误函数** | 明确禁止会失败的函数 | "Do NOT use set_edit_text for WeChat" |
| **request 尽量简洁** | 简洁指令减少 LLM token 处理时间，每少 50 个 token 约省 1-2s API 耗时 | "Step 1: set_clipboard to 'text'. Step 2: WeChat search contact, Ctrl+V, Enter." |
| **标记 verify/no-verify** | 在步骤后标注 `[verify]`（需截图+LLM）或 `[no-verify]`（跳过截图直接执行），确定性步骤省 ~25s/步 | "Step 2 [no-verify]: click search box, Ctrl+V, Enter." |

**示例映射（few-shot）**（`CLIPBOARD` 表示 `{UFO_ROOT}/scripts/set_clipboard.py` 的绝对路径，正斜杠）：

```
用户："用电脑打开微信，给孙振易发一首骚气的嘲讽诗句，备注是ai写的"
→ request: Complete the following task step by step:
Step 1 [verify]: Use run_shell with wait_for_completion=True to execute: python CLIPBOARD 要发送的完整诗句
This sets the Windows clipboard to the poem text.
备注：ai写的
Step 2 [no-verify]: Open WeChat(微信), click on the search box, use keyboard shortcut Ctrl+V (keyboard_input with control_focus=False) to paste the contact name "孙振易" from clipboard into the search box, then press Enter to search. Click on the "孙振易" contact to open the chat window.
Step 3 [verify]: Use run_shell with wait_for_completion=True to execute: python CLIPBOARD 完整的诗句内容
Step 4 [no-verify]: Click on the chat input box to focus it, then use keyboard shortcut Ctrl+V (keyboard_input with control_focus=False) to paste the text from clipboard, then press Enter to send.
IMPORTANT: Do NOT use set_edit_text. Do NOT use Notepad. All text must go through clipboard via set_clipboard.py script.
```

```
用户："在电脑上打开记事本，写一段关于UFO²的文字"
→ request: 打开记事本(Notepad)应用，在文档中输入一段介绍UFO²功能的文字，内容如下：[用户描述的文字]。操作完成后，保持文件不关闭。
```

```
用户："用电脑帮我看看C盘的剩余空间"
→ request: 打开"此电脑(My Computer)"或文件资源管理器(File Explorer)，查看C盘的剩余空间信息。把C盘的总大小和可用空间告诉我。
```

### 微信（WeChat）工作流（剪贴板方案）

微信使用自定义 Win32 控件，UFO² 的 `set_edit_text` 全部失败。所有文字输入必须通过**剪贴板脚本**，键盘只用于快捷键（Ctrl+V / Enter）。

**前置要求：**
1. 脚本：`{UFO_ROOT}/scripts/set_clipboard.py`（通过 `sys.argv` 动态接收文本）
2. `python` 已加入 `cli_mcp_server.py` 白名单
3. `run_shell` 已改为同步等待 + 返回输出

**完整工作流模板（推荐使用 [verify]/[no-verify] 标记加速）：**
```
Step 1 [verify]: Use run_shell with wait_for_completion=True to execute: python CLIPBOARD 联系人名称
Step 2 [no-verify]: WeChat click search box, Ctrl+V, Enter, click contact.
Step 3 [verify]: Use run_shell to set clipboard to message text.
Step 4 [no-verify]: Click chat input, Ctrl+V, Enter.
IMPORTANT: Do NOT use set_edit_text. Do NOT use Notepad. All text via clipboard only.
```

**核心规则：**
- 所有文字通过 `set_clipboard.py` 脚本写入剪贴板
- 键盘只用于 Ctrl+V（粘贴）和 Enter（搜索/发送）
- 使用 `keyboard_input` + `control_focus=False` 发送快捷键
- request 必须用英文编写
- **兜底方案**：若剪贴板脚本不可用，可用记事本写入文字→Ctrl+A→Ctrl+C（见「已踩坑」）

### 步骤 3：执行 UFO²

先按「路径约定」解析出 `UFO_ROOT` 与 `UFO_PYTHON`，再执行（Git Bash / MSYS 风格路径示例；Windows 路径需按解析结果替换）：

```bash
LOG_FILE="C:/Users/Administrator/AppData/Local/Temp/ufo_assistant.log"
# 将下面两处替换为实际解析结果，例如：
# UFO_ROOT_MSYS="/g/github_pj/omy-skills/tools/ufo2"
# UFO_PYTHON_WIN="G:/github_pj/omy-skills/tools/ufo2/venv/Scripts/python.exe"
# 或回退：UFO_ROOT_MSYS="/d/tools/ufo2"  UFO_PYTHON_WIN="D:/tools/ufo_venv/Scripts/python.exe"
cd "$UFO_ROOT_MSYS" && \
  "$UFO_PYTHON_WIN" -u -m ufo \
    --task "pc-$(date +%Y%m%d-%H%M%S)" \
    -r '<request>' \
    > "$LOG_FILE" 2>&1
```

**重要**：
- request 文本在 bash 中用**单引号**包裹，避免内部双引号冲突
- 使用 `run_in_background=true` 后台运行
- 日志文件固定路径：`C:\Users\Administrator\AppData\Local\Temp\ufo_assistant.log`
- 执行前确认日志目录存在：`mkdir -p /c/Users/Administrator/AppData/Local/Temp`
- 执行前在对话中注明实际使用的 `UFO_ROOT`（便于排查「改了仓库却跑的是 D 盘旧副本」）

### 步骤 4：监控并解析结果

后台启动后轮询日志文件（最多等待 10 分钟）：

1. 检查 `Welcome to use UFO🛸` → UFO² 成功启动
2. 检查 `Status: ✅ SUCCESS` / `📊 Status:        🏁 FINISH` → 单步操作成功
3. 检查 `Success` / `completed` / `任务完成` → 提取成功结果
4. 在日志中搜索关键操作日志：

   | 关键词 | 含义 |
   |--------|------|
   | `Action applied` | 本次执行的UFO²操作 |
   | `Action Execution Results` | 操作执行后的结果摘要 |
   | `✅ SUCCESS` | 单个操作执行成功 |
   | `Status: 🏁 FINISH` | 子任务完成 |
   | `Status: CONTINUE` | 还有下一步操作 |
   | `set_edit_text` 或 `click_input` 等 | 具体的UI操作函数 |
   | `Status: ASSIGN` | 从HostAgent切换到AppAgent |

5. 检查 `Error` / `Exception` / `Traceback` → 报告错误详情
6. 检查 `API` / `timeout` / `rate limit` → 提示 API 调用问题
7. 超时无结果 → 读取日志最后 30 行，报告当前执行状态

### 步骤 5：回传给用户

在**当前对话**中用清晰格式回复给用户。格式示例：

```
🖥️ 已执行：打开微信 → 找到孙振易 → 发送骚气诗句
📂 UFO_ROOT: G:\github_pj\omy-skills\tools\ufo2

📋 执行结果：
[UFO² 返回的成功/失败信息]

✅ 操作已完成（耗时 XX 秒）
```

若 UFO² 出错，回复格式：
```
⚠️ 电脑操作执行失败
原因：[具体的错误原因]
建议：[可行的解决方案或重试建议]
```

## 注意事项

- 执行完毕后可清理临时日志文件：`rm -f "/c/Users/Administrator/AppData/Local/Temp/ufo_assistant.log"`
- 若用户指令模棱两可（如"帮我看看电脑"），先向用户确认具体操作再执行
- 长耗时任务应给予用户进度提示（如"正在通过 UFO² 执行电脑操作，请稍候..."）
- UFO² 安全防护可能在敏感操作前弹确认框，需用户在屏幕前确认
- UFO² 在当前桌面操作，无画中画隔离，可能干扰用户正常使用
- 每步操作都调用 LLM，延迟较高，需耐心等待
- **改代码后**：若实际跑的是 `D:\tools\ufo2`，需把仓库改动同步过去，否则看不到效果

## 已踩坑 & 解决方案

| # | 问题 | 根因 | 解决方案 |
|---|------|------|----------|
| 1 | Evaluation Agent 报 AAD 错 / 评估报错后任务仍被判定成功 | `agents.yaml` 缺 `EVALUATION_AGENT`/`BACKUP_AGENT` 配置；评估是独立后处理，不影响核心操作 | 已补充配置（同火山引擎）。日志中核心操作有 `✅ SUCCESS` 即为成功，评估报错可忽略 |
| 2 | 微信中 `set_edit_text` 全部失败 | 微信使用自定义 Win32 控件，UIA `control_dict` 点击后丢失，报 `No application windows available` | **优选方案**：剪贴板脚本 + `keyboard_input` Ctrl+V（见上方微信工作流）。**兜底**：记事本写入→Ctrl+A→Ctrl+C 复制到剪贴板后同样操作 |
| 3 | 启动时 `CustomizedAgent (not in config)` | UFO² 尝试加载未配置的第三方 agent | 无害警告，可忽略 |
| 4 | 改了仓库 `tools/ufo2` 但行为不变 | 实际进程跑在 `D:\tools\ufo2` 旧副本 | 按路径优先级检查；或同步/ junction 两边目录 |

## 已知限制

- **UFO² 仅支持 Windows 10/11**，无法在其他平台使用
- **依赖多模态视觉模型**，需配置支持视觉能力的 API（当前使用火山引擎 Doubao Lite）
- **安全防护**开启时，UFO² 会在执行敏感操作前弹框确认，无法完全自动化
- **无隔离环境**，UFO² 直接在桌面操作，可能和你正在使用的软件冲突
- **需要用户保持电脑解锁状态**：UFO² 需要看到屏幕内容，锁屏状态下无法工作
