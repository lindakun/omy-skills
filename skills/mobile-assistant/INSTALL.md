# mobile-assistant 安装指南

手机自动化助理。将"帮我用手机打开B站搜索XX"这类自然语言指令，改写为 mobilerun goal 提示词，在 Android 设备上自动执行。

---

## 依赖总览

| 依赖 | 来源 | 用途 |
|------|------|------|
| **mobilerun** | [droidrun/mobilerun](https://github.com/droidrun/mobilerun)（GitHub 开源，源码无修改） | Android 自动化核心引擎 |
| **Python 3.11~3.13** | [python.org](https://www.python.org/) | 运行 mobilerun |
| **ADB** | [Android SDK Platform Tools](https://developer.android.com/tools/releases/platform-tools) | 连接 Android 设备 |
| **Android 手机** | — | 执行端，需开启 USB 调试 |

---

## 安装步骤

### 1. 安装 Python

从 [python.org](https://www.python.org/downloads/) 下载 Python 3.11 ~ 3.13 并安装。

**安装时务必勾选 "Add Python to PATH"。**

验证：

```powershell
python --version
# 预期输出：Python 3.11.x / 3.12.x / 3.13.x
```

### 2. 安装 ADB

1. 下载 [Android SDK Platform Tools](https://developer.android.com/tools/releases/platform-tools)
2. 解压到 `C:\Users\<你的用户名>\platform-tools\`
3. 将 `platform-tools` 目录添加到系统 PATH：
   - Win + R → `sysdm.cpl` → 高级 → 环境变量
   - 在「用户变量」中找到 `Path`，双击编辑
   - 新增一条：`C:\Users\<你的用户名>\platform-tools`
   - 确定保存

验证：

```powershell
adb version
# 预期输出：Android Debug Bridge version 1.0.41
```

### 3. 手机端设置

1. 打开手机「设置」→「关于手机」→ 连续点击「版本号」7 次，开启**开发者选项**
2. 进入「设置」→「开发者选项」→ 开启 **USB 调试**
3. 用 USB 线连接手机到电脑
4. 手机上会弹出「允许 USB 调试」对话框，勾选「始终允许」并点击「确定」

验证连接：

```powershell
adb devices
# 预期输出：
# List of devices attached
# PBV0216914011984    device
```

> **注意**：状态必须显示 `device`，如果显示 `unauthorized` 表示手机上还没有授权。

### 4. 安装 mobilerun

```powershell
# 克隆仓库
git clone https://github.com/droidrun/mobilerun.git
cd mobilerun

# 以开发模式安装 Python 包
pip install -e .

# 安装 Portal APK 到手机
mobilerun setup
```

> `mobilerun setup` 会自动下载并安装 Mobilerun Portal APK 到手机上，并启用无障碍服务。

验证安装：

```powershell
mobilerun ping
# 应该看到 Portal 已安装且可访问的确认信息
```

### 5. 配置 API Key

编辑 mobilerun 目录下的配置文件（通常是 `config.yaml` 或 `pyproject.toml`），找到 API Key 相关字段：

```yaml
# TODO: 替换为你的 API Key
api_key: "YOUR_API_KEY_HERE"
```

> API Key 通常来自你使用的 LLM 服务商（如火山引擎、OpenAI 等），具体配置字段因配置文件格式而异。

### 6. 验证全链路

```powershell
# 检查手机连接
adb devices

# 检查 Portal 状态
mobilerun ping

# 运行一个简单示例
mobilerun run "打开设置查看Android版本"
```

---

## 故障排查

| 问题 | 解决方案 |
|------|---------|
| `adb devices` 显示 `unauthorized` | 手机上重新点击「允许 USB 调试」，必要时撤销授权后重插 USB |
| `mobilerun ping` 失败 | 确保 Portal APK 已安装，无障碍服务已开启 |
| 运行时提示模型 API 不可用 | 检查配置文件中的 API Key 是否有效 |
| `pip install -e .` 报错 | 确认 Python 版本 3.11~3.13，不要使用 3.14+ |
| 手机连接后 `device` 状态闪烁 | 换一根 USB 数据线，部分充电线不支持数据传输 |

---

## 依赖文件参考

本技能还依赖一些外部 wrapper 脚本和配置文件（如 `start.py`、`config_multi_windows.yaml` 等），这些文件位于 [Auto-Test](https://github.com/lindakun/Auto-Test) 项目中。如有需要，请一并克隆：

```powershell
git clone https://github.com/lindakun/Auto-Test.git
```
