# Session 2.1' · Planner LLM Refinement (Python 重写) — Prime Prompt

> **本文档是发给 Claude Code 的 Session Prompt 真相源**, 严格遵守 CLAUDE.md 决策 #25 的 12 条 Prompt 编写公约。Claude Code 必须按 §0 → §8 顺序读完后才能动手写代码。
>
> **本 Session 定位**: M3 Milestone 第二块 — 复用 master Session 2.1 (决策 #27) 的三层 LLM 增强算法, 用 Python 重写, 落到合并仓 `C:\Users\frank.wang\genpano`。在 Session 2' 已交付的 skeleton Pipeline 之上插入 LLM 后处理 (Topic Refinement / Prompt Naturalization / Query Profile-Aware Rewrite), **不改任何 schema 顶层结构**, 只在 envelope 里追加 audit 字段, 严格 honor 决策 #26.C1 (rewrite_meta 进 attempts JSONB 子字段, 禁加 query_executions 顶层列, 由 Harness G3 锁定)。
>
> **依赖**: Session 2' (skeleton Planner 全绿, 17 topic + 400 prompt + 2614 query 端到端 dry-run 跑通)。
>
> **本 Session 不依赖**: Session 1' / 1.2' / 1.5' (Planner 是纯函数 + DB 读 + LLM 改写, 不调浏览器 / 不调 KG 写入 / 不调真实 ChatGPT 引擎)。

---

## §0 · 前置 Grep 契约 (Pre-Flight Grep Contract)

> **决策 #25 规则 2**: Claude Code 开工第一批动作必须先跑下列 grep / read 命令自证真相源未漂移。任一不一致 → STOP (Type B), 不写代码, 回到 Frank 对齐。

```bash
# F1 · 验证最近 4 条 CLAUDE.md 决策 (#29 / #30 / #31 / #32) 仍在 (Python pivot / preview env / branch-per-session / 工作仓切换)
grep -n "^29\.\|^30\.\|^31\.\|^32\." CLAUDE.md | head -20

# F2 · 验证决策 #27 (master Session 2.1 LLM Refinement 真相源) 的三层 LLM 模块 + Harness H1/H2/H3 仍在
grep -nE "refineTopicsWithLlm|naturalizePromptsWithLlm|rewriteQueriesForProfiles|H1|H2|H3|llm-canned-responses|rewrite_meta|naturalizeConfidence|realismScore" CLAUDE.md | head -40

# F3 · 验证决策 #26.C1 (persona/rewrite 进 attempts JSONB, 禁加顶层列) 真相源仍在 — 本 Session rewrite_meta 严格沿用此契约
grep -nE "persona_snapshot|attempts.*JSONB|browser_profile|rewrite_meta|G3|顶层列" CLAUDE.md | head -20

# F4 · 验证 SESSION_PROGRESS 中 Session 2' 已宣绿 (skeleton Pipeline 可用)
grep -nE "Session 2'|skeleton|17 topic|400 prompt|generatePlatformPlan" docs/SESSION_PROGRESS.md | head -20

# F5 · 验证 REPLAN §4 Session 2.1' 范围 + Phase Gate 仍如本 Prompt 描述
grep -n "Session 2\.1'" docs/REPLAN_2026_04_26.md | head -10

# F6 · 验证 PRD §4.0.1a / §4.10.3.A / §4.2.5 仍在 (Planner / 23 行矩阵 / Topic 维度 — Session 2.1' Gate 1 intent 守卫依赖)
grep -nE "§4\.0\.1a|§4\.10\.3\.A|§4\.2\.5|navigational|reduced_factor" docs/PRD.md | head -20

# F7 · 验证 Session 2' 交付的 skeleton 模块在合并仓中 (本 Session 在这些模块上 wire LLM, 不重写)
ls app/platform/planner/ 2>/dev/null | head -20

# F8 · 验证 pyproject.toml 已含 LLM client 必需依赖 (httpx / pydantic), 无新增 LLM SDK 依赖 — 本 Session 用 httpx 直调火山引擎 OpenAI-compat endpoint, 不引入 langchain / openai SDK
grep -nE "httpx|pydantic|fastapi|sqlalchemy|pytest" pyproject.toml | head -30
```

**如何使用 F1-F8 结果**:
- F1 / F2 / F3 / F6 任一未命中预期字段 → STOP Type B (真相源漂移), 暂停实施, 回到 Frank 对齐
- F5 描述与本 Prompt §2 不一致 → STOP Type B, 以 REPLAN §4 为准
- F4 显示 Session 2' 未宣绿 → STOP Type A (依赖未就绪)
- F7 缺少 Session 2' 模块 → STOP Type A (依赖未就绪, 不应该出现因为 F4 已守卫)
- F8 缺少 httpx → 走 Step 0 在本 Session 内 `pip install httpx` 补齐 (不 STOP)

---

## §1 · 真相源索引 (Truth Source Index)

> **决策 #25 规则 5 + 规则 6**: 每个 Session Prompt §1 必须列清"本 Session 引用 / 修改的真相源"到最小单元。

### 引用 (read-only, 不修改)

- **CLAUDE.md 决策 #25** (Prompt 编写 12 条公约 — 本 Session 严格遵守)
- **CLAUDE.md 决策 #27** (master Session 2.1 LLM Refinement 算法真相源, A-G 全段 — 本 Session 是其 Python 重写)
- **CLAUDE.md 决策 #26.C1** (persona snapshot / rewrite_meta 进 attempts JSONB, 禁加顶层列 — 本 Session rewrite_meta 严格沿用)
- **CLAUDE.md 决策 #15** (提及率 non-brand 口径 — Gate 2b 品类 prompt 不夹品牌名守卫依赖)
- **CLAUDE.md 决策 #21.D PRD §4.10.3.A** (23 行 Intent×Engine×Locale 矩阵 — Gate 1 intent 守卫的 lookup 入口)
- **CLAUDE.md 决策 #29 / #30 / #31 / #32** (Python pivot / preview env / branch-per-session / 工作仓切换)
- **PRD §4.0.1a** (Planner Bottom-Up 三维度算法, Topic Refinement 是其 LLM 增强层)
- **PRD §4.10.3.A** (23 行矩阵, navigational reduced_factor=0.3 — Gate 1 intent 守卫 lookup 表)
- **PRD §4.2.5** (Topic 维度: 品类 / 品牌 / 产品 三类型, Topic Refinement 必须保持 dimension 字段不变)
- **PRD §4.2.3a** (ProfileGroup 4 默认值, Query rewrite 按 ProfileGroup 加场景前缀的输入)
- **PRD §4.2.4** (Sentiment 0.5 tiebreak — 本 Session 不直接用, 但 Topic Refinement 不应破坏未来 Sentiment 测算)
- **PRD §4.6.0a** (UI 禁开发约束语 — LLM 改写后的 prompt / query 文本必须像真人话, 不能含 "informational intent" / "category dimension" 等开发术语)
- **DATA_MODEL §2.5** (`query_executions.attempts` JSONB schema, `browser_profile` 由 Session 2' 注入, `rewrite_meta` 由本 Session 注入 — 两者并列不冲突)
- **DATA_MODEL §1.5 / §1.6** (`platform_topics` / `platform_prompts` 表 — 本 Session 加 5 列 audit 字段不动主键)
- **REPLAN §4 Session 2.1'** (本 Session 范围 + Phase Gate 真相源)
- **REPLAN §6.5** (Harness 约定 — H1/H2/H3 Python 重写)
- **REPLAN §7** (4 行业不变量, beauty-personal-care 是端到端 dump 标的)
- **SESSION_PROGRESS Session 2'** (skeleton Pipeline 已交付, 17 topic / 400 prompt / 2614 query 端到端跑通)
- **SESSION_2_PRIME_PROMPT §1.1 / §5** (Session 2' 模块清单, 本 Session 在其上 wire LLM)
- **app/platform/planner/topic_planner.py** (Session 2' 交付, 本 Session 加 `refine_topics_with_llm` 函数 — 不改 `plan_topics` 主体)
- **app/platform/planner/prompt_generator.py** (Session 2' 交付, 本 Session 加 `naturalize_prompts_with_llm` 函数)
- **app/platform/planner/query_assembler.py** (Session 2' 交付, 本 Session 加 `rewrite_queries_for_profiles` 函数 + `attempts.rewrite_meta` 注入)
- **app/platform/planner/topic_pool.py** (Session 2' 交付的 `generate_platform_plan` 上层编排, 本 Session 改为可选 `llm: LlmClient | None` 参数)
- **app/platform/db/ports.py + memory_repo.py** (Session 1.5' / 2' 交付的 `KgRepositories` 接口, 本 Session 单测继续走 InMemory)
- **app/platform/llm/client.py** (Session 1.5' 交付的 `LlmClient` 火山引擎 wrapper — 本 Session 复用, 不新建 LLM 客户端)

### 前置依赖 (Prerequisites, 决策 #25 规则 12 Type A4)

> 本 Session 必须在以下 Session 全部宣绿后才能开工。任何一项未 GREEN 即触发 STOP Type A (依赖未就绪), 暂停实施直到依赖闭环。

| Session | GREEN 条件 | 本 Session 依赖点 |
| ------- | --------- | ---------------- |
| **Session 0'** | 测试地基 (uv / pytest / ruff / mypy / Group A-E baseline 38 harness 规则) 全绿, `EXPECTED_POSITIVES = 3` selftest 通过 | 本 Session 在 Group H 加 +3 (H1/H2/H3), selftest 链 14 → 17 依赖 0' 的 baseline |
| **Session 1.5'** | KG Platform Layer 交付, `LlmClient` (火山引擎 OpenAI-compat wrapper, 50 calls/industry budget) + `KgRepositories` 接口 + `InMemoryKgRepositories` 单测桩可用; `seed_brands_by_category` beauty-personal-care 行业静态种子可读 | 本 Session 复用 LlmClient (不新建客户端), Y10 dump 脚本接 beauty 行业 seed |
| **Session 2'** | Pipeline 三层 skeleton 交付 (Topic Planner / Prompt Generator / Query Assembler 纯规则模板版), Pydantic v2 模型 (`PlannedTopic` / `PlannedPrompt` / `PlannedQuery`) 锁定; `query_executions.attempts` JSONB 字段已存在; G1/G2/G3/G4 Harness 全绿 | 本 Session 在三层之上 wire LLM (扩函数不改主体); rewrite_meta 注入 `attempts[]` 路径已被 G3 守卫; 17 topic / 400 prompt / 2614 query 端到端跑通是本 Session 黄金基线 |

**前置依赖验证命令** (Step 0 必跑, 失败即 STOP Type A):
```bash
# 验证 Session 0' / 1.5' / 2' 全 GREEN
grep -E "^Session (0'|1\.5'|2')\s+\|\s+GREEN" docs/SESSION_PROGRESS.md
# 期望输出: 3 行 GREEN 标记
```

### 修改 (write, 必须列入 Decision #39 偏差登记如有偏离)

- **app/platform/planner/llm_canned_responses.py** (新建 — canned LLM transport, CI 默认走此路径, live 跑 VOLC_API_KEY)
- **app/platform/planner/topic_planner.py** (扩 — 加 `refine_topics_with_llm({topics, llm, brands_catalog, now})`, 不改 `plan_topics`)
- **app/platform/planner/prompt_generator.py** (扩 — 加 `naturalize_prompts_with_llm({prompts, topics, brands_catalog, llm})` + Gate 1/2a/2b/3 守卫)
- **app/platform/planner/query_assembler.py** (扩 — 加 `rewrite_queries_for_profiles({queries, prompts, topics, brands_catalog, llm})` + `attempts[].rewrite_meta` 注入 + 3 级 fallback ladder)
- **app/platform/planner/topic_pool.py** (扩 — `generate_platform_plan` 加 `llm: LlmClient | None = None` 参数, llm=None 时跳过 3 层 envelope)
- **app/platform/planner/types.py** (扩 — 加 `RealismScore` / `AuditStatus` Literal / `RewriteMeta` Pydantic / `LlmRefinement{Topic,Prompt,Query}Result` Pydantic)
- **app/platform/planner/intent_classifier.py** (新建 — `classify_intent_heuristic(text)` 基于关键词 heuristic 判断 intent, 用于 Gate 1 intent-drift 守卫; 不调 LLM)
- **alembic/versions/<timestamp>_session_2_1prime_planner_llm_refinement.py** (新建 migration: `platform_topics` 加 `realism_score DECIMAL(3,2)` / `llm_refined_at TIMESTAMPTZ` / `audit_status VARCHAR(20)` + CHECK + 2 索引; `platform_prompts` 加 `llm_naturalized_at TIMESTAMPTZ` / `naturalize_confidence DECIMAL(3,2)` + 索引; `query_executions` **零顶层列变更**, 只加 `COMMENT ON COLUMN attempts` 文档化 `browser_profile` (Session 2') + `rewrite_meta` (Session 2.1') JSONB 子字段)
- **app/models/platform.py** (扩 SQLAlchemy 2.0 declarative — `PlatformTopic` 加 3 字段, `PlatformPrompt` 加 2 字段, `QueryExecution` 不动)
- **tests/unit/platform/planner/test_topic_planner_llm.py** (新增 — `refine_topics_with_llm` 单测, ≥10 例覆盖三档 audit / determinism / LLM 失败容错 / budget exhausted)
- **tests/unit/platform/planner/test_prompt_generator_llm.py** (新增 — `naturalize_prompts_with_llm` 单测, ≥12 例覆盖 Gate 1/2a/2b/3 + 4 fallback reason)
- **tests/unit/platform/planner/test_query_assembler_llm.py** (新增 — `rewrite_queries_for_profiles` 单测, ≥13 例覆盖 3 级 fallback / persona 前缀 / `attempts[].rewrite_meta` 注入 / determinism)
- **tests/unit/platform/planner/test_topic_pool_llm.py** (扩 — `generate_platform_plan` 加 `llm` 参数测试, ≥18 例覆盖 LLM threading / determinism / 桶 LLM 失败容错 / budget exhausted / 时间戳 stamping / 三层 envelope 联动)
- **tests/unit/platform/planner/test_llm_canned_responses.py** (新增 — canned transport pattern matching, ≥8 例覆盖品类/品牌/产品 × Topic-refine/Prompt-naturalize/Query-rewrite)
- **tests/unit/platform/planner/test_intent_classifier.py** (新增 — `classify_intent_heuristic` 单测, ≥8 例覆盖 4 intent × 中英)
- **tests/unit/platform/planner/test_golden_beauty_llm.py** (扩 — Session 2' 的 `test_golden_beauty.py` 加 LLM-on path, ≥6 新例断言 envelope 三层联动 + determinism + canned transport 行为锁)
- **tests/integration/platform/planner/test_dump_planner_samples.py** (新增 — 端到端集成测试, 跑 `generate_platform_plan` + canned LLM 验证 ≥20 topic + ≥20 prompt + ≥20 query, dump JSON 形状校验)
- **scripts/dump_planner_samples.py** (新建 — Decision #27 / Task 8 的 Python 重写, 支持 `--industry=<slug>` / `--canned` / `--live` flags, 写 `planner-samples-20-20-20.json`)
- **scripts/ci_check.py** (扩 — Group H 段加 H1/H2/H3 三条规则, 扫 `app/platform/planner/**/*.py`)
- **scripts/python/ci-harness-selftest.py** (扩 — `EXPECTED_POSITIVES` 14 → 17, 加 H1/H2/H3 三条 fixture). **数值溯源**: Session 0' baseline 3 → Session 1' +6 = 9 → Session 1.2' +1 = 10 → Session 2' +4 (G1-G4) = 14 → 本 Session +3 (H1-H3) = **17**. 这是 Python pivot 的本地 selftest 链, 与 master TS 链无关
- **app/platform/planner/__ci_fixtures__/** (新建目录)
  - `H1_planner_no_llm_threading_topic_pool.cifixture.py` — basename 匹配 H1 rule, docstring 故意不 mention `refine_topics_with_llm` / `naturalize_prompts_with_llm` / `rewrite_queries_for_profiles` 三 token (memory `feedback_fixture_naming.md` 教训: content.includes() 自满足陷阱)
  - `H2_intent_drift_query_assembler.cifixture.py` — basename 匹配 H2, docstring 故意不 mention `classify_intent_heuristic`
  - `H3_brand_vocab_query_assembler.cifixture.py` — basename 匹配 H3, docstring 故意不 mention `find_brand_mentions_in_text` / `any_keyword_present`
- **scripts/verify_session_2_1prime.sh** (新建 — Layer 1 Phase Gate 验证脚本, 9 项检查)
- **docs/SESSION_PROGRESS.md** (扩 — 加 "Session 2.1' 已交付" 段)
- **docs/SESSION_2_1_PRIME_DELIVERY.md** (新建 — 收尾时回填实施总结 + 偏差登记 + Phase Gate 三层证据)
- **CLAUDE.md** (扩 — 收尾时加决策 #39 "Session 2.1' Planner LLM Refinement Python 交付")

### 版本警报 (Version Warnings, 列出 9 条避免实施漂移)

1. **Topic Refinement audit 三档阈值固定**: realismScore ≥ 0.7 → approved / [0.5, 0.7) → pending_review / < 0.5 → dropped。任一档位阈值改动需先发 PR 改决策 #27.A 真相源, 不在本 Session 改。
2. **Prompt Naturalization Gate 顺序固定**: Gate 1 (intent drift) → Gate 2a (brand vocabulary) → Gate 2b (品类 prompt 禁品牌泄漏) → Gate 3 (low confidence < 0.5)。任一 Gate 顺序改动需先发 PR 改决策 #27.A。
3. **Query rewrite 3 级 fallback ladder 固定**: `llm` → `fallback_prefix` (persona 短前缀) → `skeleton_only` (原文)。三档命名是观察口径不可改。
4. **rewrite_meta 字段名固定**: `originalText` / `rewrittenText` / `confidence` / `rewriteMode` / `rewriteFallbackReason` / `model` / `rewrittenAt`。Python 命名 snake_case (`original_text` / `rewritten_text` / `rewrite_mode` / 等) 但 JSONB 序列化保 camelCase (与 master 一致, 防止前端 / Admin 反序列化漂移)。
5. **rewrite_meta 写入路径固定**: 必须注入到 `query_executions.attempts[].rewrite_meta` JSONB 子字段, **禁加 query_executions 顶层列**。Harness G3 (Session 2' 已落) 黑名单 `persona_snapshot|persona_profile|agent_profile_snapshot|agent_profile_id|persona_id|rewrite_meta_column|llm_rewritten_text` 等列名持续守卫。
6. **canned transport pattern matching 子串匹配规则固定**: prompt 包含 "品类" / "品牌" / "产品" × "改写主题" / "口语化" / "场景化前缀" 等关键词。模式匹配规则在 `llm_canned_responses.py` 单一真相源, 任何改动需同步 docs。
7. **LLM 调用预算上限**: `LlmClient.maxCalls=50/industry` (Session 1.5' 已锁), 本 Session 三层 LLM 调用合计不得超过此预算; 超过抛 `LlmCallBudgetExceededError`, orchestrator catch 后部分结果返回, 不抛。
8. **Live VOLC smoke 是手工后续任务**: `backend/.env` 的 `VOLC_API_KEY=""` 为空时, Phase Gate 接受 canned-transport dump 作为 LLM-threading 等效证据 (master Session 2.1 G 段 C1 偏差已登记)。本 Session 不强制 Frank 跑 live, 但 dump JSON 形状必须与 live 形状一致。
9. **本 Session 不引入 LLM SDK**: `pyproject.toml` 不加 `langchain` / `openai` / `litellm` 等 SDK, 沿用 Session 1.5' 的 httpx 直调 OpenAI-compat endpoint。引入 SDK 需先发 PR 改决策 (会触发架构层评审)。

---

## §2 · MVP 范围声明 (MVP Scope-Cut Declaration, 决策 #25 规则 10)

### ✅ 本 Session 做 (14 项)

- **Y1**: `app/platform/planner/types.py` 扩 `RealismScore` Literal / `AuditStatus` Literal['approved', 'pending_review', 'rejected'] / `RewriteMeta` Pydantic / `LlmRefinementTopicResult` / `LlmRefinementPromptResult` / `LlmRefinementQueryResult` Pydantic v2 模型
- **Y2**: `app/platform/planner/intent_classifier.py` 新建 — `classify_intent_heuristic(text: str, language: Literal['zh-CN', 'en-US']) -> Intent` 基于关键词 heuristic (中: "推荐"/"哪些"/"如何"/"购买"/"对比" 等; 英: "what"/"which"/"how"/"buy"/"vs" 等), 不调 LLM; 用于 Gate 1 intent-drift 守卫
- **Y3**: `app/platform/planner/llm_canned_responses.py` 新建 — `create_canned_llm_transport()` 返回 `LlmTransport` 函数, 按 prompt 子串模式匹配返回 deterministic JSON; 支持三类 prompt 模式 (Topic-refine / Prompt-naturalize / Query-rewrite) × 三 dimension (品类 / 品牌 / 产品)
- **Y4**: `app/platform/planner/topic_planner.py` 扩 `refine_topics_with_llm({topics, llm, brands_catalog, now}) -> {approved_topics, audit_queue_topics, dropped_topics, llm_calls_made, llm_failure_count}` — 每 skeleton topic 入 approved_topics by reference (graceful degrade), LLM 调一次产生 N variant + realismScore, 三档分流; 失败 catch 累 `llm_failure_count` 不抛
- **Y5**: `app/platform/planner/prompt_generator.py` 扩 `naturalize_prompts_with_llm({prompts, topics, brands_catalog, llm})` — 每条 skeleton prompt LLM 改写 + Gate 1 (intent drift, 用 `classify_intent_heuristic` 比对) + Gate 2a (brand vocabulary 必带, 品牌 / 产品维度 prompt 必须保留至少一个品牌 token) + Gate 2b (品类维度 prompt 不夹品牌名, 决策 #15 守卫) + Gate 3 (low confidence < 0.5 fallback); 通过则 stamp `llm_naturalized_at + naturalize_confidence + rewrite_mode='llm'`; 失败入 `fallbacks[]` 标 reason
- **Y6**: `app/platform/planner/query_assembler.py` 扩 `rewrite_queries_for_profiles({queries, prompts, topics, brands_catalog, llm})` — 每条 query LLM 按 persona 加场景前缀 (zh-CN 用 "姐妹们, " / en-US 用 "Hey folks, ", 4 ProfileGroup 各对应一类前缀); 3 级 fallback ladder: `llm` → `fallback_prefix` → `skeleton_only`; 注入 `attempts[].rewrite_meta = {originalText, rewrittenText, confidence, rewriteMode, rewriteFallbackReason, model, rewrittenAt}`
- **Y7**: `app/platform/planner/topic_pool.py` 扩 `generate_platform_plan` 加 `llm: LlmClient | None = None` 参数; llm=None 时三层 envelope 全 null (skeleton-only path), llm 存在时三层全填充; canned transport 与 live transport 走同一代码路径, 零分支 (决策 #27.B 强约束)
- **Y8**: Pydantic v2 模型: `LlmRefinementResult` 全集合, 字段名 snake_case, model_config dict alias 序列化为 camelCase 与 master JSONB 一致
- **Y9**: Alembic migration `<timestamp>_session_2_1prime_planner_llm_refinement.py` — `platform_topics` 加 `realism_score DECIMAL(3,2)` + `llm_refined_at TIMESTAMPTZ` + `audit_status VARCHAR(20)` + CHECK (`audit_status IN ('approved','pending_review','rejected')`) + 索引 `idx_topics_audit_status` / `idx_topics_realism_score`; `platform_prompts` 加 `llm_naturalized_at TIMESTAMPTZ` + `naturalize_confidence DECIMAL(3,2)` + 索引 `idx_prompts_naturalize_confidence`; `query_executions` 零顶层列变更 (G3 持续守卫); SQLAlchemy 2.0 模型同步
- **Y10**: scripts/dump_planner_samples.py 新建 — Python 重写 master Session 2.1 G 段 dump 脚本, flags `--industry=beauty-personal-care` (默认) / `--canned` (默认 CI 路径) / `--live` (要求 VOLC_API_KEY); 接 InMemory beauty industry seed (Session 1.5' 提供) + canned LLM transport, 写 `planner-samples-20-20-20.json` (≥20 topic + ≥20 prompt + ≥20 query 完整 personaSnapshot + rewriteMeta), 是 Frank Layer 3 视觉审查 query 真实度的入口
- **Y11**: Group H Harness 三条规则 + 自验证 fixture (决策 #21.C, scripts/ci_check.py 扩):
  - **H1** `planner-must-invoke-llm` — 扫 `app/platform/planner/**/*.py`, basename 匹配 `topic_pool.py` 时要求三 token `refine_topics_with_llm` + `naturalize_prompts_with_llm` + `rewrite_queries_for_profiles` 齐备
  - **H2** `query-rewrite-must-preserve-intent` — basename 匹配 `query_assembler.py` 时要求 token `classify_intent_heuristic` 出现 (Gate 1 intent-drift 守卫被卸时拦截)
  - **H3** `query-rewrite-must-preserve-brand-vocab` — basename 匹配 `query_assembler.py` 时要求 `find_brand_mentions_in_text` + `any_keyword_present` 双 token (Gate 2a + Gate 2b 守卫被卸时拦截)
  - 3 个 self-seeded fixture (basename 匹配 rule pattern, docstring 故意不 mention 必要 token)
  - selftest EXPECTED_POSITIVES 14 → 17 (Python pivot 链, 与 master TS 链无关)
- **Y12**: pytest 单测扩 ≥ 80% 覆盖 — 新增 5 测试文件 + 扩 2 现有文件; 端到端集成测试新增 1 个; 总计 ≥ 65 新例 (master 实绩) 落在 `tests/unit/platform/planner/`; coverage 8 v8 实测必须 ≥ 80% (统计模块 `app/platform/planner/`)
- **Y13**: Frank Layer 3 视觉审查在 preview 环境 — 触发 `python scripts/dump_planner_samples.py --industry=beauty-personal-care --canned`, 上传 `planner-samples-20-20-20.json` 到 preview `https://genpano-preview.vercel.app/admin/planner-samples` (Y10 静态页), Frank 抽 5-10 条 query 看 realism / 看 fallback ladder 分布是否合理
- **Y14**: 文档同步 — `docs/SESSION_PROGRESS.md` 加 Session 2.1' 段; `docs/SESSION_2_1_PRIME_DELIVERY.md` 新建; `CLAUDE.md` 加决策 #39

### ❌ 本 Session 不做 (10 项延后, 决策 #25 规则 10 强制)

- **N1** Response 采集 (Celery worker 消费 query_executions queue, 写入 ai_responses) — 推 **Session 3'**
- **N2** 分析 pipeline 真实跑 (brand_detector / sentiment / citation_extractor) — 推 **Session 3'**
- **N3** 用户态 FastAPI router (`/brands/{id}` 等) — 推 **Session 3' / 4a'** (依赖 User/Project ACL)
- **N4** MCP Server (`genpano_get_citations` 等) — 推 **Session 3'**
- **N5** Citation Tier CRUD (DB seed + Admin API) — 推 **Session 3' / A1'**
- **N6** Cost 监控告警 (PRD §4.9.4) — 推 **Session 3' / A1'**
- **N7** Multi-turn dialogue Query (`Query.followUpPromptId`) — Phase 2, 决策 #26.C2
- **N8** Live VOLC smoke 跑通 — 手工后续任务, 接受 canned-transport dump 作为等效证据 (master Session 2.1 G 段 C1 偏差已登记)
- **N9** Frontend 修改 — Frank 在 master 决策 #21 已说 "frontend 只是当作原型图", 本 Session 零 JSX/TSX 修改; preview 端的 `planner-samples` 静态展示页留给 Session 4b' 翻译时一并落
- **N10** 历史数据回填 — Session 2' 跑过的 17 topic / 400 prompt / 2614 query 不需要 backfill realism_score, 本 Session migration 加列 nullable, 历史行留 NULL

---

## §3 · STOP Triggers (决策 #25 规则 12)

> **Type A · 环境失败**: 暂停实施, 不做 best-effort, 立即报告 Frank 等待环境就绪。

- **A1**: pyproject.toml 缺 `httpx` (LLM client 必需) — Step 0 `pip install httpx`, 不 STOP, 但失败需报告
- **A2**: PostgreSQL preview 实例不可达, alembic 无法连库 → STOP Type A, 等 Frank 修复 DATABASE_URL
- **A3**: Session 2' 模块缺失 (F7 ls 空) → STOP Type A, 等 Session 2' 重新交付
- **A4**: Session 1.5' `LlmClient` 类签名变更 → STOP Type A, 走真相源对齐 (复用 client, 不新建)
- **A5**: alembic head 与本地 schema.py 冲突 → STOP Type A, 等 Frank `alembic stamp head` 修复

> **Type B · 真相源冲突**: 暂停实施, 不写代码, 回到 Frank 对齐真相源。

- **B1**: PRD §4.10.3.A 23 行矩阵被改 (F6 grep 结果数变化) → STOP Type B
- **B2**: 决策 #27 三层 LLM 模块名变更 → STOP Type B (本 Session 是其 Python 重写, 名称不可漂)
- **B3**: 决策 #26.C1 / Harness G3 黑名单字段变更 → STOP Type B (本 Session rewrite_meta 沿用相同契约)
- **B4**: 决策 #15 / PRD §4.6.0a 与本 Prompt §2 Gate 2b 描述矛盾 → STOP Type B (品类 prompt 不夹品牌名是硬约束)
- **B5**: Session 2' 交付的 `app/platform/planner/types.py` Pydantic 模型字段名与本 Session 引用的不一致 → STOP Type B

> **Type C · 范围溢出**: 暂停实施, 回到 §2 范围内。

- **C1**: 想加 Response 采集 / Celery worker → 推 Session 3'
- **C2**: 想加用户态 API → 推 Session 3' / 4a'
- **C3**: 想加 query_executions 顶层列 (任何形如 `rewrite_meta_column` / `llm_rewritten_text` 等列名) → 严禁, 决策 #26.C1 + Harness G3
- **C4**: 想新增 LLM SDK 依赖 (langchain / openai / litellm) → 严禁, 沿用 Session 1.5' httpx 直调
- **C5**: 想降低 ≥ 80% pytest 覆盖率阈值 → 严禁, 决策 #21.A 强约束
- **C6**: 想修改 Session 1.5' / Session 2' 已交付模块 (除了在其上 wire LLM 函数 / 加 audit 字段, 不动 plan_topics / generate_prompts / assemble_queries 主体) → 严禁
- **C7**: 想修改前端 (frontend/src/**.jsx 或 .tsx) → 严禁, 决策 #21 frontend 视为原型状态

---

## §4 · Phase Gate (3 层验证)

### Layer 1 · `scripts/verify_session_2_1prime.sh` (9 项自动化检查, Step 11 必跑)

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "=== Session 2.1' Phase Gate Layer 1 ==="

# L1.1 · ruff lint 全绿
echo "[L1.1] ruff..."
ruff check app/platform/planner/ tests/unit/platform/planner/ scripts/dump_planner_samples.py

# L1.2 · mypy 类型检查全绿 (本 Session 新增模块)
echo "[L1.2] mypy..."
mypy app/platform/planner/ --strict

# L1.3 · pytest unit ≥ 80% 覆盖 (planner/ 子目录限定)
echo "[L1.3] pytest unit + coverage..."
pytest tests/unit/platform/planner/ --cov=app/platform/planner --cov-fail-under=80 --cov-report=term-missing

# L1.4 · pytest integration (dump scripts 端到端)
echo "[L1.4] pytest integration..."
pytest tests/integration/platform/planner/

# L1.5 · alembic upgrade + downgrade smoke (验证 migration 双向可执行)
echo "[L1.5] alembic round-trip..."
alembic upgrade head
alembic downgrade -1
alembic upgrade head

# L1.6 · psql 验证 query_executions 零新增顶层列 (决策 #26.C1 / G3 守卫)
echo "[L1.6] psql verify zero query_executions top-level cols added..."
psql "$DATABASE_URL" -c "SELECT column_name FROM information_schema.columns WHERE table_name='query_executions' AND column_name IN ('persona_snapshot','persona_profile','agent_profile_snapshot','agent_profile_id','persona_id','rewrite_meta_column','llm_rewritten_text','rewritten_at_column');" | grep -E "0 rows" || (echo "FAIL: forbidden column added to query_executions"; exit 1)

# L1.7 · Group H Harness 全绿
echo "[L1.7] ci_check.py Group H..."
python scripts/ci_check.py --group=H

# L1.8 · Harness selftest 17 / 17
echo "[L1.8] ci_harness_selftest..."
uv run python scripts/python/ci-harness-selftest.py | grep -E "selftest: PASS  \(17 / 17 fixture expectations met\)"

# L1.9 · dump_planner_samples 端到端 + JSON 形状校验
echo "[L1.9] dump samples smoke..."
python scripts/dump_planner_samples.py --industry=beauty-personal-care --canned --output=/tmp/planner-samples-test.json
jq -e '.topics | length >= 20' /tmp/planner-samples-test.json
jq -e '.prompts | length >= 20' /tmp/planner-samples-test.json
jq -e '.queries | length >= 20' /tmp/planner-samples-test.json
jq -e '.queries[0].attempts[0].rewrite_meta.rewriteMode' /tmp/planner-samples-test.json
jq -e '.topics[0].realismScore' /tmp/planner-samples-test.json
jq -e '.prompts[0].naturalizeConfidence' /tmp/planner-samples-test.json

echo "=== Phase Gate Layer 1 ALL PASS ==="
```

### Layer 2 · Harness selftest 17 / 17 (Step 11 必跑)

新增 3 fixture (H1 / H2 / H3), `scripts/python/ci-harness-selftest.py` 的 `EXPECTED_POSITIVES` 从 Session 2' 终态的 14 扩到 17, 最终输出必须含:

```
● selftest: PASS  (17 / 17 fixture expectations met)
```

**数值溯源**: Session 0' baseline 3 (D8/D9/D10) → Session 1' +6 (F1/F2/F3/F4-1/F4-2/F4-3) = 9 → Session 1.2' +1 (F5) = 10 → Session 2' +4 (G1/G2/G3/G4) = 14 → 本 Session +3 (H1/H2/H3) = **17**. 这是 Python pivot 的本地 selftest 链, 与 master TS 链无关。

### Layer 3 · Frank 视觉审查 + Preview 环境验证 (S1-S5)

> 决策 #30 (preview env 强约束) + 决策 #25 规则 7 (closing consistency check)

- **S1**: 本地 `bash scripts/verify_session_2_1prime.sh` 全绿
- **S2**: GitHub Actions CI 跑该 verify 脚本全绿 + Render preview 后端部署成功
- **S3**: Frank 在 preview 环境跑 `curl -X POST https://genpano-api-preview.onrender.com/admin/api/v1/platform/industries/beauty-personal-care/plan/generate -H "Cookie: <admin_session>" | jq` (Session 2' 已交付的 admin endpoint, 本 Session 让其返回的 plan 中 topic.realism_score / prompt.naturalize_confidence / query.attempts[0].rewrite_meta 三档字段非 null)
- **S4**: Frank 在 preview 跑 dump 脚本 (本地或 GitHub Actions artifact 下载 `planner-samples-20-20-20.json`), 抽 5-10 条 query 文本 **逐条肉眼审查**:
  - 文本是否像真人会问的话 (Stripe-style sanity check)?
  - 品类维度的 query 文本是否 0 品牌名泄漏?
  - persona 前缀分布是否合理 (zh-CN 4 ProfileGroup 各覆盖, en-US 只在 ChatGPT)?
  - rewriteMode 分布是否 `llm` ≥ 50% / `fallback_prefix` ≥ 20% / `skeleton_only` ≤ 10% (canned transport 期望)?
- **S5**: Frank 主观批准 "query 文本质量 ≥ master Session 2.1 同款 dump" → Phase Gate 通过

> Frank 拒绝 → 走 Step 11+1 加 LLM prompt template 调优, 不算 regression

---

## §5 · 12-Step Delivery Sequence

> **决策 #25 规则 10 + 规则 11**: 每 Step 必须独立 commit, commit 标题格式 `Session 2.1' Step <N>: <主题>`, 纯 ASCII 无特殊 Unicode (规则 7 实施过程 commit-time 检查)。

| Step | 主题 | 主要文件 | 验证 |
|---|---|---|---|
| **0** | 分支 + deps | `git checkout -b session-2-1prime` from main; `pip install httpx>=0.27` (若未装) | `git status`, `pip list` |
| **1** | Pydantic 类型 + intent_classifier | `app/platform/planner/types.py` (扩) + `intent_classifier.py` (新建) + `tests/.../test_intent_classifier.py` (≥8 例) | `pytest tests/unit/platform/planner/test_intent_classifier.py` 全绿 |
| **2** | canned transport | `app/platform/planner/llm_canned_responses.py` (新建, 三类模式 × 三 dimension = 9 patterns) + `tests/.../test_llm_canned_responses.py` (≥8 例) | `pytest tests/.../test_llm_canned_responses.py` 全绿 |
| **3** | refine_topics_with_llm | `topic_planner.py` (扩) + `tests/.../test_topic_planner_llm.py` (≥10 例覆盖三档 / determinism / failure / budget) | `pytest tests/.../test_topic_planner_llm.py` 全绿 |
| **4** | naturalize_prompts_with_llm | `prompt_generator.py` (扩, 实现 Gate 1/2a/2b/3) + `tests/.../test_prompt_generator_llm.py` (≥12 例) | `pytest tests/.../test_prompt_generator_llm.py` 全绿 |
| **5** | rewrite_queries_for_profiles | `query_assembler.py` (扩, 3 级 fallback ladder + `attempts.rewrite_meta` 注入) + `tests/.../test_query_assembler_llm.py` (≥13 例) | `pytest tests/.../test_query_assembler_llm.py` 全绿 |
| **6** | topic_pool LLM threading | `topic_pool.py` (扩 `llm` 参数) + `tests/.../test_topic_pool_llm.py` (扩 ≥18 例覆盖三层联动 / determinism / 桶失败) | `pytest tests/.../test_topic_pool_llm.py` 全绿 |
| **7** | golden_beauty LLM-on path | `tests/.../test_golden_beauty_llm.py` (扩 ≥6 新例: envelope 三层联动 + determinism + canned 行为锁) | `pytest tests/.../test_golden_beauty_llm.py` 全绿 |
| **8** | Alembic migration + SQLAlchemy 模型 | `alembic/versions/<timestamp>_session_2_1prime_planner_llm_refinement.py` 新建 + `app/models/platform.py` 扩 + 集成测试 | `alembic upgrade head` + `alembic downgrade -1` + `alembic upgrade head` 三连绿 |
| **9** | dump 脚本 + 集成测试 | `scripts/dump_planner_samples.py` 新建 + `tests/integration/platform/planner/test_dump_planner_samples.py` 新建 | `python scripts/dump_planner_samples.py --industry=beauty-personal-care --canned` 输出 ≥20 / ≥20 / ≥20 三段 |
| **10** | Group H Harness + selftest | `scripts/python/ci-check.py` 加 H1/H2/H3 + 3 fixture + `scripts/python/ci-harness-selftest.py` EXPECTED_POSITIVES 14 → 17 | `uv run python scripts/python/ci-check.py --group=H` 全绿 + `uv run python scripts/python/ci-harness-selftest.py` 17/17 |
| **11** | Phase Gate Layer 1 + Layer 2 | `scripts/verify_session_2_1prime.sh` 新建 + `bash verify_session_2_1prime.sh` 全绿 | Layer 1 9 项 + Layer 2 selftest 17/17 |
| **12** | docs 同步 + Layer 3 + Frank 验收 | `docs/SESSION_PROGRESS.md` 扩 + `docs/SESSION_2_1_PRIME_DELIVERY.md` 新建 + `CLAUDE.md` 决策 #39 草稿 + Frank Layer 3 S1-S5 走完 | Frank 主观批准 |

---

## §6 · Delivery Report Template (Step 12 收尾)

> **决策 #25 规则 3 + 规则 7**: 收尾时 Claude Code 必须填 `docs/SESSION_2_1_PRIME_DELIVERY.md`, 模板如下。

### Phase Gate 三层证据

**Layer 1**: 粘贴 `bash scripts/verify_session_2_1prime.sh` 完整 stdout, 9 项 ALL PASS

**Layer 2**: 粘贴 `uv run python scripts/python/ci-harness-selftest.py` stdout, 含 `selftest: PASS  (17 / 17 fixture expectations met)`

**Layer 3**: 粘贴 Frank S1-S5 验收记录 (preview URL + admin endpoint curl JSON 截图 + dump JSON 截屏 + Frank 主观批准截图 / 引述)

### 偏差登记 (规则 3 强制)

如实施过程发现与真相源不可调和冲突, 列入 C1/C2/...:

```markdown
**C1 (示例)**: ...
- 真相源: docs/PRD.md §X.Y
- 偏离: ...
- 理由: ...
- 后续 migration: ...
```

如零偏差, 写 "本 Session 实施过程未触发偏差登记"。

### 真相源同步

收尾必须验证以下真相源仍未漂移 (规则 7 closing loop):

- 重跑 §0 F1-F8 全部命中预期
- `docs/SESSION_PROGRESS.md` 加 "Session 2.1' 已交付" 段, 标注 pytest 数 / coverage / Harness selftest 17/17
- `CLAUDE.md` 加决策 #39 草稿块 (见下)

### 决策 #39 草稿 (Step 12 + Frank approval 后正式落 CLAUDE.md)

```markdown
39. **Session 2.1' · Planner LLM Refinement Python 交付 (2026-04-XX)**: 按 `docs/CLAUDE_CODE_SESSIONS_PYTHON.md` Session 2.1' 范围落地三层 LLM 增强 Python 重写 — Topic Refinement (LLM 给 realismScore + variant 扩展 + audit 三档) × Prompt Naturalization (LLM 把 skeleton prompt 改写成口语化 + naturalizeConfidence + Gate 1/2a/2b/3) × Query Profile-Aware Rewrite (LLM 按 persona 给 query 加场景化前缀 + 3 级 fallback ladder)。背景: Session 2' 落地的是纯规则模板 Pipeline, Frank 验收 master 时指出生成 query 像 "机器人语料"; 本 Session 在 Session 2' 同一管线上插入 3 层 LLM 后处理, **不改任何 schema 顶层结构**, 只在 envelope 里追加 audit 字段, 同时严格 honor 决策 #26.C1 (rewrite_meta 进 attempts JSONB, 禁加列, Harness G3 持续守卫)。

    **A. 三层 LLM 编排** (`app/platform/planner/`): refine_topics_with_llm / naturalize_prompts_with_llm / rewrite_queries_for_profiles, 全部走 ports/adapters 范式, 单测走 InMemory + canned transport.

    **B. Canned LLM Transport** (`llm_canned_responses.py`): 按 prompt 子串模式匹配 (品类/品牌/产品 × Topic-refine/Prompt-naturalize/Query-rewrite) 返回 deterministic JSON; CI 默认走 canned, live 跑 VOLC_API_KEY, 代码零分支.

    **C. Alembic Migration** (`<timestamp>_session_2_1prime_planner_llm_refinement.py`): platform_topics 加 3 列 (realism_score / llm_refined_at / audit_status + CHECK + 索引); platform_prompts 加 2 列; query_executions 零顶层列变更, 加 COMMENT 文档化 attempts JSONB 子字段.

    **D. Group H Harness 三条新规则**: H1 planner-must-invoke-llm / H2 query-rewrite-must-preserve-intent / H3 query-rewrite-must-preserve-brand-vocab; 3 fixture self-seeded; selftest EXPECTED_POSITIVES 14 → 17 (Python pivot 链, 与 master TS 链无关).

    **E. pytest 覆盖**: 新增 5 测试文件 + 扩 2 现有 + 1 集成测试; 总例数 ≥ 65; coverage v8 实测 ≥ 80%.

    **F. dump_planner_samples.py 端到端**: 跑 `--industry=beauty-personal-care --canned` 输出 ≥20+20+20 sample, Frank Layer 3 视觉审查通过.

    **G. 偏差登记**: 见 `docs/SESSION_2_1_PRIME_DELIVERY.md` §偏差登记 (如零偏差则空).
```

---

## §7 · Closing Consistency Loop (决策 #25 规则 7)

> Step 12 + Frank approval 之后, Claude Code 必须再次跑 §0 F1-F8 全部命令, 验证真相源未在实施过程中被改动. 任一漂移 → 在 §6 偏差登记落 C 段, 同步至 `CLAUDE.md` 决策 #39.

```bash
# 重跑 §0 全部 grep
bash <<'EOF'
grep -n "^29\.\|^30\.\|^31\.\|^32\." CLAUDE.md | head -20
grep -nE "refineTopicsWithLlm|naturalizePromptsWithLlm|rewriteQueriesForProfiles|H1|H2|H3" CLAUDE.md | head -40
grep -nE "persona_snapshot|attempts.*JSONB|browser_profile|rewrite_meta|G3" CLAUDE.md | head -20
grep -nE "Session 2'|skeleton|17 topic|400 prompt" docs/SESSION_PROGRESS.md | head -20
grep -n "Session 2\.1'" docs/REPLAN_2026_04_26.md | head -10
grep -nE "§4\.0\.1a|§4\.10\.3\.A|§4\.2\.5|navigational" docs/PRD.md | head -20
ls app/platform/planner/ | head -20
grep -nE "httpx|pydantic|fastapi|sqlalchemy|pytest" pyproject.toml | head -30
EOF
```

如全部命中预期 → 收尾完成. 否则 → 偏差登记.

---

## §8 · 10 Final Reminders (Claude Code 实施前必读)

1. **真相源不重抄, 只引用注释**: 实现代码引用真相源用 `# See PRD §4.10.3.A (23-row matrix)` 这种风格的注释, **绝不**把 PRD / DATA_MODEL / 决策内容拷贝进代码注释 (规则 1).
2. **commit 标题纯 ASCII**: `Session 2.1' Step <N>: <主题>`, 中文主题 OK, 但禁 emoji / §  / ✅ / — 等特殊 Unicode (memory `feedback_genpano_session_commit_rule.md`).
3. **常量单一入口**: `REALISM_THRESHOLD_APPROVED = 0.7` / `REALISM_THRESHOLD_AUDIT = 0.5` / `NATURALIZE_CONFIDENCE_FALLBACK = 0.5` / `INTENT_DRIFT_TOLERANCE = 0` 等阈值在 `app/platform/planner/types.py` 或 `intent_classifier.py` 单一定义, 严禁散布魔法值.
4. **Pydantic v2 不是 v1**: 用 `model_validator` / `field_validator` / `ConfigDict`, 禁 `@validator` / `class Config` (Pydantic v1 风格); 字段名 snake_case, JSONB 序列化 alias 为 camelCase 与 master 一致.
5. **SQLAlchemy 2.0 async 不是 1.x sync**: 用 `select()` / `async with AsyncSession()` / `await session.execute()`, 禁 `Query.filter().all()` (1.x 风格).
6. **零 query_executions 顶层列**: 决策 #26.C1 + Harness G3 持续守卫. 任何加列念头 → 立即 STOP Type C, 改用 `attempts[].rewrite_meta` JSONB 子字段.
7. **零 frontend 修改**: 决策 #21 frontend 视为原型状态, 本 Session 范围零 JSX/TSX. preview 端的 `planner-samples` 静态展示页留给 Session 4b' 翻译时一并落.
8. **InMemoryKgRepositories 是单测唯一数据源**: 单测零网络 / 零 DB / 零 Prisma 解析, 沿用 Session 1.5' / 2' 的 InMemory 模式.
9. **每 Step 跑 verify 后 commit**: Step 11 之前每 Step 完成必须先跑相关 pytest 子集 + ruff, 全绿后 commit; Step 11 跑全量 `verify_session_2_1prime.sh` 一次过.
10. **收尾必跑 closing loop §0 + §7**: Step 12 收尾前 Claude Code 必须再次跑一遍 §0 F1-F8 + §7 闭环, 真相源任一漂移在 §6 偏差登记落 C 段, 同步 CLAUDE.md 决策 #39.

---

> **本 Prompt 版本**: v1.0, 2026-04-26
> **下一个 Session**: Session 3' · 分析引擎 + 用户态 API + MCP Server (M3 Milestone 末)
> **关联 Session**: Session 2' (依赖, 已交付 skeleton Pipeline) / Session 1.5' (依赖, 已交付 KG 数据 + LlmClient) / Session 3' (后继, 消费本 Session 的 audited topic / naturalized prompt / rewritten query)
