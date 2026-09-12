---
name: unsloth-studio-vision-tuning
description: 排查并调优 unsloth-studio 本地多模态（视觉）模型的部署参数。当出现"大图/高分辨率截图请求返回 HTTP 500"、"Could not reach an upstream service"、"llama-server 崩溃/SIGABRT"、加载参数未设置、上下文被压缩、输出重复循环/空白刷屏/大量空格等症状时使用。覆盖根因定位（n_ubatch 断言、空格对齐失控）、参数矩阵实测、崩溃报告与日志取证。
metadata:
  platforms: [macos, linux]
  requires: [python3, curl, unsloth-studio]
  agent_created: true
---

# unsloth-studio 视觉模型部署调参

本地用 unsloth-studio 跑多模态模型时，**"大图返回 HTTP 500"几乎总是 `n_ubatch` 没设导致的**。
本技能给出取证 → 定位 → 修复 → 验证的完整闭环。

## 一、30 秒快速判断

现象：小图 OK，一旦超过某个尺寸就 `HTTP 500 {"message":"Could not reach an upstream service"}`。

```bash
# 1) 看 batch 参数是否为空
curl -s "$BASE/api/inference/status" -H "Authorization: Bearer $TOKEN" -o /tmp/st.json
python3 -c "import json;d=json.load(open('/tmp/st.json'),strict=False);\
print('n_batch',d.get('requested_n_batch'),'n_ubatch',d.get('requested_n_ubatch'),'ctx',d.get('context_length'))"
```

`requested_n_ubatch=None` → **基本可以确诊**，直接跳到第四节修复。

## 二、根因（务必理解，否则会调错参数）

视觉编码器走**非因果注意力**，llama.cpp 在 `src/llama-context.cpp` 有硬断言：

```
GGML_ASSERT((cparams.causal_attn || cparams.n_ubatch >= n_tokens_all)
  && "non-causal attention requires n_ubatch >= n_tokens") failed
```

即 **`n_ubatch` 必须 ≥ 单张图片的 token 数**。不满足时不是报错、不是降级——
而是 `ggml_abort()` **直接杀进程**（SIGABRT），对外表现为 500。

关键数量级：
- `--mtmd-batch-max-tokens` 默认 **1024**
- Gemma3/Gemma4 视觉预算上限 **1120 token**（实测含开销约 **1143**）
- → 默认 1024 < 1143，**任何触发满预算的图必崩**

同尺寸下的 token 数（Gemma4-26B，比例 3456:1660）：

| 输入宽度 | 像素 | prompt_tokens | n_ubatch=1024 | n_ubatch=2048 |
|---|---|---|---|---|
| 2048 | 2.02 MP | 942 | ✅ 侥幸通过 | ✅ |
| 2304 | 2.55 MP | 1143 | ❌ 崩溃 | ✅ |
| 3456 | 5.74 MP | 1143 | ❌ 崩溃 | ✅ |

> token 数在 ≥2304px 后**封顶 1143**（预算饱和），所以再增大分辨率不会增加 token，
> 但仍然需要 `n_ubatch` 能承载 1143。

## 三、取证：拿断言原文和崩溃栈

### 3.1 studio 日志（注意：调试接口要 UI 会话，拿不到）

`/api/settings/debug/logs` 会返回 `{"detail":"Remote access requires a UI session."}`，
**改从磁盘读**：

```bash
grep -h -E "GGML_ASSERT|ggml_abort|abort" ~/.unsloth/studio/logs/llama-server/*.log | sort -u
```

### 3.2 macOS 崩溃报告（证明是崩溃而非超时）

```bash
ls -t ~/Library/Logs/DiagnosticReports/llama-server-*.ips | head
```

`.ips` 格式 = **首行 header JSON + 次行 payload JSON**，用 `usedImages` 还原符号名：

```python
import json, sys
raw = open(sys.argv[1]).read()
hdr, body = json.loads(raw.split('\n',1)[0]), json.loads(raw.split('\n',1)[1])
print(body['exception'], body['termination'])   # EXC_CRASH / SIGABRT / Abort trap: 6
imgs = body['usedImages']
for t in body['threads']:
    if t.get('triggered'):
        for f in t['frames'][:12]:
            print(imgs[f['imageIndex']]['name'], f.get('symbol',''))
```

典型栈（确诊标志）：

```
ggml_abort
llama_context::decode(llama_batch const&)
llama_decode
mtmd_helper_decode_image_chunk      ← 图像分片
process_mtmd_chunk(...)
```

### 3.3 环境限制

- `ps aux` 在沙箱内被拒（`operation not permitted`）→ 不要靠它找进程
- `llama-server --help` 可直接看全部开关，找二进制：
  `find ~/.unsloth -maxdepth 4 -name "llama-server" -type f`
- studio 状态接口返回的 `chat_template` 含**裸控制字符** → 一律 `json.load(..., strict=False)`

## 四、修复

```bash
curl -X POST "$BASE/v1/load" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
        "model_path": "<模型 id>",
        "n_batch":    4096,
        "n_ubatch":   2048,
        "n_parallel": 1,
        "force_reload": true
      }'
```

加载期间 `context_length` 会短暂显示为极小值（如 768），**必须轮询到 `loaded` 且 `loading` 为空**再判定。

```bash
for i in $(seq 1 60); do
  curl -s "$BASE/api/inference/status" -H "Authorization: Bearer $TOKEN" -o /tmp/st.json
  python3 -c "
import json,sys;d=json.load(open('/tmp/st.json'),strict=False)
sys.exit(0 if d.get('loaded') and not d.get('loading') else 1)" && break
  sleep 5
done
```

### 参数调优矩阵（实测）

| 配置 | n_batch | n_ubatch | n_parallel | ctx | ≥2304px |
|---|---|---|---|---|---|
| 原厂默认 | 未设 | 未设(=1024) | 4 | 95,744 | ❌ |
| 仅调 batch | 4096 | 1024 | 4 | 95,744 | ❌ **没解决** |
| + 单槽位 | 4096 | 1024 | 1 | 234,752 | ❌ |
| **C 推荐（单会话）** | 4096 | **2048** | 1 | **209,920** | ✅ |
| **D 保并发** | 4096 | **2048** | 4 | 58,368 | ✅ |
| ❌ 反例 | 8192 | 2048 | 4 | **768** | ⚠️ 上下文塌陷 |

**铁律**：
1. **只有 `n_ubatch` 能修 500**。只调 `n_batch` 是把可用图从 1024px 抬到 2048px 的假阳性。
2. `n_ubatch` 只要 **≥ 1152** 即可，取 2048 留余量。
3. **不要同时拉大 `n_batch` 和 `n_ubatch`**：8192/2048 + 4 槽位会挤爆显存，ctx 塌到 768，比崩溃更糟。**一维一维调**。
4. `n_parallel` 从 4 → 1 可让上下文 2.45×（95,744 → 234,752），单人场景强烈建议。

## 五、验证：尺寸扫描

```python
# 等比缩放同一张图，逐档送检，打印 HTTP 状态 / 耗时 / prompt_tokens
for w in [2048, 2304, 2560, 3072, 3456]:
    ...  # PIL resize → data URL → /v1/chat/completions
```

判据：**全部档位 OK，且 `prompt_tokens` 在 1143 附近封顶**。
修复后应看到 `usage.prompt_tokens=1143` 的高分辨率档位全部 200。

## 六、对照官方模型卡应检查的其他项

| 项 | 期望 | 说明 |
|---|---|---|
| 采样参数 | `temp=1.0 / top_p=0.95 / top_k=64` | Gemma4 QAT 卡片标准；studio 通常已预置，客户端**不要覆盖成 0.2** |
| MTP 投机解码 | `spec_drafter_kind=mtp`，`spec_fallback_reason=None` | 卡片推荐 `--spec-type draft-mtp --spec-draft-n-max 4 -ngl 999 -fa on` |
| 视觉投影器 | `mmproj_fallback_reason=None` | 非 None 说明 projector 降级，画质会掉 |
| GPU 卸载 | `gpu_layers=-1` | 等价卡片 `-ngl 999` |
| 模态顺序 | **图像在文本之前** | 卡片明确要求 |
| 上下文 | `context_length` 应接近 `native_context_length` | 若被 `openai_api_auto_switch_overrides` 的 `custom_context_length` 压小要清理 |
| 视觉预算 | 70 / 140 / 280 / 560 / 1120 | OCR 用小字要选高档（1120） |

数据库位置（只读查）：
```bash
python3 -c "
import sqlite3
con=sqlite3.connect('file:$HOME/.unsloth/studio/studio.db?mode=ro',uri=True)
for k,v,t in con.execute('SELECT key,value_json,updated_at FROM app_settings'): print(k,v[:200])"
```

## 七、两个必须告知用户的坑

1. **`n_batch` / `n_ubatch` 不持久化**。`studio.db` 里没有对应字段，从 UI 重新加载会退回默认，
   **大图崩溃会复发**。每次重载都要显式带上，或确认 UI 高级选项里的 batch 设置。
2. **兜底保险**：可用 `llama_extra_args` 传 `--image-max-tokens 1024`，
   让模型把超预算的图降采样到 `n_ubatch` 以内而不是崩——**代价是牺牲细字识别精度**。

## 八、画质提醒与"原图直送"的代价

同为 1143 tokens，**输入分辨率越高字面越准**：
2048px 把"战戟9000"识别成"战9000"，2560px 起才正确；
1024px 缩图更差——把"战戟"读成"战胜"、"送拍套"读成"送蒂芬妮"、"3UG5"读成"3UGS"，
甚至商品页 `elements` 任务**直接拒答**（"由于您没有上传具体的截图"）。
→ **不要把大图一味压小来规避 500**。修复 `n_ubatch` 后应原图直送。

### ⚠️ 但原图直送会引入新的失效模式：空白刷屏

视觉 token 从 ~450（1024px）涨到 1143（原图）后，**关 thinking 时约 1/3 概率**
模型退化成输出约 **247,000 个连续空格**（≈8,611 token），单次耗时从 1s 飙到 24s，
可见文字只剩开头一句。

**实测发生率（桌面截图 OCR，关 thinking）**：

| 条件 | 样本 | 刷屏 | 率 |
|---|---|---|---|
| 原图，同请求连打 | 12 | 4 | 33% |
| 原图，变体请求（强制未命中缓存） | 6 | 2 | 33% |
| 缩图 1024px | 3 | 0 | 0% |

**与缓存命中无关，稳定 1/3。** 开 thinking 模式下未复现。

### 🚨 最危险的地方：`.strip()` 会完美掩盖它

```python
text = (msg["content"] or "").strip()   # ← 247K 空格被全部抹掉，输出看起来"很干净"
```

**肉眼审查 100% 漏掉**，只有 token 数露馅。所以：

```python
raw = msg["content"] or ""
if len(raw) > 50000 or raw.count(" ") / max(len(raw), 1) > 0.6 \
   or (usage_total_tokens > 3000 and len(raw) < 500):
    # 判定为空白刷屏 → 重试
```

**铁律：任何视觉模型的输出健康检查，必须先量原始长度再做 strip。**

## 九、刷屏的根因与根治（227 次受控实验结论）

### 根因：不是"随机退化"，是「空格列对齐」失控

刷屏产物是 **100% 纯空格**、长度恒为 ~247,592 字符 —— 因为模型在用空格做**列对齐**，
对齐宽度算不出来时一路填到 max_tokens 截断。这也解释了为什么惩罚"重复空格"特别有效。
若提示词里出现「**保持原始的行列结构**」这类要求，就会把它推上这条 40% 会失控的路。

### 解法一（首选，零成本）：改提示词

```
❌ 逐字提取截图中的全部文字内容，尽量保持原始的行列结构和阅读顺序。不要翻译，不要补充说明。
✅ 逐字提取截图中的全部文字内容，按从上到下、从左到右的阅读顺序逐行输出。不要翻译，不要补充说明。
```

删掉「保持原始的行列结构」→ 模型改用换行表达结构，失控路径直接消失。
**实测 40% → 0%（15/15），不碰任何采样参数。**

### 解法二（叠加，兼修重复字）：`repetition_penalty: 1.1`

```json
{ "temperature": 0.2, "top_p": 0.95, "top_k": 64, "repetition_penalty": 1.1 }
```

**实测 40% → 0%（15/15）**，且**额外修好「战戟→战战」这类重复 token 错误**（0/4 → 4/4）。
代价：单次 1.3s → 1.9s。**1.05 强度不够（实测仍有 7%），1.1 是甜点，超过 1.2 会扭曲分布反而更糟。**

### 实测参数对比（桌面 OCR，各 12~15 次）

| 配置 | 刷屏率 | 备注 |
|---|---|---|
| 基线 `temp0.2 · rep1.0` | **40%** | 合并 22/57 ≈ 39% |
| `temp1.0`（官方采样） | 8% | **不够**，单靠温度治不了 |
| `rep 1.05` | 7% | 残留，强度不足 |
| **`rep 1.1`** | **0%** | 推荐 |
| `freq_pen 0.5` | 0% | 可用，1.6s 更快 |
| `temp1.0 + rep1.1` | 0% | 可用但最慢（2.9s） |
| `DRY 0.8` | 33% | ❌ **本环境无效** |
| **提示词去"行列结构"** | **0%** | ✅ 零成本首选 |

### ❌ DRY 采样器在 unsloth-studio 里不可用

Unsloth 官方推荐用 DRY 替代重复惩罚，但**本环境参数被静默丢弃**。
验证法：固定 `seed`，只改 `dry_multiplier`，两次输出**逐字节完全一致** → 未透传。

原因：studio 的 OpenAI 兼容接口白名单只有
`temperature / top_p / top_k / min_p / repetition_penalty / presence_penalty / frequency_penalty / seed`
（`seed` 已验证生效）。要用 DRY 只能走加载期 `llama_extra_args`。

### 兜底仍然必须有

最优配置实测 0/27，但 **95% 置信上界约 11%** —— 不能声称绝对 0。
保留健康检查 + 重试：命中缓存后重试一次仅 0.6~1.0s。

### 同类断言参考

Gemma 4 的非因果注意力架构除了 `n_ubatch`，还与 `--image-min-tokens` 冲突会触发
`GGML_ASSERT` —— **不要传 `--image-min-tokens`**。上游追踪：`llama.cpp#21516`、
`google-deepmind/gemma#622`。

### 精度 vs 速度的取舍（Gemma4-26B，原图）

| 模式 | 平均耗时 | 精度 | 风险 |
|---|---|---|---|
| 开 thinking | 32.2s | 最高（商品页 OCR 全对） | 无刷屏 |
| 关 thinking + rep1.1 | 12.2s→略增 | 好（重复字也被修正） | 残余 <11%，需重试 |
| 缩图 1024 + 关 thinking | 8.5s | 差（多字错读 + elements 拒答） | 无 |


