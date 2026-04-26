# GENPANO 决策记录（Decisions Log）

> **源起**：Frank 阅毕 `PRD_SESSION_REVIEW.md` 后回复"全部同意，需要选择的你自己决定"。
> 本文件把 Review 里所有"待 Frank 决策"的条目一次性定下来，作为后续批量修订 PRD / Session / Adapter / DATA_MODEL 的依据。
> **记录日期**：2026-04-20
> **有效范围**：v1 MVP；所有延到 Phase 2 的事项标注 `[Phase 2]`。

---

## 原则

1. **能简不繁**：MVP 能用最简单方案就不上复杂基础设施（例：Postgres 物化视图 vs ClickHouse）。
2. **语义优先于兼容**：PUT vs PATCH / 单数 vs 复数，只要语义更贴近业务就选它，不纠结"历史兼容"。
3. **数据完整性 > 速度**：涉及用户数据删除 / 账号池调度冲突时，宁可返回 PENDING / 30 天窗口，不做不可逆操作。
4. **决策可回滚**：DB schema、端点路径、token 命名全部保留扩展空间（enum 都留 `unknown` / `other` 兜底）。

---

## 决策清单

### 1. `/dashboard` 去留 (A-P0-2)
- **决策**：**删除 Session T1（Daily Digest / Action Center Spike）**。
- **理由**：PRD §4.6.1-0 已标记 SUPERSEDED；留着会让 MVP Session 变钝、同时和 `/brand/overview` 产生两条主入口。如果将来想做仪表板，另开 Phase 2 Spike，不阻塞 MVP。
- **落地动作**：
  - `CLAUDE_CODE_SESSIONS.md` 删除整段 Session T1；同时把 §2b.4 `navigate('/dashboard')` → `navigate('/brand/overview')`。
  - 在 `app/router.tsx`（将来 Claude Code 产出的）要求：`/dashboard` 永久返回 `301 /brand/overview`，并在 `scripts/ci-check.mjs` 加 `curl -I /dashboard | grep 301` 断言。

### 2. Topic 更新 HTTP 方法 (A-P1-1 / D-P0-2)
- **决策**：**全部统一为 `PATCH`**。
- **理由**：该操作是"标记为关键 / 忽略"的字段级 merge，PATCH 语义更贴切；且前端只发送被改动的字段可以省带宽。
- **落地动作**：
  - `PRD.md §4.5.1` 的 `PUT /api/v1/projects/:id/topics/:topicId` → `PATCH ...`。
  - `CLAUDE_CODE_SESSIONS.md` Session 2 Task 4 继续使用 PATCH（已经是）。
  - `openapi.yaml` 写 `patch` method。

### 3. ProfileGroup 命名（单数 vs 复数） (D-P0-1)
- **决策**：**全项目统一为 `profileGroupIds: string[]`**（复数、非空数组；`[]` 表示"任意"）。
- **理由**：PRD §4.2.3a 与 Session 2 已是 plural；ADAPTER_CONTRACT §2.1 的 singular `profileGroupId: string | null` 是孤例；且未来要支持"交叉 profile"时必然要数组。
- **落地动作**：
  - 改 `ADAPTER_CONTRACT.md` §2.1 / §3.3 / §3.4 / §6.2 / §10.1 全部单数引用。
  - `null` 语义改为 `[]`；Adapter 里判定 `if (query.profileGroupIds.length === 0) use any group`。
  - 重命名 `BrowserProfile.profileId` → `instanceId`，彻底消歧。

### 4. `null` profileGroup 时 scheduler 策略 (D-P1-1)
- **决策**：**(A) 返 `NO_ACCOUNT_AVAILABLE`、Query 置 `PENDING`，不重试**。
- **理由**：静默跨 segment 用号会污染指标（luxury_collector 的 account 跑 beauty_daily 的 Query 会让样本失真）；返 PENDING 把问题显式暴露给 Admin。
- **落地动作**：`ADAPTER_CONTRACT.md §3.3` 加绑定规则表；Session 1.2 retry logic 对应改写。

### 5. 账号删除方式 (D-P0-4)
- **决策**：**30 天延迟硬删 + 立即登出 + 立即吊销所有 session / API token**。
- **理由**：
  - 与 GDPR / CCPA 对齐（"30 天撤回窗口"是行业共识）；
  - 避免用户手滑，降低 Support 负担；
  - 期间账号入 `users.deletion_requested_at` 非空态，对外 API 一律 404。
- **落地动作**：
  - `openapi.yaml` 加 `DELETE /users/me` → 204；body `{ reason?: string }`。
  - `DATA_MODEL.md` 新增 `users.deletion_requested_at TIMESTAMPTZ`、`users.deletion_confirmed_at TIMESTAMPTZ`。
  - Cron 每日 02:00 扫描 `deletion_requested_at < now() - 30 days` 硬删（级联 projects / brands / responses 的外键用 `ON DELETE SET NULL` 归属到 `deleted_user`，或 CASCADE——具体表级由 DATA_MODEL 决定）。
  - 删除期间用户走 `/forgot-password` 返回"账号已申请删除，若想撤回请点此链接"。

### 6. Accent 主色锁定 (C-P1-2)
- **决策**：**锁 `#605BFF`（Stripe Purple）为 MVP 唯一生效主色**。
- **理由**：DASHBOARD_REDESIGN_PROPOSAL 的三个候选色属于未收敛提案，留换主题能力会让 Claude Code 多写 `ThemeProvider` + theme-switch 状态，不值得。
- **落地动作**：`DESIGN_TOKENS.md` 顶端加一段 `Production theme: #605BFF (locked for v1 MVP). Alternatives in DASHBOARD_REDESIGN_PROPOSAL are pending A/B in Phase 2 — do not implement toggle.`

### 7. Heatmap 聚合方案 (E-P0-3)
- **决策**：**Postgres `MATERIALIZED VIEW` + 每小时 `REFRESH CONCURRENTLY`**。
- **理由**：
  - 当前数据量（预计 MVP 上线后每日 ~10w–50w Response）远低于 ClickHouse 的性价比拐点；
  - 物化视图与现有 Postgres 事务层兼容，不引入新基础设施；
  - 若后续数据涨到 10M+/天再评估 ClickHouse / Citus。
- **落地动作**：`DATA_MODEL.md` 的 `heatmap_mention_agg` DDL + 定时刷新脚本（pg_cron 或应用层 scheduler）。

### 8. Citation 归因匹配规则 (E-P0-2)
- **决策**：**只做精确匹配 + alias 精确匹配 + eTLD+1 归一化；不做 Levenshtein fuzzy**。
- **理由**：fuzzy 在 MVP 阶段信号噪声比太差（品牌简称与品类词、竞品子品牌撞衫），会让 `citation_share` KPI 被虚假归因污染。
- **落地动作**：
  - `kg_brand_domains` 表作为 alias 映射源；
  - `ai_response_citations.confidence` 精确归因 = 1.0、alias = 0.9、未命中 = `brand_id NULL + confidence 0`；
  - Phase 2 再引入带 labeled data 的 fuzzy / LLM 匹配。

### 9. Brand 提交 → 首日采集 触发机制 (E-P1-5)
- **决策**：**采用"Outbox Pattern"** —— Admin approve 品牌时写 `brand_bootstrap_jobs` 表一条，Planner 的 5 分钟轮询 worker 认领并执行首日采集。
- **理由**：避免直接 HTTP 同步调用导致 Admin 接口超时；Outbox 表天然给每个 approve 做 idempotency + 可追踪。
- **落地动作**：`DATA_MODEL.md` 新增 `brand_bootstrap_jobs`；Admin Session A3 增 enqueue 调用。

### 10. Profile Group 持久化 vs 硬编码 (E-P1-4)
- **决策**：**持久化到 DB**（建 `profile_groups` + `browser_profiles` 两张表）。
- **理由**：Admin 将来必然要调权，硬编码迁移成本高；两张表各自只有 5–7 列，DDL 成本低。
- **落地动作**：`DATA_MODEL.md` 建表 + Session 2 seed 6 条 baseline group + `GET /admin/profile-groups` 端点。

### 11. 测试数据 Seeding (B-P1-2)
- **决策**：**用 `PRD_TEST_DATA_V1.md` 的 fixtures + `npm run seed:admin` 单命令注入 SQLite dev DB**。
- **理由**：fixtures 已经按规模写好（128K Attempts / 1560 Topics）；相比 HAR replay 更确定、相比 seed migration 更易刷新。
- **落地动作**：Session A2 Prompt 第一段加明示。

### 12. `PARSER_FAIL` 归属 (B-P1-1)
- **决策**：**不入 Tracker 重试池，由 Analyzer 的 `parse_status` 单独兜底**。
- **理由**：PARSER_FAIL 是结构化解析失败（engine 换了 DOM），重新执行 adapter 不解决；要的是 HAR snapshot + 人工更新 selector。
- **落地动作**：`ADMIN_PRD_B_PIPELINE.md` 重试规则表里把 PARSER_FAIL 显式标注"Analyzer only, 入 `parse_failures` 审核队列"。

### 13. KG LLM 预算与 Pipeline 预算关系 (B-P1-3)
- **决策**：**两个预算各自硬约束，上报到同一张 `cost_events` 表、`budget_scope` 字段区分（`pipeline` vs `kg`）**。
- **落地动作**：Admin A4 Prompt 补说明；`DATA_MODEL.md` `cost_events` 表含 `budget_scope` 枚举列。

### 14. `BrowserProfile.profileId` 重命名 (D-P1-2)
- **决策**：**重命名为 `instanceId`**。
- **理由**：和 `profileGroupIds` 彻底拉开概念距离，避免 analytics join 搞错。
- **落地动作**：`ADAPTER_CONTRACT.md §3.2` 字段名 + 所有引用。

### 15. Heatmap token 与 Chart token 边界 (C-P1-1)
- **决策**：**`BrandTopicHeatmap` 只用 `--color-heatmap-*`；所有其他图表只用 `--color-chart-*`**。
- **落地动作**：`DESIGN_TOKENS.md` 加边界声明 + Harness C9 grep 规则（heatmap 组件里不得出现 `var(--color-chart-`，反之亦然）。

### 16. Sentiment 计算 (E-P2-2) — 提前到 MVP
- **决策**：**MVP 就启用"规则 + 词典"的简化 sentiment，落库 `ai_responses.sentiment`；LLM 增强延到 Phase 2**。
- **理由**：Dashboard / Heatmap / KPI 都依赖 sentiment；延后意味着 MVP 展示 Mock 数据——违反"PRD=Session=frontend"的核心要求。
- **落地动作**：Session 1 Prompt 改为"基于 SnowNLP 中文 + VADER 英文，字段 `sentiment_source = 'rule'`"；不再标 TODO。

### 17. 其他 Phase 2 延后事项
以下一律延至 Phase 2，Session Prompt 里用 `// Phase 2` 注释占位：
- **E-P2-1** Alias fuzzy 匹配（见决策 8）
- **E-P2-3** 周报 / 月报调度（MVP 仅"立即导出 PDF"按钮）
- **E-P2-4** CSV 异步作业（MVP 限 1000 行同步下载，超出给提示"使用 API"）
- **E-P2-5** MCP 完整端点（MVP 只留 `openapi.yaml` 骨架 + Bearer Token 认证桩）
- **D-P2-4** `extractedBy` 新增 `api_structured / hover_card / unknown` 枚举值（现在先把这 3 个加到 enum 并标注"目前适配器不一定都用得上"）

### 18. 其他文档级别改动（一揽子同意项，无歧义）
- Spike 术语统一为 `Session Tn`（A-P2-1）。
- `/dashboard 301` 加 CI 断言（A-P2-2）。
- Drawer 组件 token 强引（A-P2-3）。
- Session 4a Auth 汇总表（A-P2-4）。
- 生成管线侧栏标注"（单页，三层 Tab）"（B-P2-1）。
- Admin Session Prompt 末尾加"Tokens must be from `src/theme/tokens.ts`"（B-P2-2）。
- API path 统一 `:id` 风格，grep 禁 `{id}` （D-P2-1）。
- DB 表 `platform_queries` → `query_executions`（D-P2-2）。
- `intent` 全程字符串传输 + VARCHAR(50) 存储（D-P2-3）。
- `extractedBy` 扩展 + `unknown` 兜底（D-P2-4）。
- Landing inline rgba → `--color-accent-alpha-05 / -10`、`--color-accent-2-alpha-06`（C-P1-3）。
- 缺 `--color-success-hover / --color-danger-hover` → 按 base +10% Shade 生成（C-P2）。
- `ExecutableQuery` required/optional 字段表（D-P1-5）。
- `AIResponse.profile` 走 `Object.freeze` deep-copy，adapter 禁 mutate（D-P1-3）。
- 重试次数文案改"最多 3 次 attempt（1 原始 + 2 重试）"（D-P1-4）。
- `ProfileGroupResponse` schema 加 `ADAPTER_CONTRACT.md §2.3`（D-P1-6）。
- `brand_rankings` 物化视图（E-P1-2）。
- `platform_topics` 完整 DDL（E-P1-3）。

---

## 决策后的最终"Ready-to-Session Gate"

决策全部关闭后，15 条 P0 + 21 条 P1 将体现在下列文档变更里：

| 产出物 | 类型 | 目标位置 |
|---|---|---|
| `DATA_MODEL.md` | 新建 | `docs/DATA_MODEL.md` |
| `openapi.yaml` | 新建 | `docs/openapi.yaml` |
| `REVISION_DIFF.md` | 新建 | `docs/REVISION_DIFF.md` |
| `DESIGN_TOKENS.md` | 修订 | 5 token 新增 + drawer 尺寸 + alpha 变种 + heatmap 边界声明 |
| `ADAPTER_CONTRACT.md` | 修订 | profileGroupIds 全线改 plural + `instanceId` 重命名 + §2.3 API Shapes + §6 重试文案 + §8 citation 匹配 |
| `CLAUDE_CODE_SESSIONS.md` | 修订 | 删 Spike T1 + `/brand/overview` 路由 + Auth 端点汇总 + ProfileGroupFilter 三页断言 + token 强引 |
| `PRD.md` | 修订 | PATCH 对齐 + 删除账号 30 天说明 |
| `ADMIN_PRD_B_PIPELINE.md` | 修订 | PARSER_FAIL 标注 + "单页三 Tab" |
| `ADMIN_PRD_C_KG.md` | 修订 | KG 预算上报 `cost_events.budget_scope` |
| `ADMIN_CLAUDE_CODE_SESSIONS.md` | 修订 | Seeding 命令 + token 引用末行 + bootstrap_jobs outbox |
| `TEST_STRATEGY.md` | 修订 | 新增 grep 规则（token 未定义、path `{id}`、dashboard 301、heatmap/chart 越界）|

---

**执行顺序**：本轮 Claude 按 §7 的 E→D→C→A 顺序批量改；最终产出 `REVISION_DIFF.md` 列每处 before/after，Frank 做最终复核。
