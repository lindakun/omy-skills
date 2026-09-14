---
name: x-promo-thread
description: 通过 chrome-devtools MCP 驱动本机 Chrome，在 X（Twitter）上发布推广推文串（Thread）。覆盖登录态确认、双语文案撰写、首条发布、从 CreateTweet 响应抓推文 ID、逐条回复串链、以及发帖结果的独立验证。触发词：X 推广、发推、Twitter 发帖、推文串、Thread、在 X 上发推广、帮我在 X 上发布。
metadata:
  platforms: [macos]
  requires: [chrome-devtools-mcp]
  agent_created: true
---

# x-promo-thread — X 推广推文串发布

用 `mcp__chrome-devtools__*` 工具操作**本机已登录的 Chrome**，在 X 上发布推广内容。

核心难点不在"打字"，而在**确认到底发出去了没有**——X 的前端有大量"看起来成功、其实没发出去"的假象。
本技能的所有步骤设计都围绕这一个目标。

---

## 前置条件

1. `chrome-devtools` MCP 已连接（`ToolSearch` 搜 `mcp__chrome-devtools__list_pages` 验证）。
2. Chrome 里 X 已登录（个人号或项目号）。
3. 已确认发布内容、语言、形式（见 Step 0）。

---

## Step -1 — 前置自检（先做，失败即止）

**别急着写文案，先确认工具真的能调。** 这一步不通过，后面全是白费功夫。

1. `ToolSearch` 精确名查 `mcp__chrome-devtools__list_pages`。**查不到就直接停**，如实报告跳过，
   不要靠猜、不要改用别的浏览器工具硬上（登录态在用户的 Chrome 里，换工具等于换浏览器）。
2. `list_pages` 拿不到 X 页面：`new_page` 打开 `https://x.com/home`，看是否落在登录态。
3. **Chrome 进程在跑 ≠ MCP 工具可用。** 实测过的坑：Chrome 主进程 + `chrome-devtools-mcp --autoConnect`
   辅助进程都在跑，但工具根本没注册进当前会话，`ToolSearch` 精确名和关键词搜索都搜不到。
   判断依据只有一条——**工具能不能调**，不是进程在不在。

### 无人值守 / 定时任务场景（重要）

自动化的 prompt 里通常已经写死了语言、形式、审核要求，且**不允许调用 `AskUserQuestion`**。
此时：**跳过 Step 0 的交互确认**，直接采用任务提示里的预设值，并在最终汇报里
**明确声明所用的默认值**（语言 / 形式 / 角度），让用户事后能核对。

---

## Step 0 — 发布前必须确认（不可跳过）

发推是**不可逆的公开操作**，属"对外操作先问再做"。用 `AskUserQuestion` 一次问清三项：

| 问题 | 选项 |
|------|------|
| 语言 | 中文为主 / English 为主 / 中英双语 |
| 形式 | 推文串 Thread（推荐）/ 单条长文 / X Article |
| 审核 | 先看草稿 / 直接发 |

**项目铁律**：若推广对象有"不得涉及收费"的要求（如 Easy Prompt），全篇文案只允许出现
「完全免费 / 无付费墙 / 无会员 / 无广告 / 不登录即可浏览」，**不得出现任何价格、套餐、Pro 版、升级等字眼**。

---

## Step 0.5 — 取站点真实数据（不依赖浏览器）

写文案前要引用的数字（收录条数等）**不用开浏览器也能取**，而且比读首页更可靠：

```bash
curl -s "https://prompts.hhxxttxs.icu/zh/api/prompts?limit=1"
# 响应 JSON：{ items: [...], total: 5434, page, pageSize, hasMore }
#   → total 就是实时收录条数
```

- 首页 hero 文案里写死的「收录 3258+ 条」是过时静态文案，**不要照抄**，以 `total` 为准。
- `GET /zh/api/categories` **不是接口**（返回 Next.js 页面 HTML），别拿它取分类数。
- 实测值：2026-09-13 / 09-14 均为 `total = 5434`。

> 取数走 HTTP，发帖走 chrome-devtools MCP —— 两者独立。**MCP 不可用时取数仍然做得了**，
> 但没 MCP 就发不了帖，见 Step -1。

---

## Step 1 — 文案撰写规则（踩过坑，务必遵守）

### 1.1 X 编辑器会吃掉换行

`fill` 写入的 `\n` 会被 Draft.js 丢弃，多行文案会变成连排的「一句话」，
中英对照时会读成 `…能搜索的站3258+ curated AI prompts…` 这种硬伤。

**因此：每条推文都按「无换行也读得通」写。**

- 用 `·`、`｜`、`。` 做视觉分隔，而不是换行。
- 中英对照写成两个完整句子，而不是两行。
- 每条独立成段，句末补标点，别让上句直接黏下句。

好的写法：

```
📚 覆盖 10 大能力场景：推理 / 代码 / 写作 / RAG / Agent / 数据分析 / 安全红队 / 图文视频生成 / 产品运营。Covers 10 capability areas, synced from top open-source prompt repos like awesome-prompts & ai-boost.
```

### 1.2 字数预算

X 免费号单条上限 **280 加权字符**，中文/日文/韩文每字按 **2** 计。

- 预算控制在 **270 以内**留余量。
- URL 统一按 23 计，不管实际长度。
- 表情按 2 计。
- 想快速估算：CJK 字数 × 2 + 拉丁字符数 + URL 数 × 23 + 表情数 × 2。

### 1.3 Thread 结构模板（5 条）

| # | 作用 | 要点 |
|---|------|------|
| 1 | 钩子 | 一句话价值主张 + 站点 URL + 2–3 个 hashtag |
| 2 | 覆盖范围 | 能力场景 / 内容来源，建立专业感 |
| 3 | 功能亮点 | 3–4 个具体能力，动词开头 + emoji |
| 4 | 免费声明 | 明确"免费"，逐条打掉付费顾虑 |
| 5 | CTA | 中英两个站点链接 + 双语 hashtag |

---

## Step 2 — 定位浏览器与页面

```js
// mcp__chrome-devtools__list_pages
```

找到 X 的页面。若没有，用 `new_page` 打开 `https://x.com/home`。
拿到 `pageId` 后**后续所有调用都带这个 pageId**。

> 用户常同时开着一堆标签页（本地服务、其他站点）。不要 `new_page` 重复开 X，
> 优先复用已有的 X 页面，避免登录态/草稿混乱。

---

## Step 3 — 发布首条

### 3.1 打开编辑器

```
navigate_page { pageId, type: "url", url: "https://x.com/compose/post" }
```

X 会把 `/compose/post` 回弹到 `/home` 并把编辑器做成弹层或内联框，**两种都可用**。

> 该账号**可能没有「添加推文」（+）按钮**，即没有原生串推入口。
> 别在这上面浪费时间——Thread 一律用「首条 + 逐条回复」实现，效果等价。

### 3.2 写入文案

先 `take_snapshot` 拿到编辑框的 `uid`，再：

```
fill { pageId, uid: "<Post text 输入框>", value: "<推文正文>" }
```

写入后用 `evaluate_script` 回读校验：

```js
() => {
  const ta = document.querySelector('[data-testid="tweetTextarea_0"]');
  return { text: ta ? ta.innerText : null };
}
```

### 3.3 点击发布 —— **务必用 evaluate_script 点，不要用 click 工具**

**踩坑记录**：用 `click` 工具点 uid（无论内联框还是弹层里的 Post 按钮），
工具会返回 `Successfully clicked on the element`，但**实际根本没发出**——
没有 CreateTweet 请求、文案还原封不动躺在编辑器里。

可靠做法是直接对真实 DOM 节点派发点击：

```js
() => {
  const ta = document.querySelector('[data-testid="tweetTextarea_0"]');
  const txt = ta ? ta.innerText : '';
  if (!txt.includes('<文案特征词>')) return { posted: false, reason: 'text mismatch' };
  const btns = [...document.querySelectorAll('[data-testid="tweetButton"],[data-testid="tweetButtonInline"]')];
  const b = btns.find(x => x.offsetParent !== null);
  if (!b) return { posted: false, reason: 'no button' };
  b.click();
  return { posted: true };
}
```

带上「文案特征词」断言，既是校验也是保险：内容不对就绝不点。

---

## Step 4 — 拿首条推文 ID（Thread 的锚点）

发完后立刻抓网络请求（**点击不会导航，请求记录还在**）：

```
list_network_requests { pageId, resourceTypes: ["xhr","fetch"], includePreservedRequests: true }
```

在结果里找 `POST https://x.com/i/api/graphql/<queryId>/CreateTweet [200]`，记下它的 `reqid`，然后：

```
get_network_request { pageId, reqid: <CreateTweet 的 reqid> }
```

在响应体里取：

```
data.create_tweet.tweet_results.result.rest_id          → 推文 ID
data.create_tweet.tweet_results.result.core.user_results.result.tweet_counts.tweets  → 发帖后总数（可用来确认 +1）
data.create_tweet.tweet_results.result.legacy.full_text → 实际入库的正文（可核对换行是否被吃）
```

推文 URL：`https://x.com/<screen_name>/status/<rest_id>`

> `get_network_request` 的 `responseFilePath` 参数会被工作区根目录限制拒绝，
> 直接读内联响应即可。
>
> 顺带记下 `tweet_counts.tweets`——它比主页时间线靠谱得多，是「是否真的发出去了」的硬证据。

---

## Step 5 — 逐条回复串成 Thread

对第 2…N 条循环：

**① 导航到上一条推文页**

```
navigate_page { pageId, type: "url", url: "https://x.com/<screen_name>/status/<上一条ID>" }
```

**② 聚焦回复编辑器（用 evaluate_script，免快照）**

```js
() => {
  const ta = document.querySelector('[data-testid="tweetTextarea_0"]');
  if (!ta) return 'no textarea';
  const ed = ta.querySelector('[contenteditable="true"]') || ta;
  ed.focus(); ed.click();
  return { ok: document.activeElement.isContentEditable };
}
```

**③ 用 `type_text` 输入（不需要 uid，直接打进焦点元素）**

```
type_text { pageId, text: "<本条正文>" }
```

> `type_text` 是这条流水线里最省事的一环：**免快照、免 uid**。
> 但**正文里不要带 `\n`**——会触发回车，可能提前提交，也可能被吞掉。
> 配合 Step 1.1 的「无换行文案」正好。

**④ 带断言点击 Reply**

同 Step 3.3 的脚本，把 `tweetButton`/`tweetButtonInline` 换成回复框上的按钮（`innerText` 为 `Reply`），
断言特征词换成该条文案的独特片段。

**⑤ 回读确认并取新 ID**

```js
() => {
  const links = [...new Set(
    [...document.querySelectorAll('a[href*="/status/"]')]
      .map(a => a.getAttribute('href'))
      .filter(h => /\/status\/\d+$/.test(h))
  )];
  const ta = document.querySelector('[data-testid="tweetTextarea_0"]');
  return {
    statusLinks: links,
    editorText: ta ? ta.innerText.slice(0, 30) : null,
    toasts: [...document.querySelectorAll('[data-testid="toast"]')].map(t => t.innerText),
  };
}
```

判断标准（三者同时满足才算成功）：

- `toasts` 含 `Your post was sent.`
- `editorText` 已被清空（只剩 `\n`）
- 出现新的 `/status/<新ID>`，且不在上一轮的列表里

新一轮的 ID 就是下一条回复的目标父推文。

---

## Step 6 — 最终验证

### 6.1 链条顺序

导航到**最后一条**推文页，回读对话区：

```js
() => {
  const arts = [...document.querySelectorAll('article')];
  return arts.map((a, i) => {
    const t = a.querySelector('[data-testid="tweetText"]');
    return { i, txt: t ? t.innerText.slice(0, 45) : null };
  });
}
```

应得到按发布顺序排列的 N 条，且每条正文与草稿一致。

### 6.2 公开可达性（**必做**）

用**独立访客上下文**打开（不带登录态）：

```
new_page { url: "https://x.com/<screen_name>/status/<首条ID>", isolatedContext: "guest-check" }
```

```js
() => ({
  title: document.title,
  articles: document.querySelectorAll('article').length,
  bodyStart: document.body.innerText.slice(0, 350),
})
```

`articles > 0` 且正文出现在 `bodyStart` 中 → 对外公开可见。
检查完用 `close_page` 关掉这个临时上下文。

---

## 重要陷阱：主页时间线为空 ≠ 发布失败

**现象**：账号主页 `x.com/<user>` 显示 "N posts"，但推文列表完全不渲染。
访客视图甚至显示 `@<user> hasn't posted / When they do, their posts will show up here`。
接口 `UserOriginalsTimeline` 返回 200，但响应里只有 "Who to follow" 模块和游标，没有任何推文。

**原因**：新号 / 0 粉丝账号常出现此状态，是 **X 侧的时间线渲染策略**，不是账号被封、也不是发帖失败。

**验证方式**：**永远不要用主页列表判断发帖成败**。改用：

1. `tweet_counts.tweets` 是否 +1（Step 4）
2. `CreateTweet` 是否 200（Step 4）
3. 直接访问 `x.com/<user>/status/<id>`（Step 6）
4. 独立访客上下文是否能看到（Step 6.2）

这四条里任一条通过，就是发出去了。

---

## 已知限制

| 限制 | 说明 | 绕过 |
|------|------|------|
| 截图无法落盘 | `take_screenshot` 的 `filePath` 会被沙箱工作区根目录限制拒绝（`Access denied: ... not within any of the configured workspace roots`），工作区内路径也不行 | 走纯文字推文；或让用户手动补图 |
| 换行丢失 | Draft.js 吞掉 `\n` | 按无换行版式写文案（Step 1.1） |
| 无原生串推按钮 | 部分账号编辑器中不存在「添加推文」（+） | 用「首条 + 逐条回复」链式会话，视觉等价 |
| `click` 工具可能空点 | 返回成功但未触发提交 | 一律改用 `evaluate_script` 派发点击（Step 3.3） |
| 单条长文受限 | 免费号 280 加权字符 | 拆成 Thread；或确认账号有长文权限再试 |

---

## 红线

1. **发布前必须拿到用户确认**（语言 / 形式 / 是否先看稿）——公开且不可逆。
2. **不代用户编造事实**。文案里的数字必须来自站点或仓库的真实数据（例如线上实时抓取的收录条数），
   不要照抄 README 里写死的旧数字。
3. **遵守项目推广铁律**。若明确"不得涉及收费项目"，全篇不得出现价格 / 会员 / Pro / 升级等字眼。
4. **`<user>/status/<id>` 之外的推文不擅自删除、转发、点赞**——只做用户要求的事。
5. **验证后再报告**。没有 `CreateTweet` 200 / `tweet_counts` +1 / status 链接三者之一，
   不能宣布"发布成功"。
6. **发布后如实汇报副作用**（换行被吞、无配图、账号 0 粉丝曝光低等），不要只报喜。

---

## 故障排查

| 现象 | 原因 | 处理 |
|------|------|------|
| `ToolSearch` 搜不到 `mcp__chrome-devtools__*` | 工具未注册进当前会话（跟进程在不在无关） | 见 Step -1，直接停止并如实报告，不要硬试 |
| `click` 返回成功但没发出去 | 工具空点 / uid 失效 | 改用 Step 3.3 的 `evaluate_script` 点击 |
| 无 CreateTweet 请求 | 同上，未触发提交 | 同上；回读编辑器确认文案是否还在 |
| 编辑框取到 `"\n"` 空值 | 内容已随发帖清空 | 说明**发布成功**，去 Step 4 取 ID |
| 主页看不到推文 | X 侧时间线渲染策略 | 见「重要陷阱」章节，换四种方式验证 |
| 正文换行没了 | Draft.js 吞 `\n` | 按无换行版式重写；必要时删掉重发 |
| `get_network_request` 报 workspace root 错 | 不能写文件 | 去掉 `responseFilePath`，读内联响应 |
| `type_text` 后内容为空 | 未聚焦到编辑器 | 重跑 Step 5 第②步，确认 `isContentEditable === true` |
| `resize_page` 报 `Restore window to normal state` | 窗口处于最大化 | 无需 resize；直接截图或跳过 |
| 找不到 `tweetTextarea_0` | 页面未加载完 / 不是推文页 | `wait_for` 文本或 `reload` 后重试 |

---

## 完整脚本骨架（供复制）

```js
// 通用：带上特征词断言 + 点击发布按钮（Step 3.3 / Step 5④ 通用）
() => {
  const ta = document.querySelector('[data-testid="tweetTextarea_0"]');
  const txt = ta ? ta.innerText : '';
  if (!txt.includes('<特征词>')) return { posted: false, reason: 'text mismatch', txt };
  const btns = [...document.querySelectorAll('[data-testid="tweetButton"],[data-testid="tweetButtonInline"]')];
  const b = btns.find(x => x.offsetParent !== null);
  if (!b) return { posted: false, reason: 'no button' };
  b.click();
  return { posted: true, txtLen: txt.length };
}
```

```js
// 通用：聚焦回复编辑器（Step 5②）
() => {
  const ta = document.querySelector('[data-testid="tweetTextarea_0"]');
  if (!ta) return 'no textarea';
  const ed = ta.querySelector('[contenteditable="true"]') || ta;
  ed.focus(); ed.click();
  return { ok: document.activeElement.isContentEditable };
}
```

```js
// 通用：回读发帖结果（Step 5⑤）
() => {
  const links = [...new Set(
    [...document.querySelectorAll('a[href*="/status/"]')]
      .map(a => a.getAttribute('href'))
      .filter(h => /\/status\/\d+$/.test(h))
  )];
  const ta = document.querySelector('[data-testid="tweetTextarea_0"]');
  return {
    statusLinks: links,
    editorText: ta ? ta.innerText.slice(0, 30) : null,
    toasts: [...document.querySelectorAll('[data-testid="toast"]')].map(t => t.innerText),
  };
}
```
