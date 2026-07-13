# macrun

`omy-skills` 的 **macOS 桌面** 薄运行时，供 `mac-assistant` 技能调用。

```bash
# 在 tools/macrun 下
python3.11 -m venv venv
source venv/bin/activate
pip install -e .
cp config.template.yaml config.local.yaml
# 编辑 API Key（仅 macrun run / 可选视觉 gate 需要）
macrun doctor
macrun dump-tree
macrun run "打开 TextEdit，输入 Hello mac-assistant"
```

## 策略概览

| 路径 | 策略 |
|------|------|
| `macrun run` | Accessibility 控件树为主，失败才截图 + LLM |
| `wechat-send` / `wechat-read` | **脚本路径**：备注后缀选人，默认**不调视觉** |
| 中文输入 | 剪贴板 `pbcopy` + Cmd+V |

## 微信 CLI

前置：联系人/群备注末尾加统一后缀（默认 `-1688`，见 `config`）。`文件传输助手` 免后缀。

```bash
# 发送（默认 send_mode=enter，须与微信「Enter 发送」一致）
macrun wechat-send --contact "陈可欣" --message "晚上好" -l /tmp/mac_assistant.log

# 读会话：只截图，不 OCR
macrun wechat-read --session "陈可欣" -l /tmp/mac_assistant.log
# → /tmp/wechat_screenshot.jpg
```

### wechat-send 可靠性要点

1. Esc + 点击输入带（防粘贴进搜索框）  
2. 剪贴板探测：`paste verify` / `send verify`  
3. 发送前取消全选（全选 + Enter 会删字不发）  
4. `send_mode` 对齐本机：`enter` | `cmd_enter` | `both`  
5. 仅失败时截图：`/tmp/wechat_send_fail.jpg`  

成功日志须含 `paste verify: ok` 与 `send verify: ok`。

### 相关配置（`config.local.yaml` → `wechat`）

见 `config.template.yaml` 注释：`remark_suffix`、`send_mode`、`focus_input`、`verify_send`、`fail_screenshot` 等。

技能说明：[`skills/mac-assistant/SKILL.md`](../../skills/mac-assistant/SKILL.md)  
安装：[`skills/mac-assistant/INSTALL.md`](../../skills/mac-assistant/INSTALL.md)

## 测试

```bash
python -m unittest discover -s tests -v
```
