---
name: video-dl
description: 基于 yt-dlp 的视频下载技能，支持 X.com(Twitter)、YouTube、Bilibili 等平台。自动识别平台并附加推荐参数完成下载。
metadata:
  platforms: [macos, linux, windows]
  requires: [yt-dlp, python3]
---

# video-dl 视频下载

基于 [yt-dlp](https://github.com/yt-dlp/yt-dlp) 的视频下载技能，从 URL 自动识别平台，附加该平台最佳参数完成下载。

## 支持平台

| 平台 | URL 特征 | 高清是否需要登录 |
|------|----------|:--:|
| YouTube | `youtube.com/watch`、`youtu.be/`、`youtube.com/shorts/` | **通常需要** cookies（反爬验证） |
| X.com / Twitter | `x.com/*/status/`、`twitter.com/*/status/` | **需要** cookies |
| Bilibili | `bilibili.com/video/`、`b23.tv/` | 720p 以上需要 cookies |

## 环境准备

### 常量

```bash
PYTHON=/Users/linda/.workbuddy/binaries/python/versions/3.13.12/bin/python3
PIP_TARGET=/Users/linda/.workbuddy/binaries/python/envs/default
YT_DLP=$PIP_TARGET/bin/yt-dlp
FFMPEG=/opt/homebrew/bin/ffmpeg   # macOS Homebrew 路径
NODE=/Users/linda/.workbuddy/binaries/node/versions/22.22.2/bin/node
```

### 首次安装

```bash
$PYTHON -m venv $PIP_TARGET
$PIP_TARGET/bin/pip install yt-dlp
```

### 更新

```bash
$PIP_TARGET/bin/pip install -U yt-dlp
```

### FFmpeg（强烈建议）

Bilibili / YouTube 的高清视频通常音视频分轨，需要 FFmpeg 合并。**隔离 venv 的 PATH 不包含 Homebrew 路径**，需显式指定：

```bash
# 安装（macOS）
brew install ffmpeg

# 验证（两条都需通过）
which ffmpeg && ffmpeg -version >/dev/null 2>&1 && echo "ffmpeg OK"
```

缺失时 yt-dlp 产出分轨文件（如 `.f100026.mp4` + `.f30280.m4a`），需手动合并。

### JS 运行时（YouTube 必备）

YouTube 已启用 n-sig 反爬，需要 Node.js 运行时 + 远程破解脚本：

```bash
# 验证 Node 可用
$NODE --version
```

无需额外安装，隔离环境已自带 Node.js。yt-dlp 首次使用时会自动从 GitHub 下载 solver 脚本（`--remote-components ejs:github`）。

---

## 工作流

收到下载请求后，按以下步骤执行：

### Step 1 — 解析请求

从用户消息中提取：
- **URL**：视频链接
- **需求**：全视频 / 仅音频 / 字幕 / 指定画质
- **输出目录**：用户指定 或 默认当前目录

### Step 2 — 环境检查

```bash
$YT_DLP --version
```

若未安装则执行首次安装。

**FFmpeg 检查**（Bilibili/YouTube 必备）：

```bash
$FFMPEG -version >/dev/null 2>&1 && echo "FFmpeg OK" || echo "FFmpeg MISSING"
```

### Step 3 — 识别平台、组装参数

根据 URL 域名匹配平台，基础参数 + 平台增强参数：

```bash
BASE_ARGS="--no-playlist -o \"%(title)s.%(ext)s\""
FFMPEG_ARGS="--ffmpeg-location $FFMPEG"
JS_ARGS="--js-runtimes node:$NODE --remote-components ejs:github"
```

| 平台 | 增强参数 |
|------|---------|
| YouTube | `--cookies-from-browser chrome $JS_ARGS -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best" --merge-output-format mp4` |
| X.com | `--cookies-from-browser chrome` |
| Bilibili | `--cookies-from-browser chrome --merge-output-format mp4`（高清时；低清可省略 cookies） |

> **FFmpeg 可用时**，YouTube 和 Bilibili 必须加 `--merge-output-format mp4` 和 `$FFMPEG_ARGS`，否则产出分轨文件。
> **YouTube 必须加 `$JS_ARGS`**，否则 n-sig 反爬会导致只有 storyboard 图片可用。

### Step 4 — 执行

```bash
cd "$OUTPUT_DIR"
$YT_DLP $BASE_ARGS $FFMPEG_ARGS $JS_ARGS $PLATFORM_ARGS "$URL"
```

> `$FFMPEG_ARGS` / `$JS_ARGS` 始终带上：FFmpeg 可用时自动合并，不可用时退化为分轨；JS 运行时不适用时 yt-dlp 自行忽略。

### Step 5 — 验证

```bash
ls -lh "$OUTPUT_DIR"/*.mp4 "$OUTPUT_DIR"/*.mkv "$OUTPUT_DIR"/*.webm 2>/dev/null | tail -1
```

文件存在且大小 > 0 → 成功。

**若产出分轨文件**（如 `.f100026.mp4` + `.f30280.m4a`），用 FFmpeg 合并后删除分轨：

```bash
$FFMPEG -y -i '视频.fXXXXX.mp4' -i '音频.fXXXXX.m4a' -c copy '文件名.mp4' \
  && rm -f '视频.f'* '音频.f'*
```

### Step 6 — 报告

```
📥 已下载：{文件名}
📏 大小：{文件大小}
⏱ 耗时：{秒}
```

---

## 参数速查

### 格式选择 `-f`

| 值 | 含义 |
|----|------|
| `best` | 最佳单一文件 |
| `bestvideo+bestaudio` | 最佳视频+最佳音频（需 FFmpeg 合并） |
| `bestvideo[height<=1080]+bestaudio` | 限制 1080p |
| `worst` | 最小文件 |
| `-F` | 仅列出可用格式（不下载） |

### 输出模板 `-o`

| 模板 | 示例输出 |
|------|---------|
| `"%(title)s.%(ext)s"` | `视频标题.mp4` |
| `"%(title)s-%(id)s.%(ext)s"` | `标题-dQw4w9WgXcQ.mp4` |
| `"~/Downloads/%(title)s.%(ext)s"` | 指定目录 |

### 常用开关

| 开关 | 作用 |
|------|------|
| `--no-playlist` | 只下载单个视频 |
| `--cookies-from-browser chrome` | 从 Chrome 读取登录态 |
| `--extract-audio --audio-format mp3` | 仅提取音频为 mp3 |
| `--write-subs --sub-lang zh,en` | 下载中英文字幕 |
| `--embed-subs` | 字幕嵌入视频文件 |
| `--list-formats` / `-F` | 列出可用格式 |
| `--limit-rate 5M` | 限速 |
| `--proxy socks5://127.0.0.1:1080` | 代理 |

---

## 各平台命令速查

### YouTube

```bash
YT_DLP="/Users/linda/.workbuddy/binaries/python/envs/default/bin/yt-dlp"
NODE="/Users/linda/.workbuddy/binaries/node/versions/22.22.2/bin/node"

# 最佳画质（完整参数：cookies + JS运行时 + FFmpeg合并）
$YT_DLP --no-playlist --cookies-from-browser chrome \
  --js-runtimes node:$NODE --remote-components ejs:github \
  --ffmpeg-location /opt/homebrew/bin/ffmpeg \
  -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best" \
  --merge-output-format mp4 -o "%(title)s.%(ext)s" "URL"

# 限制 1080p
$YT_DLP --no-playlist --cookies-from-browser chrome \
  --js-runtimes node:$NODE --remote-components ejs:github \
  --ffmpeg-location /opt/homebrew/bin/ffmpeg \
  -f "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best" \
  --merge-output-format mp4 -o "%(title)s.%(ext)s" "URL"

# 仅音频
$YT_DLP --no-playlist --cookies-from-browser chrome \
  --js-runtimes node:$NODE --remote-components ejs:github \
  -x --audio-format mp3 -o "%(title)s.%(ext)s" "URL"

# 带字幕
$YT_DLP --no-playlist --cookies-from-browser chrome \
  --js-runtimes node:$NODE --remote-components ejs:github \
  --ffmpeg-location /opt/homebrew/bin/ffmpeg \
  -f "bestvideo+bestaudio" --merge-output-format mp4 \
  --write-subs --sub-lang zh-Hans,en --embed-subs -o "%(title)s.%(ext)s" "URL"

# 先看格式再选
$YT_DLP -F "URL"
```

### X.com / Twitter

```bash
YT_DLP="/Users/linda/.workbuddy/binaries/python/envs/default/bin/yt-dlp"

# 基本下载（需要 Chrome cookies）
$YT_DLP --no-playlist --cookies-from-browser chrome -o "%(title)s.%(ext)s" "URL"

# Chrome cookies 失败时尝试 Safari
$YT_DLP --no-playlist --cookies-from-browser safari -o "%(title)s.%(ext)s" "URL"
```

### Bilibili

```bash
YT_DLP="/Users/linda/.workbuddy/binaries/python/envs/default/bin/yt-dlp"

# 高清下载（推荐：cookies + 音视频合并）
$YT_DLP --no-playlist --cookies-from-browser chrome \
  --ffmpeg-location /opt/homebrew/bin/ffmpeg --merge-output-format mp4 \
  -o "%(title)s.%(ext)s" "URL"

# 匿名下载（低清，通常 ≤720p，不需要 FFmpeg）
$YT_DLP --no-playlist -o "%(title)s.%(ext)s" "URL"

# 带弹幕
$YT_DLP --no-playlist --write-subs --sub-lang all -o "%(title)s.%(ext)s" "URL"
```

### 通用（未知平台）

```bash
YT_DLP="/Users/linda/.workbuddy/binaries/python/envs/default/bin/yt-dlp"

# 先列出格式
$YT_DLP -F "URL"
# 选好格式后下载
$YT_DLP --no-playlist -f best -o "%(title)s.%(ext)s" "URL"
```

---

## 输出位置

- **默认**：当前工作目录
- **用户指定**：`-o "~/Downloads/%(title)s.%(ext)s"`
- **批量下载**：建议分目录 `-o "~/Downloads/yt-dl/%(title)s.%(ext)s"`

---

## 红线

1. **不下载版权保护内容**（DRM、付费墙后内容）。若 yt-dlp 报 DRM 错误，直接告知用户无法下载。
2. **不滥用**。不批量爬取、不攻击服务器。同一个网站两次请求间隔 ≥ 3 秒。
3. **cookies 安全**。`--cookies-from-browser` 只在本地使用，cookies 不会发送给第三方。
4. **必须验证结果**。下载后确认文件存在且大小合理，才报告成功。
5. **不伪造 UA / 不绕过明确的访问限制**。
6. **仅下载用户明确提供的 URL**，不自行搜索或猜测。

---

## 故障排查

| 现象 | 原因 | 处理 |
|------|------|------|
| `cookies-from-browser` 报错 | 浏览器未登录对应网站 | 让用户先在 Chrome 中登录，再重试 |
| Chrome cookies 失败 | Chrome 正在运行导致锁定 | 尝试 `--cookies-from-browser safari` |
| `HTTP Error 403` | 被网站拦截 | 可能需要 cookies 或代理 |
| `Requested format not available` | 所选格式不存在 | 用 `-F` 列出实际可用格式，选存在的 |
| 下载速度极慢 | 网络问题 | 尝试 `--limit-rate 10M` 或换代理 |
| Bilibili 只能下 360p | 未登录 | 加 `--cookies-from-browser chrome` |
| `WARNING: ffmpeg not found` | 缺少 FFmpeg 或 PATH 不包含 Homebrew | `brew install ffmpeg`；始终用 `--ffmpeg-location /opt/homebrew/bin/ffmpeg` 显式指定 |
| X.com 视频为 0 字节 | 未传 cookies | 必须 `--cookies-from-browser` |
| 出现 `n challenge solving failed` / 只有 storyboard 图片 | YouTube 反爬升级，缺 JS 运行时 | 加 `--js-runtimes node:$NODE --remote-components ejs:github` |
| 产出两个分轨文件（`.fXXXXX.mp4` + `.fXXXXX.m4a`） | FFmpeg 未找到，yt-dlp 无法合并 | 用 `--ffmpeg-location` 显式指定；或手动 `ffmpeg -i 视频 -i 音频 -c copy 输出.mp4` |
