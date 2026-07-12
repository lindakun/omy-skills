# pc-assistant 安装指南

PC 桌面自动化助理。基于微软 UFO² 框架，将"用电脑操作XXX"等自然语言指令，在 Windows 桌面上自动完成 UI 操作（打开应用/点击/输入/读取信息等）。

---

## 依赖总览

| 依赖 | 来源 | 用途 |
|------|------|------|
| **UFO²（已魔改）** | 本仓库 `tools/ufo2/`（已包含完整魔改源码，无需额外下载） | 桌面自动化框架 |
| **Python 3.11** | [python.org](https://www.python.org/) 或 ComfyUI 自带的嵌入式 Python | 运行 UFO² |
| **火山引擎 API** | [volcengine.com](https://www.volcengine.com/) | 驱动 LLM 视觉模型 |

---

## 安装步骤

### 1. 安装 Python 3.11

UFO² 推荐 Python 3.11。从 [python.org](https://www.python.org/downloads/) 下载安装。

**安装时务必勾选 "Add Python to PATH"。**

验证：

```powershell
python --version
# 预期输出：Python 3.11.x
```

> **小提示**：如果你装了 ComfyUI，可以直接用它的嵌入式 Python，路径类似 `F:\ComfyUI_windows\python_embeded\python.exe`

### 2. 克隆本仓库（UFO² 已包含在内）

```powershell
git clone https://github.com/lindakun/omy-skills.git
cd omy-skills
```

UFO² 魔改版源码就在 `tools/ufo2/` 目录下，**不需要再从 GitHub 重新 clone UFO²**，也不用打补丁。

### 3. 创建虚拟环境并安装依赖

```powershell
cd tools\ufo2

# 创建虚拟环境（推荐在 ufo2 目录内）
python -m venv venv

# 激活虚拟环境
venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

> 安装可能需要几分钟，请耐心等待。

### 4. 配置 API Key

UFO² 依赖多模态视觉模型，当前使用**火山引擎 Doubao Lite**。

1. 打开 `config\ufo\agents.yaml`
2. 将文件中所有 `YOUR_VOLC_ARK_API_KEY` 替换为你的真实 API Key

配置文件格式示例：

```yaml
HOST_AGENT:
  API_TYPE: "openai"
  API_BASE: "https://ark.cn-beijing.volces.com/api/v3"
  API_KEY: "YOUR_VOLC_ARK_API_KEY"  # ← 在这里填入你的 Key
  API_MODEL: "doubao-seed-2-0-lite-260428"
```

> **如何获取火山引擎 API Key？**
> 1. 访问 [火山引擎方舟平台](https://console.volcengine.com/ark/)
> 2. 创建接入点，选择 Doubao 系列模型
> 3. 获取 API Key（格式为 `ark-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx-xxxxx`）

### 5. 验证环境

```powershell
# 确保虚拟环境已激活
venv\Scripts\activate

# 运行一个简单测试任务
python -m ufo --task "pc-test" -r "Step 1: Open Notepad, type 'Hello UFO', wait 2 seconds, then close it."
```

预期效果：系统会自动打开记事本 → 输入文字 → 等待后关闭。

---

## 故障排查

| 问题 | 解决方案 |
|------|---------|
| 启动时报 AAD 认证错误 | `agents.yaml` 中缺少 `EVALUATION_AGENT` 或 `BACKUP_AGENT` 配置。本仓库已配齐这 4 个 agent |
| 微信中 `set_edit_text` 失败 | 微信使用自定义 Win32 控件，无法直接输入文字。需使用剪贴板方案（见 SKILL.md 中的微信工作流） |
| 安全防护弹框 | 本魔改版已将 `SAFE_GUARD` 设为 `False`，减少了弹框，但系统级安全提示仍需人工确认 |
| API 调用超时 | 检查 API Key 是否有效、网络是否可访问 `ark.cn-beijing.volces.com` |
| `pip install -r requirements.txt` 报错 | 确认使用 Python 3.11（非 3.12/3.13），部分依赖可能不兼容更高版本 |

---

## 关于魔改

本仓库中的 UFO² 基于 [microsoft/UFO](https://github.com/microsoft/UFO) 开源项目，进行了以下优化改造：

| 修改文件 | 改动内容 |
|---------|---------|
| `config/ufo/system.yaml` | 优化超参：MAX_TOKENS=1000, SLEEP_TIME=0.3, SAFE_GUARD=False 等，大幅提升执行速度 |
| `config/ufo/agents.yaml` | 配齐 HOST_APP_EVALUATION_BACKUP 四个 agent，全部使用火山引擎 Doubao Lite |
| `requirements.txt` | numpy/pandas 版本放宽为 `>=`，避免版本冲突 |
| `ufo/client/mcp/local_servers/cli_mcp_server.py` | 添加 `python`/`powershell` 到白名单；`run_shell` 支持同步等待并返回输出 |
| `ufo/client/mcp/local_servers/ui_mcp_server.py` | control_dict 为空时自动刷新控件列表，增加容错性 |
| `ufo/agents/processors/...` | 新增 `[verify]/[no-verify]` 机制，确定性步骤跳过截图+LLM 验证，每步省约 25 秒 |
| `ufo/prompts/share/base/host_agent.yaml` | 提示词中追加 `needs_verification` 字段说明 |
| `scripts/set_clipboard.py` | 新增剪贴板写入脚本（详见下方） |

### set_clipboard.py 说明

微信等应用自定义 Win32 控件会导致 UFO² 的 `set_edit_text` 全部失败。解决方案是通过剪贴板中转：

1. 用 `python scripts/set_clipboard.py "要发送的文字"` 将文本写入 Windows 剪贴板
2. 在目标应用中用 Ctrl+V 粘贴

该脚本已包含在 `tools/ufo2/scripts/` 中。
