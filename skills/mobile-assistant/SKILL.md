---
name: mobile-assistant
description: 手机自动化助理。将"帮我用手机打开B站搜索XX并把结果发我"这类自然语言指令，改写为 mobilerun 可执行的 goal 提示词，调用 Auto-Test 项目的 start.py 在已连接的 Android 设备上执行移动端自动化（打开APP/搜索/点击/读取屏幕信息），并将执行结果在对话中回复给用户。依赖 adb 连接的 Android 设备。
---

# mobile-assistant 手机自动化助理

## 触发条件

当用户说**涉及手机操作**的指令时启用。典型触发词：
- "用手机..." / "帮我用手机..."
- "在手机上..." / "手机上..."
- "用手机自动化..."
- "手机帮我打开 XX APP..."

## 前置条件

本技能依赖以下路径和环境，执行前必须验证，不满足则直接提示用户：

1. **Auto-Test 项目**：`G:\github_pj\Auto-Test\start.py` —— 必须存在
2. **Android 设备已连接**：运行 `/c/Users/Administrator/platform-tools/adb.exe devices` 检查是否有 `device` 状态的设备；若无，提示："⚠️ 请用 USB 连接 Android 手机，开启 USB 调试并授权此电脑"
3. **Python 环境**：`C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe` —— 必须存在（装有 mobilerun 的受管 Python）

## 工作流

### 步骤 1：用户意图解析

解析用户自然语言指令，提取三要素：
- **目标 APP**：要打开的 APP（如"B站/哔哩哔哩"、"微信"、"抖音"）
- **操作**：做什么（搜索、点赞、滑动、点击等）
- **回传内容**：最终要告诉用户什么信息（如"第一个视频的名称"、"搜索结果"）

### 步骤 2：生成 mobilerun goal 提示词

将用户指令**改写为移动端 agent 能执行的清晰指令**。核心规则：

| 规则 | 说明 | 示例 |
|------|------|------|
| APP 用真名 | 使用手机上 APP 的实际名，中英文兼顾 | "哔哩哔哩(B站)" |
| "搜索X" | 明确写"在搜索框中输入'X'并执行搜索" | "在搜索框中输入'阿根廷世界杯'并执行搜索" |
| "把XX发我/告诉我" | **必须显式要求** agent 在最终完成消息（Goal achieved message）中包含该值 | "完成操作后，在最终回复消息中明确写出第一个视频的标题，然后退出APP" |
| 消除歧义 | 补足上下文，避免代词 | "在搜索结果页找到第一个视频"而非"找到它" |
| 退出 | 操作完成后建议加上"退出APP" | ", 完成后退出APP。" |

**示例映射（few-shot）：**

```
用户："帮我用手机打开B站搜索'阿根廷世界杯',然后把第一个视频名称发我"
→ goal: 在手机上打开哔哩哔哩(B站)APP。在搜索框中输入"阿根廷世界杯"并执行搜索。在搜索结果页找到第一个视频，读取它的标题。完成操作后，在最终回复消息中明确写出第一个视频的标题，然后退出APP。
```

```
用户："用手机给B站首页第一个视频点个赞"
→ goal: 打开哔哩哔哩(B站)APP，在首页找到第一个视频，点击点赞按钮，完成后退出APP。
```

```
用户："用手机打开抖音看看今天的热搜是什么"
→ goal: 打开抖音APP，查看今日热搜榜，读取热搜榜前三条的内容。完成操作后，在最终回复消息中明确写出热搜前三名，然后退出APP。
```

### 步骤 3：调用 start.py 执行

以受管 Python 置顶 PATH、启用无缓冲模式，在 Auto-Test 目录后台运行：

```bash
LOG_FILE="C:/Users/Administrator/AppData/Local/Temp/mobilerun_assistant.log"
cd /g/github_pj/Auto-Test && \
  PATH="/c/Users/Administrator/.workbuddy/binaries/python/versions/3.13.12:/c/Users/Administrator/platform-tools:$PATH" \
  PYTHONUNBUFFERED=1 \
  python -u start.py '<goal>' > "$LOG_FILE" 2>&1
```

**重要**：
- goal 文本在 bash 中用**单引号**包裹，避免内部双引号冲突（中文指令几乎不含单引号）
- 必须同时把 `platform-tools` 加入 PATH（start.py 内部用 bare `adb` 检测设备，而系统 PATH 中不含 adb）
- 使用 `run_in_background=true` 后台运行
- 日志文件固定路径：`C:\Users\Administrator\AppData\Local\Temp\mobilerun_assistant.log`
- 可能需要在执行前先确认日志目录存在（`mkdir -p`）

### 步骤 4：监控并解析结果

后台启动后轮询日志文件（最多等待 10 分钟）：
1. 检查 `🎉 Goal achieved:` 行 → 提取之后的文本作为成功结果
2. 检查 `未检测到 Android 设备！` → 提示用户连接设备
3. 检查 `错误` / `Error` 行 → 报告错误详情
4. 检查 `任务完成` → 提取最后的成功信息
5. 超时无结果 → 读取日志最后 20 行，报告当前执行状态

轮询策略：每 15 秒读一次日志文件。可用 `sleep 15 && cat <logfile>` 循环。

### 步骤 5：回传给用户

在**当前对话**中用清晰格式回复给用户。格式示例：

```
📱 已执行：打开B站 → 搜索"阿根廷世界杯" → 读取第一个视频

🎯 第一个视频名称：2026年阿根廷世界杯纪念特辑

✅ 操作顺利完成（耗时 XX 秒）
```

若设备未连接，回复格式：
```
⚠️ 无法执行手机操作
原因：未检测到 Android 设备。
请用 USB 连接手机，开启 USB 调试并授权此电脑，然后重试。
```

## 注意事项

- 不修改 Auto-Test 项目源码，仅调用其 `start.py` 入口
- 执行完毕后清理临时日志文件：`rm -f "C:/Users/Administrator/AppData/Local/Temp/mobilerun_assistant.log"`
- 若用户指令模棱两可（如"帮我看看手机"），先向用户确认具体操作再执行
- 长耗时任务（如搜索结果读取）应给予用户进度提示（如"正在通过手机执行，请稍候..."）
- longcat 会自动分析任务复杂度选择视觉模型：简单的点击/滑动操作用 `lite`，需要**读取屏幕文字/识别元素**的任务自动用 `turbo`（如搜索后读取标题、读取热搜榜等），无需在 goal 中手动 hints 模型选择

## 已知限制

- **微信（WeChat）聊天窗口不可操作**：微信聊天页面因安全/隐私机制，会屏蔽 Android 无障碍服务（Accessibility Service），导致 mobilerun 的 `get_state` 无法读取页面内容（返回 "No active window or root filtered out"）。可执行的步骤止步于「打开微信 → 看到聊天列表 → 点击聊天项」，进入聊天界面后无法进一步操作（输入、发送、读取消息等）。
- **解决方案**：若需向微信联系人发送消息，建议用户自行在手机上操作，或在 goal 中仅执行"打开微信并定位到联系人"的步骤，输入/发送部分需人工配合。

## 微信多模态读取工作流（绕过聊天页屏蔽）

虽然微信聊天页面屏蔽了无障碍服务和 adb `input tap`，但**聊天列表的主界面**（含每条聊天项的预览 snippet）是可截图的。利用这一点可以"看"到达达发的最后一条消息：

**步骤：**
1. **启动微信**：`adb shell am start -n com.tencent.mm/.ui.LauncherUI`
2. **等待加载**：`sleep 3`（让微信完成启动）
3. **截图**：`adb shell screencap -p /sdcard/x.png && adb pull /sdcard/x.png <本地路径>`
4. **多模态识别**：用 Read 工具加载截图，AI 自动识别聊天列表中每个联系人的最后消息预览（snippet）
5. **回传用户**：将识别的消息内容用纯文本格式回复给用户

**适用场景：**
- "打开微信看达达发了什么" → 截聊天列表图 → 识别 snippet → 回复
- "微信里张三给我发的是啥" → 同上
- 适用于微信**聊天列表主界面**能看到的内容；**不适用于**进入聊天页面后的多轮历史消息、发送消息等。

**注意：**
- 屏幕物理尺寸通常是 1080x1920，但截图工具返回的 PNG 是按 1:1 像素保存（与 `wm size` 一致）。`input tap` 在微信主界面有时会被屏蔽，但如果不点击也能拿到聊天列表预览（每条聊天的最后一两行消息），多数场景够用。
- 真正要看完整消息历史仍需在手机上进入聊天窗口（人工操作）。
