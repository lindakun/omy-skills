# 技能目录（omy-skills）

面向 **Claude Code / Codex / WorkBuddy / OpenCode** 等支持 `SKILL.md` 的 Agent 工具。  
设计原则：可移植路径、密钥不入库、主机平台写清楚。

## 一览

| 技能 | 说明 | 主机平台 | 执行端 | 运行时 |
|------|------|----------|--------|--------|
| [mobile-assistant](skills/mobile-assistant/) | 自然语言 → 手机操作 | **macOS / Windows / Linux** | Android | [mobilerun](https://github.com/droidrun/mobilerun)（外置）+ 本仓库配置模板 |
| [pc-assistant](skills/pc-assistant/) | 自然语言 → 桌面 UI | **仅 Windows 10/11** | 本机桌面 | 本仓库 `tools/ufo2`（UFO² 魔改） |

## 安装入口

| 技能 | macOS / Linux | Windows |
|------|---------------|---------|
| mobile | `./scripts/install-mobile.sh` | `.\scripts\install-mobile.ps1` |
| pc | 不适用 | `.\scripts\install-pc.ps1` |

注册到本机 Agent 技能目录（可选）：

```bash
./scripts/link-skills.sh          # 或 --dry-run
```

```powershell
.\scripts\link-skills.ps1
```

## 环境变量

| 变量 | 用途 |
|------|------|
| `OMY_SKILLS_ROOT` | 本仓库根目录 |
| `MOBILERUN_CONFIG` | mobile：仓库内 `tools/mobilerun/config.local.yaml`（推荐） |
| `VOLC_ARK_API_KEY` | 火山方舟 Key（安装脚本可注入本地配置） |
| `UFO_ROOT` / `UFO_PYTHON` | pc-assistant 覆盖路径（Windows） |

## 约定

- Skill 正文只描述可移植命令与检查项，不写死盘符/用户名。
- 密钥与 `*.local.yaml` / 本地 `agents.yaml` 不提交；模板用占位符。
- mobile 安装脚本**只写仓库内配置**，不覆盖 mobilerun 用户默认配置目录。
