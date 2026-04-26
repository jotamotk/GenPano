# GENPANO 文档修订差异记录（Revision Diff Log）

> **源起**：`PRD_SESSION_REVIEW.md` 中 15 条 P0 + 21 条 P1 + 19 条 P2 共 55 项发现，经 Frank 2026-04-20 "全部同意，需选择的自决" 签字后，依 `DECISIONS.md` 批量落地到 8 份文档（新建 2 份、修订 6 份）。
>
> **本文件作用**：为 Frank 提供一次性审阅入口——每个决策（§1–§18）对应"哪个文件的哪一段改了什么"、"改动前 vs 改动后"。阅毕本文件即可签字 "Ready-to-Session"。
>
> **日期**：2026-04-20
> **负责人**：Claude（代 Frank 执行决策）
> **关联文档**：`PRD_SESSION_REVIEW.md`（审查报告）、`DECISIONS.md`（决策记录）

---

## 目录索引

1. [新建文档](#新建文档)
2. [修订文档](#修订文档)
3. [按决策索引的变更矩阵](#按决策索引的变更矩阵)
4. [已知遗留与 Phase 2 清单](#已知遗留与-phase-2-清单)
5. [Ready-to-Session 核验清单](#ready-to-session-核验清单)

---

## 新建文档

### N-1. `DATA_MODEL.md`（新建，953 行，31 张表）

**覆盖决策**：§5（删账号 30 天）、§7（物化视图）、§8（Citation 归因）、§9（Outbox）、§10（ProfileGroup 持久化）、§13（cost_events.budget_scope）、§18（query_executions / intent VARCHAR / extractedBy 扩展 / brand_rankings MV / platform_topics DDL）。

**核心表清单**：

| 领域 | 表 | 关键字段 / 索引 |
|---|---|---|
| 用户与项目 | `users` | `deletion_requested_at TIMESTAMPTZ`, `deletion_confirmed_at TIMESTAMPTZ`（§5） |
| | `projects` | FK → users (ON DELETE SET NULL → `deleted_user`) |
| 知识图谱 | `kg_brands` / `kg_products` / `kg_industries` / `kg_categories` / `kg_aliases` / `kg_brand_domains` | `kg_brand_domains` 作 citation alias 源（§8） |
| 生成管线 | `platform_topics` | 完整 DDL（§18 E-P1-3） |
| | `platform_prompts` | FK → platform_topics |
| | `query_executions` | 原 `platform_queries` 重命名（§18 D-P2-2） |
| | `attempts` | `attempt_number`（1 原始 + 最多 2 重试）+ `failure_mode` |
| | `ai_responses` | `detected_brand_ids UUID[]` + GIN 索引；`sentiment VARCHAR`, `sentiment_source ENUM('rule','llm')`（§16） |
| | `ai_response_citations` | `brand_id NULL` 表示未命中（§8）；`confidence NUMERIC(3,2)`：1.0 exact / 0.9 alias / 0 miss |
| | `brand_mentions` / `product_mentions` | 分表 |
| Profile | `profile_groups` | Admin 可调权（§10） |
| | `browser_profiles` | `instance_id`（§14，原 profileId） |
| | `accounts` / `account_states` | FK → profile_groups |
| 指标 | `metric_snapshots` | 日级快照 |
| | `mv_heatmap_mention_agg` | Postgres MATERIALIZED VIEW + `REFRESH CONCURRENTLY` 每小时（§7） |
| | `mv_brand_rankings` | 物化视图（§18 E-P1-2） |
| | `brand_mention_daily_agg` | 增量聚合 |
| 管理 | `audit_logs` | 全审计 |
| | `cost_events` | `budget_scope ENUM('pipeline','kg')`（§13） |
| | `brand_submissions` / `brand_discovery_logs` | |
| | `brand_bootstrap_jobs` | Outbox Pattern；Admin approve 时 enqueue（§9） |
| | `parse_failures` | PARSER_FAIL 兜底队列（§12） |
| Phase 2 占位 | `export_jobs` / `report_schedules` | 仅 DDL，无业务逻辑 |

**验证**：所有 PK / FK / CHECK 约束齐全；所有 ENUM 带 `unknown` / `other` 兜底（§原则 4）；按 decisions §原则 1 优先 Postgres 原生能力，不引入 ClickHouse。

---

### N-2. `openapi.yaml`（新建，1557 行，31 paths，32 schemas）

**覆盖决策**：§2（PATCH 方法）、§3（profileGroupIds plural）、§5（DELETE /users/me 30 天）、§13（CostEvent.budgetScope）、§14（BrowserProfile.instanceId）、§18（ProblemDetails RFC 7807 / intent VARCHAR / `:id` 风格 / Auth endpoints 汇总）。

**Paths 摘录（31 条）**：

| 组 | Path | Methods | 重要契约 |
|---|---|---|---|
| Auth | `/api/v1/auth/login` | POST | 200 + `{ token, user }` |
| | `/api/v1/auth/register` | POST | 201 + `{ token, user }` |
| | `/api/v1/auth/logout` | POST | 204（吊销当前 session） |
| | `/api/v1/auth/forgot-password` | POST | 202 |
| | `/api/v1/auth/reset-password` | POST | 204 |
| Users | `/api/v1/users/me` | GET / DELETE | DELETE 返 204，写 `deletion_requested_at`（§5） |
| Projects | `/api/v1/projects` | GET / POST | |
| | `/api/v1/projects/:id` | GET / PATCH / DELETE | PATCH 字段级 merge |
| | `/api/v1/projects/:id/brands` | GET / POST | |
| | `/api/v1/projects/:id/topics` | GET / POST | |
| | `/api/v1/projects/:id/topics/:topicId` | GET / **PATCH** / DELETE | §2 决议：PATCH（原 PUT）|
| ProfileGroups | `/api/v1/profile-groups` | GET | 返 `ProfileGroupResponse[]`（§10） |
| Admin | `/api/v1/admin/brand-submissions` | GET / POST approve | Approve 触发 outbox（§9） |
| | `/api/v1/admin/cost-events` | GET | 支持 `?budget_scope=pipeline\|kg` 过滤（§13） |
| MCP（Phase 2 骨架） | `/api/v1/mcp/tools/*` | POST | Bearer Token 认证桩，无实现（§17） |

**Schemas 摘录（32 个）**：

| Schema | 关键字段 | 决策锚点 |
|---|---|---|
| `User` | `deletionRequestedAt: date-time \| null` | §5 |
| `Project` | `primaryBrandId, competitorBrandIds[]` | 无变更 |
| `Brand` | `aliases[], domains[]` | §8 |
| `ExecutableQuery` | **`profileGroupIds: string[]`**（非空数组；`[]` 表示任意）、`intent: string` | §3、§18 |
| `BrowserProfile` | **`instanceId: string`**（原 profileId） | §14 |
| `AIResponse` | `sentiment, sentimentSource: "rule"\|"llm"`、`detectedBrandIds: UUID[]` | §16、§8 |
| `Citation` | `brandId?: UUID, confidence: 0\|0.9\|1.0` | §8 |
| `CostEvent` | **`budgetScope: "pipeline"\|"kg"`** | §13 |
| `AdapterError` | 8 种错误码（CAPTCHA/TIMEOUT/NETWORK/LOGIN_EXPIRED/QUOTA_EXCEEDED/PARSER_FAIL/NO_ACCOUNT_AVAILABLE/UNKNOWN） | §4、§12 |
| `ProblemDetails` | RFC 7807 | §18 |
| `ProfileGroupResponse` | `id, name, engines, segments, profileCount` | §10 |

**验证**：`python -c "import yaml; yaml.safe_load(open('openapi.yaml'))"` 通过；所有 path 用 `:id` 风格（§18 D-P2-1）。

---

## 修订文档

> **说明**：以下每条列"改动前（Before）"与"改动后（After）"的核心对照。完整 patch 以 git diff 为准。

---

### R-1. `DESIGN_TOKENS.md`（+27 行）

#### R-1.1 新增 13 个 token（§18 C-P1-3 / C-P2 / §15）
**Before（Missing）**：Landing / Drawer 用到的若干颜色 / 尺寸以 hardcoded rgba / px 形式散落。

**After（新增 token 清单）**：
```css
--color-danger: #E5484D;
--color-danger-hover: #D1383D;       /* C-P2：base +10% Shade */
--color-success-hover: #13856A;      /* C-P2：base +10% Shade */
--color-text-on-accent: #FFFFFF;
--color-overlay-drawer: rgba(0,0,0,0.45);
--color-scrim: rgba(0,0,0,0.6);
--color-accent-alpha-05: rgba(96,91,255,0.05);
--color-accent-alpha-10: rgba(96,91,255,0.10);
--color-accent-2-alpha-06: rgba(var(--color-accent-2-rgb),0.06);
--drawer-width-desktop: 520px;
--drawer-width-tablet: 480px;
--drawer-width-mobile: 100%;
--drawer-animation-duration: 280ms;
```

#### R-1.2 MVP 主题锁定声明（§6）
**Before**：三个候选主色（#605BFF / #7C3AED / #3B82F6）并列，未指定 MVP 生效哪个。

**After**（文档开头新增）：
> **Production theme: `#605BFF` (Stripe Purple) — locked for v1 MVP.**
> 其他候选色（见 `DASHBOARD_REDESIGN_PROPOSAL.md`）为 Phase 2 A/B 备选，**不实现 theme toggle**。

#### R-1.3 Heatmap / Chart token 边界声明（§15）
**Before**：`--color-chart-*` 与 `--color-heatmap-*` 未划分用途。

**After**（新增约束段）：
> **C-P1-1 边界规则**：
> - `BrandTopicHeatmap` 仅允许 `var(--color-heatmap-*)`；
> - 所有其他图表组件仅允许 `var(--color-chart-*)`；
> - Harness grep 断言见 `TEST_STRATEGY.md §G-04`。

---

### R-2. `ADAPTER_CONTRACT.md`（+39 行，11 处改动）

#### R-2.1 §2.1 ExecutableQuery：profileGroupId → profileGroupIds（§3）
**Before**：
```ts
interface ExecutableQuery {
  profileGroupId: string | null;  // null = any
  ...
}
```
**After**：
```ts
interface ExecutableQuery {
  profileGroupIds: string[];      // 非空数组；[] 表示任意（any group）
  ...
}
```
+ 新增字段 required/optional 表（§18 D-P1-5）。
+ 新增 `intent` 字段存储说明：`intent: string`，VARCHAR(50) 存储（§18 D-P2-3）。

#### R-2.2 §2.2 AIResponse immutability（§18 D-P1-3）
**Before**：未约束 adapter 是否可以 mutate `response.profile`。

**After**：
> **Immutability 要求**：`AIResponse.profile` 在离开 adapter 前必须通过 `Object.freeze(structuredClone(profile))` 深冻结。Analyzer / Tracker 禁止再 mutate。

#### R-2.3 §2.3（新增）API Data Shapes
新增整节，定义前后端共享的 Response 结构（引用 openapi.yaml）：
- `ProfileGroupResponse`
- Logout 204
- `DELETE /users/me` 契约（§5：204 + 30 天窗口）

#### R-2.4 §3.2 BrowserProfile.profileId → instanceId（§14）
**Before**：`profile: { profileId: string, ... }`
**After**：`profile: { instanceId: string, ... }`

#### R-2.5 §3.3 Binding rules（§4）
**Before**：无 profileGroup 时的调度策略隐式（"随便找一个"）。

**After**：显式规则表
| ExecutableQuery.profileGroupIds | DB 匹配结果 | Adapter 返回 |
|---|---|---|
| `[]` | 任意可用 group | 成功 |
| `[gA, gB]` | 无账号可用 | `NO_ACCOUNT_AVAILABLE`；Query 置 `PENDING`，不入重试池 |
| `[gA, gB]` | 账号全忙 | 等待 + 重试（最多 2 次） |

#### R-2.6 §6.1 重试文案（§18 D-P1-4 / §12）
**Before**："重试 3 次"（语义不清）
**After**："最多 3 次 attempt（1 原始 + 2 次重试）"；新增 PARSER_FAIL 行：
| Failure Mode | Retry? | 归属 |
| PARSER_FAIL | 否 | 入 `parse_failures`，由 Analyzer 兜底 |

#### R-2.7 §8.1 extractedBy enum（§18 D-P2-4）
**Before**：`extractedBy: "text_regex" | "citation_block"`
**After**：`extractedBy: "text_regex" | "citation_block" | "api_structured" | "hover_card" | "unknown"`

#### R-2.8 §8b（新增）Citation Attribution Rules（§8）
新增整节：
> MVP Citation 归因策略：
> 1. **Exact match**：URL eTLD+1 与 `kg_brand_domains.domain` 严格相等 → `brand_id` + `confidence = 1.0`；
> 2. **Alias match**：eTLD+1 命中 alias 表 → `brand_id` + `confidence = 0.9`；
> 3. **Miss**：以上均不中 → `brand_id = NULL` + `confidence = 0`。
> **禁止** Levenshtein / LLM fuzzy（§原则 3：数据完整性 > 速度）；Phase 2 再评估。

#### R-2.9 §10 cross-ref（§18 D-P2-2）
- 新增："DB 表级真相源见 `DATA_MODEL.md`"
- `platform_queries` → `query_executions`

---

### R-3. `CLAUDE_CODE_SESSIONS.md`（-276 行整体，12 处编辑）

#### R-3.1 Session T1（Daily Digest Spike）整段删除（§1）
**Before**：3574–3850 行（含 PromptBody、AcceptanceCriteria、测试矩阵）。
**After**：整段移除；目录 / 导航索引同步删除。后续 Session 编号不受影响（T1 原本就 Spike 前缀）。

#### R-3.2 §2b.4 navigate 目标路径（§1）
**Before**：`navigate('/dashboard')`
**After**：`navigate('/brand/overview')`

#### R-3.3 CI 断言新增（§1）
新增 CI check 清单第 13 条：
> 13. `/dashboard` 301 重定向：`curl -I http://localhost:PORT/dashboard | grep -q "301"` 且 `Location` 头指向 `/brand/overview`（DECISIONS §1）。

#### R-3.4 Session 2 Task 4 PATCH 语义说明（§2）
**Before**：`PATCH /api/v1/projects/:projectId/topics/:topicId`（无说明）
**After**：增加 `PATCH 语义：字段级 merge（只传被修改字段），与 PRD.md §4.5.1 对齐。`

#### R-3.5 `platform_queries` → `query_executions`（§18）
**Before**（L726）：`存储到 platform_queries`
**After**：`存储到 query_executions`

#### R-3.6 Session 4b ProfileGroupFilter 三页 grep 断言（§3 衍生）
新增 Harness：
```bash
grep -l "ProfileGroupFilter" \
  src/pages/BrandDetailPage.jsx \
  src/pages/TopicsPage.jsx \
  src/pages/DiagnosticsPage.jsx
# 预期：三个文件均命中
```

#### R-3.7 Session 4a Auth 端点汇总表（§18 A-P2-4）
新增 1c 节：7 条 endpoint 汇总（含 DELETE /users/me 30 天说明）。

#### R-3.8 前置阅读 section（§18）
新增文档顶部 prerequisites：
> - `DATA_MODEL.md`（DB schema）
> - `openapi.yaml`（API 契约）
> - `ADAPTER_CONTRACT.md §2.3 / §8b`
> - `DECISIONS.md`

#### R-3.9 Retry 文案（§18 D-P1-4）
**Before**：L287 "指数退避重试 (最多 3 次)"
**After**："指数退避重试 (最多 3 次 attempt - 1 原始 + 2 次重试)"

#### R-3.10 Sentiment MVP = 规则+词典（§16）
**Before**（L1010–L1011）："使用 LLM 对 AI 回答中品牌/产品相关内容进行情感分析"（implies Phase 2 / TODO）
**After**："MVP 阶段使用规则+词典（中文 SnowNLP / 英文 VADER），字段 `sentiment_source = 'rule'`；LLM 增强延到 Phase 2。"

#### R-3.11 跳过的 edit（已由其他文档承接）
- **Drawer token 强引**：原 Triad T3 承载，Triad 已全段删除；Drawer 现由 T1'-T5' IA v2 sessions 引用 `DESIGN_TOKENS.md §C8 Drawer 契约` 承接（见 R-1.1）。
- **BrowserProfile.profileId → instanceId**：CLAUDE_CODE_SESSIONS 本身未直接引用该字段；重命名主要在 `ADAPTER_CONTRACT.md`（R-2.4）与 `DATA_MODEL.md`（N-1）落地。

---

### R-4. `PRD.md`（6 处改动）

#### R-4.1 §4.5.1 Topic 更新方法（§2）
**Before**：`PUT /api/v1/projects/:id/topics/:topicId`
**After**：`PATCH /api/v1/projects/:id/topics/:topicId`；新增 `// 2026-04-20 与 CLAUDE_CODE_SESSIONS §2 Task 4 对齐为 PATCH（字段级 merge）`

#### R-4.2 §4.6.1-0 /dashboard SUPERSEDED（§1）
**Before**：已标 SUPERSEDED 但未指定替代路由。
**After**：`/dashboard 永久 301 → /brand/overview（见 DECISIONS §1）`

#### R-4.3 §4.1.1e 账号删除流程（§5）
**新增完整子节**（原文件已有 §4.1.1e 账号删除主体，确认含 30 天窗口 + 204 + 立即登出 + 恢复链接流程）。

#### R-4.4 §4.x Sentiment MVP 策略（§16）
**Before**：Sentiment 描述为 "Phase 2 或 TODO"
**After**：`MVP 使用规则+词典（SnowNLP / VADER），sentiment_source = 'rule'`

#### R-4.5 `platform_queries` 重命名
PRD 本身不落 DB table 定义；DATA_MODEL.md 承接此变更（N-1）。

#### R-4.6 `profileGroupIds` 复数验证
PRD 全文已为 plural，无需再改。

---

### R-5. `ADMIN_PRD_B_PIPELINE.md`（2 处改动）

#### R-5.1 PARSER_FAIL 重试规则（§12）
**Before**：PARSER_FAIL 未在重试规则表显式出现（或归入通用"重试 3 次"）。
**After**：新增行 `| PARSER_FAIL | 0 重试 | 入 parse_failures 审核队列 |` + 解释段落。

#### R-5.2 侧栏标签（§18 B-P2-1）
**Before**：`🔗 生成管线`
**After**：`🔗 生成管线（单页，三层 Tab）`

---

### R-6. `ADMIN_PRD_C_KG.md`（1 处改动）

#### R-6.1 KG 预算上报（§13）
**Before**：KG LLM 预算仅提及上限，不指 cost_events 表。
**After**（§4.1 LLM Use Constraints 下新增段）：
> KG LLM 调用成本记入 `cost_events` 表，`budget_scope = 'kg'`（与 Pipeline 的 `budget_scope = 'pipeline'` 区分）。两者各自硬约束，独立告警。详见 `DATA_MODEL.md cost_events`。

---

### R-7. `ADMIN_CLAUDE_CODE_SESSIONS.md`（3 类改动）

#### R-7.1 Session A2 seeding（§11）
**Before**：Session A2 Prompt 未明示 seed 命令。
**After**：Prompt 开头新增：
> 执行 `npm run seed:admin`（使用 PRD_TEST_DATA_V1.md fixtures：128K attempts / 1560 topics / 9 engines；幂等可重复）。

#### R-7.2 Session A3 Outbox Pattern（§9）
**Before**：Approve 动作直接同步启动采集。
**After**：新增 Outbox Pattern 说明——写 `brand_bootstrap_jobs` 表；Planner 5 分钟轮询 worker 认领；禁止 API handler 内同步采集。

#### R-7.3 所有 Admin Session 末尾 Token 强引（§18 B-P2-2）
共 8 个 Session（A1 / A2 / A2.1 / A2.2 / A2.3 / A2.4 / A3 / A4）末尾统一追加：
> **Token 强引要求**：所有颜色、间距、尺寸必须从 `src/theme/tokens.ts` 读取；禁止硬编码 hex / rem / px。详见 `DESIGN_TOKENS.md`。

---

### R-8. `TEST_STRATEGY.md`（+8 条 grep 规则）

#### R-8.1 新增 §2.2 前节"G-01–G-08 grep 断言"
| 规则 | 目的 | 决策锚点 |
|---|---|---|
| G-01 | Token 未定义兜底（CSS var 引用 vs 定义 diff） | §18 |
| G-02 | API path 风格（`:id` only，禁 `{id}`） | §18 D-P2-1 |
| G-03 | `/dashboard` 301 redirect 断言 | §1 |
| G-04 | Heatmap / Chart token 边界 | §15 |
| G-05 | ProfileGroupFilter 三页覆盖 | §3 衍生 |
| G-06 | `profileGroupId` 单数禁用 | §3 |
| G-07 | `.profileId` → `.instanceId` 完成 | §14 |
| G-08 | `platform_queries` → `query_executions` 迁移 | §18 D-P2-2 |

---

## 按决策索引的变更矩阵

| DECISIONS § | 决策摘要 | 落地文件 | 落地位置 |
|---|---|---|---|
| §1 | 删 Spike T1 + `/dashboard` 301 | CLAUDE_CODE_SESSIONS.md、PRD.md | R-3.1 / R-3.2 / R-3.3、R-4.2 |
| §2 | Topic 更新 PATCH | PRD.md、CLAUDE_CODE_SESSIONS.md、openapi.yaml | R-4.1、R-3.4、N-2 |
| §3 | profileGroupIds plural | ADAPTER_CONTRACT.md、openapi.yaml、TEST_STRATEGY.md | R-2.1、N-2、R-8.1 G-06 |
| §4 | NO_ACCOUNT_AVAILABLE + PENDING | ADAPTER_CONTRACT.md | R-2.5 |
| §5 | 删账号 30 天窗口 | PRD.md、DATA_MODEL.md、openapi.yaml | R-4.3、N-1、N-2 |
| §6 | 锁 #605BFF | DESIGN_TOKENS.md | R-1.2 |
| §7 | Postgres 物化视图 | DATA_MODEL.md | N-1（mv_heatmap_mention_agg / mv_brand_rankings） |
| §8 | Citation 精确归因 | ADAPTER_CONTRACT.md、DATA_MODEL.md | R-2.8、N-1（kg_brand_domains） |
| §9 | Outbox Pattern | ADMIN_CLAUDE_CODE_SESSIONS.md、DATA_MODEL.md | R-7.2、N-1（brand_bootstrap_jobs） |
| §10 | ProfileGroup 持久化 | DATA_MODEL.md、openapi.yaml | N-1（profile_groups + browser_profiles）、N-2 |
| §11 | `npm run seed:admin` | ADMIN_CLAUDE_CODE_SESSIONS.md | R-7.1 |
| §12 | PARSER_FAIL 独立兜底 | ADMIN_PRD_B_PIPELINE.md、ADAPTER_CONTRACT.md、DATA_MODEL.md | R-5.1、R-2.6、N-1（parse_failures） |
| §13 | cost_events.budget_scope | ADMIN_PRD_C_KG.md、DATA_MODEL.md、openapi.yaml | R-6.1、N-1、N-2 |
| §14 | instanceId 重命名 | ADAPTER_CONTRACT.md、DATA_MODEL.md、openapi.yaml、TEST_STRATEGY.md | R-2.4、N-1、N-2、R-8.1 G-07 |
| §15 | Heatmap / Chart 边界 | DESIGN_TOKENS.md、TEST_STRATEGY.md | R-1.3、R-8.1 G-04 |
| §16 | Sentiment 规则+词典 | PRD.md、CLAUDE_CODE_SESSIONS.md、DATA_MODEL.md | R-4.4、R-3.10、N-1（ai_responses.sentiment_source） |
| §17 | Phase 2 延后清单 | 各文件占位（`// Phase 2` 注释） | — |
| §18 | 一揽子文档级 | 全部文档 | 见各 R-* |

---

## 设计细节澄清（audit 二次核验发现）

### A. `BrowserProfile.profileGroupId`（单数）是否违反 §3？——不违反

最终核验中 grep 发现 `openapi.yaml:1326` 的 `BrowserProfile.profileGroupId`（单数）仍存在。经设计复核，这是**正确的**：

| 语义 | 字段 | 多/单 | 原因 |
|---|---|---|---|
| "这个浏览器实例归属哪个 ProfileGroup" | `BrowserProfile.profileGroupId` | **单数**（FK） | 一个 browser_profiles 行只能归属一个 profile_groups 行 |
| "这条 Query 需要被哪些 ProfileGroup 执行" | `ExecutableQuery.profileGroupIds` | **复数** | 一条 Query 可匹配多个 group；`[]` 表示任意 |

`DECISIONS §3` 的复数化决策**仅针对 `ExecutableQuery`** 层（调度需求场景），不影响 `BrowserProfile` 层的 FK 引用。TEST_STRATEGY §G-06 的 grep 规则 `profileGroupId[^s]` 需要加豁免：`openapi.yaml` 的 `BrowserProfile` / `browser_profiles` 表 FK 合法。

**落地**：无代码改动；仅澄清语义边界。

### B. PRD §4.6.1-0 Daily Digest 特性残余——已彻底 SUPERSEDED

`PRD.md §4.6-IA-v2` 的"废除映射表"已显式标记 `§4.6.1-0 Dashboard Daily Digest Spike ⛔ SUPERSEDED`，`/dashboard` 路由整个废除。审核发现旧 §4.6.1-0 的详细 layout 规格仍存留于 PRD 较早章节（历史文档保留），但由于 §4.6-IA-v2 的 SUPERSEDES 声明优先级更高，Claude Code 在阅读 §4.6-IA-v2 后应自动忽略旧规格。

**补充编辑（本次新增）**：
1. PRD.md 路由表（原 §B 附近，Line 630）：`/dashboard` 行改为 `⛔ 永久 301 → /brand/overview` + 新增 `/brand/overview` 独立行承接原 Empty State E1；
2. PRD.md §E Empty State：`E1 Dashboard Empty` 改名为 `E1 Brand Overview Empty`，锚点从 `/dashboard` 迁到 `/brand/overview`。

---

## 已知遗留与 Phase 2 清单

> 以下事项在 MVP 不实现，文档中以 `// Phase 2` 或 `[Phase 2]` 注释占位，避免 Claude Code 误实现。

| 条目 | 决策来源 | 占位文件 |
|---|---|---|
| Alias fuzzy / Levenshtein 归因 | §8 / §17 E-P2-1 | ADAPTER_CONTRACT.md §8b |
| 周报 / 月报调度 | §17 E-P2-3 | openapi.yaml（`report_schedules` path 不开放）、DATA_MODEL.md（表仅 DDL） |
| CSV 异步作业 | §17 E-P2-4 | openapi.yaml（`export_jobs` path 不开放） |
| MCP 完整端点 | §17 E-P2-5 | openapi.yaml（仅 `/api/v1/mcp/tools/*` 骨架 + Bearer Token 认证桩） |
| LLM Sentiment | §16 / §17 | DATA_MODEL.md `sentiment_source = 'llm'` 预留 |
| Theme toggle | §6 | DESIGN_TOKENS.md 声明锁死 |
| Dashboard 主页 | §1 | router 级永久 301；无任何 React 组件 |

---

## Ready-to-Session 核验清单

签字前，Frank 请勾选以下 7 项——全部 ✅ 才代表"可以把 Session Prompt 贴进 Claude Code"。

- [ ] **1. DB 真相源**：`DATA_MODEL.md` 31 表齐全，FK / CHECK / ENUM 完整；开发者无需再去 PRD 反查 schema。
- [ ] **2. API 真相源**：`openapi.yaml` 31 paths + 32 schemas；可用 `openapi-validator` 通过；前后端都以此为 contract。
- [ ] **3. Session Prompt 一致性**：`CLAUDE_CODE_SESSIONS.md` 每个 Session 的 path / method / schema 均与 openapi.yaml 一致；grep 无 `/dashboard` / `profileGroupId`（单数）/ `platform_queries` 等旧名。
- [ ] **4. Adapter 层契约**：`ADAPTER_CONTRACT.md §2.3 / §8b / §6.1` 与 DATA_MODEL / openapi 对齐；retry / PARSER_FAIL / citation 三处规则明确。
- [ ] **5. Token 层**：`DESIGN_TOKENS.md` 13 新 token 全部在 `src/theme/tokens.css` 可 grep；heatmap / chart 边界通过 TEST_STRATEGY §G-04。
- [ ] **6. Admin 流**：`ADMIN_*` 文件链路完整——seed（§11）→ approve（§9 Outbox）→ budget（§13）→ parse failure 人工队列（§12）。
- [ ] **7. CI 断言**：`TEST_STRATEGY.md §G-01–§G-08` 已纳入 Harness；`scripts/ci-check.mjs` 第 13 条 `/dashboard` 301 断言可跑过。

---

**下一步**：Frank 签字后，即可按 `CLAUDE_CODE_SESSIONS.md` Session 0 → N 顺序把 Prompt 贴进 Claude Code。如 Session 中途发现新 drift，走 "追加 DECISIONS §N + 更新 REVISION_DIFF" 流程，不得直接改 PRD / openapi / DATA_MODEL。
