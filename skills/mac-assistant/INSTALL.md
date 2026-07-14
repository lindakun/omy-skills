# mac-assistant 安装指南

在 **macOS** 上安装 Mac 桌面自动化依赖（`macrun`）。

> 仅支持 macOS。Windows 请用 [pc-assistant](../pc-assistant/INSTALL.md)。

---

## 依赖

| 依赖 | 说明 |
|------|------|
| macOS 12+ | Accessibility + Screen Capture |
| Python **3.11+** | 推荐 3.11–3.13（可用 brew / miniconda / uv） |
| 本仓库 `tools/macrun` | 薄运行时 |
| **辅助功能**权限 | 读控件、点击、键入、剪贴板自动化 |
| **屏幕录制**权限 | `wechat-read` 截图、失败时 `wechat_send_fail` 截图 |
| 多模态 LLM API（可选） | 默认火山引擎 Doubao；**仅** `gates.send: true` 或 `macrun run` 智能体路径需要。默认 `wechat-send` / `wechat-read` **不调视觉** |

---

## 微信备注约定（选人必做）

`wechat-send` / `wechat-read` **选人不用视觉**，靠备注后缀保证唯一：

1. 在微信里给常联系的人/群改备注，末尾统一加后缀（默认 **`-1688`**）。  
   例：口语「LvLLM」→ 备注 `LvLLM-1688`。  
2. 配置项：`tools/macrun/config.local.yaml` → `wechat.remark_suffix`（可改）。  
3. **文件传输助手** 无法改备注，在 `no_suffix_sessions` 白名单内，搜索原名。  
4. 未改备注会导致搜索失败或进错会话，脚本 **直接 FAIL** 并提示目标搜索串。

### 本机微信发送键（必对齐）

打开微信设置，确认是 **Enter 发送** 还是 **⌘Enter 发送**，与配置一致：

| 微信设置 | `wechat.send_mode` |
|----------|-------------------|
| Enter 发送 | `enter`（默认推荐） |
| ⌘Enter 发送 | `cmd_enter` |
| 不确定 | `both`（兼容，略慢） |

---

## 一键安装

```bash
git clone https://github.com/lindakun/omy-skills.git
cd omy-skills
export OMY_SKILLS_ROOT="$(pwd)"

chmod +x scripts/install-mac.sh
./scripts/install-mac.sh --api-key "ark-xxxxxxxx"
# 可选：--persist-env 写入 ~/.zshrc

source tools/macrun/venv/bin/activate
export MACRUN_CONFIG="$OMY_SKILLS_ROOT/tools/macrun/config.local.yaml"
```

脚本会：

1. 在 `tools/macrun` 创建 venv 并 `pip install -e .`
2. 从 `config.template.yaml` 生成 `config.local.yaml` 并注入 Key  
3. **不会**自动修改系统隐私权限（需你手动授权）

---

## 系统权限（必做）

1. 打开 **系统设置 → 隐私与安全性**
2. **辅助功能**：勾选你将用来运行 Agent / 终端的 App  
   （Terminal、iTerm、WorkBuddy、Cursor、Claude、Grok 等——**谁启动 macrun 就勾谁**）
3. **屏幕录制**：同样勾选上述 App（读消息截图 / 失败截图）
4. 若刚勾选，**重启该 App** 后再试

检查：

```bash
macrun doctor
```

期望看到 `Accessibility: OK`；ScreenCapture 至少在授权后可通过。

---

## 验证

```bash
macrun dump-tree          # 前台 App AX 摘要
macrun run "打开 TextEdit，输入 Hello mac-assistant"
```

微信（需已安装微信 Mac，并完成备注后缀）：

```bash
# 读：应看到 query='…-1688'、screenshot saved；打开图确认会话
macrun wechat-read --session "文件传输助手" -l /tmp/mac_assistant.log
# 打开日志中 SCREENSHOT: 指向的路径（含会话名与时间戳）

# 发：须出现 paste verify: ok 与 send verify: ok
macrun wechat-send --contact "文件传输助手" \
  --message "macrun 安装验证" -l /tmp/mac_assistant.log
```

成功发送的日志特征：`send_mode=enter`（或你的配置）、`focus input`、`paste verify: ok`、`send verify: ok`、`✅ SUCCESS`。  
失败时查看 `/tmp/mac_assistant.log` 与 `/tmp/wechat_send_fail.jpg`。

---

## 注册到 Agent

```bash
./scripts/link-skills.sh
```

保证 Agent 能读到 `skills/mac-assistant/SKILL.md`。

---

## 故障排查

| 问题 | 处理 |
|------|------|
| Accessibility FAIL | 给**实际宿主**授权辅助功能并重启 App |
| screencapture 失败 | 授权屏幕录制 |
| API 错误 | 检查 `config.local.yaml` Key / 网络 / 模型名（仅 `run` 或视觉 gate 需要） |
| 找不到 macrun | `source tools/macrun/venv/bin/activate` 或把 venv/bin 加入 PATH |
| 进错会话 / 搜不到人 | 备注加后缀；日志中的 `query=` 应与微信备注一致 |
| `paste verify: FAIL` | 焦点未在输入框；看 fail 截图；可调 `input_click_x_ratio` / `input_click_bottom_inset` |
| 输入框有字一发送就空、无气泡 | 旧逻辑全选后 Enter 会删字；更新 macrun；日志应有 `collapse selection` |
| `send verify` 残留正文 | `send_mode` 与微信 Enter/⌘Enter 设置不一致 |
| 假成功（旧版） | 须有 `paste verify` + `send verify`；勿只认 `FINISH` |

---

## 配置说明

- 模板：`tools/macrun/config.template.yaml`
- 本地：`tools/macrun/config.local.yaml`（gitignore，勿提交真实 Key）
- 环境变量：`MACRUN_CONFIG`、`VOLC_ARK_API_KEY`、`OMY_SKILLS_ROOT`

微信相关默认策略：

- **选人 / 发送 / 读消息**：脚本 + 备注后缀 + 剪贴板探测，**不调视觉**
- **失败截图**：`fail_screenshot`（仅失败）
- **可选视觉**：`gates.send: true`（调试用 Gate2）
- 通用桌面 `macrun run`：AX 为主，失败才截图
