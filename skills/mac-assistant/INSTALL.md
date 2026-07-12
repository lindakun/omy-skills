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
| 多模态 LLM API | 默认火山引擎 Doubao |
| **辅助功能**权限 | 读控件、点击、键入 |
| **屏幕录制**权限 | 失败时截图（非每步） |

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
   （Terminal、iTerm、WorkBuddy、Cursor、Claude 等——**谁启动 macrun 就勾谁**）
3. **屏幕录制**：同样勾选上述 App（用于失败截图）
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
# 微信（需已安装微信 Mac）
macrun run "打开 WeChat。用剪贴板粘贴测试流程仅打开主窗口即可，然后 finish 说明已打开。"
```

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
| API 错误 | 检查 `config.local.yaml` Key / 网络 / 模型名 |
| 找不到 macrun | `source tools/macrun/venv/bin/activate` 或把 venv/bin 加入 PATH |
| 微信输不了中文 | goal 强制剪贴板；见 SKILL 微信 few-shot |
| 点错控件 | `macrun dump-tree` 看 id，或收窄 goal 步骤 |

---

## 配置说明

- 模板：`tools/macrun/config.template.yaml`
- 本地：`tools/macrun/config.local.yaml`（gitignore，勿提交真实 Key）
- 环境变量：`MACRUN_CONFIG`、`VOLC_ARK_API_KEY`、`OMY_SKILLS_ROOT`

策略：**AX 为主，失败才截图**（`screenshot_on_failure` / `screenshot_when_tree_empty`）。
