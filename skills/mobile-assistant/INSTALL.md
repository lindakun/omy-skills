# mobile-assistant 安装指南

在任意 **Windows 主机 + Android 手机** 上安装手机自动化技能依赖。

本技能调用开源 [mobilerun](https://github.com/droidrun/mobilerun)，**不依赖**任何作者私有仓库或本机绝对路径。

---

## 依赖总览

| 依赖 | 用途 |
|------|------|
| Python 3.11 ~ 3.13 | 运行 mobilerun |
| [ADB Platform Tools](https://developer.android.com/tools/releases/platform-tools) | 连接手机 |
| Android 手机 + USB 调试 | 执行端 |
| [mobilerun](https://github.com/droidrun/mobilerun) | 自动化引擎 |
| 本仓库 `tools/mobilerun/*.yaml` | 模型/设备配置模板 |
| 多模态 LLM API | 默认火山引擎 Doubao |

---

## 安装步骤

> ⚠️ 首次运行 PowerShell 脚本遇到执行策略报错？
> ```powershell
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
> ```

### 1. 克隆本仓库并设置根路径

```powershell
git clone https://github.com/lindakun/omy-skills.git
cd omy-skills
$env:OMY_SKILLS_ROOT = (Resolve-Path .).Path
```

### 2. Python

安装 3.11~3.13，勾选 Add to PATH。

```powershell
python --version
```

### 3. ADB

1. 下载 Platform Tools 并解压到任意目录（例如 `%LOCALAPPDATA%\Android\platform-tools`）
2. 将该目录加入用户 PATH
3. 验证：

```powershell
adb version
```

### 4. 手机

1. 开发者选项 → 开启 **USB 调试**
2. USB 连接电脑并授权
3. 验证：

```powershell
adb devices
# 应出现 <serial>    device
```

### 5. 安装 mobilerun

```powershell
git clone https://github.com/droidrun/mobilerun.git
cd mobilerun
pip install -e .
mobilerun setup
mobilerun ping
```

建议设置：

```powershell
$env:MOBILERUN_HOME = "C:\path\to\mobilerun"   # 你的实际 clone 路径
```

### 6. 生成本地配置（推荐脚本）

回到 **omy-skills** 仓库根：

```powershell
# 将 serial 换成 adb devices 里的设备号；模拟器可省略 -DeviceSerial
.\scripts\install-mobile.ps1 `
  -ApiKey "ark-xxxxxxxx" `
  -MobilerunHome $env:MOBILERUN_HOME `
  -DeviceSerial "你的设备序列号"
```

脚本会：

- 从模板生成 `tools/mobilerun/config.local.yaml`
- 写入 API Key（若提供）
- 设置用户环境变量 `MOBILERUN_CONFIG`（以及可选的 `MOBILERUN_HOME`）
- 若提供了 `MobilerunHome`，同步一份配置到该目录

**请勿**将含真实 Key 的 `config.local.yaml` 提交到 git。

### 7. 手动配置（可选）

```powershell
copy tools\mobilerun\config_multi_windows.yaml tools\mobilerun\config.local.yaml
# 编辑 config.local.yaml：替换 YOUR_VOLC_ARK_API_KEY，并设置 device serial
```

设备段说明：

- 模拟器：可使用模板中的 `android_emulator`（默认 serial `emulator-5554`）
- 真机：在配置中把 serial 改成 `adb devices` 显示的序列号

### 8. 验证

```powershell
adb devices
mobilerun ping
mobilerun run "打开设置查看Android版本"
```

### 9. 注册技能

将 `skills/mobile-assistant` 提供给 Agent，保证能加载 `SKILL.md`。

---

## 故障排查

| 问题 | 处理 |
|------|------|
| `unauthorized` | 手机上重新授权 USB 调试 |
| `mobilerun ping` 失败 | 重新 `mobilerun setup`，检查无障碍/Portal |
| API 不可用 | 检查 `config.local.yaml` 中 Key 与网络 |
| 找不到配置 | 设置 `MOBILERUN_CONFIG` 或 `OMY_SKILLS_ROOT` |
| 真机无响应 | 确认 serial 与 `adb devices` 一致，数据线支持数据传输 |

---

## 与 pc-assistant 的关系

| | mobile-assistant | pc-assistant |
|--|------------------|--------------|
| 执行端 | Android | Windows 桌面 |
| 引擎 | mobilerun（外置安装） | 本仓库 `tools/ufo2` |
| 安装脚本 | `scripts/install-mobile.ps1` | `scripts/install-pc.ps1` |
