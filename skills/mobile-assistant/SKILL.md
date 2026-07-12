---
name: mobile-assistant
description: 手机自动化助理。将"帮我用手机打开B站搜索XX并把结果发我"这类自然语言指令，改写为 mobilerun 可执行的 goal，在已连接的 Android 设备上执行移动端自动化（打开APP/搜索/点击/读取屏幕信息），并将结果回复用户。依赖 adb 与 mobilerun。主机支持 macOS / Windows / Linux。
metadata:
  platforms: [macos, windows, linux]
  device: android
  requires: [adb, mobilerun]
---

# mobile-assistant 手机自动化助理

## 触发条件

当用户说**涉及手机操作**的指令时启用。典型触发词：
- "用手机..." / "帮我用手机..."
- "在手机上..." / "手机上..."
- "用手机自动化..."
- "手机帮我打开 XX APP..."

涉及「电脑/桌面」操作时用 `pc-assistant`（仅 Windows），不要用本技能。

## 路径与依赖解析（可移植）

**不要写死**任何个人盘符、用户名或作者机器路径。

### `REPO_ROOT`

1. 环境变量 `OMY_SKILLS_ROOT`
2. 搜索含 `tools/mobilerun` 与 `skills/mobile-assistant/SKILL.md` 的目录
3. 找不到 → 提示用户设置 `OMY_SKILLS_ROOT`

### 配置策略（二选一，优先仓库本地配置）

| 优先级 | 来源 | 说明 |
|--------|------|------|
| 1 | 环境变量 `MOBILERUN_CONFIG` | 推荐：指向仓库内 `config.local.yaml` |
| 2 | `{REPO_ROOT}/tools/mobilerun/config.local.yaml` | 由 `install-mobile.sh` / `.ps1` 从模板生成 |
| 3 | 不传 `-c`，使用 mobilerun **默认用户配置** | 由 `mobilerun configure` 生成；**不要**去改系统/应用支持目录里的文件，除非用户明确要求 |

技能侧**只读**上述路径；安装脚本也**只写**仓库内 `config.local.yaml`（gitignore），不覆盖用户已有的默认配置。

### 运行时

| 项 | 解析方式 |
|----|----------|
| `adb` | PATH 中的 `adb`（`adb devices` 至少一台 `device`） |
| `mobilerun` | PATH 中的 `mobilerun` CLI（`mobilerun --version`） |
| 配置 | 见上表 |
| 日志 | Unix：`/tmp/mobilerun_assistant.log`；Windows：`%TEMP%\mobilerun_assistant.log` |

### 前置检查（失败则提示安装，勿硬编码路径）

按顺序执行：

1. `adb version` 成功  
2. `adb devices` 中至少一台状态为 `device`（可用 `mobilerun devices`）  
3. `mobilerun --version` 成功  
4. 可选但推荐：`mobilerun doctor`、对目标设备 `mobilerun ping`  
5. **若使用仓库 `config.local.yaml` / `MOBILERUN_CONFIG`**：文件存在且视觉模型 API Key **不是** `YOUR_VOLC_ARK_API_KEY`；`serial` 不是 `YOUR_ADB_SERIAL`  
6. **若走 mobilerun 默认配置（优先级 3）**：跳过占位符检查，以 `mobilerun ping` / `run` 结果为准  

不满足时引导用户阅读 `skills/mobile-assistant/INSTALL.md`：

- macOS / Linux：`./scripts/install-mobile.sh --api-key ...`
- Windows：`.\scripts\install-mobile.ps1 -ApiKey ...`

## 工作流

### 步骤 1：解析意图

提取：目标 APP、操作、需要回传的信息。

### 步骤 2：生成 mobilerun goal

| 规则 | 说明 | 示例 |
|------|------|------|
| APP 用真名 | 中英文兼顾 | `哔哩哔哩(B站)` |
| 搜索写清楚 | 输入并执行搜索 | `在搜索框中输入"…"并执行搜索` |
| 回传写进最终消息 | 要求 Goal achieved 中包含结果 | `在最终回复中明确写出第一个视频的标题` |
| 消歧义 | 避免代词 | `搜索结果页第一个视频` |
| 建议退出 APP | 减少残留状态 | `完成后退出APP` |

**few-shot：**

```
用户：帮我用手机打开B站搜索"阿根廷世界杯"，把第一个视频名称发我
→ goal: 在手机上打开哔哩哔哩(B站)APP。在搜索框中输入"阿根廷世界杯"并执行搜索。在搜索结果页找到第一个视频，读取它的标题。完成操作后，在最终回复消息中明确写出第一个视频的标题，然后退出APP。
```

```
用户：用手机打开抖音看看今天热搜前三条
→ goal: 打开抖音APP，查看今日热搜榜前三条。完成操作后，在最终回复消息中明确写出热搜前三名，然后退出APP。
```

### 步骤 3：执行

优先使用官方 CLI（**不依赖**任何外部私有仓库）：

先解析配置路径：

```bash
# 伪代码
CONFIG="${MOBILERUN_CONFIG:-$REPO_ROOT/tools/mobilerun/config.local.yaml}"
# 若 CONFIG 文件不存在 → 不传 -c，使用 mobilerun 默认配置
```

**macOS / Linux（Bash）：**

```bash
LOG_FILE="${TMPDIR:-/tmp}/mobilerun_assistant.log"
GOAL='<goal 文本>'

if [[ -n "${MOBILERUN_CONFIG:-}" && -f "$MOBILERUN_CONFIG" ]]; then
  CONFIG="$MOBILERUN_CONFIG"
elif [[ -f "$REPO_ROOT/tools/mobilerun/config.local.yaml" ]]; then
  CONFIG="$REPO_ROOT/tools/mobilerun/config.local.yaml"
else
  CONFIG=""
fi

if [[ -n "$CONFIG" ]]; then
  nohup mobilerun run -c "$CONFIG" "$GOAL" >"$LOG_FILE" 2>&1 &
else
  nohup mobilerun run "$GOAL" >"$LOG_FILE" 2>&1 &
fi
echo $!   # 可选：记录 PID
```

**Windows（PowerShell）：**

```powershell
$log = Join-Path $env:TEMP "mobilerun_assistant.log"
$goal = '<goal 文本>'
$config = $env:MOBILERUN_CONFIG
if (-not $config -or -not (Test-Path $config)) {
  $candidate = Join-Path $env:OMY_SKILLS_ROOT "tools\mobilerun\config.local.yaml"
  if (Test-Path $candidate) { $config = $candidate } else { $config = $null }
}
if ($config) {
  Start-Process -FilePath "mobilerun" -ArgumentList @("run", "-c", $config, $goal) `
    -RedirectStandardOutput $log -RedirectStandardError $log -NoNewWindow
} else {
  Start-Process -FilePath "mobilerun" -ArgumentList @("run", $goal) `
    -RedirectStandardOutput $log -RedirectStandardError $log -NoNewWindow
}
```

要点：
- goal 用单引号或安全转义，避免引号冲突  
- 后台运行；确保 `adb` 在 PATH 中  
- 多设备时可用 `mobilerun run -d <serial> ...`  
- 复杂任务可加 `--reasoning`；需要截图理解可加 `--vision`  

### 步骤 4：监控（最多约 10 分钟）

每约 15 秒读一次日志：

| 信号 | 处理 |
|------|------|
| `Goal achieved` / 成功完成类文案 | 提取结果 |
| 未检测到设备 / no device / Can't find any android device | 提示连接手机并授权 USB 调试 |
| `Error` / 异常栈 | 报告错误 |
| 超时 | 贴日志末尾约 20 行 |

### 步骤 5：回复用户

```
📱 已执行：…
🎯 结果：…
✅ 完成（耗时 …）
```

## 微信相关限制

- 微信**聊天页**常屏蔽无障碍，`get_state` 可能失败；难以自动输入/发送/读完整聊天记录。  
- **聊天列表**仍可能截图 + 多模态识别 snippet：  
  1. `adb shell am start -n com.tencent.mm/.ui.LauncherUI`  
  2. 等待数秒  
  3. `adb shell screencap` + `adb pull`  
  4. 用读图能力识别列表预览并回复用户  

## 注意事项

- 不修改 mobilerun 上游源码；不擅自改用户默认配置目录  
- 配置用本仓库模板生成的 `config.local.yaml`，或用户自己的 `mobilerun configure` 结果  
- 指令不清时先确认  
- 长任务给进度提示  
- 结束后可删除临时日志  
