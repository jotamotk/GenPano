# Session 3' · 分析引擎 + 用户态 API + MCP Server (Python 重写)

> **本文件是给 Claude Code 的 Session 3' 实施 Prompt**, 遵循 CLAUDE.md 决策 #25 的 12 条 Prompt 编写公约。
>
> **依赖**: Session 2' (Planner 三层) + Session 2.1' (LLM Refinement) + Session 1.2' (Adapter live) 全部 PASS, main HEAD 含 `query_executions` + `ai_responses` 表 + `app/platform/planner/topic_pool.py` 完整 LLM threading + Camoufox launch + 3 引擎 Adapter live execute()
>
> **里程碑**: M3 Milestone 末段 (M3 = Pipeline 端到端 + 用户态数据出口完成), 是 MVP 数据闭环的关键节点 — 本 Session 之前用户看不到真实数据, 之后用户在 preview frontend 上能从 ai_responses 看到聚合后的 brand/industry 视图。
>
> **分支**: `session-3prime` (从 main 当前 HEAD fork, 决策 #31)

---

## §0 · 前置 Grep 契约 (Pre-Flight Grep Contract, 决策 #25 规则 2)

**实施第一批动作 (写代码之前, 必须依次跑这 8 条 grep, 输出与 §1 真相源索引一致才继续; 不一致则 STOP, 走规则 11 freshness check)**:

```bash
# F1 · 决策 #29-#33 是否仍是 Python pivot 真相源 (Session 2.1' 后是否新增决策)
grep -nE "^(29|30|31|32|33|34|35|36|37|38|39|40)\." CLAUDE.md | head -30

# F2 · Decision #9 (Auth-Required) + Decision #19 (Citation 6 行动面) + Decision #21 Session A5 (Citation Tier CRUD)
grep -nE "(Auth-Required|MCP API.*Bearer|Citation.*Tier|basePriceByTier|citation_share|citation_source_loss|attribution_mismatch)" CLAUDE.md | head -25

# F3 · Decision #26.C1 (rewrite_meta JSONB) + Harness G3 (query_executions 列名黑名单) + Decision #27 (Session 2.1 LLM Refinement)
grep -nE "(rewrite_meta|persona_snapshot|attempts.*JSONB|G3.*query_execution|browser_profile)" CLAUDE.md | head -20

# F4 · SESSION_PROGRESS Session 2' + 2.1' + 1.2' 是否都已 PASS (本 Session 依赖 3 层都就位)
grep -nE "(Session (2|2\.1|1\.2)'.*PASS|Session (2|2\.1|1\.2)'.*GREEN)" docs/SESSION_PROGRESS.md | head -10

# F5 · REPLAN §4 Session 3' 范围 (本 Prompt §2 来源)
sed -n '264,282p' docs/REPLAN_2026_04_26.md

# F6 · PRD §4.2 (分析层) + §4.5 (用户态 API) + §4.5.2 (MCP) + §4.9.4 (Cost monitoring)
grep -nE "^####? §4\.(2|5|9\.4)" docs/PRD.md | head -25

# F7 · 当前 backend 已有结构 (Session 1.2'/2'/2.1' 后)
ls app/platform/  # planner/ + db/ + llm/ + discovery/ + knowledge_graph/
ls app/  # 期望看到 admin/ + accounts/ + engines/ + parsers/ + platform/ + scheduler/ (Session 1.2' 后)
ls app/api/ 2>/dev/null  # 不存在则 Session 3' 创建; 存在 (从 4a' 来) 则 read-only refer

# F8 · MCP 协议 / FastAPI sub-app 是否已加依赖 (期望 pyproject.toml 已含 mcp; 若无则 Step 0 加)
grep -nE "^(mcp|fastapi-mcp|jsonrpc)" pyproject.toml || echo "[INFO] mcp not in pyproject — Step 0 add"
grep -nE "^celery" pyproject.toml | head -3  # 期望 Session 1.2' 已加
```

**Pre-flight 失败的 per-grep STOP 映射 (决策 #25 规则 12 + 规则 11)**:

| Grep | 失败条件 | STOP 类型 | 处置 |
|---|---|---|---|
| F1 | CLAUDE.md 缺决策 #29-#33 (Python pivot) 或新增 #34+ 与本 Prompt §1 索引冲突 | **Type B** | 列出新决策号 + 影响面, 等 Frank 同步真相源 |
| F2 | 决策 #9 / #19 / #21 任一关键字 (Auth-Required / citation_share / Citation Tier) 在 CLAUDE.md 中消失 | **Type B** | 不写代码; 检查是否决策被废弃, 走规则 4 双向同步 |
| F3 | `rewrite_meta` / `attempts JSONB` / G3 黑名单关键字漂移 | **Type B** | 决策 #26.C1 是硬约束, 任何偏离立即 STOP, 不得自行加 query_executions 顶层列 |
| F4 | SESSION_PROGRESS Session 2' / 2.1' / 1.2' 任一未 PASS | **Type A** (依赖未就绪) | 暂停实施, 等前置 Session 宣绿; 不做 best-effort |
| F5 | REPLAN §4 Session 3' 范围与 §2 描述不符 | **Type B** | 以 REPLAN §4 为准, 改 §2 描述对齐 |
| F6 | PRD §4.2 / §4.5 / §4.5.2 / §4.9.4 任一段号在 PRD 中找不到 (重排或删除) | **Type B** | 段号漂移 → 走规则 6 (锚定到最小单元); 等 Frank 决定改 PRD 还是改 Prompt |
| F7 | `app/platform/` 缺 planner/db/llm 任一子目录 (Session 1.5'+2'+2.1' 应已落) | **Type A** | 前置 Session 未交付完整, 暂停 |
| F8 | `pyproject.toml` 缺 `mcp` (或选 `fastapi-mcp` / 自实现 dispatcher) | 不 STOP, Step 0 内 `uv add mcp` 补齐 (规则 12 Type A1 例外) | Celery 缺失 → STOP Type A (1.2' 应已落) |

**任一 F1-F7 STOP → 写 alignment note 给 Frank, 不进 §5 实施步骤; F8 走 Step 0 补依赖 (不 STOP)。**

---

## §1 · 真相源索引 (Source-of-Truth Index, 决策 #25 规则 5)

> **本 Session 引用 / 修改的真相源全清单**。`[引用]` = 只读, `[修改]` = 本 Session 改写。任一引用项的段号在 §0 grep 中漂移即 STOP。

### 引用 (read-only, 不改)

| 真相源 | 段号 | 引用目的 |
|---|---|---|
| `CLAUDE.md` | 决策 #25 (12 条 Prompt 公约) | 本 Prompt 自身的元规范 |
| `CLAUDE.md` | 决策 #9 (Auth-Required) | MCP API Day 1 必须 Bearer token, 用户态 API 必须 RequireAuth |
| `CLAUDE.md` | 决策 #15 (提及率 non-brand 口径) | 分析层聚合时 `mention_rate` 默认仅统计 `topic.dimension='品类'` 的 query |
| `CLAUDE.md` | 决策 #16 (CSV 导出 Tier 1) | `mention_rate_pct` + `mention_rate_all_pct` 双列契约 |
| `CLAUDE.md` | 决策 #19 (Citation 6 行动面 §4.2.6 + §4.2.7) | 5 级 Tier / 3 级归因 / `citation_share` brandsAttributed-based / PANO A 公式 / `citation_source_loss` T-14d diff |
| `CLAUDE.md` | 决策 #21 Session A5 (Citation Tier CRUD + MCP Token) | 本 Session 落地 Citation Tier 表 + MCP Token 表 (master 是 A5, Python pivot 合并到 3') |
| `CLAUDE.md` | 决策 #21.D PRD §4.9.4 (Cost monitoring) | 4 源 Cost 告警 + `cost_paused` flag + Planner 停止入队 |
| `CLAUDE.md` | 决策 #26.C1 (rewrite_meta + persona 进 attempts JSONB) | 本 Session **不得**给 query_executions 加任何 persona/rewrite 顶层列 |
| `CLAUDE.md` | 决策 #27 (Session 2.1 LLM Refinement) | 分析层读 `query_executions.attempts[].rewrite_meta + browser_profile` 时复用 Session 2.1 schema |
| `CLAUDE.md` | 决策 #29 (Python pivot) | FastAPI / SQLAlchemy / Celery / Pydantic 栈 |
| `CLAUDE.md` | 决策 #30 (preview env + Frank Layer 3 verification) | Phase Gate Layer 3 Frank 在 preview 上验证 |
| `CLAUDE.md` | 决策 #31 (branch-per-session) | `session-3prime` 从 main fork |
| `docs/PRD.md` | §4.2 (分析层 5 KPI) | 提及率 / SoV / 情感 / 引用份额 / 行业排名 计算口径 |
| `docs/PRD.md` | §4.2.4.A (Sentiment 0.5 tiebreak) | `[0,0.45] negative / (0.45,0.55) neutral / [0.55,1.0] positive`; 单一入口 `classify_sentiment()` |
| `docs/PRD.md` | §4.2.5 (Brand Topics) | Topic 第 1 层补充 (Brand Mode `/brand/topics`) |
| `docs/PRD.md` | §4.2.6.A-H (Citation 真相源) | `AiCitation` + `CitationDomainAuthority` + 5 级 Tier 表 + 3 级归因 + `citation_share` + PANO A + `citation_source_loss` 全算法 |
| `docs/PRD.md` | §4.2.7.A-F (Citation 6 行动面) | 归因诊断 / 内容策略 / 外联 PR / 竞品解构 / Simulator / 3 MCP 工具 + 2 CSV 导出 |
| `docs/PRD.md` | §4.5 (用户态 API 总览) | API 路由表 + auth middleware + RBAC |
| `docs/PRD.md` | §4.5.2 (MCP Server 协议) | 3 工具 (`genpano_get_citations` / `list_pr_targets` / `simulate_authority_boost`) + Bearer token + JSON-RPC 2.0 |
| `docs/PRD.md` | §4.6.4 (CSV 导出 Tier 1) | 10 个 exportType 字段字典, MVP 8 个 + Citation 行动面追加 #9/#10 |
| `docs/PRD.md` | §4.8.1 / §4.8.5 (诊断类型) | `citation_attribution_mismatch` 与 `citation_source_loss` **互斥触发** (Harness E3) |
| `docs/PRD.md` | §4.9.4 (Cost monitoring) | 4 源告警 + `cost_paused` 标志 + Planner 停止入队 (不 kill Worker) |
| `docs/PRD.md` | §4.10.4a (i18n 覆盖矩阵) | API response 字段双语化, 品牌名按 User.locale 渲染 |
| `docs/DATA_MODEL.md` | §1.6 (`ai_citations` 表) | citation 持久化 schema |
| `docs/DATA_MODEL.md` | §1.7 (`citation_domain_authorities` 表) | 5 级 Tier 表 schema |
| `docs/DATA_MODEL.md` | §1.8 (`mcp_api_tokens` 表) | MCP Token 表 + Redis pub-sub 吊销黑名单 (60s) |
| `docs/DATA_MODEL.md` | §2.5 (`ai_responses` 列扩展, 决策 #21.D) | `cost_usd` / `cost_cny` / `token_count` / `latency_breakdown` / `trigger_source` 5 列 + 索引 `idx_responses_trigger_source_date` |
| `docs/REPLAN_2026_04_26.md` | §4 (Session 3') | 本 Session 范围定义 (lines 264-282) |
| `docs/REPLAN_2026_04_26.md` | §5 (M3 Milestone) | 本 Session 是 M3 末段 |
| `docs/REPLAN_2026_04_26.md` | §6.5 (Harness 规则组) | Harness Group I 命名预留 (本 Session 新增) |
| `docs/REPLAN_2026_04_26.md` | §7 (frontend 集成原则) | preview frontend 切到 FastAPI 真实 API 由 Session 4b' 收尾, 本 Session 只交付后端契约 |
| `docs/SESSION_PROGRESS.md` | Session 2' / 2.1' / 1.2' 行 | 必须全 GREEN 才能开 3' (规则 12 Type A4) |
| `docs/SESSION_2_PRIME_PROMPT.md` | §1.1 / §5 | Session 2' Pydantic 模型字段名 (本 Session 读 + 聚合) |
| `docs/SESSION_2_1_PRIME_PROMPT.md` | §1 / §5 Step 5 | Session 2.1' rewrite_meta 字段名 (本 Session 读) |
| `docs/SESSION_1_2_PRIME_PROMPT.md` | §1 / §5 | Session 1.2' Camoufox + Adapter execute() 真实写入 ai_responses 的契约 |
| `app/platform/planner/topic_pool.py` | `generate_platform_plan()` 返回 envelope | 本 Session 不改, 只 read for analysis aggregation |
| `app/platform/db/ports.py` | `KgRepositories` 接口 | 本 Session 扩 `AiCitationRepo` / `CitationDomainAuthorityRepo` / `McpApiTokenRepo` 等子接口 |
| `app/parsers/citation_extractor.py` | Session 1.2' 已实现的 3 级归因 | 分析 worker 调用此函数, 不重写 |
| `app/parsers/sentiment_classifier.py` | Session 1.2' 已实现的 `classify_sentiment` | 分析 worker 调用此函数, 不重写 |
| `app/parsers/brand_matcher.py` | Session 1.2' 已实现的 brand 匹配 | 分析 worker 调用此函数, 不重写 |

### 前置依赖 (Prerequisites, 决策 #25 规则 12 Type A4)

> 本 Session 是 M3 末段, 依赖 4 个上游 Session 全部宣绿。任何一项未 GREEN 即触发 STOP Type A (依赖未就绪)。

| Session | GREEN 条件 | 本 Session 依赖点 |
| ------- | --------- | ---------------- |
| **Session 2'** | Pipeline skeleton + Pydantic 模型 + `query_executions` JSONB attempts 字段; G1-G4 Harness 全绿 | aggregator 读 `topic.dimension` 做 mention_rate non-brand 过滤 (决策 #15); 字段名稳定不漂移 |
| **Session 2.1'** | LLM Refinement 三层 envelope + `attempts[].rewrite_meta` JSONB schema; H1-H3 Harness 全绿; `platform_topics.audit_status` / `platform_prompts.naturalize_confidence` 列就位 | 分析 worker 读 `attempts[].rewrite_meta + browser_profile` 时复用 Session 2.1' schema; rewrite_meta 字段名 (camelCase JSONB) 稳定 |
| **Session 1.2'** | Adapter execute() 真实写入 `ai_responses` (含 6 枚举 response_source labeling, 决策 #28.G); F4-1/F4-2/F4-3 Harness 全绿 | response_collector worker 复用 executeWithRetry; ai_responses.response_source 字段已存在; 6 枚举不可改 |
| **Session A1'** | Admin Citation Tier CRUD UI 落地, 5 级 Tier 表 (`citation_domain_authorities`) + `basePriceByTier` 默认值 + Admin 写权限就位 | 本 Session MCP 工具 `simulate_authority_boost` + Citation Share / PANO A 公式读 Tier 表; Tier 权重必须从 DB 读 (Harness I5 禁硬编码) |

**前置依赖验证命令** (Step 0 必跑, 失败即 STOP Type A):
```bash
# 验证 Session 2' / 2.1' / 1.2' / A1' 全 GREEN
grep -E "^Session (2'|2\.1'|1\.2'|A1')\s+\|\s+GREEN" docs/SESSION_PROGRESS.md
# 期望输出: 4 行 GREEN 标记
```

**Session A5 折叠说明**: master 把 Citation Tier CRUD + MCP Token 签发拆到 Session A5, Python pivot 已合并到本 Session 3' (理由见 §1 真相源版本警告 #5)。本 Session 同时承担 Admin Citation Tier CRUD API + MCP Token 签发 API + 用户态 MCP 消费三块。

### 修改 (本 Session 写入)

| 文件 / 表 | 内容 | 锚点 |
|---|---|---|
| `app/workers/response_collector.py` | **新建** Celery worker · 消费 `query_executions` queue, 调 Adapter execute(), 写 `ai_responses` (含 5 列扩展 + response_source labeling 决策 #28.G) | 决策 #21.D + 决策 #28.G |
| `app/workers/analysis.py` | **新建** Celery worker · 消费 `ai_responses` 新增事件, 调 `brand_matcher` + `sentiment_classifier` + `citation_extractor`, 写 `brand_mentions` / `ai_citations` / 聚合表 | PRD §4.2 |
| `app/analysis/aggregator.py` | **新建** 聚合层: 5 KPI 计算 (mention_rate / sov / sentiment / citation_share / industry_ranking), `mention_rate` 仅 dimension='品类' (决策 #15) | PRD §4.2 + 决策 #15 |
| `app/analysis/citation_share.py` | **新建** Citation Share / PANO A / `citation_source_loss` T-14d diff 算法 (PRD §4.2.6.G/H) | 决策 #19 |
| `app/analysis/diagnostics.py` | **新建** 诊断生成器 · `citation_source_loss` 与 `citation_attribution_mismatch` **互斥触发** (Harness I3) | PRD §4.8.1/§4.8.5 |
| `app/api/v1/brands.py` | **新建** 用户态 router: 6 sub-routes (`/brands/{id}` / `/topics` / `/citations` / `/sentiment` / `/competitors` / `/products`) | PRD §4.5 + 决策 #9 (auth) |
| `app/api/v1/industries.py` | **新建** 4 sub-routes (`/industries/{slug}` + `/ranking` + `/topics` + `/knowledge-graph`) | PRD §4.5 |
| `app/api/v1/csv_export.py` | **新建** 8 个 MVP exportType + Citation #9 `pr_targets` (#10 `content_gap` Phase 2 deferred) | PRD §4.6.4 + 决策 #16 |
| `app/api/v1/auth_dependency.py` | **新建** `RequireAuth` FastAPI Depends · 验证 user JWT (Session 4a' 颁发) | 决策 #9 |
| `app/mcp/server.py` | **新建** MCP Server FastAPI sub-app · JSON-RPC 2.0 over HTTP, 3 工具 + Bearer token | PRD §4.5.2 |
| `app/mcp/tools/get_citations.py` | **新建** `genpano_get_citations` 工具 | PRD §4.2.7.F |
| `app/mcp/tools/list_pr_targets.py` | **新建** `list_pr_targets` 工具 | PRD §4.2.7.C/F |
| `app/mcp/tools/simulate_authority_boost.py` | **新建** `simulate_authority_boost` 工具 (Phase 2 简化版: 返回 Tier delta 模拟) | PRD §4.2.7.E/F |
| `app/mcp/auth.py` | **新建** Bearer token 验证 + Redis pub-sub 60s 吊销黑名单 | 决策 #21 Session A5 |
| `app/admin/api/v1/citation_tiers/route.py` | **新建** Admin Citation Tier CRUD (5 级 Tier 权重 + `basePriceByTier`) | 决策 #19 + 决策 #21 Session A5 |
| `app/admin/api/v1/mcp_tokens/route.py` | **新建** Admin MCP Token 签发 + 吊销 + 列表 | 决策 #21 Session A5 |
| `app/cost/monitor.py` | **新建** Cost 监控 4 源 + `cost_paused` flag + Planner 停止入队信号 (Redis pub-sub) | PRD §4.9.4 |
| `alembic/versions/<hash>_session_3prime_analysis_layer.py` | **新建** migration · `ai_citations` + `citation_domain_authorities` + `mcp_api_tokens` + `brand_mentions` + 4 个聚合物化表 + `ai_responses` 扩 5 列 (决策 #21.D) + index | DATA_MODEL §1.6/§1.7/§1.8/§2.5 |
| `app/db/models/ai_citation.py` | **新建** SQLAlchemy 模型 | DATA_MODEL §1.6 |
| `app/db/models/citation_domain_authority.py` | **新建** SQLAlchemy 模型 + 5 级 Tier 数据库 seed | DATA_MODEL §1.7 |
| `app/db/models/mcp_api_token.py` | **新建** SQLAlchemy 模型 | DATA_MODEL §1.8 |
| `app/db/models/brand_mention.py` | **新建** SQLAlchemy 模型 | PRD §4.2 |
| `tests/unit/analysis/*.py` | **新建** ≥8 文件 (aggregator / citation_share / diagnostics / brand_mention_writer / 等), pytest ≥80% coverage | TEST_STRATEGY v1.1 §11 |
| `tests/unit/api/v1/*.py` | **新建** ≥10 文件 (brands_routes / industries_routes / csv_export / auth_dependency / mcp_*), pytest ≥80% coverage | TEST_STRATEGY v1.1 §11 |
| `tests/unit/workers/*.py` | **新建** ≥4 文件 (response_collector / analysis / cost_monitor / mcp_token_revoker), 用 `celery_app.conf.task_always_eager=True` | TEST_STRATEGY v1.1 §11 |
| `tests/integration/api_v1_smoke.py` | **新建** httpx + 真实 Postgres + 真实 Redis 端到端 (Auth → /brands/{id} → JSON 校验 → CSV 导出 → MCP curl) | TEST_STRATEGY v1.1 §11 |
| `tests/fixtures/seed_loreal_data.py` | **新建** 注入 1 个 industry + 5 个 brand + 50 条 ai_responses + 200 条 brand_mentions + 80 条 ai_citations 的 fixture, 让 `/brand/overview?brandId=loreal` 真实返回数据 | Phase Gate Layer 3 |
| `scripts/seed_citation_tiers.py` | **新建** 5 级 Tier seed + Admin reseed 命令 | 决策 #19 |
| `scripts/dump_analysis_samples.py` | **新建** 端到端 dump 脚本 (类似 Session 2.1' dump_planner_samples), 输出 `/brand/loreal` 视图 JSON 供 Frank 视觉审查 | Layer 3 |
| `scripts/ci_check.py` Group I | **新建** 5 条 Harness (I1 mention_rate non-brand 唯一调用入口 / I2 citation_share brandsAttributed-based / I3 attribution_mismatch ⊥ source_loss / I4 MCP 端点 0 匿名 / I5 Tier 权重禁硬编码) + 5 fixtures | 决策 #19 + 决策 #21.E + 决策 #9 |
| `scripts/ci_harness_selftest.py` | EXPECTED_POSITIVES 22 → 27 (+5 新 fixture) | 验证 Harness Group I 真能拦 |
| `scripts/verify_session_3prime.sh` | **新建** Layer 1 verify shell, ≥10 检查 | 决策 #25 规则 7 |
| `docs/SESSION_PROGRESS.md` | 追加 Session 3' GREEN 行 (Phase Gate 通过后) | 决策 #25 规则 4 |
| `CLAUDE.md` | **新增决策 #40** · Session 3' 交付总结 + 偏差登记 (C 段) | 决策 #25 规则 3 |
| `docs/CLAUDE_CODE_SESSIONS_PYTHON.md` | 标记 Session 3' DONE | 决策 #25 规则 4 |

### 真相源版本警告 (Frank 直读 + Claude Code 必须 honor)

1. **Auth-Required (决策 #9)**: 所有用户态 `/api/v1/**` 路由必须挂 `Depends(RequireAuth)`; MCP `/mcp/**` 必须挂 `Depends(RequireMcpToken)` (Bearer + Redis 黑名单查询); Harness I4 grep 拦 0 匿名路径
2. **决策 #15 mention_rate non-brand 口径**: aggregator 的 `mention_rate` 默认 SQL `WHERE topic.dimension = '品类'`, **不**新增字段; CSV 导出双列 (`mention_rate_pct` non-brand + `mention_rate_all_pct` 全量); Harness I1 守护单一入口
3. **决策 #19 Citation 6 行动面**: 5 级 Tier 权重 (1.0/0.7/0.4/0.15/0) **禁硬编码**, 必须从 `citation_domain_authorities` 表 / Admin 参数服务读 (Harness I5); URL 归一化必走 `tldextract` (Python 替 `tldts`); `citation_share` = brandsAttributed-based (不是 mentioned-based, Harness I2); `citation_source_loss` 与 `attribution_mismatch` **互斥** (Harness I3)
4. **决策 #21.D PRD §4.9.4 Cost 监控**: 触发后写 `admin_runtime_flags.cost_paused = true`, Planner 停止入队 (Redis pub-sub 通知 `app/platform/scheduler/`), **不** kill 已运行 Worker; preview env 注入 fake threshold 让 Frank 看到 alert (Layer 3 Frank 验)
5. **决策 #21 Session A5 (合并到本 3')**: master 把 Citation Tier CRUD + MCP Token 签发拆到 Session A5, Python pivot 合并到本 Session — 因为 Python 后端的 Tier seed + Token 签发是 MCP server / Admin API 的依赖, 拆离反而增加 cross-session 协调负担
6. **决策 #26.C1 + Harness G3**: 本 Session **不得**给 `query_executions` 加任何 persona/rewrite_meta/agent_profile 顶层列; rewrite_meta 一律读 `attempts[].rewrite_meta` JSONB; Layer 1 verify L1.6 复用 Session 2.1' 的 8-列黑名单 psql 检查
7. **决策 #28.G response_source labeling**: Session 1.2' 已落地 6 枚举 (`web_ui` / `api_fallback` / `mock_proxy` / `cached_replay` / `admin_har_replay` / `harness_fixture`); 本 Session 的 `response_collector` worker 写 `ai_responses` 必须显式 label, **不**用 schema default; Harness F4 已守护 (本 Session 不 regress)
8. **PRD §4.2.4.A Sentiment 0.5 tiebreak 单一入口**: aggregator 调用 `app/parsers/sentiment_classifier.classify_sentiment()` (Session 1.2' 已实现), **不**自己实现; `(sentiment|score) > 0.5` 字面量 grep 拦截已在 Session 1.2' Harness 落地, 本 Session 不 regress
9. **PRD §4.5.2 MCP 协议 = JSON-RPC 2.0 over HTTP (POST)**: 单一 endpoint `POST /mcp/v1/jsonrpc` 接所有方法; 不走 Stdio MCP transport (Anthropic MCP 协议两种 transport, JSON-RPC over HTTP 是 Web 友好版); Bearer token via `Authorization` header
10. **PRD §4.6.4 CSV 导出 Tier 1**: 8 个 MVP exportType + Citation 行动面追加 #9 `pr_targets` (本 Session 落); #10 `content_gap` Phase 2 deferred (本 Session **不**做); UTF-8 BOM + `csv` 库禁手写 + 10k 行上限 + 5/min 限流; **列删除永远 breaking** (CHANGELOG 必须记)

---

## §2 · MVP Scope-Cut Declaration (决策 #25 规则 10)

### ✅ 本 Session 做 (Y1-Y17)

- **Y1** · `app/db/models/` 新增 5 个 SQLAlchemy 模型: `AiCitation` / `CitationDomainAuthority` / `McpApiToken` / `BrandMention` + 1 个聚合物化表模型 (锚 DATA_MODEL §1.6/§1.7/§1.8 + PRD §4.2)
- **Y2** · `app/db/models/ai_response.py` 扩 5 列 (`cost_usd` / `cost_cny` / `token_count` / `latency_breakdown` / `trigger_source` CHECK IN 5 值) + index `idx_responses_trigger_source_date` (锚 DATA_MODEL §2.5 + 决策 #21.D)
- **Y3** · `alembic/versions/<hash>_session_3prime_analysis_layer.py` 单一 migration 包含 Y1+Y2 + Citation Tier seed (5 级 Tier 数据 + `basePriceByTier` 默认值) + 9 个新 index
- **Y4** · `app/workers/response_collector.py` Celery worker · 消费 `query_executions` queue (Session 1.2' 落), 调 Adapter execute() (Session 1.2' 落), 写 `ai_responses` 含全部 5 列 + 显式 `response_source` (决策 #28.G); 失败重试逻辑复用 Session 1.2' `executeWithRetry`; 单测 ≥8 例 (含 NO_ACCOUNT_AVAILABLE 留 pending 不当失败)
- **Y5** · `app/workers/analysis.py` Celery worker · 消费 `ai_responses` post-insert event (DB trigger or Celery chain), 顺序调 (a) `app.parsers.brand_matcher.find_brand_mentions()` 写 `brand_mentions` (b) `app.parsers.sentiment_classifier.classify_sentiment()` 写 `brand_mentions.sentiment_score + sentiment_label` (c) `app.parsers.citation_extractor.extract_citations()` 写 `ai_citations`; 单测 ≥10 例
- **Y6** · `app/analysis/aggregator.py` · 5 KPI SQL 聚合 (mention_rate non-brand 决策 #15 / sov / sentiment_distribution / citation_share brandsAttributed-based / industry_ranking); SQL 用 SQLAlchemy ORM + `select()` 不写 raw SQL; 单测 ≥12 例 (含双 mention_rate 口径 / dimension='品类' 过滤 / topN brand 排序 / 时间窗 / engine 筛选)
- **Y7** · `app/analysis/citation_share.py` · `compute_citation_share()` brandsAttributed-based + `compute_pano_a()` 公式 `Σ(tier_weight × authority_confidence) / Σ_industry × 100` + `compute_citation_source_loss(window_days=14)` T-14d diff (PRD §4.2.6.H); 单测 ≥10 例
- **Y8** · `app/analysis/diagnostics.py` · 诊断生成器 · `citation_source_loss` (P1, ≥3 域丢失 AND remaining < 70%) + `citation_attribution_mismatch` (P2); **互斥触发**护栏 — 同一 brand × time-window 内若 `citation_source_loss` 已生成则 `citation_attribution_mismatch` 跳过, 反之亦然; 单测 ≥6 例 (含互斥决策矩阵)
- **Y9** · `app/api/v1/brands.py` FastAPI router · 6 sub-routes 全部挂 `Depends(RequireAuth)`; 返回 Pydantic v2 schema (snake_case Python + camelCase API alias); pagination + filter (engine / dimension / time_window) 全支持
- **Y10** · `app/api/v1/industries.py` · 4 sub-routes 同 Y9 规范
- **Y11** · `app/api/v1/csv_export.py` · 8 个 MVP exportType + #9 `pr_targets` (Citation 行动面 §4.2.7.C); UTF-8 BOM + Python `csv` 库; 10k 行上限 + 5/min 限流 (slowapi); 列字典锚 PRD §4.6.4 表
- **Y12** · `app/api/v1/auth_dependency.py` · `RequireAuth` FastAPI Depends · 验证 Session 4a' 颁发的 user JWT (Bearer header), 注入 `current_user: UserSchema`; 失败 401
- **Y13** · `app/mcp/server.py` FastAPI sub-app · JSON-RPC 2.0 over HTTP `POST /mcp/v1/jsonrpc`; 3 工具 dispatcher; Bearer token via `Depends(RequireMcpToken)`; 错误码遵循 JSON-RPC 2.0 spec (-32600/-32601/-32602/-32603/-32000)
- **Y14** · `app/mcp/tools/{get_citations,list_pr_targets,simulate_authority_boost}.py` 3 工具; `simulate_authority_boost` 是 Phase 2 简化版 (返回 Tier delta 模拟, 不接 `basePriceByTier` 滑杆完整 UI — 完整 Simulator UI 留给 Session 4b' v1.1)
- **Y15** · `app/mcp/auth.py` · `RequireMcpToken` Depends · 查询 `mcp_api_tokens` 表 + 60s Redis pub-sub 黑名单查询; 失败 401 + log
- **Y16** · `app/admin/api/v1/citation_tiers/route.py` Admin CRUD (List/Get/Update/Reseed) · 调 `requireAdminSession()` (Session A0' 落) + audit 日志; UI 留给 Session A1'
- **Y17** · `app/admin/api/v1/mcp_tokens/route.py` Admin Token 签发 (POST 创建明文返回一次, hash 入库) / 吊销 (DELETE 写 Redis 黑名单 60s) / 列表; UI 留给 Session A1'
- **Y18** · `app/cost/monitor.py` · 4 源监控 (per-engine cost_usd 累计 / per-account cost_usd / hourly burst / daily 预算) + `cost_paused` flag (Redis SET) + Planner 停止入队 (Redis pub-sub `pipeline:cost_paused` channel, Planner Worker 监听); 单测 ≥6 例
- **Y19** · `tests/integration/api_v1_smoke.py` · 端到端 (httpx + 真实 PG + 真实 Redis): 注册 user → 登录拿 JWT → curl `/api/v1/brands/loreal` → 验 JSON shape → curl CSV 导出 → curl MCP `/mcp/v1/jsonrpc` 调 `genpano_get_citations` (含 Bearer)
- **Y20** · Harness Group I 5 条规则 + 5 self-seeded fixtures + selftest 22 → 27 (含 I1 mention_rate 单一入口 / I2 citation_share brandsAttributed / I3 attribution_mismatch ⊥ source_loss / I4 MCP/api 0 匿名路径 / I5 Tier 权重禁硬编码)
- **Y21** · `scripts/dump_analysis_samples.py` · 端到端 dump (种 loreal fixture → run analysis → 输出 `analysis-samples-loreal.json` 供 Frank 视觉审查 5 KPI + diagnostics + citation_share)
- **Y22** · `scripts/verify_session_3prime.sh` · Layer 1 verify shell, 11 检查
- **Y23** · `pytest --cov=app` ≥ 80% 全线 (branches/lines/functions/statements)
- **Y24** · Frank Layer 3 验收: 在 preview frontend `https://genpano-preview.vercel.app/brand/overview?brandId=loreal` 看到真实 5 KPI 卡 (从 ai_responses 聚合); curl preview Render API `https://genpano-api-preview.onrender.com/api/v1/brands/loreal` 返回 JSON; curl MCP `https://.../mcp/v1/jsonrpc` 返回 citation 列表; preview 注入 fake threshold 触发 cost alert
- **Y25** · 文档同步: SESSION_PROGRESS Session 3' GREEN 行 / CLAUDE.md 决策 #40 草稿 / CLAUDE_CODE_SESSIONS_PYTHON.md Session 3' DONE 标记

### ❌ 本 Session 不做 (N1-N12, deferred)

- **N1** · 完整 Simulator UI (Tier delta 滑杆 + `basePriceByTier` 调整 + ROI 模拟图表) → Session 4b' v1.1 (PRD §4.2.7.E)
- **N2** · Citation 行动面 #10 `content_gap` CSV 导出 → Phase 2 (PRD §4.2.7.B v1.1)
- **N3** · KOL Shannon entropy 多样性卡 + Acquisition 事件流 (v1.1) → Phase 2 (PRD §4.2.7.D)
- **N4** · 完整前端集成 (替换 mock.js → fetch FastAPI) → Session 4b' (REPLAN §4)
- **N5** · Admin UI (Citation Tier CRUD UI / MCP Token 列表 UI / Cost 实时图表) → Session A1' (REPLAN §4)
- **N6** · Playwright E2E 6 关键路径 → Session 4b' (TEST_STRATEGY v1.1 §11 Phase 4)
- **N7** · Visual regression baseline → Session 4b' (决策 #18 Phase 4)
- **N8** · 多轮对话 Query 分析 → Phase 2 (决策 #26.C2)
- **N9** · 完整 i18n 双语化 (英文 brand 名 / 英文 KPI label / 英文 alert 文案) → Session 4b' 配合前端落 (PRD §4.10.4a)
- **N10** · 自动 PR 推荐算法完整版 (Tier 2 覆盖矩阵 + KOL 多样性 + 已覆盖降权 4 因子) → 本 Session 只落 Tier 2 覆盖矩阵基础查询 + `pr_score` 单一公式; 4 因子加权完整版延 Phase 2 (PRD §4.2.7.C)
- **N11** · pgvector 嵌入做语义 KPI (e.g. semantic similarity 找类似品牌) → Phase 2
- **N12** · WebSocket 实时推送 KPI 变化 → Phase 2 (MVP 用 polling)

---

## §3 · STOP-Trigger Template (决策 #25 规则 12)

### Type A · 环境失败 (实施前 / 中断时遇到 → STOP, Frank 决策)

- **A1** · `pyproject.toml` 缺 `mcp` (或选 `fastapi-mcp` / 自实现 JSON-RPC dispatcher) → STOP, Frank 拍板; 不擅自添加 dependency 重大调整
- **A2** · PostgreSQL preview unreachable (Render preview DB) → STOP, Frank 检查 Render 控制台
- **A3** · Redis preview unreachable → STOP (本 Session 重度依赖 Redis: cost_paused flag / MCP token 黑名单 / Celery broker)
- **A4** · `app/platform/planner/topic_pool.py` (Session 2.1' 落) 关键函数 (`generate_platform_plan` / 三层 LLM threading) 缺失 → STOP Type A
- **A5** · `app/engines/adapters/{doubao,deepseek,chatgpt}/index.py` 的 execute() (Session 1.2' 落) 缺失 → STOP Type A4
- **A6** · `app/parsers/{brand_matcher,sentiment_classifier,citation_extractor}.py` (Session 1.2' 落) 缺失 → STOP Type A4
- **A7** · alembic head conflict (Session 2.1' migration 后 main 又跑过 migration) → STOP, 跑 `alembic merge heads` 后再续

### Type B · 真相源冲突 (规则 4 触发, 必须先 sync)

- **B1** · PRD §4.5 用户态 API 路由表与 §1 引用不符 (e.g. 增删 sub-route) → STOP, 列 diff, Frank 决定先改 PRD 还是按现有写
- **B2** · PRD §4.2.6 Citation 算法 (5 级 Tier 权重 / 3 级归因 / `citation_share` 公式 / PANO A) 与决策 #19 不符 → STOP
- **B3** · PRD §4.9.4 Cost monitoring 4 源 列表 / `cost_paused` flag 名不匹配 → STOP
- **B4** · DATA_MODEL §1.6/§1.7/§1.8/§2.5 schema (字段名 / 类型 / CHECK 约束) 与本 Prompt §1 引用项不符 → STOP, 先改 DATA_MODEL 再写 migration
- **B5** · 决策 #26.C1 / Harness G3 列名黑名单已扩 (e.g. 增加 `rewrite_meta_column` 之类) 与本 Prompt 不一致 → STOP
- **B6** · Session 2' / 2.1' Pydantic 模型字段名 (e.g. `personaSnapshot` vs `persona_snapshot`) 与本 Session 引用的 aggregator 读取路径不一致 → STOP
- **B7** · Session A0' (Admin auth) 的 `requireAdminSession()` helper signature 已变 → STOP

### Type C · 范围溢出 (规则 10 守卫)

- **C1** · 不要做完整 Simulator UI (N1)
- **C2** · 不要做 Content Gap CSV (N2)
- **C3** · 不要做完整前端集成 (N4)
- **C4** · 不要做 Admin UI (N5)
- **C5** · 不要做 Playwright E2E (N6)
- **C6** · 不要给 `query_executions` 加任何 persona/rewrite_meta 顶层列 (Harness G3)
- **C7** · 不要硬编码 5 级 Tier 权重 (Harness I5, 必须 DB seed)
- **C8** · 不要降低 80% pytest coverage 阈值
- **C9** · 不要修改 Session 1.2'/2'/2.1' 的核心模块主体 (只能 read 或 extend, 不能改 plan_topics/generate_prompts/assemble_queries 主体)
- **C10** · 不要改 frontend (本 Session 0 frontend 文件改动)
- **C11** · 不要给 MCP server 加 Stdio transport (PRD §4.5.2 只要 JSON-RPC over HTTP)
- **C12** · 不要给 user-facing API 加任何匿名路径 (Harness I4)

---

## §4 · Phase Gate (3-Layer Acceptance, 决策 #30)

### L3/L4 Phase Gate 卡控 (Hard Fail, 决策 2026-04-26)

**真相源**: `docs/REPLAN_2026_04_26.md §5` L3/L4 测试覆盖矩阵 + §5.3 Hard Fail 卡控规范.

**Hard Fail 强制**: 下列 L3/L4/Visual 任一未跑绿, GitHub Actions branch protection 拦截 merge. 不允许 soft warning, 不允许临时跳过.

**本 Session 必跑 L3 集成测试 (4 项)**:
- Response 采集 (Celery worker → ai_responses 入库 + response_source labeled); 分析 pipeline (brand_detector + sentiment + citation 真实跑); 用户态 brand API 6 路径 (auth-required); MCP Bearer token 验证 + 吊销 60s 生效

**本 Session 必跑 L4 E2E 测试 (1 项)**:
- Frank 在 preview /brand/overview?brandId=loreal 看到真实数据 (KPI 5 张 + 趋势图)

**本 Session Visual baseline (1 张)**:
- `/brand/overview.png` 建立后 Playwright `to_have_screenshot()` diff < 0.1%, 后续 PR 不得破

**补救测试**: **TS#3 → Python pytest 267+** (master Session 3 测试 + Citation §4.2.6/§4.2.7 全链路 Python 重写)

**Phase Gate 通过条件 (在原有 Layer 1-3 基础上追加)**:
- G_L3.1: 4 项分析 pipeline 集成测试全部绿 (response collection / brand detection / sentiment / citation)
- G_L4.1: Frank 浏览器 /brand/overview 显示真实 KPI 5 张卡
- G_Visual.1: `/brand/overview.png` baseline 已建立 + Playwright 0 diff
- G_Remedial.1: master TS Citation 全链路测试翻译完整, pytest 测试数 ≥ 267

### Layer 1 · `scripts/verify_session_3prime.sh` (11 检查)

```bash
#!/bin/bash
set -e

# L1.1 ruff (lint)
poetry run ruff check app/ tests/ scripts/

# L1.2 mypy --strict
poetry run mypy --strict app/ scripts/

# L1.3 pytest unit ≥80% coverage
poetry run pytest tests/unit/ --cov=app --cov-fail-under=80

# L1.4 pytest integration smoke
poetry run pytest tests/integration/api_v1_smoke.py -v

# L1.5 alembic upgrade + downgrade + upgrade round-trip
poetry run alembic upgrade head
poetry run alembic downgrade -1
poetry run alembic upgrade head

# L1.6 psql verify zero forbidden cols on query_executions (复用 G3 黑名单, 8 列)
psql $DATABASE_URL -c "SELECT column_name FROM information_schema.columns WHERE table_name='query_executions' AND column_name IN ('persona_snapshot','persona_profile','agent_profile_snapshot','agent_profile_id','persona_id','rewrite_meta_column','llm_rewritten_text','rewritten_at_column');" | grep -E "0 rows" || (echo "FAIL: forbidden col exists" && exit 1)

# L1.7 ci_check.py Group I all green
poetry run python scripts/ci_check.py --group=I

# L1.8 selftest 27/27 fixture expectations met
poetry run python scripts/ci_harness_selftest.py | grep -E "27 / 27 fixture expectations met"

# L1.9 Citation Tier 5 级 seed 已落库 (Tier 0/1/2/3/4)
psql $DATABASE_URL -c "SELECT COUNT(*) FROM citation_domain_authorities WHERE tier IN (0,1,2,3,4);" | grep -E "^\s*5$" || (echo "FAIL: tiers != 5" && exit 1)

# L1.10 dump_analysis_samples 真跑 + jq 校验 KPI / diagnostics / citation_share keys 齐
poetry run python scripts/dump_analysis_samples.py --brand=loreal --output=/tmp/analysis-samples-loreal.json
jq -e '.kpis.mention_rate_non_brand | numbers' /tmp/analysis-samples-loreal.json
jq -e '.kpis.sov | numbers' /tmp/analysis-samples-loreal.json
jq -e '.kpis.sentiment_distribution.positive | numbers' /tmp/analysis-samples-loreal.json
jq -e '.kpis.citation_share | numbers' /tmp/analysis-samples-loreal.json
jq -e '.kpis.industry_ranking | numbers' /tmp/analysis-samples-loreal.json
jq -e '.diagnostics | arrays' /tmp/analysis-samples-loreal.json
jq -e '.pano_a | numbers' /tmp/analysis-samples-loreal.json

# L1.11 MCP curl smoke (本地 dev server)
poetry run uvicorn app.main:app --port 8000 &
sleep 3
TOKEN=$(poetry run python scripts/issue_test_mcp_token.py)
curl -s -X POST http://localhost:8000/mcp/v1/jsonrpc \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"genpano_get_citations","params":{"brandId":"loreal"}}' \
  | jq -e '.result.citations | arrays'
kill %1
```

### Layer 2 · Harness Selftest 27/27

5 new fixtures (I1-I5) joining Session 0'-2.1' fixtures (22 → 27):
- **I1** · `mention_rate_dual_entry.cifixture.py` — 故意在 `app/api/v1/csv_export.py` 直接计算 mention_rate 不调 aggregator (违反单一入口)
- **I2** · `citation_share_mentioned_based.cifixture.py` — 故意写 `citation_share = brands_mentioned / total` (应该是 brands_attributed)
- **I3** · `diagnostics_both_triggered.cifixture.py` — 故意同时返回 `source_loss` + `attribution_mismatch` 而无互斥护栏
- **I4** · `mcp_anonymous_route.cifixture.py` — 故意定义 `@router.post("/mcp/...")` 不挂 `Depends(RequireMcpToken)`
- **I5** · `tier_weight_hardcoded.cifixture.py` — 故意 `TIER_WEIGHTS = {1: 1.0, 2: 0.7, ...}` 字面量

Each fixture 文件名 basename matches its rule's pattern; docstring deliberately does **NOT** mention the required identifier (per CLAUDE.md decision #27 lesson learned: `content.includes()` self-satisfaction trap).

### Layer 3 · Frank S1-S6 Verification (preview env)

- **S1** · `bash scripts/verify_session_3prime.sh` 全绿 (Layer 1 + 2 自动)
- **S2** · `git push origin session-3prime` → GitHub Action 跑通 → Render `genpano-api-preview` deploy 成功 → Vercel `genpano-preview` (frontend, 暂无变化但应仍可访问) deploy 成功
- **S3** · curl preview API:
  ```
  TOKEN=<frank 在 preview 注册账号后 /auth/login 拿 JWT>
  curl -s "https://genpano-api-preview.onrender.com/api/v1/brands/loreal" -H "Authorization: Bearer $TOKEN" | jq
  ```
  → 看到 5 KPI + brand 数据 (从种入的 fixture 聚合)
- **S4** · curl preview MCP:
  ```
  MCP_TOKEN=<admin /admin/api/v1/mcp_tokens POST 拿>
  curl -s -X POST "https://genpano-api-preview.onrender.com/mcp/v1/jsonrpc" \
    -H "Authorization: Bearer $MCP_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","id":1,"method":"genpano_get_citations","params":{"brandId":"loreal"}}' | jq
  ```
  → 看到 citation 列表 + tier_weight + authority_confidence 字段
- **S5** · 在 preview env 注入 fake cost threshold (env var `COST_THRESHOLD_DAILY_USD=0.01`), 跑 1 个 Adapter execute → 触发 `cost_paused` flag → 在 Admin Cost Monitor 页 (Session A1' 后) 或 curl `/admin/api/v1/runtime_flags` 看到 `cost_paused=true`
- **S6** · Frank 视觉审查 `analysis-samples-loreal.json` (Step 9 dump 输出): mention_rate non-brand 与 全量 双值合理 (差异反映 dimension 过滤效果) / sov sum=100 / sentiment 三段 sum=100 / citation_share 仅统计 attributed brand / industry_ranking 是 1-N 整数 / diagnostics 仅有 source_loss 或 mismatch 之一不同时存在 / pano_a ∈ [0, 100] (PRD §4.2.6.G 公式)

---

## §5 · 12-Step Delivery Order (atomic commits, 每 Step 一个 commit + 跑 verify shell 局部)

### Step 0 · Branch + dependency 加 mcp/jsonrpc + 拿 main HEAD

```bash
git checkout main && git pull origin main
git checkout -b session-3prime
# 加 dep (本 Session 选定: 自实现 JSON-RPC dispatcher, 不引入 mcp SDK 减少未知依赖, Frank 拍板)
poetry add slowapi  # CSV 限流
poetry add tldextract  # URL 归一化, 替 tldts
poetry add redis  # 本 Session 重度依赖, Session 1.2' 已加则跳过
git add pyproject.toml poetry.lock
git commit -m "Session 3' Step 0: dep slowapi + tldextract + branch fork"
```

### Step 1 · DATA_MODEL §1.6/§1.7/§1.8/§2.5 文档落地 + SQLAlchemy 模型 (Y1+Y2)

- 写 `app/db/models/ai_citation.py` + `citation_domain_authority.py` + `mcp_api_token.py` + `brand_mention.py`
- 扩 `app/db/models/ai_response.py` 5 列
- 单测 `tests/unit/db/models/{test_ai_citation,test_citation_domain_authority,test_mcp_api_token,test_brand_mention,test_ai_response_extension}.py` 各 ≥3 例 (字段约束 / unique / index / CHECK)
- commit `Session 3' Step 1: SQLAlchemy models for analysis layer`

### Step 2 · Alembic migration (Y3) + Tier seed 文件

- `alembic revision --autogenerate -m "session_3prime_analysis_layer"`
- 手工调整 (CHECK 约束 Alembic autogenerate 不生; index 名规范化; 5 级 Tier seed `op.bulk_insert`)
- 写 `scripts/seed_citation_tiers.py` reseed 命令
- alembic upgrade/downgrade/upgrade round-trip 测
- commit `Session 3' Step 2: alembic migration + tier seed`

### Step 3 · response_collector worker (Y4)

- `app/workers/response_collector.py` Celery task
- 用 `celery_app.conf.task_always_eager=True` 单测
- ≥8 例 (含 NO_ACCOUNT_AVAILABLE pending / api_fallback labeling / cost 字段写入 / trigger_source 5 值穷举)
- commit `Session 3' Step 3: response_collector celery worker`

### Step 4 · analysis worker + brand_mention/ai_citation 写入 (Y5)

- `app/workers/analysis.py` 调 brand_matcher + sentiment_classifier + citation_extractor
- ≥10 例 (含 brand 别名匹配 / sentiment 三档 / citation 3 级归因 / domain authority lookup)
- commit `Session 3' Step 4: analysis worker pipeline`

### Step 5 · aggregator (Y6) + citation_share (Y7) + diagnostics (Y8)

- `app/analysis/aggregator.py` 5 KPI SQL
- `app/analysis/citation_share.py` PANO A + source_loss
- `app/analysis/diagnostics.py` 互斥护栏
- ≥28 例 (12 + 10 + 6)
- commit `Session 3' Step 5: aggregation + citation_share + diagnostics`

### Step 6 · 用户态 API routers (Y9+Y10+Y11+Y12)

- `app/api/v1/auth_dependency.py` (RequireAuth Depends)
- `app/api/v1/brands.py` 6 sub-routes
- `app/api/v1/industries.py` 4 sub-routes
- `app/api/v1/csv_export.py` 9 exportTypes (8 MVP + #9 pr_targets)
- `app/main.py` mount routers
- ≥25 例 (Pydantic schema / pagination / filter / 401 unauth / 429 rate-limit)
- commit `Session 3' Step 6: user-facing FastAPI routers`

### Step 7 · MCP server (Y13+Y14+Y15)

- `app/mcp/server.py` JSON-RPC dispatcher
- `app/mcp/auth.py` Bearer + Redis 黑名单
- `app/mcp/tools/{get_citations,list_pr_targets,simulate_authority_boost}.py`
- `app/main.py` mount sub-app at `/mcp`
- ≥15 例 (含 invalid jsonrpc / method not found / param validation / token revoke / 3 工具各自 contract)
- commit `Session 3' Step 7: MCP server JSON-RPC over HTTP`

### Step 8 · Admin Citation Tier CRUD + MCP Token 签发 (Y16+Y17)

- `app/admin/api/v1/citation_tiers/route.py` (List/Get/Update/Reseed) + `requireAdminSession()`
- `app/admin/api/v1/mcp_tokens/route.py` (Create/Revoke/List)
- ≥10 例
- commit `Session 3' Step 8: admin citation tier crud + mcp token endpoints`

### Step 9 · Cost monitor (Y18) + dump 脚本 (Y21)

- `app/cost/monitor.py` 4 源 + Redis pub-sub `pipeline:cost_paused` channel
- Planner 监听 channel (扩 `app/platform/scheduler/platform_scheduler.py` 加 `pause_check`)
- `scripts/dump_analysis_samples.py` 端到端 (种 fixture → run analysis → 输出 JSON)
- ≥6 例
- commit `Session 3' Step 9: cost monitor + dump analysis samples`

### Step 10 · Integration smoke test + Frank fixture (Y19)

- `tests/integration/api_v1_smoke.py` httpx + 真实 PG + 真实 Redis 端到端
- `tests/fixtures/seed_loreal_data.py` 注入 Frank Layer 3 验收数据
- 跑 `pytest tests/integration/`
- commit `Session 3' Step 10: integration smoke test + loreal fixture`

### Step 11 · Harness Group I (Y20) + selftest 27/27

- `scripts/ci_check.py` 加 5 条 Group I 规则
- 5 self-seeded fixtures `__ci_fixtures__/I*.py`
- `scripts/ci_harness_selftest.py` EXPECTED_POSITIVES 22 → 27
- 跑 `python scripts/ci_harness_selftest.py` 必须打印 `27 / 27 fixture expectations met`
- commit `Session 3' Step 11: harness group I + selftest 27/27`

### Step 12 · Phase Gate Layer 1+2 + 文档同步 + Layer 3 + Decision #40

- 跑 `bash scripts/verify_session_3prime.sh` 11 检查全绿
- `git push origin session-3prime` → preview env deploy
- Frank S2-S6 端到端验证 (curl + 视觉审查 dump JSON)
- 写 `CLAUDE.md` 决策 #40 草稿 (本 Prompt §6 模板)
- 更新 `docs/SESSION_PROGRESS.md` Session 3' GREEN 行
- 更新 `docs/CLAUDE_CODE_SESSIONS_PYTHON.md` Session 3' DONE 标记
- commit `Session 3' Step 12: docs sync + decision #40 + phase gate green`
- PR `session-3prime` → `main`, Frank approve, merge

---

## §6 · Delivery Report Template (决策 #25 规则 3, 收尾时填)

> **本段空白由 Claude Code 在 Step 12 收尾时填入, 然后用作 Decision #40 的草稿**

### Phase Gate Layer 1 (verify shell 11 检查)

- [ ] L1.1 ruff: __ violations
- [ ] L1.2 mypy --strict: __ errors
- [ ] L1.3 pytest unit coverage: __% (目标 ≥80%)
- [ ] L1.4 integration smoke: __ tests pass / fail
- [ ] L1.5 alembic round-trip: PASS / FAIL
- [ ] L1.6 query_executions forbidden cols: 0 (or list)
- [ ] L1.7 Group I harness: __ pass / __ fail
- [ ] L1.8 selftest: __ / 27 fixture expectations met
- [ ] L1.9 Tier seed: 5 rows verified
- [ ] L1.10 dump_analysis_samples jq: all keys present
- [ ] L1.11 MCP curl smoke: PASS / FAIL

### Phase Gate Layer 2 (selftest)

- [ ] 27 / 27 fixture expectations met
- [ ] I1-I5 each 各被对应 grep rule 抓到 ≥1 次

### Phase Gate Layer 3 (Frank preview)

- [ ] S1 verify shell green
- [ ] S2 GitHub Action + Render + Vercel preview deploy 成功
- [ ] S3 curl `/api/v1/brands/loreal` JSON shape 通过 (5 KPI + diagnostics + citation_share)
- [ ] S4 curl MCP `/mcp/v1/jsonrpc` JSON-RPC 2.0 response 通过
- [ ] S5 cost_paused flag 触发 + Admin endpoint 看到
- [ ] S6 Frank 视觉审查 dump JSON 通过 (subjective approval)

### 偏差登记 (规则 3, C 段)

- **C1 (空)** · Session 3' 实施过程中如遇真相源不可调和冲突, 在此登记
- **C2 (空)** · ...

### 真相源同步

- [ ] DATA_MODEL §1.6/§1.7/§1.8/§2.5 段号未漂移
- [ ] PRD §4.2/§4.5/§4.5.2/§4.6.4/§4.9.4 段号未漂移
- [ ] CLAUDE.md 决策 #9/#15/#19/#21/#26/#27/#28/#29-#32 引用稳定
- [ ] SESSION_PROGRESS Session 3' GREEN 行已加
- [ ] CLAUDE_CODE_SESSIONS_PYTHON.md Session 3' 标记 DONE

### Decision #40 草稿 (Frank 复审 + 入 CLAUDE.md)

#### 40. Session 3' · 分析引擎 + 用户态 API + MCP Server (Python 重写) 交付 (2026-04-XX)

按 `docs/CLAUDE_CODE_SESSIONS_PYTHON.md` Session 3' 范围落地分析层 + 用户态 API + MCP Server, 完成 M3 Milestone 末段 = Pipeline 端到端数据闭环。

**A. 分析层** (`app/analysis/` + `app/workers/`):
- response_collector worker 消费 query_executions, 写 ai_responses (含 5 列扩展 + 显式 response_source)
- analysis worker 调 brand_matcher + sentiment_classifier + citation_extractor 写 brand_mentions + ai_citations
- aggregator 5 KPI (mention_rate non-brand 默认决策 #15 / sov / sentiment / citation_share / industry_ranking)
- citation_share PANO A 公式 + citation_source_loss T-14d diff
- diagnostics 互斥护栏 (source_loss ⊥ attribution_mismatch)

**B. 用户态 API** (`app/api/v1/`):
- 6 brand routes + 4 industry routes + CSV 导出 9 exportTypes (8 MVP + Citation #9 pr_targets)
- 全部 `Depends(RequireAuth)` (决策 #9 Auth-Required Day 1)
- Pydantic v2 schema + camelCase API alias

**C. MCP Server** (`app/mcp/`):
- FastAPI sub-app + JSON-RPC 2.0 over HTTP `POST /mcp/v1/jsonrpc`
- 3 工具: genpano_get_citations / list_pr_targets / simulate_authority_boost (Phase 2 简化版)
- Bearer token + Redis pub-sub 60s 黑名单

**D. Admin endpoints** (本 Session 落, Admin UI 留 A1'):
- Citation Tier CRUD (5 级 Tier seed + reseed 命令)
- MCP Token 签发 / 吊销 / 列表

**E. Cost monitor** (`app/cost/monitor.py`):
- 4 源监控 + cost_paused Redis flag + Planner 停止入队 (pub-sub)

**F. Harness Group I 5 条 + selftest 27/27**:
- I1 mention_rate 单一入口 / I2 citation_share brandsAttributed / I3 attribution_mismatch ⊥ source_loss / I4 MCP/api 0 匿名 / I5 Tier 权重禁硬编码

**G. 偏差登记 (规则 3)**:
- (待 Step 12 填)

---

## §7 · Closing Consistency Loop (决策 #25 规则 7)

收尾前必须重跑 §0 的 8 条 grep 命令, 验证真相源段号 / Harness 规则编号 / SESSION_PROGRESS 行 / 决策 #29-#32 都未漂移; 若发现新偏离则回 §6 偏差登记 C 段补登记 + 必要时改 §1 引用项段号:

```bash
# 收尾 closing loop, 重跑 §0
cat <<'EOF' | bash
set -e
echo "[F1] decisions #29-#40"
grep -nE "^(29|30|31|32|33|34|35|36|37|38|39|40)\." CLAUDE.md | head -30
echo "[F2] auth+citation+a5"
grep -nE "(Auth-Required|MCP API.*Bearer|Citation.*Tier|basePriceByTier|citation_share|citation_source_loss|attribution_mismatch)" CLAUDE.md | head -25
echo "[F3] persona/rewrite_meta JSONB"
grep -nE "(rewrite_meta|persona_snapshot|attempts.*JSONB|G3.*query_execution|browser_profile)" CLAUDE.md | head -20
echo "[F4] sessions 2'/2.1'/1.2' GREEN"
grep -nE "(Session (2|2\.1|1\.2)'.*PASS|Session (2|2\.1|1\.2)'.*GREEN)" docs/SESSION_PROGRESS.md | head -10
echo "[F5] REPLAN §4 Session 3'"
sed -n '264,282p' docs/REPLAN_2026_04_26.md
echo "[F6] PRD §4.2/§4.5/§4.9.4"
grep -nE "^####? §4\.(2|5|9\.4)" docs/PRD.md | head -25
echo "[F7] backend tree"
ls app/
echo "[F8] mcp / celery dep"
grep -nE "^(mcp|fastapi-mcp|jsonrpc|celery|slowapi|tldextract)" pyproject.toml
EOF
```

任一段回不出来或 diff 出现 → 回 §6 C 段登记。

---

## §8 · Final Reminders (10 条 Claude Code 必须 honor)

1. **真相源不重抄, 只 `# See PRD §X.Y`** — 任何 schema 字段 / 算法公式 / 阈值常量必须用注释指向 PRD/DATA_MODEL/CLAUDE.md 而不是在 Python docstring 抄一遍 (规则 1)
2. **Commit format ASCII**: `Session 3' Step <N>: <主题>` 不用 emoji / em-dash / 中文括号; commit body 引 CLAUDE.md 决策号 (规则 4 反向同步)
3. **Constants 单一入口**: `app/analysis/constants.py` 集中放 `CITATION_TIER_WEIGHTS_LOOKUP_TABLE` (DB 取 fallback) / `MENTION_RATE_NON_BRAND_DIMENSION = '品类'` / `SENTIMENT_CONFIDENCE_FALLBACK = 0.5` / `CITATION_SOURCE_LOSS_WINDOW_DAYS = 14` / `CITATION_SOURCE_LOSS_THRESHOLD_REMAINING = 0.7` (PRD §4.2.6.H) / `MAX_CSV_ROWS = 10000` (PRD §4.6.4) / `CSV_RATE_LIMIT_PER_MIN = 5`
4. **Pydantic v2** 不是 v1 — 用 `model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)` 实现 snake_case Python ↔ camelCase API 互转
5. **SQLAlchemy 2.0 async** — 所有 query 用 `select()` + `await session.execute()`, 不写 raw SQL (除非 alembic migration); 不用 1.x `query()` API
6. **Zero `query_executions` 顶层列添加** (Harness G3, 决策 #26.C1) — rewrite_meta + persona 只能 read `attempts[].rewrite_meta` + `attempts[].browser_profile`
7. **Zero frontend 改动** (Session 4b' 收尾) — 本 Session 不碰任何 `.tsx` / `.jsx` / `frontend/`
8. **Celery test 用 `task_always_eager=True`** — 单测内不真起 broker, 集成测试用真 Redis (preview env Render Redis instance)
9. **MCP transport = JSON-RPC over HTTP only** (PRD §4.5.2) — 不引入 stdio MCP, 不引入 SSE
10. **CSV `csv` 库不手写 join** — Python stdlib `csv.writer` + `csv.QUOTE_NONNUMERIC`, UTF-8 BOM 写 `b'\xef\xbb\xbf'` 头, 限流走 slowapi `@limiter.limit("5/minute")`

---

**结束**: 本 Prompt 是给 Claude Code 在 `C:\Users\frank.wang\genpano` 工作仓的 `session-3prime` 分支上执行的完整指令; 严格按 §0 → §1 → §2 → §3 → §5 顺序起手, §4 是验收标准, §6 是收尾报告模板, §7 是闭环检查, §8 是不可违反的硬约束。完成后 PR 到 main, Frank 复审并 approve 后 merge — 然后才能开 Session A1' (Admin UI 完整化)。
