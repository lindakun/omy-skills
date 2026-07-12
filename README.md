# omy-skills

可复用的 **WorkBuddy / Agent 技能集**：把自然语言变成手机或 Windows 桌面上的自动化操作。

> 设计目标：`git clone` 后按安装指南配置 API Key，即可在任意 Windows 机器上使用，**不依赖作者本机路径**。

## 技能一览

| 技能 | 说明 | 平台 | 本仓库自带运行时 |
|------|------|------|------------------|
| [mobile-assistant](skills/mobile-assistant/) | 自然语言 → Android 手机自动化 | Windows 主机 + Android 手机 | 配置模板（引擎用 [mobilerun](https://github.com/droidrun/mobilerun)） |
| [pc-assistant](skills/pc-assistant/) | 自然语言 → Windows 桌面 UI 自动化 | Windows 10/11 | 魔改版 [UFO²](https://github.com/microsoft/UFO)（`tools/ufo2`） |

## 5 分钟快速开始

> ⚠️ **首次运行 PowerShell 脚本？** 如果遇到执行策略报错，先运行：
> ```powershell
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
> ```

### 0. 克隆仓库

```powershell
git clone https://github.com/lindakun/omy-skills.git
cd omy-skills
```

建议设置环境变量（技能与安装脚本都会用到）：

```powershell
# 当前会话
$env:OMY_SKILLS_ROOT = (Resolve-Path .).Path

# 可选：写入用户环境变量（永久）
[System.Environment]::SetEnvironmentVariable("OMY_SKILLS_ROOT", $env:OMY_SKILLS_ROOT, "User")
```

### 1. 安装 PC 桌面技能（pc-assistant）

```powershell
# 需要 Python 3.11 + 火山引擎 API Key
.\scripts\install-pc.ps1 -ApiKey "你的火山引擎API_Key"
```

详见 [skills/pc-assistant/INSTALL.md](skills/pc-assistant/INSTALL.md)。

### 2. 安装手机技能（mobile-assistant）

```powershell
# 需要 Python 3.11~3.13、ADB、已开启 USB 调试的 Android 手机
.\scripts\install-mobile.ps1 -ApiKey "你的火山引擎API_Key"
```

详见 [skills/mobile-assistant/INSTALL.md](skills/mobile-assistant/INSTALL.md)。

### 3. 接入 Agent 技能

将 `skills/pc-assistant`、`skills/mobile-assistant` 注册/复制到你的 Agent 技能目录（WorkBuddy、Claude Code skills 等），保证 Agent 能读到对应 `SKILL.md`。

技能运行时会按 `OMY_SKILLS_ROOT`（或自动探测含 `tools/ufo2` 的仓库根）解析路径，无需改源码。

## 目录结构

```
omy-skills/
├── README.md
├── .gitignore
├── scripts/
│   ├── install-pc.ps1        # PC 技能一键安装（venv + API Key）
│   └── install-mobile.ps1    # 手机技能配置生成 + 环境变量
├── skills/
│   ├── mobile-assistant/
│   │   ├── SKILL.md          # 手机自动化技能定义（Agent 入口）
│   │   └── INSTALL.md        # ADB/mobilerun/手机调试 安装指南
│   └── pc-assistant/
│       ├── SKILL.md          # PC 桌面自动化技能定义（Agent 入口）
│       └── INSTALL.md        # UFO² venv/火山 API 安装指南
└── tools/
    ├── ufo2/                 # 魔改 UFO²（pc-assistant 运行时，44K+ 行 Python）
    │   ├── MODIFICATIONS.md  # 魔改清单（性能/微信/火山引擎）
    │   ├── config/ufo/
    │   │   ├── agents.yaml   # 四 Agent 配置模板（火山 Doubao）
    │   │   ├── system.yaml   # 系统参数优化配置
    │   │   └── mcp.yaml      # MCP 集成配置
    │   ├── scripts/
    │   │   └── set_clipboard.py  # 剪贴板脚本（微信专用）
    │   └── ufo/              # UFO² 核心源码
    └── mobilerun/
        └── config_multi_windows.yaml  # mobilerun 多模型/多设备配置模板
```

## 路径与环境变量约定

| 变量 | 用途 | 是否必须 |
|------|------|----------|
| `OMY_SKILLS_ROOT` | 本仓库根目录绝对路径 | 强烈建议 |
| `VOLC_ARK_API_KEY` | 火山引擎方舟 API Key（安装脚本可写入配置） | 使用默认模型时必须 |
| `UFO_ROOT` | 覆盖 UFO² 源码目录（默认 `$OMY_SKILLS_ROOT/tools/ufo2`） | 可选 |
| `UFO_PYTHON` | 覆盖 Python 解释器（默认 `$UFO_ROOT/venv/Scripts/python.exe`） | 可选 |
| `MOBILERUN_HOME` | mobilerun 源码/安装目录 | mobile 技能建议设置 |
| `MOBILERUN_CONFIG` | mobilerun 使用的 yaml 配置文件路径 | 可选 |

## 安全说明

- 仓库内 API Key **仅为占位符**（`YOUR_VOLC_ARK_API_KEY` 等）。
- 安装脚本会在**本地配置文件**中写入你提供的 Key；请勿把含真实 Key 的文件 `git commit`。
- 已在 `.gitignore` 中忽略 `venv/`、`.env`、`*.local.yaml` 等。

## 平台要求

- **pc-assistant**：Windows 10/11（UFO² 依赖 UIA）
- **mobile-assistant**：Windows 主机 + USB 调试 Android 设备
- 两个技能都需要可访问多模态 LLM API（默认火山引擎 Doubao）
