# omy-skills

可复用的 **Agent 技能集**（Claude Code / Codex / WorkBuddy / OpenCode 等）：把自然语言变成 **Android 手机** 或 **Windows 桌面** 上的自动化操作。

> 设计目标：`git clone` 后按平台安装指南配置 API Key 即可用，**不依赖作者本机路径**；密钥不入库。

## 技能一览

| 技能 | 说明 | 主机平台 | 本仓库自带 |
|------|------|----------|------------|
| [mobile-assistant](skills/mobile-assistant/) | 自然语言 → Android 自动化 | **macOS / Windows / Linux** | 配置模板（引擎 [mobilerun](https://github.com/droidrun/mobilerun)） |
| [pc-assistant](skills/pc-assistant/) | 自然语言 → Windows 桌面 UI | **仅 Windows 10/11** | 魔改 [UFO²](https://github.com/microsoft/UFO)（`tools/ufo2`） |

更完整的目录说明见 [SKILLS.md](SKILLS.md)。

## 5 分钟快速开始

### 0. 克隆仓库

```bash
git clone https://github.com/lindakun/omy-skills.git
cd omy-skills
export OMY_SKILLS_ROOT="$(pwd)"
```

```powershell
git clone https://github.com/lindakun/omy-skills.git
cd omy-skills
$env:OMY_SKILLS_ROOT = (Resolve-Path .).Path
```

### 1. 手机技能（mobile-assistant，推荐跨平台）

需要：ADB、已 USB 调试的 Android、`mobilerun`、多模态 LLM API（默认火山 Doubao）。

**macOS / Linux：**

```bash
chmod +x scripts/install-mobile.sh scripts/link-skills.sh
# 可选：brew install --cask android-platform-tools
# 可选：uv tool install mobilerun
./scripts/install-mobile.sh --api-key "你的火山引擎API_Key" --device-serial "adb序列号"
export MOBILERUN_CONFIG="$OMY_SKILLS_ROOT/tools/mobilerun/config.local.yaml"
```

**Windows：**

```powershell
# 若执行策略报错：Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\install-mobile.ps1 -ApiKey "你的火山引擎API_Key" -DeviceSerial "adb序列号"
```

详见 [skills/mobile-assistant/INSTALL.md](skills/mobile-assistant/INSTALL.md)。

### 2. PC 桌面技能（pc-assistant，仅 Windows）

```powershell
.\scripts\install-pc.ps1 -ApiKey "你的火山引擎API_Key"
```

详见 [skills/pc-assistant/INSTALL.md](skills/pc-assistant/INSTALL.md)。

### 3. 接入 Agent

```bash
./scripts/link-skills.sh          # macOS / Linux：链到已存在的 ~/.claude/skills 等
```

```powershell
.\scripts\link-skills.ps1
```

或将 `skills/*` 手动复制/软链到各工具的 skills 目录。  
运行时靠 `OMY_SKILLS_ROOT`（及 mobile 的 `MOBILERUN_CONFIG`）解析路径。

## 目录结构

```
omy-skills/
├── README.md
├── SKILLS.md                 # 技能目录与平台矩阵
├── .gitignore
├── scripts/
│   ├── install-mobile.sh     # mobile：生成 config.local.yaml（macOS/Linux）
│   ├── install-mobile.ps1    # mobile：同上（Windows）
│   ├── install-pc.ps1        # pc：venv + agents.yaml（Windows）
│   ├── link-skills.sh        # 软链 skills 到常见 Agent 目录
│   └── link-skills.ps1
├── skills/
│   ├── mobile-assistant/
│   │   ├── SKILL.md
│   │   └── INSTALL.md
│   └── pc-assistant/
│       ├── SKILL.md
│       └── INSTALL.md
└── tools/
    ├── mobilerun/
    │   ├── config.template.yaml       # 主机无关 Android 配置模板
    │   ├── config_multi_windows.yaml  # 旧名，兼容保留
    │   └── config.local.yaml          # 本地生成（gitignore）
    └── ufo2/                          # pc-assistant 运行时
        ├── MODIFICATIONS.md
        ├── config/ufo/
        ├── scripts/set_clipboard.py
        └── ufo/
```

## 路径与环境变量约定

| 变量 | 用途 | 是否必须 |
|------|------|----------|
| `OMY_SKILLS_ROOT` | 本仓库根目录绝对路径 | 强烈建议 |
| `VOLC_ARK_API_KEY` | 火山引擎方舟 API Key | 使用默认火山模型时需要 |
| `MOBILERUN_CONFIG` | mobile 使用的 yaml（推荐指向仓库 `config.local.yaml`） | mobile 推荐 |
| `UFO_ROOT` | 覆盖 UFO² 目录（默认 `$OMY_SKILLS_ROOT/tools/ufo2`） | 可选 |
| `UFO_PYTHON` | 覆盖 Python（默认 Windows venv 路径） | 可选 |
| `MOBILERUN_HOME` | mobilerun 源码目录（若用源码安装） | 可选 |

**mobile 配置策略：** 优先 `MOBILERUN_CONFIG` → 仓库内 `config.local.yaml` → 否则使用 mobilerun 默认用户配置（`mobilerun configure`）。安装脚本**不会**改写 Application Support / AppData 中的默认配置。

## 安全说明

- 仓库内 API Key **仅为占位符**（`YOUR_VOLC_ARK_API_KEY` 等）。
- 安装脚本写入**本地** `*.local.yaml` / `agents.yaml`；请勿把含真实 Key 的文件 `git commit`。
- `.gitignore` 已忽略 `venv/`、`.env`、`*.local.yaml` 等。

## 平台要求

- **mobile-assistant**：macOS / Windows / Linux 主机 + USB 调试 Android
- **pc-assistant**：Windows 10/11（UFO² 依赖 UI Automation）
- LLM：可访问的多模态 API（默认火山引擎 Doubao）
