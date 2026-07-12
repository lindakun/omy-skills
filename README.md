# omy-skills

达叔自建的 WorkBuddy 技能收藏集~ 🌸

## 技能列表

### mobile-assistant 📱
手机自动化助理。将"帮我用手机打开B站搜索XX"这类自然语言指令，改写为 mobilerun goal 提示词，在 Android 设备上自动执行。

### pc-assistant 🖥️
PC 桌面自动化助理。基于微软 UFO² 框架，将"用电脑操作XXX"等自然语言指令，在 Windows 桌面上自动完成 UI 操作。

## 目录结构

```
omy-skills/
├── README.md
├── .gitignore
├── skills/
│   ├── mobile-assistant/
│   │   ├── SKILL.md          # WorkBuddy 技能定义
│   │   └── INSTALL.md        # 安装指南
│   └── pc-assistant/
│       ├── SKILL.md          # WorkBuddy 技能定义
│       └── INSTALL.md        # 安装指南
└── tools/
    └── ufo2/                 # 魔改版 UFO² 源码（含 WeChat 兼容 + no-verify 优化）
```
