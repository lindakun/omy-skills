# UFO² 魔改说明（相对 microsoft/UFO）

本目录是 [microsoft/UFO](https://github.com/microsoft/UFO)（UFO²）的 **vendored 魔改副本**，服务于 `pc-assistant` 技能：在 Windows 上跑桌面 UI 自动化，并针对微信输入、执行速度、火山引擎 API 做了本地化改造。

> 未与上游逐 commit 做完整 diff；以下清单来自源码中的 `OPTIMIZED` / `ADDED` 注释与人工核对（2026-07）。

---

## 目标

| 目标 | 做法 |
|------|------|
| 更快 | 减 token、减 sleep、关评估/高亮/部分日志；`[no-verify]` 跳过截图+多模态 |
| 微信可用 | 剪贴板脚本 + `run_shell` 同步 + CLI 白名单放行 `python` |
| 国内 API | `agents.yaml` 默认火山引擎方舟（Doubao），四 agent 配齐 |
| 更稳 | `control_dict` 空时自动刷新；MAX_RETRY 降低避免长时间空转 |

---

## 改动清单

### 1. 配置：`config/ufo/system.yaml`

标记为 `OPTIMIZED 2026-07-11` 的项（相对上游偏保守默认值）：

| 配置项 | 魔改倾向 | 作用 |
|--------|----------|------|
| `MAX_TOKENS` | 2000 → **1000** | 缩短 LLM 输出上限 |
| `MAX_RETRY` | 20 → **3** | 失败快速停 |
| `CONTROL_BACKEND` | 去掉 omniparser | 仅 `uia`（omniparser 端点不可用） |
| `SLEEP_TIME` / `RECTANGLE_TIME` | 1 → **0.3** | 步间延迟 |
| `SAFE_GUARD` | True → **False** | 少弹确认框 |
| `HIGHLIGHT_BBOX` | True → **False** | 不画标注框 |
| `LOG_LEVEL` | DEBUG → **WARNING** | 少日志开销 |
| `INCLUDE_LAST_SCREENSHOT` | True → **False** | 少 token |
| `REQUEST_TIMEOUT` | 250 → **120** | 更快超时 |
| `LOG_TO_MARKDOWN` / `SCREENSHOT_TO_MEMORY` | → **False** | 少 I/O |
| `EVA_SESSION` / `EVA_ALL_SCREENSHOTS` | → **False** | 跳过易崩的评估链路 |
| `MCP_TOOL_TIMEOUT` | 30 → **10** | 适配 `set_clipboard.py`（&lt;2s） |

### 2. 配置：`config/ufo/agents.yaml`

- 四个 agent 均配置：`HOST_AGENT` / `APP_AGENT` / `EVALUATION_AGENT` / `BACKUP_AGENT`
- `API_TYPE: openai` 兼容协议，`API_BASE` 指向火山方舟
- **仓库内 API Key 仅为占位符** `YOUR_VOLC_ARK_API_KEY`，真实 Key 只写本地运行目录

### 3. 依赖：`requirements.txt`

- `numpy` / `pandas` 等版本约束放宽为 `>=`，降低本机装包冲突概率

### 4. CLI MCP：`ufo/client/mcp/local_servers/cli_mcp_server.py`

- `ALLOWED_CLI_COMMANDS` 增加 **`python` / `python.exe` / `powershell` / `powershell.exe`**（`ADDED 2026-07-11`）
- `run_shell(..., wait_for_completion=True)`：同步等待并回传 stdout/stderr（剪贴板脚本必需）

### 5. UI MCP：`ufo/client/mcp/local_servers/ui_mcp_server.py`

- `_verify_id`：当 `control_dict` 为空时，从 `selected_app_window` **自动刷新**控件列表（微信等场景点击后控件树丢失时的容错）

### 6. `[verify]` / `[no-verify]` 流水线

| 文件 | 改动 |
|------|------|
| `ufo/module/context.py` | 新增 `ContextNames.NEEDS_VERIFICATION` |
| `ufo/agents/processors/schemas/response_schema.py` | 响应字段支持 `needs_verification` |
| `ufo/agents/processors/strategies/host_agent_processing_strategy.py` | 解析 LLM 的 `needs_verification`；无字段时按 subtask 文本模式推断 |
| `ufo/agents/processors/host_agent_processor.py` | 写入 global context |
| `ufo/agents/processors/strategies/app_agent_processing_strategy.py` | `needs_verification=False` 时跳过截图采集、控件信息、多模态 LLM（text-only） |
| `ufo/prompts/share/base/host_agent.yaml` | 强制输出 `needs_verification`；说明与 request 中 `[no-verify]`/`[verify]` 的对应关系 |

**技能侧约定**：request 里对机械步骤写 `[no-verify]`（如 Ctrl+V、Enter），需确认 UI 的步骤写 `[verify]`，约省 **~25s/步**。

### 7. 新增脚本：`scripts/set_clipboard.py`

- 通过 `win32clipboard` 把 `sys.argv` 文本写入系统剪贴板
- 配合微信：无法用 `set_edit_text` 时，改用 **脚本写剪贴板 + `keyboard_input` 发 Ctrl+V**

---

## 未改 / 上游保留部分

- Galaxy / AIP / Dataflow / WebUI 等大体量模块随源码一并 vendored，**非本技能主路径**，未做针对性业务魔改
- License 仍为上游 MIT（见 `LICENSE`）
- 安全相关 SSRF/路径校验等上游修复尽量保留；`SAFE_GUARD=False` 会降低交互式确认，**仅建议可信本机使用**

---

## 与本机 `D:\tools\ufo2` 的关系

| 位置 | 角色 |
|------|------|
| 仓库 `tools/ufo2` | **版本源**（git 跟踪；Key 占位） |
| `D:\tools\ufo2` + `D:\tools\ufo_venv` | 可选**运行副本**（可含真实 Key、logs；勿提交） |

关键魔改文件在两边应对齐（`system.yaml`、`cli_mcp_server.py`、`ui_mcp_server.py`、`set_clipboard.py`、processors 等）。路径解析顺序见 `skills/pc-assistant/SKILL.md`。

---

## 建议的上游同步方式

1. 记录当前魔改文件列表（本文件）
2. 拉取 microsoft/UFO 新版本到临时目录
3. 仅合并 `ufo/` 核心与 `config/`，再重放本清单中的补丁
4. 跑一次记事本冒烟 + 微信剪贴板发送冒烟
