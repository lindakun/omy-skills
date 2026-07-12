# mobile-assistant 安装指南

在 **macOS / Windows / Linux 主机 + Android 手机** 上安装手机自动化技能依赖。

本技能调用开源 [mobilerun](https://github.com/droidrun/mobilerun)，**不依赖**作者私有仓库或本机绝对路径。  
安装脚本**只写入本仓库**内的 `tools/mobilerun/config.local.yaml`，**不会**覆盖 mobilerun 自带的用户默认配置目录。

---

## 依赖总览

| 依赖 | 用途 |
|------|------|
| 主机 OS | macOS / Windows / Linux |
| Python 3.11 ~ 3.13（或 uv） | 运行 / 安装 mobilerun |
| [ADB Platform Tools](https://developer.android.com/tools/releases/platform-tools) | 连接手机 |
| Android 手机 + USB 调试 | 执行端 |
| [mobilerun](https://github.com/droidrun/mobilerun) | 自动化引擎 |
| 本仓库 `tools/mobilerun/config.template.yaml` | 模型/设备配置模板 |
| 多模态 LLM API | 默认火山引擎 Doubao（也可改用其它 OpenAI 兼容提供商） |

---

## 快速安装

### 0. 克隆仓库

```bash
git clone https://github.com/lindakun/omy-skills.git
cd omy-skills
export OMY_SKILLS_ROOT="$(pwd)"   # macOS / Linux
```

```powershell
git clone https://github.com/lindakun/omy-skills.git
cd omy-skills
$env:OMY_SKILLS_ROOT = (Resolve-Path .).Path
```

### 1. ADB

**macOS：**

```bash
brew install --cask android-platform-tools
adb version
```

**Windows：** 下载 Platform Tools，加入用户 PATH，然后 `adb version`。

### 2. 手机

1. 开发者选项 → 开启 **USB 调试**
2. USB 连接电脑并在手机上点「允许」
3. 验证：

```bash
adb devices
# 应出现 <serial>    device
```

### 3. 安装 mobilerun

推荐（跨平台）：

```bash
# 需已安装 uv：https://docs.astral.sh/uv/
uv tool install mobilerun
mobilerun --version
```

或从源码：

```bash
git clone https://github.com/droidrun/mobilerun.git
cd mobilerun
pip install -e .    # 使用 Python 3.11–3.13
```

连接设备后：

```bash
mobilerun setup
mobilerun doctor
mobilerun ping
```

### 4. 生成本地配置（写入仓库内，不碰系统默认配置）

**macOS / Linux：**

```bash
chmod +x scripts/install-mobile.sh
./scripts/install-mobile.sh \
  --api-key "ark-xxxxxxxx" \
  --device-serial "你的设备序列号"

# 当前 shell 生效（脚本会打印 export）；需要写入 shell rc 时再加：
# ./scripts/install-mobile.sh --api-key "..." --device-serial "..." --persist-env

export OMY_SKILLS_ROOT="$(pwd)"
export MOBILERUN_CONFIG="$OMY_SKILLS_ROOT/tools/mobilerun/config.local.yaml"
```

**Windows（PowerShell）：**

> 若遇执行策略限制：
> ```powershell
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
> ```

```powershell
.\scripts\install-mobile.ps1 `
  -ApiKey "ark-xxxxxxxx" `
  -DeviceSerial "你的设备序列号"
# 默认写入用户环境变量；仅当前会话：加 -NoPersistEnv
```

脚本会：

- 从 `tools/mobilerun/config.template.yaml` 生成 `tools/mobilerun/config.local.yaml`
- 写入 API Key / 设备 serial（若提供）
- **不**修改 Application Support / AppData 下的 mobilerun 默认配置

**请勿**将含真实 Key 的 `config.local.yaml` 提交到 git。

### 5. 手动配置（可选）

```bash
cp tools/mobilerun/config.template.yaml tools/mobilerun/config.local.yaml
# 编辑：替换 YOUR_VOLC_ARK_API_KEY、YOUR_ADB_SERIAL
export MOBILERUN_CONFIG="$PWD/tools/mobilerun/config.local.yaml"
```

也可不设 `MOBILERUN_CONFIG`，改用：

```bash
mobilerun configure   # 写入 mobilerun 自己的默认配置路径
```

此时 Agent 在仓库内找不到 `config.local.yaml` 时，会直接调用 `mobilerun run`（走默认配置）。

### 6. 验证

```bash
adb devices
mobilerun doctor
mobilerun ping
mobilerun run -c "$MOBILERUN_CONFIG" "打开设置查看Android版本"
# 若未设置 MOBILERUN_CONFIG 且无 config.local.yaml：
# mobilerun run "打开设置查看Android版本"
```

### 7. 注册到 Agent 工具

```bash
./scripts/link-skills.sh           # macOS / Linux
# 或
.\scripts\link-skills.ps1          # Windows
```

将 `skills/mobile-assistant` 链接到 Claude Code / Codex / 通用 agents 等技能目录（见脚本帮助）。  
也可手动复制/软链到你的 Agent 技能路径。

---

## 故障排查

| 问题 | 处理 |
|------|------|
| `unauthorized` | 手机上重新授权 USB 调试 |
| `Can't find any android device` | 检查线缆、驱动（Windows）、`adb kill-server && adb start-server` |
| `mobilerun ping` 失败 | 重新 `mobilerun setup`，检查无障碍/Portal |
| API 不可用 | 检查 `config.local.yaml` 中 Key 与网络，或默认配置中的提供商 |
| 找不到配置 | 设置 `MOBILERUN_CONFIG` 或 `OMY_SKILLS_ROOT`；或依赖 `mobilerun configure` |
| 真机无响应 | 确认 serial 与 `adb devices` 一致 |
| macOS 系统 Python 过旧 | 用 `uv tool install mobilerun`，不必改系统 Python |

---

## 与 pc-assistant 的关系

| | mobile-assistant | pc-assistant |
|--|------------------|--------------|
| 主机 | macOS / Windows / Linux | **仅 Windows 10/11** |
| 执行端 | Android | Windows 桌面 UI |
| 引擎 | mobilerun（外置安装） | 本仓库 `tools/ufo2` |
| 安装 | `install-mobile.sh` / `.ps1` | `install-pc.ps1` |
