# pc-assistant 安装指南

在 **任意 Windows 10/11** 机器上，从本仓库安装 PC 桌面自动化运行时。

---

## 依赖

| 依赖 | 说明 |
|------|------|
| Windows 10/11 | UFO² 依赖 UI Automation |
| Python **3.11** | 推荐；装机时勾选 Add to PATH |
| 本仓库 `tools/ufo2/` | 已含魔改 UFO²，无需再 clone 上游 |
| 多模态 LLM API | 默认火山引擎 Doubao（OpenAI 兼容协议） |

---

## 一键安装（推荐）

> ⚠️ 首次运行 PowerShell 脚本遇到执行策略报错？
> ```powershell
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
> ```

在仓库根目录：

```powershell
git clone https://github.com/lindakun/omy-skills.git
cd omy-skills

# 将 key 换成你的火山引擎方舟 API Key
.\scripts\install-pc.ps1 -ApiKey "ark-xxxxxxxx"
```

脚本会：

1. 定位仓库根并设置用户环境变量 `OMY_SKILLS_ROOT`
2. 在 `tools/ufo2` 创建 `venv` 并 `pip install -r requirements.txt`
3. 把 API Key 写入本地 `tools/ufo2/config/ufo/agents.yaml`（**请勿 commit 该文件若含真实 Key**）

也可先设环境变量再安装：

```powershell
$env:VOLC_ARK_API_KEY = "ark-xxxxxxxx"
.\scripts\install-pc.ps1
```

---

## 手动安装

### 1. Python 3.11

```powershell
python --version   # 期望 3.11.x
```

### 2. 虚拟环境与依赖

```powershell
cd tools\ufo2
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -U pip
pip install -r requirements.txt
```

### 3. 配置 API Key

编辑 `tools/ufo2/config/ufo/agents.yaml`，将所有 `YOUR_VOLC_ARK_API_KEY` 替换为真实 Key。  
四个 agent（`HOST_AGENT` / `APP_AGENT` / `EVALUATION_AGENT` / `BACKUP_AGENT`）都需要有效 Key。

获取 Key：[火山引擎方舟控制台](https://console.volcengine.com/ark/)

### 4. 环境变量

```powershell
$env:OMY_SKILLS_ROOT = "C:\path\to\omy-skills"   # 改成你的实际路径
# 可选覆盖：
# $env:UFO_ROOT = "$env:OMY_SKILLS_ROOT\tools\ufo2"
# $env:UFO_PYTHON = "$env:UFO_ROOT\venv\Scripts\python.exe"
```

### 5. 冒烟测试

```powershell
cd tools\ufo2
.\venv\Scripts\Activate.ps1
python -m ufo --task "pc-test" -r "Step 1: Open Notepad, type 'Hello UFO', wait 2 seconds, then close it."
```

### 6. 注册技能

把 `skills/pc-assistant` 提供给 Agent（复制到技能目录或配置技能路径），确保 Agent 能加载 `SKILL.md`。

---

## 故障排查

| 问题 | 处理 |
|------|------|
| AAD 认证错误 | 检查 `agents.yaml` 是否四 agent 齐全且 Key 非占位符 |
| 微信无法输入 | 使用 SKILL 中的剪贴板 + Ctrl+V 流程 |
| `pip install` 失败 | 确认 Python 3.11；必要时换镜像源 |
| 找不到 UFO | 设置 `OMY_SKILLS_ROOT` 指向本仓库根 |
| API 超时 | 检查 Key、网络与 `ark.cn-beijing.volces.com` 连通性 |

---

## 魔改说明

相对 [microsoft/UFO](https://github.com/microsoft/UFO) 的改动见：

[`tools/ufo2/MODIFICATIONS.md`](../../tools/ufo2/MODIFICATIONS.md)

主要包括：性能参数、`[no-verify]`、微信剪贴板脚本、火山引擎配置模板、CLI 白名单等。
