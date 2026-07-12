# macrun

`omy-skills` 的 **macOS 桌面** 薄运行时，供 `mac-assistant` 技能调用。

```bash
# 在 tools/macrun 下
python3.11 -m venv venv
source venv/bin/activate
pip install -e .
cp config.template.yaml config.local.yaml
# 编辑 API Key
macrun doctor
macrun dump-tree
macrun run "打开 TextEdit，输入 Hello mac-assistant"
```

策略：**Accessibility 控件树为主，失败才截图**。中文与微信优先剪贴板（`pbcopy` + Cmd+V）。
