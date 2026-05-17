# ADAPTER_CONTRACT.md

> **本文件地位**: GENPANO AI 引擎 Adapter 的 **唯一真相源 (Single Source of Truth)**。
>
> - PRD §4.3 (AI 引擎爬取系统) 仅描述"做什么 / 为什么"，具体接口、状态机、错误码、反检测技巧在此固化。
> - ADMIN_PRD §4.2 (Module B — 数据管道 & 采集健康) 的监测指标定义、告警规则从本文件派生。
> - 所有 Adapter 代码 (`src/engines/adapters/**`) 实现必须与本文件一一对应；任何偏离需先在此更新，再改代码。
> - Adapter / account-pool / admin wrapper implementation should use this file as the contract reference.
>
> **维护原则**: 本文件的每一条规则都来自一次真实的生产 Bug 或 CF/风控对抗实验 (源头: `github.com/jotamotk/GenPano` 测试床 2025Q1-Q2)。禁止删除未替换的规则；如需废弃，保留历史并标注 `DEPRECATED-YYYY-MM-DD + 原因`。
>
> **最后更新**: 2026-04-17

---

## 目录

1. [契约范围 & 读者指引](#1-契约范围--读者指引)
2. [AIEngineAdapter 接口定义](#2-aiengineadapter-接口定义)
3. [Profile-Aware 执行模型](#3-profile-aware-执行模型)
4. [反检测三层防御](#4-反检测三层防御)
5. [账号 & Cookie 生命周期](#5-账号--cookie-生命周期)
6. [错误分类 & 重试 & 冷却](#6-错误分类--重试--冷却)
7. [代理池 & 账号调度](#7-代理池--账号调度)
8. [DOM 抽取约定](#8-dom-抽取约定)
9. [CAPTCHA 三级解决策略](#9-captcha-三级解决策略)
10. [观测 & 持久化 & 数据契约](#10-观测--持久化--数据契约)
11. [MVP 落地顺序 & 引擎清单](#11-mvp-落地顺序--引擎清单)
12. [交叉引用矩阵](#12-交叉引用矩阵)

---

## 1. 契约范围 & 读者指引

### 1.1 什么算"Adapter"

一个 Adapter 负责 **把一条 Query 变成一条结构化 Response**，对接一个具体 AI 引擎。**MVP 引擎宇宙锁定 3 家** (Decision #28.C1, 2026-04-22): `chatgpt` / `doubao` / `deepseek-CN` — 其它引擎 (Gemini / Perplexity / Kimi / Grok / 智谱 / Claude) 推到 Phase 2+。`deepseek-CN` 命名留出 `deepseek-overseas` 命名空间, 该日落地 Session 1.2 双修正最终版。

Adapter 内部可能分两种形态:

- **Web Adapter (主路径)**: 浏览器自动化，真实模拟用户提问、抓 DOM。
- **API Adapter (降级路径)**: 官方 / 第三方 OpenAPI 兜底 (成本更高、可能缺 Citation)。

Worker 启动时按 `WORKER_REGION` + `ADAPTER_MODE` 配置决定加载哪些 Adapter；调度器只感知"引擎名"，不关心主/降级形态 (由 Adapter 内部路由)。

> ⚠️ **每条 Response 必须自带来源标签**: `AIResponse.responseSource` (6 值枚举) 是 Session 1.2 引入的硬约束 — Web 路径写 `web_ui`、API 降级写 `api_fallback`、HAR 回放写 `cached_replay` 等。详见 §10.1 字段表 + §10.5 枚举语义表 + Harness F4-1/F4-2/F4-3。**没有 schema default**, 三层 (Adapter / API fallback / Prisma create) 必须显式 stamp。

### 1.2 本契约覆盖

- Adapter 接口形状 (输入 / 输出 / 生命周期钩子)
- 执行上下文构造 (Profile × Account × Proxy)
- 反检测最佳实践 (通过实验验证过的，不是理论推导)
- 错误分类 & 重试策略 (每一种错误的含义、上游处置、用户侧是否计入成功率)
- 账号池状态机
- DOM 抽取规则 (每个引擎特有的 quirks)
- CAPTCHA 处置 (3 级成本递增)
- 持久化数据契约 (HAR / 截图 / AiCitation / Response 原文)

### 1.3 本契约 **不** 覆盖

- Prompt 生成、Topic 规划 → 见 PRD §4.2
- 数据分析 / PANO Score 计算 → 见 PRD §4.6
- Admin 监测 UI → 见 ADMIN_PRD §4.2
- 用户侧功能 / UI 文案 → 见 PRD §4.1 / §4.6

### 1.4 读者路线

| 你是 | 从哪里读起 |
|------|-----------|
| 写 Adapter 代码 | §2 → §3 → §6 → §8 → §10 |
| 写账号池 / 注册机 | §5 → §7 → §6 |
| 写 Admin 监测 | §6 错误码表 + §10 持久化字段 |
| 做安全 / 合规 review | §4 + §5 (Cookie 存储) + §10 (HAR 脱敏) |
| 加新引擎 | 全文一遍，写一个 `ADAPTER_{ENGINE}.md` 放 §8.X 作为附录 |

---

## 2. AIEngineAdapter 接口定义

### 2.1 接口 (TypeScript)

```typescript
// src/engines/types.ts

// MVP 锁 3 家 (Decision #28.C1, 2026-04-22). 'deepseek-CN' 命名为 Phase 2 'deepseek-overseas' 留空间.
export type EngineId =
  | 'chatgpt'
  | 'doubao'
  | 'deepseek-CN';

// 6 值枚举 — 每条 Response 必须显式 stamp, NO SCHEMA DEFAULT (Decision #28.C3, Harness F4-1/F4-2/F4-3).
export type ResponseSource =
  | 'web_ui'              // 浏览器 DOM 抽取 (主路径, 含 system prompt / RAG / browsing / 引用卡片等 Web-only 语义)
  | 'api_fallback'        // 官方 OpenAPI 降级 (citations 通常空)
  | 'mock_proxy'          // dev / staging mock transport
  | 'cached_replay'       // HAR replay (CI L3 / regression)
  | 'admin_har_replay'    // Admin 后台手工触发的回放 (排错 / 审查)
  | 'harness_fixture';    // self-seeded violation fixture (永远不入生产)

export type EngineRegion = 'overseas' | 'cn';
export type AdapterMode = 'web' | 'api';

export interface ExecutableQuery {
  id: string;                       // queryId, 主键, 用于溯源
  prompt: string;                   // 完整的用户侧提问文本
  promptId: string;                 // 上游 Prompt 的 ID (见 PRD §4.2)
  language: 'zh-CN' | 'en-US';      // 决定 Prompt 语种与引擎 routing
  intent:
    | 'informational'
    | 'commercial'
    | 'transactional'
    | 'navigational';
  profileGroupIds: string[];        // empty array = any group; Profile-Aware 采样 (见 §3)
  requiresLogin: boolean;           // true 时若无可用账号 → PENDING (不是 FAILED)
  topicDimension: '品类' | '品牌' | '产品';  // 提及率统计口径依赖
  createdAt: string;                // ISO 8601
}

#### ExecutableQuery 字段表

| Field | Type | Required? | Default | Notes |
|---|---|---|---|---|
| id | string (UUID) | yes | — | upstream generated |
| prompt | string | yes | — | ≥10 chars, non-empty |
| promptId | string (UUID) | yes | — | FK to Prompt |
| language | enum zh-CN / en-US | yes | — | determines engine routing |
| intent | enum (informational/commercial/transactional/navigational) | yes | — | string transport, VARCHAR(50) storage |
| profileGroupIds | string[] | yes | [] | empty = any group |
| requiresLogin | boolean | yes | false | true → PENDING if no account |
| topicDimension | enum (品类/品牌/产品) | yes | — | mention-rate aggregation basis |
| createdAt | string (ISO 8601) | yes | — | set by scheduler |

`intent` 是总是作为 JSON 字符串传输 (`'informational'` 等)。禁止使用数值编码。存储: VARCHAR(50) 在 DB。该规则由 `scripts/ci-check.mjs` 的 CI-intent-str 规则强制执行。

export interface ExecutionContext {
  engineId: EngineId;
  region: EngineRegion;
  mode: AdapterMode;
  profile: BrowserProfile;          // 见 §3.2
  account: AccountSnapshot | null;  // null 当 requiresLogin=false
  proxy: ProxySnapshot | null;      // null 当 region='cn' 对国内引擎
  attempt: number;                  // 第几次尝试 (1-3)
  traceId: string;                  // 贯穿本次执行的追踪 ID
}

export interface AIResponse {
  queryId: string;
  engineId: EngineId;
  executionMode: AdapterMode;
  responseSource: ResponseSource;   // 必填, 见 §10.5 枚举语义 + Harness F4-1/F4-2/F4-3
  rawText: string;                  // 回答全文 (必须是 textContent, 见 §8.2)
  rawHtmlPath: string | null;       // S3 path to full HTML snapshot
  harPath: string | null;           // S3 path to HAR file (CI 回放必须保留)
  screenshotPath: string | null;    // S3 path to viewport screenshot
  citations: ParsedCitation[];      // 见 PRD §4.2.6 A
  latencyMs: number;                // t_submit → t_last_chunk
  responseStartedAt: string;
  responseCompletedAt: string;
  profile: BrowserProfile;
  accountIdUsed: string | null;
  proxyIdUsed: string | null;
  status: 'success' | 'partial';    // partial 仅当已抽到主体文本但 Citation 失败
}

export interface ParsedCitation {
  url: string;                      // 已归一化 (tldts, 见 PRD §4.2.6.D)
  domain: string;                   // eTLD+1
  anchorText: string | null;
  position: number;                 // 在回答中的出现序 (1-based)
  extractedBy: 'footnote' | 'reference_card' | 'citation_tooltip' | 'inline_link' | 'api_structured' | 'hover_card' | 'unknown';
}

export type AdapterError =
  | { code: 'CF_BLOCKED'; cfRayId?: string }
  | { code: 'COOKIE_EXPIRED'; accountId: string }
  | { code: 'CAPTCHA_REQUIRED'; capType: 'turnstile' | 'challenge' | 'hcaptcha' | 'recaptcha' | 'slider' | 'vision' }
  | { code: 'PAGE_CRASHED'; consoleDump?: string }
  | { code: 'PROXY_DEAD'; proxyId: string }
  | { code: 'NO_ACCOUNT_AVAILABLE' }
  | { code: 'EXTRACT_EMPTY'; reason: string }
  | { code: 'TIMEOUT'; stage: 'nav' | 'submit' | 'first_chunk' | 'stream_end' };

export interface AIEngineAdapter {
  readonly engineId: EngineId;
  readonly region: EngineRegion;
  readonly mode: AdapterMode;

  /** 健康探针: 不执行 Query, 只验证登录态 + DOM 关键元素存在 */
  healthCheck(ctx: Omit<ExecutionContext, 'attempt' | 'traceId'>): Promise<
    { ok: true } | { ok: false; error: AdapterError }
  >;

  /** 执行一次 Query, 返回结构化 Response 或抛 AdapterError */
  execute(
    query: ExecutableQuery,
    ctx: ExecutionContext
  ): Promise<AIResponse>;   // throw AdapterError on failure

  /** Adapter 自身的预热 (启动浏览器 / 加载 stealth / 加载 cookie), 幂等可重入 */
  warmup(ctx: ExecutionContext): Promise<void>;

  /** 资源释放; scheduler 停采或 worker shutdown 时调用 */
  dispose(): Promise<void>;
}
```

### 2.2 语义合同

- **execute 必须抛 AdapterError**，不要吞错返空串。上层调度器 (`src/scheduler/`) 靠 `error.code` 决策重试、冷却、告警。
- **`requiresLogin = true AND account = null` 必须抛 `NO_ACCOUNT_AVAILABLE`**，调度器会把 Query 状态置 **PENDING** (不是 FAILED)，等账号补充后重入。FAILED 会计入成功率并污染看板。
- **partial Response 的判定**: 已抽到 rawText (≥30 char) 但 citations 解析失败 → `status='partial'`, 不抛异常。看板上 partial 计入"成功但降级"单独统计，不计入 `citation_source_loss`。
- **healthCheck 与 execute 必须共用 warmup 后的 Browser Context**，不要 healthCheck 里额外起浏览器 (成本 + 漂移)。
- **traceId** 贯穿 execute → 解析 → 持久化，所有日志、HAR、截图文件名都以 traceId 为前缀，便于 Admin 失败重试中心 (ADMIN_PRD §4.2.6) 定位。

#### AIResponse immutability

`AIResponse.profile` 是 `ExecutionContext.profile` 在 `execute()` 返回时的不可变深拷贝。Adapter 实现必须禁止在执行期间修改 `ExecutionContext.profile`；如需运行期状态变更，单独记录日志，通过 `Object.freeze({ ...ctx.profile })` 返回冻结快照。

### 2.3 API Data Shapes

#### ProfileGroupResponse

```typescript
interface ProfileGroupResponse {
  id: string;              // pg_young_female_tier1
  nameZh: string;
  nameEn: string;
  description: string;
  industryScope?: string[]; // null = global
  isDefault: boolean;
}
// GET /api/v1/profile-groups → ProfileGroupResponse[]
```

#### Logout 响应

`POST /api/auth/logout → 204 No Content` (无响应体，幂等)。前端**禁止**调用 `.json()`；仅检查 `resp.ok`。

#### Delete User

`DELETE /api/users/me → 204 No Content`。请求体: `{ reason?: string }` (可选，≤500 字符)。
副作用: `users.deletion_requested_at = now()`，立即吊销所有 session/token，发送告别邮件。
30 天可撤回窗口: 期间所有对外 API 返回 404；用户通过 `/forgot-password` 返回"账号已申请删除，点此撤回"。
30 天后: cron 硬删级联清理 (按 DATA_MODEL.md §10 规则)。

### 2.5 禁止项

- ❌ 业务代码直接 `import { chromium } from 'playwright'`; 必须走 `src/engines/adapters/{engine}/` 封装。
- ❌ Adapter 内部起后台定时器 / setInterval; 定时任务全部归 scheduler (§7.3)。
- ❌ 在 Adapter 里写死 query 字符串测试 (fixture 必须走 `tests/fixtures/scraping/queries.json`)。
- ❌ execute 返回后不 release 浏览器 Page/Context; 必须 `try/finally`。

---

## 3. Profile-Aware 执行模型

### 3.1 三元组 → 上下文

```
ExecutableQuery × BrowserProfile × AccountCookies → ExecutionContext
       │                │                │
       │                │                └── §5 账号池提供, 对应一个真实登录账号 (masked)
       │                └── §3.2 模拟"不同地区/不同人设的真实用户"
       └── §2.1 上游 Pipeline 产出 (Topic → Prompt → Query)
```

PRD §4.2.3a 定义了 **ProfileGroup** (用户画像分桶)；本层把一个 ProfileGroup 采样成一个具体 `BrowserProfile`。

### 3.2 BrowserProfile

```typescript
export interface BrowserProfile {
  instanceId: string;              // stable per-instance ID; distinct from profileGroupIds membership
  locale: 'zh-CN' | 'en-US' | 'ja-JP' | ...;
  timezone: string;                // 'Asia/Shanghai' / 'America/New_York' / ...
  viewport: { width: 1920 | 1536 | 1366; height: 1080 | 864 | 768 };
  userAgent: string;               // 与 viewport/OS 一致, 不要混搭
  platform: 'Win32' | 'MacIntel' | 'Linux x86_64';
  languages: string[];             // ['zh-CN', 'zh', 'en']
  /** 账号组别, 让 scheduler 避免把同一类 Query 喂给同一账号 */
  segmentGroup: 'baseline' | 'beauty_daily' | 'luxury_collector' | ...;
}
```

**关键决策**: `userAgent`/`platform`/`viewport`/`languages` **必须来自一份 coherent preset 表** (`config/browser-profiles.json`)，随机组合会被风控识别 (UA 说是 Windows 但 platform 报 MacIntel → 直接 CF_BLOCKED)。

### 3.3 账号与 Profile 的绑定关系

Given `ExecutableQuery.profileGroupIds = []`, sample any profile; given non-empty array, sampled `BrowserProfile.segmentGroup` must be one of them. In all cases, `Account.segmentGroup` must match the final sampled profile's `segmentGroup`. If no matching account exists, return `NO_ACCOUNT_AVAILABLE`, set Query to PENDING, do not retry.

**原因**: 同一账号被反复喂"美妆"和"奢侈品"两类 Query，会被引擎的个性化模型污染 → 结果偏离真实画像。跨 segment 静默用号会污染指标。

### 3.4 Profile 采样接口

```typescript
// src/profiles/sampler.ts
export function sampleProfile(
  profileGroupIds: string[],
  seed?: string   // 给定 seed 时确定性, 用于 HAR 回放
): BrowserProfile;
```

- `profileGroupIds` 为空数组时采样任意 Profile。
- `profileGroupIds` 非空时，采样的 Profile 必须其 `segmentGroup` 在该数组内。
- HAR 回放测试 (§10.3) 必须传 seed，保证同一 Query 回放出同一 Profile。
- 生产环境不传 seed，每次采样随机 (但在 ProfileGroup 定义的分布内)。

---

## 4. 反检测三层防御

来自真实对抗: CF (Cloudflare) / PerimeterX / 自研风控 的三层击穿成本递增。Adapter 必须 **同时** 覆盖这三层，任何一层缺失都会在 48h 内被封。

### 4.1 第一层 — 浏览器指纹 (必做, 最基础)

**选型决策**: **Camoufox (基于 Firefox ESR + 反指纹 patch) > playwright-extra + stealth plugin > 裸 Playwright**。

- Camoufox 已内置: navigator.webdriver 擦除、WebGL/Canvas 指纹噪声、字体白名单、WebRTC 泄漏防护。
- 部署上 Camoufox 用 `launch_persistent_context` + 固定 user_data_dir, 让 cookie/indexedDB 持久化 (关键, 否则每次都要重登)。
- 必须启动参数 (通过 2025Q1 实战验证):
  ```
  --disable-blink-features=AutomationControlled
  --disable-dev-shm-usage        # 防 /dev/shm 太小导致 tab 崩溃
  --disable-software-rasterizer  # 容器里关这个否则 Gemini 图层崩
  --no-default-browser-check
  --disable-features=IsolateOrigins,site-per-process
  ```
- ❌ 禁止加 `--headless=new` 跑真实爬取 (CF 识别率显著升高)，只在 CI HAR 回放用 headless。
- ❌ 禁止开 DevTools Protocol 监听到业务回调 (`Network.enable` 等) — 有些风控脚本检测 CDP 通道活跃度。

### 4.2 第二层 — 行为指纹 (关键, 决定存活周期)

**原则**: 真实用户不会在 50ms 内提交、不会鼠标坐标永远 (0,0)、不会在输入框里用 `fill()` 瞬间灌完 300 字。

| 行为 | 实现 | 为什么 |
|------|------|--------|
| 输入延迟 | `page.type(selector, text, { delay: randomBetween(20, 80) })` | fill() 瞬时注入会被 doubao/Gemini 前端 trace 识别 |
| 鼠标移动 | 进入对话框前先 `page.mouse.move(x, y, { steps: 15 })` 走 2-3 个关键点 | 纯程序驱动 click 没有 mousemove 事件轨迹 |
| 滚动 | 结果渲染中随机 `page.evaluate(() => window.scrollBy(0, 120))` 1-2 次 | 完全无滚动 = 明显机器人 |
| 停顿 | 提交前随机停 2-5s, 输入完成后停 1-3s | 真实用户读了 Prompt 才发 |
| 页面打开即走 | 禁止 `goto` → 立刻 `click submit`; 必须有 `waitForSelector(chat_input)` + 至少 3s 停顿 | 风控的 t_load → t_first_interaction 阈值 |

**Quill 编辑器特殊处理** (Gemini / 部分豆包入口使用 contenteditable Quill):

三段降级注入链:

```typescript
async function injectQuill(page: Page, sel: string, text: string) {
  // Method 1: execCommand (最像真实)
  try {
    await page.evaluate(({ sel, text }) => {
      document.querySelector<HTMLElement>(sel)!.focus();
      document.execCommand('insertText', false, text);
    }, { sel, text });
    if (await verifyText(page, sel, text)) return;
  } catch {}
  // Method 2: ClipboardEvent paste
  try {
    await page.evaluate(({ sel, text }) => {
      const el = document.querySelector<HTMLElement>(sel)!;
      const dt = new DataTransfer();
      dt.setData('text/plain', text);
      el.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true }));
    }, { sel, text });
    if (await verifyText(page, sel, text)) return;
  } catch {}
  // Method 3: innerHTML 兜底 (最易被风控识别, 仅最后手段)
  await page.evaluate(({ sel, text }) => {
    document.querySelector<HTMLElement>(sel)!.innerHTML = `<p>${text}</p>`;
  }, { sel, text });
}
```

### 4.3 第三层 — 网络指纹 (代理质量决定)

- **TLS/JA3 指纹**: Camoufox 已对齐 Firefox ESR; 不要用任何 HTTP client 替代浏览器调用 /backend-api/*。
- **IP 类型**: 必须住宅代理 (residential)，数据中心 IP 对 ChatGPT/Gemini 100% CF_BLOCKED。
- **IP 稳定性**: 同一账号在一次会话内 (Cookie 生命期内) 必须用同一 IP 出口；IP 轮换 = 账号要求重新验证。
- **MVP 采购方案**: 海外 Ninja Clash 订阅 (从订阅链接拉节点) + 国内直连 (豆包/DeepSeek 不需要代理)。Admin 只看订阅健康度，不做 IP 池 CRUD (避免 Solo 阶段过度工程化)。

### 4.4 反检测失败信号表

Adapter 在 execute 过程中若探测到以下任一信号，立即抛对应 AdapterError (不要硬撑重试):

| 信号 | 触发动作 | 对应错误 |
|------|---------|---------|
| 页面 title 包含 "Just a moment..." / "Attention Required" | 抛 | CF_BLOCKED |
| `cf-ray` / `cf-cache-status` header + 403 | 抛 | CF_BLOCKED |
| 出现 CF Turnstile iframe | 走 §9 | CAPTCHA_REQUIRED |
| URL 重定向到 `/login` / `/signin` + 已传 cookie | 抛 | COOKIE_EXPIRED |
| `page.isClosed()` / `page.crash` 事件 | 抛 | PAGE_CRASHED |
| chat_input selector 15s 内未出现 | 抛 | TIMEOUT (stage: 'nav') |

---

## 5. 账号 & Cookie 生命周期

### 5.1 账号状态机

```
           ┌────────────┐   consecutive_failures ≥ 3   ┌────────────┐
           │   ACTIVE   │────────────────────────────>│   BANNED   │ (终态, 不回流)
           └────┬───────┘                              └────────────┘
                │                                            ▲
                │ COOKIE_EXPIRED / CAPTCHA_REQUIRED          │
                ▼                                            │
           ┌────────────┐    12h 后自动 warmup 探测    ┌─────┴──────┐
           │  COOLDOWN  │─────────── 探测失败 ─────────│   FROZEN   │
           └────┬───────┘                              └────────────┘
                │ 探测成功                                   ▲
                ▼                                            │
           ┌────────────┐                                    │
           │   ACTIVE   │   Admin 手动冻结 (Cookie 污染等)  │
           └────────────┘────────────────────────────────────┘
```

**数据模型**:

```prisma
model LLMAccount {
  id                   String   @id @default(cuid())
  engineId             EngineId
  usernameMasked       String   // 显示用 (m***@gmail.com)
  encryptedCookies     Bytes    // AES-256-GCM, KMS 托管密钥
  status               AccountStatus // ACTIVE / COOLDOWN / FROZEN / BANNED / PENDING_REGISTER
  segmentGroup         String?  // §3.3 与 Profile 绑定
  cooldownUntil        DateTime?
  consecutiveFailures  Int      @default(0)
  lastUsedAt           DateTime?
  lastHealthCheckAt    DateTime?
  registeredAt         DateTime
  createdBy            String   // 'auto_register' | 'admin_manual'
  @@index([engineId, status, segmentGroup])
}
```

### 5.2 Cookie 保活

- **定时任务** (Celery Beat / BullMQ cron): `cookie_keep_alive` 每 2h 执行一次 (原始测试床是 6h, 但 doubao/deepseek 在 6h 内就有滑动风控, 调到 2h)。
- 保活动作: 对每个 ACTIVE 账号, 打开 home 页 + 读一次 `/api/user/me` (或等价), 不发 Query。
- 失败 (COOKIE_EXPIRED) → 状态置 COOLDOWN, `cooldownUntil = now + 12h`。
- **禁止** 保活时替用户发 Query (会被识别为批量行为)。

### 5.3 Cookie 录入格式

> **DEPRECATED-<TODO-merge-date>** for `doubao` / `deepseek` (Refs #1118 / Epic #1110):
> Phase 3 cleanup retires the env-variable / Admin-paste cookie injection
> path for these two MVP engines; cookies are now sourced exclusively from
> the vm_session execution mode + vm_side runner (see ADR-016). The
> original text below is preserved per AGENTS.md "Admin Surface Rule"
> (维护原则: 禁止删除未替换的规则, 标 DEPRECATED + 原因) so future
> engines that still rely on manual cookie paste — e.g. ChatGPT, Gemini —
> keep a working reference. Status for other engines is unchanged.

用户 (Admin) 导出 Cookie 有两种来源:

- **EditThisCookie JSON** (数组): `[{"domain": ".chatgpt.com", "name": "__Secure-next-auth.session-token", "value": "...", "expirationDate": 1.7e9, ...}]`
- **浏览器 Copy as HAR** 里 `request.cookies[]`

Admin 粘贴 Cookie 时 (ADMIN_PRD §4.2.4 账号池):

1. 粘贴框只接受上面两种格式 (检测到就自动判断)，其它格式拒绝。
2. 前端转成 Playwright `BrowserContext.addCookies()` 格式:
   ```ts
   { name, value, domain, path, expires, httpOnly, secure, sameSite }
   ```
3. **DeepSeek 特例**: 除了 Cookie, 还必须同时粘贴 `localStorage.userToken` (DeepSeek 用 localStorage 存 bearer token, Cookie 不够)。表单上是两个输入框。
4. 存储: `encryptedCookies` 字段用 KMS 加密; Admin UI 回显永远显示 `***`。审计日志记录 "粘贴了 cookie" 不记录明文。

### 5.3a 账号 Pre-Warm (2026-04-21 新增)

> **问题背景**: Review 2026-04-21 §3 指出, Admin 管理员批量导入 Cookie 后, 账号状态从 PENDING 跳到 ACTIVE 缺少一个"健康探测+缓存预热"步骤, 导致头几次真实 Query 命中未预热账号 → 失败率突增 → COOKIE_EXPIRED 标签误判 → 账号被无谓降级. 必须固化 pre-warm 流程.

**触发时机**:
1. Admin 首次粘贴 Cookie 后 (status: `PENDING` → 触发 pre-warm)
2. `COOLDOWN` 到期账号恢复前 (status: `COOLDOWN` → pre-warm → `ACTIVE`)
3. 自动注册完成后 (status: `ACTIVE` 但 `last_used_at == null`)

**Pre-Warm 步骤** (`src/accounts/prewarm.ts` 单一入口):

```
1. 加载 encryptedCookies → 解密 → BrowserContext.addCookies()
2. 导航到引擎主页 (doubao.com / chat.deepseek.com / chat.openai.com)
3. 探测: 
   - 豆包: 检测 .user-avatar-menu 存在 (已登录) 且无 .captcha-overlay
   - DeepSeek: 检测 .sidebar-user-info 且 localStorage.userToken 有效
   - ChatGPT: 检测 sidebar 导航存在且 /api/auth/session 返回 200
4. 探测失败 → 账号置 QUARANTINED (不是 COOLDOWN), 跳人工审核, 不重试
5. 探测成功 → 发一条极轻量 Query ("1+1=?") 验证真实对话通路
6. 轻量 Query 成功 → status = ACTIVE, last_used_at = now, health_score = 1.0
7. 轻量 Query 失败 (超时 / 对话框无响应) → 账号置 QUARANTINED, 触发人工告警
```

**性能预算**:
- 单账号 pre-warm < 45s (含导航 + 探测 + 轻 Query)
- 并发上限: 同引擎同时只 pre-warm 3 个账号 (避免触发风控)

**失败降级**:
- Pre-warm 失败不计入 Query 成功率 (因 QUARANTINED 账号还没真正服务过业务 Query)
- 24h 内同账号 pre-warm 失败 ≥ 2 次 → 永久隔离, 需 Admin 重新粘贴 Cookie
- 登录探测误报(.user-avatar-menu 偶发选择器漂移) → P2 告警, Admin 手动标记为"已验证"可覆写

**状态机扩展** (覆盖 §5.1 中 `status`):
```
PENDING → PRE_WARMING → ACTIVE             (成功)
PENDING → PRE_WARMING → QUARANTINED        (探测或轻 Query 失败)
COOLDOWN → PRE_WARMING → ACTIVE            (恢复成功)
COOLDOWN → PRE_WARMING → QUARANTINED       (恢复失败, 升级为隔离)
```

**观测字段** (`Accounts` 表新增):
- `prewarm_last_run_at TIMESTAMP`
- `prewarm_success_count INTEGER DEFAULT 0`
- `prewarm_failure_count INTEGER DEFAULT 0`
- `prewarm_last_failure_code TEXT` (例: `CAPTCHA_REQUIRED`, `SELECTOR_MISSING`, `LIGHT_QUERY_TIMEOUT`)

Admin §4.2.4 (账号池仪表盘) 新增列: "Pre-Warm 成功率 (近 7d)" + "末次 pre-warm 失败码".

**测试**:
- L3 集成 `account-prewarm.test.ts` (Session 1): 录制 pre-warm HAR, 验证状态迁移正确
- L3 `account-prewarm-failure.test.ts`: 注入探测失败, 验证进 QUARANTINED
- Harness (Session 1 追加): 所有账号状态迁入 `ACTIVE` 必须经过 `PRE_WARMING` 中间态, 禁止 `PENDING → ACTIVE` 直跳 (grep `status:\s*['"]ACTIVE['"]` 反查上一行 `PRE_WARMING`)

### 5.4 自动注册 (CN 引擎)

> **DEPRECATED-<TODO-merge-date>** for `doubao` / `deepseek` (Refs #1118 / Epic #1110):
> Phase 3 cleanup retires this auto-registration flow for the two MVP
> engines; account provisioning is now handled inside the vm_session
> execution mode + vm_side runner (see ADR-016). Preserved per AGENTS.md
> "Admin Surface Rule" (维护原则: 禁止删除未替换的规则, 标 DEPRECATED +
> 原因) so the historical contract and harness expectations remain
> recoverable if a future engine reuses the lubansms-based flow.

MVP 只做 **豆包 + DeepSeek** 的自动注册, 不做 ChatGPT/Gemini (成本高 + 风控严)。

流程 (由 `src/accounts/auto_register.ts` 实现):

```
account_pool.active_count < threshold (默认 3)
  → 触发 register_worker
    → 向 鲁班SMS (lubansms.com) 请求一个可用手机号 (project_id = 该引擎)
    → 启 Camoufox, 打开注册页
    → 填手机号 → 点发验证码
    → 轮询 鲁班SMS get_sms API 拿验证码 (60s 超时)
    → 填验证码 → 设置密码 → 完成注册
    → 注册成功后 → 立刻 loginFlow → 导出 Cookie → 存库, status=ACTIVE
    → 失败 (CAPTCHA / 短信超时 / 手机号被封) → 释放号码 + 记录失败原因 + P1 告警
```

Harness:

- 鲁班SMS 调用必须走 `src/accounts/sms/luban.ts` 单一入口, 便于后期切换到其他接码商。
- 每次注册产 `AccountRegistrationLog` (success/fail + duration + cost), Admin §4.2.4 表格展示近 7 天。

---

## 6. 错误分类 & 重试 & 冷却

### 6.1 错误码表 (权威)

| code | 含义 | 归因 | 账号处置 | 代理处置 | 重试策略 | 计入成功率 | 告警级别 |
|------|------|------|---------|---------|---------|-----------|---------|
| `CF_BLOCKED` | Cloudflare 403 / "Just a moment..." | 代理 IP 被识别 | 不动 | **加黑 24h** | 换代理重试 1 次, 仍失败 → FAILED | 是 | 单条 P3, 1h > 5% P1 |
| `COOKIE_EXPIRED` | 被重定向到 /login 且已带 cookie | 账号 | **COOLDOWN 12h** | 不动 | 换账号重试 1 次 | 否 (不计入, 账号问题) | 单条 P4, 引擎级 P2 |
| `CAPTCHA_REQUIRED` | 页面出现 Turnstile/hCaptcha/滑块/视觉 | — | 不动 | 不动 | 走 §9 三级解决 | 部分计入 | P3 |
| `PAGE_CRASHED` | page.crash / page.isClosed | 浏览器 | 不动 | 不动 | 重启 Browser Context, 重试最多 1 次 | 是 | P3 |
| `PROXY_DEAD` | TCP 连不上代理 / 代理 5xx | 代理 | 不动 | **加黑 1h** | 换代理重试 1 次 | 是 | P3 |
| `NO_ACCOUNT_AVAILABLE` | requiresLogin=true 且无 ACTIVE 账号 | 账号池水位 | — | — | **不重试, Query 置 PENDING**, 账号补充后重入 | 否 | 引擎级水位 P1 |
| `EXTRACT_EMPTY` | 页面加载成功但抽文本 < 30 char | 可能 DOM 变更 | 不动 | 不动 | 不重试 (抽失败大概率是 selector 过期, 重试也没用) | 是 | **DOM 变更 P1** (连续 3 条同 selector 失败) |
| `PARSER_FAIL` | 结构化解析失败 (DOM 变更) | engine | 不动 | 不动 | 重试 = 否；路由 = Analyzer only（入 `parse_failures` 审核队列）；见 DECISIONS §12 和 DATA_MODEL.md §5.6 | 是 | P1 |
| `TIMEOUT` | 任何 stage 超时 | — | 不动 (< 3 次) / COOLDOWN (3 次) | 不动 | 最多 3 次 attempt（1 原始 + 2 次重试），指数退避 2s/4s | 是 | P3 |

**"不计入成功率"** 的含义: 这条 Query 从分母中扣除 (因为失败原因与 AI 引擎无关, 不该影响可用性看板)。DB 保留记录, 有单独的"运维侧失败"看板。

### 6.2 重试决策核心逻辑

```typescript
// src/scheduler/retry.ts
async function executeWithRetry(query: ExecutableQuery, adapter: AIEngineAdapter) {
  let attempt = 0;
  const MAX = 3;
  let lastErr: AdapterError | null = null;

  while (attempt < MAX) {
    attempt++;
    const ctx = await buildContext(query, adapter, attempt);   // 每次都重选账号 + 代理
    try {
      return await adapter.execute(query, ctx);
    } catch (e) {
      const err = toAdapterError(e);
      await applyErrorSideEffects(err, ctx);                   // 见 §6.1 表的"处置"列
      if (!shouldRetry(err, attempt)) {
        if (err.code === 'NO_ACCOUNT_AVAILABLE') {
          return markAsPending(query);                         // 不是 FAILED !
        }
        throw err;
      }
      await backoff(attempt);
      lastErr = err;
    }
  }
  throw lastErr!;
}
```

### 6.3 `retry_count` 字段的坑

**源头 Bug** (来自测试床 `scraping-experience-report.md`): 最初 `retry_count` 写在 ExecutableQuery 上, 被 scheduler 与 adapter 并发修改, 导致 "重试 3 次" 实际变成 "重试 6-9 次" (race condition)。

**约束**: `retry_count` **只存在 ExecutionContext.attempt** (内存变量), 不落库; 真正落库的是 `attempts: Attempt[]` 数组 (每次 attempt 一条 append-only 记录), 用数组长度判断次数。

### 6.4 跨 attempt 的副作用边界

- 账号 COOLDOWN / 代理加黑 **立即生效**, 下一个 attempt 自动避开。
- HAR / 截图 / rawHtml 每个 attempt 独立存档, 文件名含 `attempt-{n}`。
- 账号 `consecutive_failures` **仅在 attempt N 失败且 attempt N+1 换了账号** 的情况下才 +1 (避免同一账号反复尝试把失败数刷高)。

---

## 7. 代理池 & 账号调度

### 7.1 代理调度

- **代理不是先到先得**: 每次 attempt 重新 sampleProxy(), 基于 `failure_rate_1h` 排除近 1h 失败率 > 30% 的节点。
- **IP 粘性**: 同一账号在 `cooldown_until` 触发前, 优先复用上次成功的代理 (原测试床 bug: IP 一直换导致账号被风控要求"验证新设备")。
- **Ninja Clash 订阅刷新**: 每 6h 拉一次订阅, 新节点默认 `status='probing'`, 跑 healthCheck 通过才入池。

### 7.2 账号调度 (SELECT FOR UPDATE)

并发 scheduler (两个 worker) 可能同时选中同一账号:

```sql
-- ❌ 不要:
SELECT id FROM llm_accounts WHERE engine=$1 AND status='ACTIVE' ORDER BY last_used_at ASC LIMIT 1;

-- ✅ 必须:
BEGIN;
SELECT id FROM llm_accounts
  WHERE engine=$1 AND status='ACTIVE' AND segment_group=$2
    AND (last_used_at IS NULL OR last_used_at < NOW() - INTERVAL '30 seconds')
  ORDER BY last_used_at ASC NULLS FIRST
  LIMIT 1 FOR UPDATE SKIP LOCKED;
UPDATE llm_accounts SET last_used_at = NOW() WHERE id = $selected;
COMMIT;
```

`FOR UPDATE SKIP LOCKED` 保证并发 scheduler 选到不同账号, 不会阻塞。

### 7.3 全局 Cron

```
cookie_keep_alive            */2 * * * *     (见 §5.2)
reset_daily_counts           0 0 * * *       (重置 daily_query_count 等)
proxy_health_check           */5 * * * *     (轮询代理 ping)
account_pool_watermark_check */10 * * * *    (低水位 → 触发 auto_register, 见 §5.4)
subscription_refresh         0 */6 * * *     (Ninja Clash 订阅拉取)
```

实现方式 MVP 用 `node-cron` + 单实例锁 (Redis SET NX), Phase 2 换 BullMQ 或 Temporal。

### 7.4 0-Node Fallback (代理池全挂 / 订阅源不可达, 2026-04-21 新增)

> **问题背景**: Review 2026-04-21 §3 指出, 现有 §7.1-§7.3 假设 `proxy_nodes` 表里至少有 1 个 healthy 节点. 但有两类全挂场景:
> 1. **节点全死**: Ninja Clash 订阅源还能连, 但所有节点 ping fail (供应商封了我们的订阅 / 节点池迁移期)
> 2. **订阅源不可达**: Ninja Clash 订阅 URL 本身 5xx 或 DNS fail (供应商宕机)
> 
> 此前两种场景都会导致 Worker 死循环 retry, 浪费资源 + 不发告警 + Frank 没察觉。

**触发条件**:
- A: `SELECT count(*) FROM proxy_nodes WHERE region = 'overseas' AND health = 'healthy'` = 0 持续 ≥ 5 分钟
- B: `subscription_refresh` cron 连续 3 次失败 (即 18h 拉不到订阅)

**降级动作** (`admin_runtime_flags.overseas_proxy_pool_dead = true`):

1. **海外 Worker 进入 idle**: 不再 enqueue 新 Query 给 ChatGPT/海外引擎, 已入队的标记 `proxy_unavailable_skip` (区别于 PROXY_DEAD 单节点死亡), Query 状态 → PENDING
2. **国内 Worker 继续工作**: 豆包/DeepSeek 走国内直连不受影响, Planner 该周期内的整体配额不放大 (避免国内引擎被打挂)
3. **告警**: 立即 P1 告警 (PagerDuty + Slack #ops), 含触发条件 (A/B), 末次健康节点数, 末次订阅成功时间
4. **状态可视化**: Admin §4.2.1 (代理池仪表盘) 顶部红色 banner "海外代理池不可用 - 海外引擎已暂停"
5. **手动恢复**: Admin 修复后清除 flag (一键), 国内 Worker 不需重启, 海外 Worker 自动从 idle 退出
6. **数据补偿**: 恢复后, 在 idle 时段被跳过的 Query 自动从 PENDING 重新入队 (Planner 不重复生成同一 Query)

**A vs B 的区别**:
- A 仍可重试 (新订阅刷新可能拉回新节点)
- B 必须 Admin 介入排查 (订阅 URL 失效 / 账单过期 / Cloudflare 拦截)

**Schema 扩展**:

```prisma
model AdminRuntimeFlags {
  key                          String   @id
  value                        String   // 'true' | 'false' | JSON
  reason                       String?  // 触发原因, 如 "0_overseas_healthy_nodes_5min"
  setAt                        DateTime @default(now())
  setBy                        String?  // userId 或 'system'
  expiresAt                    DateTime?  // null = 永久, 否则到期自动清除
}
```

预定义 flags:
- `overseas_proxy_pool_dead` (本节)
- `cost_paused` (PRD §4.9.4.4)
- `kg_planner_paused` (Admin Session A1 用)

**测试**:
- L3 集成 `proxy-zero-node.test.ts`: 模拟 healthy=0 持续, 验证海外 Worker 进 idle + flag 写入 + 告警发出
- L3 `proxy-subscription-unreachable.test.ts`: 模拟订阅 URL 5xx 3 次, 验证 B 路径
- L3 `proxy-pool-recovery.test.ts`: 模拟节点恢复, 验证 PENDING Query 自动入队不重复

**Harness** (Session 2 追加):
- `admin-runtime-flag-cleanup`: `admin_runtime_flags` 任何写入必须配 `setAt` + `reason`, grep 缺一即报
- `proxy-zero-fallback-must-pause-overseas-only`: `src/scheduling/**` 处理 `overseas_proxy_pool_dead` 时, 必须只暂停 region='overseas', 不能误伤 region='cn'

---

## 8. DOM 抽取约定

### 8.1 Selector 稳定性层级

```
data-testid  >  aria-label  >  语义化 class (.reference-card)  >  CSS 组合  >  XPath
    ↑                                                                         ↑
  首选                                                                      禁止
```

- 任何新 Adapter 必须首先尝试 `data-testid`; 引擎改版时这个属性往往保留。
- 禁止 XPath 绝对路径 (`/html/body/div[3]/div[1]/...`) — 改版必挂。
- 所有 selector 集中在 `src/engines/adapters/{engine}/selectors.ts` 作为 const 导出, 便于 PR 对比。

### 8.2 textContent vs innerText

**硬性要求**: 抽回答主体必须用 `textContent`, 不是 `innerText`。

**为什么** (源头: `gemini-debug-notes.md`):

- `innerText` 受 CSS 布局影响, 如果元素 `display:none` / 未渲染, 返空。
- 豆包和 Gemini 用 SSR 首屏 + 客户端 hydrate, Playwright headless 下有一瞬间布局未完成, innerText 返空字符串, textContent 正常。
- 多段落之间 innerText 自动 \n, textContent 粘连 — 需要手工在 `</p>` 处加 \n。

实现:

```typescript
async function extractText(page: Page, sel: string): Promise<string> {
  return await page.evaluate((s) => {
    const nodes = document.querySelectorAll(s);
    return Array.from(nodes)
      .map((n) => n.textContent || '')
      .join('\n\n')   // 多段落明确分隔
      .replace(/\n{3,}/g, '\n\n')
      .trim();
  }, sel);
}
```

### 8.3 引擎特异 quirks

#### 8.3.1 ChatGPT

- 回答 streaming 完成标志: 最后一条 message 没有 `data-message-status="in_progress"` 属性。
- Citation 是 footnote 链接 (`<a href="...">` 中 `data-testid="cite-xxx"`), 脚注号角标 `<sup>` 对应 URL 列表。
- 登录失效重定向: `location.pathname === '/auth/login'`。

#### 8.3.2 豆包

- Citation DOM: `.reference-card` 容器, 每个里面 `.ref-title` + `.ref-url` (注意是 href 但不是 `<a>`, 是 `data-href`)。
- 登录失效标志: 页面出现"请登录"关键词 **连续 2 次及以上** (1 次可能是 tooltip, 误判率高)。12h cooldown 才回流。
- Streaming 完成: `.chat-item[data-streaming="false"]`。

#### 8.3.3 DeepSeek

- Citation DOM: `.citation-tooltip` 悬浮层, **必须触发 mouseenter** 才会渲染内部 url; 抽取时先 `page.hover(selector)` 再读。
- 回答前置清理: DeepSeek 有 "思考中..." 折叠块 (`.thinking-collapse`), 抽正文时必须 skip (否则把思考过程当成回答)。
- 登录态同时依赖 Cookie + `localStorage.userToken` (见 §5.3), 只设 Cookie 会被吞掉 Query。

#### 8.3.4 其它引擎 (Gemini / Perplexity / Kimi / Grok / 智谱 / Claude)

每个引擎在 `src/engines/adapters/{engine}/README.md` 写 quirks 小节; 本文件只收录已稳定运行的 3 个 MVP 引擎。

### 8.4 Citation 抽取与 PRD §4.2.6 对齐

- 每条 Citation 的 `extractedBy` 字段必须是以下之一: `footnote | reference_card | citation_tooltip | inline_link | api_structured | hover_card | unknown` (§2.1 ParsedCitation)。
- URL 归一化必须用 `tldts` 库 (PRD 依赖规则), 输出 `domain = eTLD+1`, 禁止手写 regex。
- 抽取失败 (选择器匹配 0 个) **不抛 EXTRACT_EMPTY**, 而是 `status='partial'` + `citations=[]`; 只有主体文本也空才抛。

### 8.5 extractedBy 分类

`unknown` 是"部分抽取成功但分类失败"的后备值；**禁止抛异常**，应总是分配 `unknown` 并由 analyzer 通过 `parse_failures` 审核队列调查。

---

## 8b. Citation Attribution Rules

Citations 通过两步精确匹配归因到品牌（MVP 阶段无模糊匹配）：

1. **Domain match** (步骤 1)：归一化 URL 为 eTLD+1（使用 `tldts`），查表 `kg_brand_domains` (M:1 → brand)。Confidence = 1.0。

2. **Alias match** (步骤 2)：若步骤 1 未中，扫描 citation `text`/`title` 针对 `kg_brand_aliases.alias` 的精确匹配（大小写不敏感）。Confidence = 0.9。

3. **Fallback**：brand_id = NULL, confidence = 0。行记录仍写入 `ai_response_citations` 供审计。

**Phase 2 计划**：引入 Levenshtein ≤2 模糊 + LLM 分类器；MVP 阶段仅精确匹配。

---

## 9. CAPTCHA 三级解决策略

成本递增, Adapter 按顺序尝试, 前一级失败才升级。

### 9.1 Level 1 — CapSolver API (首选)

覆盖: Turnstile / hCaptcha / reCAPTCHA v2 v3 / CF Challenge。

```typescript
// src/captcha/capsolver.ts
async function solveWithCapSolver(
  type: 'turnstile' | 'hcaptcha' | 'recaptcha',
  siteKey: string,
  pageUrl: string
): Promise<string>;  // token, 注入回页面 iframe callback
```

- 配额: 单账号 20 次/天, 超出 P2 告警。
- 超时: 单次 90s, 超时抛 CAPTCHA_REQUIRED (不升级到 Level 2, 改下条 Query 重试)。

### 9.2 Level 2 — 视觉 CAPTCHA (Volcano Ark)

覆盖: 图片点选 (选出所有"红绿灯")、物体识别、滑块 (视觉判断缺口位置)。

```typescript
// src/captcha/vision.ts
// 调火山方舟 doubao-seed-2.0-pro, 传图片 + prompt "返回红绿灯中心坐标 [x,y]"
async function solveVisionCaptcha(screenshot: Buffer, task: string): Promise<{x: number; y: number}[]>;
```

- 成本: ~0.02 CNY / 次, 但每天配额受限。
- 超时: 30s。
- 滑块拼图 Level 2 是 **视觉判缺口位置** → Level 3 **用人类轨迹曲线** 滑过去。

### 9.3 Level 3 — 滑块轨迹模拟

```typescript
// src/captcha/slider.ts
async function slideWithHumanTrajectory(
  page: Page,
  from: {x: number; y: number},
  to: {x: number; y: number}
) {
  // 贝塞尔曲线生成 80-120 个插值点, 每点间隔 5-15ms
  // 中途 2-3 个"犹豫" (回退 5px 再前进)
  // 最终位置有 ±2px 抖动
}
```

### 9.4 人工兜底 (告警, 不自动)

三级全失败 → P1 告警到 Admin 告警中心 (ADMIN_PRD §4.2.6 失败重试中心分组 `CAPTCHA_UNSOLVED`), 人工登录一次 Cookie 再入池。**不把人工环节写进自动化流程**, 避免阻塞调度。

---

## 10. 观测 & 持久化 & 数据契约

See `DATA_MODEL.md §2-§5` for full DDL.

### 10.1 持久化字段 (Response 表)

```prisma
model AiResponse {
  id                    String   @id @default(cuid())
  queryId               String   @unique
  engineId              EngineId
  executionMode         AdapterMode
  responseSource        ResponseSource  // 必填, NO SCHEMA DEFAULT (见 §10.5 + Decision #28.C3)
  status                ResponseStatus  // SUCCESS / PARTIAL / FAILED
  rawText               String          @db.Text
  rawHtmlUrl            String?         // S3/OSS
  harUrl                String?         // 关键: Admin 失败复现 + CI 回放
  screenshotUrl         String?
  latencyMs             Int
  responseStartedAt     DateTime
  responseCompletedAt   DateTime
  profileSnapshot       Json            // BrowserProfile 全量
  accountIdUsed         String?
  proxyIdUsed           String?
  errorCode             String?         // §6.1 code
  errorDetail           Json?
  attempts              Json            // Attempt[] append-only
  citations             AiCitation[]    // 见 PRD §4.2.6.A
  createdAt             DateTime @default(now())
  @@index([engineId, createdAt])
  @@index([status, errorCode])
}
```

### 10.2 HAR 录制约束

- **每次 attempt 独立一份 HAR**, 文件名 `{traceId}-attempt{n}-{engine}.har`。
- **上传前必须 sanitize**:
  - 删除 `request.headers.Authorization` 值
  - 删除所有 `Cookie` / `Set-Cookie` header
  - 删除 POST body 中的 `refresh_token` / `session_token` 字段
  - **保留**: 响应体、URL、method、status (这些是回放必需)。
- Harness 规则:
  ```bash
  grep -rE 'Authorization|Cookie|refresh_token' tests/fixtures/scraping/
  ```
  非空命中即 CI 失败。

### 10.3 CI 回放 (L3 测试)

```typescript
// tests/scraping/{engine}.spec.ts
test('doubao success path', async ({ page }) => {
  await page.routeFromHAR('tests/fixtures/scraping/doubao-abc12345.har', {
    update: false, notFound: 'abort'
  });
  const adapter = new DoubaoAdapter();
  const resp = await adapter.execute(fixtureQuery, fixtureCtx);
  expect(resp.status).toBe('success');
  expect(resp.rawText).toContain('兰蔻');
  expect(resp.citations.length).toBeGreaterThan(0);
});
```

- 每个 Adapter 至少 2 个 HAR fixture (success + 降级/失败路径)。
- CI 不连真实网络, 整个 adapter 层测试 < 30s。

### 10.4 Metrics (推给 Admin ADMIN_PRD §4.2)

物化视图 `engine_health_5min` 每 5 分钟由 `refresh_engine_health` cron 刷新:

```sql
CREATE MATERIALIZED VIEW engine_health_5min AS
SELECT
  engine_id,
  date_trunc('minute', created_at) - (EXTRACT(minute FROM created_at)::int % 5) * interval '1 minute' AS window_start,
  COUNT(*) AS sample_count,
  COUNT(*) FILTER (WHERE status = 'SUCCESS') * 1.0 / NULLIF(COUNT(*) FILTER (WHERE error_code NOT IN ('NO_ACCOUNT_AVAILABLE', 'COOKIE_EXPIRED')), 0) AS success_rate,
  percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms) FILTER (WHERE status = 'SUCCESS') AS p50_latency_ms,
  percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) FILTER (WHERE status = 'SUCCESS') AS p95_latency_ms,
  jsonb_object_agg(error_code, cnt) FILTER (WHERE error_code IS NOT NULL) AS error_breakdown
FROM (
  SELECT engine_id, created_at, status, error_code, latency_ms, COUNT(*) OVER (PARTITION BY engine_id, error_code) AS cnt
  FROM ai_responses
  WHERE created_at > NOW() - INTERVAL '24 hours'
) t
GROUP BY engine_id, window_start;
```

**成功率分母注意**: `NO_ACCOUNT_AVAILABLE` 和 `COOKIE_EXPIRED` 从分母剔除 (见 §6.1 "计入成功率" 列); 这是看板与 PRD §4.6 "引擎可用性" 的一致定义。

### 10.5 `responseSource` 枚举语义 (Session 1.2 双修正最终版, 2026-04-22)

每条 `AIResponse` / `ai_responses` row **必须** 显式 stamp `responseSource: ResponseSource`。schema 层 **无 default** (DDL 走 `ADD DEFAULT` backfill → `DROP DEFAULT` 双步), Adapter 层 / API fallback 层 / Prisma `create` 调用三处由 Harness F4-1/F4-2/F4-3 强制要求字段出现; 漏写即 PR block。

| 枚举值 | 来源路径 | 典型场景 | citations? | 进入分析? |
|--------|---------|---------|-----------|----------|
| `web_ui` | 浏览器 DOM 抽取 (主路径, 含 system prompt / RAG / browsing / 引用卡片等 Web-only 语义) | 3 家引擎正常采集 | ✅ 有 | ✅ 是 |
| `api_fallback` | 官方 OpenAPI 降级 | Web 失败 fallback / cold start | ❌ 通常空 | ✅ 是 (但 citation_share 不计入) |
| `mock_proxy` | dev / staging mock transport | 本地开发 / 集成测试桩 | varies | ❌ 否 (env=production 直接拒收) |
| `cached_replay` | HAR replay | CI L3 / 回归测试 | 跟原始一致 | ❌ 否 |
| `admin_har_replay` | Admin 后台手工触发回放 | 排错 / 审查 / 客户事件 reproduce | 跟原始一致 | ❌ 否 |
| `harness_fixture` | self-seeded violation fixture | __ci_fixtures__ 故意违规样本 | varies | ❌ 永远不入生产 |

**为什么需要这个字段** (Decision #28.C3):
- **数据可信度审计**: 平台聚合的 PANO Score / 提及率 / 情感都基于 `web_ui` 才是 "AI 引擎的真实回答"; `api_fallback` 是降级证据, 应 weighted-down; `mock_proxy` / `*_replay` 不能污染生产指标
- **回放可追溯**: HAR replay 写库后必须能跟真实采集区分, 否则 Admin 排错时 "为什么这条 query 在生产里看不到, 但在 ai_responses 表里有 row" 无法解释
- **Harness 强约束**: 三处 (Web Adapter / API fallback / Prisma create) 任一漏写都会导致后续分析口径偏移, 所以 schema 不给 default, 让漏写当场炸而不是默默 fallback 成 `web_ui` 蒙混过关

**Harness 三条规则定位**:
- **F4-1** `web-adapter-must-stamp-response-source` — 扫 `backend/src/engines/adapters/**`, 排除 `api-fallback.ts` / `selectors.ts` / `types.ts`, 构造 AIResponse-shape 对象 (含 `rawText:` + `citations:`) 必须含 `responseSource:` 键
- **F4-2** `api-fallback-must-stamp-response-source` — 扫 basename `api-fallback.ts`, 同样的 shape gate + key 要求
- **F4-3** `prisma-airesponse-create-must-include-response-source` — 扫 `prisma.aiResponse.create|createMany` 调用, 40 行窗口内必须出现 `responseSource:`
- 自验证 fixture 在 `backend/src/engines/adapters/__ci_fixtures__/F4-{1,2}_*/` 与 `backend/src/__ci_fixtures__/F4-3_*`, selftest EXPECTED_POSITIVES 21/21 PASS

---

## 11. MVP 落地顺序 & 引擎清单

### 11.1 优先级

| Phase | 引擎 | Adapter 形态 | Region | 备注 |
|-------|------|-------------|--------|------|
| **MVP M1 (Week 1)** | **DeepSeek** | Web | cn | 国内直连, 无代理, 验证 Adapter 框架 |
| **MVP M2 (Week 1-2)** | **豆包** | Web | cn | 国内直连, 接码注册 + Cookie 保活全流程 |
| **MVP M3 (Week 2-3)** | **ChatGPT** | Web (API 降级) | overseas | Ninja Clash 代理 + 反 CF 全套 |
| Phase 2 M4 | Gemini | Web | overseas | Quill 注入 + 视觉 CAPTCHA |
| Phase 2 M5 | Perplexity | API 为主 | overseas | API 较稳, Citation 天然结构化 |
| Phase 3 | Kimi / 智谱 / Grok / Claude | Web + API | 混合 | 按市场份额排 |

### 11.2 每引擎的"Adapter Ready" 定义 (进 PHASE GATE)

- [ ] 健康探针能在 10s 内返回 ok
- [ ] 单 Query 成功路径 P95 延迟 < 30s (ChatGPT < 60s)
- [ ] 2 个 HAR fixture (success + 降级) sanitize 过 CI
- [ ] 错误码覆盖 §6.1 全部 8 种 (能抛出, 不一定都触发过)
- [ ] 账号状态机的 ACTIVE↔COOLDOWN↔FROZEN 路径有单测
- [ ] selectors.ts 集中, 无 XPath 绝对路径
- [ ] Citation 抽取准确率 ≥ 80% (在 fixture 集上人工验证)

---

## 12. 交叉引用矩阵

| 规则 | 本文档 | PRD | ADMIN_PRD | SESSIONS |
|------|--------|-----|-----------|----------|
| Adapter 接口 | §2 | §4.3.3 (指向本文件) | — | App Session 1 §1 |
| Profile-Aware | §3 | §4.2.3a / §4.3 | — | App Session 1 §1, Admin A2.4 |
| 反检测防御 | §4 | §4.3 | — | App Session 1.2 |
| 账号状态机 | §5.1 | §4.3 | §4.2.4 | Admin A2 §5 |
| Cookie 录入 | §5.3 | — | §4.2.4 (粘贴表单) | Admin A2 §5 |
| 自动注册 | §5.4 | §4.3 | §4.2.4 | App Session 1 §1, Admin A2 §5 |
| 错误码表 | §6.1 | §4.3 | §4.2.2 / §4.2.6 | App Session 1.2, Admin A2 §3/§7 |
| 重试策略 | §6.2 | §4.3 | §4.2.6 | App Session 1.2 |
| retry_count race | §6.3 | — | — | App Session 1.2 |
| 代理调度 | §7.1 | §4.3 | §4.2.5 | Admin A2 §6 |
| 账号 FOR UPDATE | §7.2 | — | §4.2.4 | Admin A2 对抗性验证 |
| DOM textContent | §8.2 | — | — | App Session 1.2 |
| 引擎 quirks | §8.3 | — | — | App Session 1.2 |
| Citation 抽取 | §8.4 | §4.2.6 (A-H) | — | App Session 3 §1.5/§1.6 |
| CAPTCHA 三级 | §9 | §4.3 | §4.2.6 (CAPTCHA_UNSOLVED 分组) | App Session 1.2 |
| HAR 持久化 + 脱敏 | §10.2 | — | §4.2.6 (样本回放) | Adapter test coverage |
| engine_health_5min | §10.4 | — | §4.2.2 | Admin A2 §3 |

**维护规则**: 本矩阵由任何一处规则变更触发 review; 如果某行在三个文档中定义漂移, **以本文件为准**, 其它文档修正回来 (这是"单一真相源"的含义)。

---

**END OF ADAPTER_CONTRACT.md**
