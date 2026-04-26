# Session 2' · Planner Pipeline (Topic → Prompt → Query, Python 重写) — Prime Prompt

> **本文档是发给 Claude Code 的 Session Prompt 真相源**, 严格遵守 CLAUDE.md 决策 #25 的 12 条 Prompt 编写公约。Claude Code 必须按 §0 → §8 顺序读完后才能动手写代码。
>
> **本 Session 定位**: M3 Milestone 第一块基石 — 复用 master Session 2 (决策 #26) 的 Planner 算法逻辑, 用 Python 重写 (FastAPI / SQLAlchemy 2.0 async / pytest), 落到合并仓 `C:\Users\frank.wang\genpano` (jotamotk/GenPano.git fork)。
>
> **依赖**: Session 1.5' (KG 提供 brands / products / categories / 关系边, 决策 #37 占位)。
>
> **本 Session 不依赖**: Session 1' / 1.2' (Adapter 框架与 Planner 解耦, Planner 是纯函数 + DB 读, 不调任何浏览器或外部 LLM)。

---

## §0 · 前置 Grep 契约 (Pre-Flight Grep Contract)

> **决策 #25 规则 2**: Claude Code 开工第一批动作必须先跑下列 grep / read 命令自证真相源未漂移。任一不一致 → STOP (Type B), 不写代码, 回到 Frank 对齐。

```bash
# F1 · 验证最近 4 条 CLAUDE.md 决策 (#29 / #30 / #31 / #32) 仍在 (Python pivot / preview env / branch-per-session / 工作仓切换)
grep -n "^29\.\|^30\.\|^31\.\|^32\." CLAUDE.md | head -20

# F2 · 验证决策 #26 (master Session 2 算法真相源) 的 Planner 模块清单 + Harness G1/G2/G3/G4 仍在
grep -nE "intent-engine-locale-matrix|category-purity|topic-planner|prompt-generator|query-assembler|sample-guard|topic-pool|G1|G2|G3|G4" CLAUDE.md | head -40

# F3 · 验证 PRD §4.10.3.A 23 行 Intent×Engine×Locale 矩阵真相源仍在
grep -nE "§4\.10\.3\.A|EXPECTED_EXPLICIT_ROW_COUNT|23 行|Intent.*Engine.*Locale" docs/PRD.md | head -20

# F4 · 验证 PRD §4.2.5 + §4.2.3a + §4.6.0a 仍在 (Topic 维度 / ProfileGroup / 提及率非品牌口径)
grep -nE "§4\.2\.5|§4\.2\.3a|§4\.6\.0a|品类.*Topic|non-brand|ProfileGroup" docs/PRD.md | head -20

# F5 · 验证 REPLAN §4 Session 2' 范围 + Phase Gate 仍如本 Prompt 描述
grep -n "Session 2'" docs/REPLAN_2026_04_26.md | head -10

# F6 · 验证 SESSION_PROGRESS 中 Session 1.5' 已宣绿 (KG 数据可用)
grep -nE "Session 1\.5'|KG|knowledge graph|industries.*beauty" docs/SESSION_PROGRESS.md | head -20

# F7 · 验证决策 #26.C1 (persona snapshot 进 attempts JSONB, 不加 query_executions 顶层列) 真相源
grep -nE "persona_snapshot|attempts.*JSONB|browser_profile|G3|顶层列" CLAUDE.md | head -20

# F8 · 验证 pyproject.toml 已含 Session 2' 必需依赖 (Session 0' 已落地基础: fastapi / sqlalchemy / asyncpg / alembic / pydantic / pytest)
grep -nE "fastapi|sqlalchemy|asyncpg|alembic|pydantic|pytest|httpx" pyproject.toml | head -30
```

**如何使用 F1-F8 结果**:
- F1 / F2 / F3 / F4 / F7 任一未命中预期字段 → STOP Type B (真相源漂移), 暂停实施, 回到 Frank 对齐
- F5 描述与本 Prompt §2 不一致 → STOP Type B, 以 REPLAN §4 为准
- F6 显示 Session 1.5' 未宣绿 → STOP Type A (依赖未就绪), 暂停实施
- F8 缺少基础依赖 → 走 Step 0 在本 Session 内 `pip install` 补齐 (不 STOP)

---

## §1 · 真相源索引 (Truth Source Index)

> **决策 #25 规则 5/6/7**: 本 Session **引用 / 修改** 的全部真相源, 锚定到最小单元。

### 1.1 引用 (read-only, 不得修改)

| 真相源 | 段号 | 用途 |
|---|---|---|
| `CLAUDE.md` | 决策 #25 (12 条 Prompt 公约) | Prompt 编写规范 |
| `CLAUDE.md` | 决策 #26 (master Session 2 算法) | 复用算法语义, A-H 段全文必读 |
| `CLAUDE.md` | 决策 #26.A (Planner 模块清单) | 8 个模块名映射: `intent-engine-locale-matrix.ts` → `intent_engine_locale_matrix.py` 等 |
| `CLAUDE.md` | 决策 #26.C1 (persona 进 attempts JSONB) | 严禁加 `query_executions` 顶层列 (G3 拦截黑名单) |
| `CLAUDE.md` | 决策 #26.C2 (多轮对话延后) | Query 仍是单轮模型, `personaSnapshot` 单次快照 |
| `CLAUDE.md` | 决策 #26.C3 (用户态 API 延后) | 本 Session 只交付 3 个 admin 只读端点 |
| `CLAUDE.md` | 决策 #26.E (Group G Harness 4 条) | G1-G4 Python 重写 (锚 EXPECTED_EXPLICIT_ROW_COUNT=23 / category purity / no persona column / no hardcoded engine list) |
| `CLAUDE.md` | 决策 #15 (提及率 non-brand 口径) | 品类维度 Topic + Prompt 禁夹品牌名, Planner 配额品类 ≥ 40% |
| `CLAUDE.md` | 决策 #21.D (PRD §4.10.3.A 23 行矩阵) | 矩阵作为单一真相源, navigational 全线 reducedFactor=0.3 |
| `CLAUDE.md` | 决策 #21.A (Harness G 段在 Session 0' 已埋桩) | Session 2' 只补具体 grep 实现 + fixtures |
| `CLAUDE.md` | 决策 #29-#32 (Python pivot / preview env / branch / repo) | 横切要求 |
| `docs/PRD.md` | §4.0.1a (Planner Bottom-Up) | Planner 算法语义 |
| `docs/PRD.md` | §4.10.3.A (Intent×Engine×Locale 23 行) | 矩阵真相源, EXPECTED_EXPLICIT_ROW_COUNT 锚定 |
| `docs/PRD.md` | §4.2.3a (ProfileGroup) | profile 采样维度, 4 个 default group |
| `docs/PRD.md` | §4.2.5 (Topic 维度 = 品类 / 品牌 / 产品) | 三维度配额 + 锚定逻辑 |
| `docs/PRD.md` | §4.2.4 (Prompt × Intent × Language) | 4 Intent + zh-CN 全线 + en-US 仅 ChatGPT |
| `docs/PRD.md` | §4.6.0a (UI 不暴露开发约束) | Planner 内部错误不进 UI 文案 |
| `docs/DATA_MODEL.md` | §1.5 (platform_topics) | dimension / topic_name / mention_count 等 |
| `docs/DATA_MODEL.md` | §1.6 (platform_prompts) | prompt_text / intent / language / applies_to_engines |
| `docs/DATA_MODEL.md` | §2.5 (query_executions / attempts JSONB) | persona_snapshot 进 attempts.browser_profile, 严禁顶层列 |
| `docs/REPLAN_2026_04_26.md` | §4 Session 2' | 范围 / 依赖 / Phase Gate |
| `docs/REPLAN_2026_04_26.md` | §6.5 (Harness Python 分布) | A-H 各组分配 |
| `docs/REPLAN_2026_04_26.md` | §7 (4 行业不变) | beauty / luxury / food / fashion |
| `docs/SESSION_PROGRESS.md` | Session 1.5' 段 | KG 表名 + seed 命令 |
| `docs/SESSION_1_5_PRIME_PROMPT.md` (read-only 参考) | §1.1 / §5 | KG repo 接口形状 |
| `app/platform/db/ports.py` (Session 1.5' 已建) | KgRepositories 接口 | Planner 通过此接口读 KG, 不直接 touch SQLAlchemy |
| `app/platform/db/memory_repo.py` (Session 1.5' 已建) | InMemoryKgRepositories | 单测唯一来源 |

### 1.2 修改 (write, 本 Session 在合并仓 `C:\Users\frank.wang\genpano` 内的产出)

| 真相源 | 段号 / 文件 | 操作 |
|---|---|---|
| `app/platform/planner/__init__.py` | new | export 8 模块的 public API |
| `app/platform/planner/intent_engine_locale_matrix.py` | new | PRD §4.10.3.A 23 行矩阵单一真相源, `EXPECTED_EXPLICIT_ROW_COUNT = 23` + `lookup_matrix(intent, engine, locale)` |
| `app/platform/planner/category_purity.py` | new | `validate_category_topic_purity` / `validate_category_prompt_purity` + 2 异常类 |
| `app/platform/planner/topic_planner.py` | new | `generate_topics(repos, industry_id) -> list[PlannedTopic]` 三维度 |
| `app/platform/planner/prompt_generator.py` | new | `generate_prompts(topics, brands_catalog) -> list[PlannedPrompt]` |
| `app/platform/planner/agent_profiles.py` | new | FNV-1a 确定性 hash + 8 preset (Session 1' Python 已含 profile-sampler 引用即可, Phase A 决议) |
| `app/platform/planner/query_assembler.py` | new | `assemble_queries(prompts, profiles) -> list[PlannedQuery]`, persona 进 attempts.browser_profile envelope |
| `app/platform/planner/sample_guard.py` | new | `meets_category_quota(topics, min_share=0.4)` |
| `app/platform/planner/topic_pool.py` | new | 上层编排 `generate_platform_plan(industry_slug, repos, *, llm=None, intents=None)` (llm=None 跳过 LLM, 留给 Session 2.1' 填) |
| `app/platform/planner/seed/profile_groups.py` | new | 4 default ProfileGroup seed |
| `app/platform/planner/types.py` | new | Pydantic v2 dataclass: `PlannedTopic` / `PlannedPrompt` / `PlannedQuery` / `MatrixEntry` |
| `app/api/admin/v1/platform/router.py` | new | FastAPI router 挂 3 端点 |
| `app/api/admin/v1/platform/topics_endpoint.py` | new | `GET /admin/api/v1/platform/industries/{slug}/topics` |
| `app/api/admin/v1/platform/prompts_endpoint.py` | new | `GET /admin/api/v1/platform/topics/{topic_id}/prompts` |
| `app/api/admin/v1/platform/plan_generate_endpoint.py` | new | `POST /admin/api/v1/platform/industries/{slug}/plan/generate` (dry-run) |
| `alembic/versions/<ts>_session_2prime_planner_baseline.py` | new | `platform_topics` / `platform_prompts` / `query_executions` / `agent_profile_snapshots` 4 表, CHECK 约束走 raw `op.execute()`, **零 persona 顶层列** |
| `tests/unit/platform/planner/test_*.py` | new | 9 套单测 (matrix / purity / topic_planner / prompt_generator / agent_profiles / query_assembler / sample_guard / topic_pool / golden_beauty) |
| `tests/integration/admin_api/test_platform_router.py` | new | 3 endpoint 集成测试 (httpx AsyncClient) |
| `scripts/ci/harness_group_g.sh` | new | G1/G2/G3/G4 grep 实现 (Session 0' 已留组占位) |
| `scripts/ci/harness_selftest.py` | edit | EXPECTED_POSITIVES 数组追加 G1-G4 fixture 期望 |
| `tests/fixtures/__ci_fixtures__/G1_matrix_row_count_wrong.cifixture.py` | new | 故意写 `EXPECTED_EXPLICIT_ROW_COUNT = 22` |
| `tests/fixtures/__ci_fixtures__/G2_purity_guard_missing_topic_planner.cifixture.py` | new | docstring 内**禁** mention `validate_category_topic_purity` 字符串 |
| `tests/fixtures/__ci_fixtures__/G2_purity_guard_missing_prompt_generator.cifixture.py` | new | docstring 内**禁** mention `validate_category_prompt_purity` |
| `tests/fixtures/__ci_fixtures__/G3_persona_column.cifixture.sql` | new | 故意 ALTER TABLE 加 `persona_snapshot` 列 |
| `tests/fixtures/__ci_fixtures__/G4_hardcoded_engines.cifixture.py` | new | 故意写 `engines = ['doubao', 'deepseek-CN', 'chatgpt']` 数组字面量, 非 matrix lookup |
| `docs/SESSION_PROGRESS.md` | edit | 追加 "Session 2' 宣绿 (yyyy-mm-dd)" + 9 段 verify evidence |
| `docs/CLAUDE_CODE_SESSIONS_PYTHON.md` | edit | Session 2' 行从 "scheduled" 改为 "delivered" |
| `CLAUDE.md` | new 决策 #39 | 登记 Session 2' 交付 + C 段偏差 (若有) |

### 1.3 版本警示 (Version Warnings)

> 这些点已被多个真相源反复强调, 任何一处偏离都触发 STOP Type B。

1. **23 行矩阵不可加减** — `EXPECTED_EXPLICIT_ROW_COUNT = 23` 硬约束, 新增引擎 / locale 必须先改 PRD §4.10.3.A 真相源, 然后同步本常量 + 测试。Harness G1 用 regex `/EXPECTED_EXPLICIT_ROW_COUNT\s*=\s*(\d+)/` 锁死。
2. **navigational reducedFactor = 0.3 全线** — 4 行 navigational cell 全部 0.3, 不分 engine, 不可 cell-level 覆写。
3. **品类 Topic / Prompt 零品牌泄漏** — `validate_category_topic_purity` 和 `validate_category_prompt_purity` 必须 wire 进 hot path, 违规抛 `CategoryTopicBrandLeakError` / `CategoryPromptBrandLeakError`。Harness G2 锁定 token 出现。
4. **`query_executions` 零 persona 顶层列** — persona snapshot 进 `attempts` JSONB 的 `browser_profile` 子字段。Harness G3 黑名单: `persona_snapshot` / `persona_profile` / `agent_profile_snapshot` / `agent_profile_id` / `persona_id` (5 词)。
5. **引擎枚举只在 matrix 文件出现** — 其他 planner 模块禁直写 `['doubao', 'deepseek-CN', 'chatgpt']` 数组, 必须 `lookup_matrix(...)` 或从 matrix 派生。Harness G4 白名单 `intent_engine_locale_matrix.py`。
6. **品类配额 ≥ 40%** — `meets_category_quota` 默认 `min_share=0.4`, 测试用最小 fixture 不强制 (避免 KG 太薄假阳)。
7. **MVP 3 引擎不变** — `chatgpt | doubao | deepseek-CN` literal, 决策 #28.G C4 锁定。`deepseek-CN` 是 EngineId literal (将来留 `deepseek-overseas` 余地), 目录路径 `app/engines/adapters/deepseek/` 不改。
8. **本 Session 不调 LLM** — `topic_pool.generate_platform_plan(llm=None)` 是默认路径, LLM refinement 留给 Session 2.1' 填三层 envelope (refine_topics_with_llm / naturalize_prompts_with_llm / rewrite_queries_for_profiles)。
9. **本 Session 不交付用户态 API** — 决策 #26.C3 明确: `/api/v1/industries/{slug}/topics` 等用户态端点延到 Session 3' / 4a' (依赖 User / Project ACL middleware)。

---

## §2 · MVP 范围声明 (Scope-Cut Declaration)

> **决策 #25 规则 10**: 用 "本 Session 做 / 不做" 双列表 + §X.Y 锚点声明, 禁 "核心功能" 模糊措辞。

### ✅ 本 Session 做 (Y1-Y14)

- **Y1 · 23 行 Intent×Engine×Locale 矩阵单一真相源** (`intent_engine_locale_matrix.py`):
  - `EXPECTED_EXPLICIT_ROW_COUNT = 23` 常量
  - `MATRIX: dict[tuple[Intent, EngineId, Locale], MatrixEntry]` 23 显式行
  - `lookup_matrix(intent, engine, locale) -> MatrixEntry` 单行返回 (非数组)
  - navigational 全线 `reduced_factor = 0.3`, 其余 `1.0`
  - 隐式 cell 仅 1 个 (`overseas-sea × transactional × doubao` 不存在), `lookup_matrix` 抛 `MatrixCellNotEnabledError`

- **Y2 · 品牌纯度守卫** (`category_purity.py`):
  - `validate_category_topic_purity(topics, brand_names)` 扫所有 `topic.dimension == '品类'` 的 topic_name
  - `validate_category_prompt_purity(prompts, brand_names)` 同理扫 prompt_text
  - 命中即抛 `CategoryTopicBrandLeakError(topic_name, leaked_brand)` / `CategoryPromptBrandLeakError(prompt_text, leaked_brand)`
  - 别名长短消歧 + 大小写不敏感 + ASCII 短别名 (<3 字符) 走 word boundary

- **Y3 · Topic Planner 三维度** (`topic_planner.py`):
  - 品类 dimension Topic ≥ 40% 配额, 锚 KG `kg_categories` 树
  - 品牌 dimension Topic 锚 `primary_brand` + competitor 关系边 (`COMPETES_WITH` / `SAME_GROUP`)
  - 产品 dimension Topic 锚 flagship SKU + 关系边 (`SUBSTITUTES` / `PAIRS_WITH` / `UPGRADES_TO` / `BUDGET_ALT_OF`)
  - 生成后立即跑 `validate_category_topic_purity` (G2 执行点)

- **Y4 · Prompt Generator** (`prompt_generator.py`):
  - Topic × 4 Intent 扇出, 按 `matrix_row.enabled is True` 过滤禁 cell
  - language 跟随 Intent × Engine × Locale 决策 (zh-CN 全线 + en-US 仅 ChatGPT)
  - Prompt 写 `applies_to_engines: list[EngineId]` 字段 (Query Assembler 消费)
  - 生成后立即跑 `validate_category_prompt_purity`

- **Y5 · Agent Profiles** (`agent_profiles.py`):
  - FNV-1a 确定性 hash 做 `(profile_group_id, seed) -> preset` 映射
  - 8 preset 覆盖 `cn-consumer-desktop` / `overseas-consumer-us` / `overseas-consumer-sea` 三组
  - 同 `(group_id, seed)` 必得同 preset (单测断言)

- **Y6 · Query Assembler** (`query_assembler.py`):
  - Prompt × Engine × Profile 扇出最终 Query
  - `base_sample_range` 默认 `(min=3, max=8)`, 可注入
  - navigational intent 应用 `reduced_factor = 0.3` (向下取整, 至少 1)
  - persona snapshot 注入 `attempts[0].browser_profile` JSONB envelope
  - **零 query_executions 顶层列** (G3 锚点)

- **Y7 · Sample Guard** (`sample_guard.py`):
  - `meets_category_quota(topics, min_share=0.4) -> bool`
  - 边界 `[0, 1]` clamp + 测试覆盖 0 / 0.39 / 0.40 / 0.41 / 1

- **Y8 · Topic Pool 上层编排** (`topic_pool.py`):
  - `generate_platform_plan(industry_slug, repos, *, llm=None, intents=None, base_sample_range=None) -> PlatformPlan`
  - 返回 `PlatformPlan(industry_slug, industry_id, planner={topics}, prompts={prompts}, queries={queries})`
  - `llm=None` 跳过 3 层 LLM envelope (留给 Session 2.1')
  - `intents` 参数窄化 (默认全 4 intent, 可传 `['informational']` 单 intent)

- **Y9 · 4 ProfileGroup seed** (`seed/profile_groups.py`):
  - `cn-consumer-desktop-default` / `cn-consumer-mobile-default` / `overseas-consumer-us-default` / `overseas-consumer-sea-default`
  - 静态 `Pydantic` 数据, 单测 fixture 直接 import

- **Y10 · 3 个 Admin 只读 API** (`app/api/admin/v1/platform/`):
  - `GET /admin/api/v1/platform/industries/{slug}/topics` — 列出某行业当前所有 Topic, 分 dimension 聚合 + 配额统计
  - `GET /admin/api/v1/platform/topics/{topic_id}/prompts` — 列出某 Topic 下的所有 Prompt, 按 intent + language 聚合
  - `POST /admin/api/v1/platform/industries/{slug}/plan/generate` — 幂等触发 `generate_platform_plan` 做 dry-run 预览 (不写库, 返回 topics/prompts/queries 三段计数 + 样本)
  - 三端点都 `Depends(require_admin_session)` (Session A0' 已交付)

- **Y11 · Alembic Migration** (`alembic/versions/<ts>_session_2prime_planner_baseline.py`):
  - `platform_topics` 表: id / industry_id / dimension / topic_name / anchor_brand_id / anchor_product_id / mention_count / metadata JSONB / created_at / updated_at + CHECK `dimension IN ('品类','品牌','产品')` (raw `op.execute()`)
  - `platform_prompts` 表: id / topic_id / intent / language / prompt_text / applies_to_engines TEXT[] / created_at / updated_at + CHECK `intent IN ('informational','commercial','transactional','navigational')`
  - `query_executions` 表: id / prompt_id / engine_id / status / attempts JSONB (含 browser_profile 子字段) / scheduled_at / executed_at / created_at + 索引 `(engine_id, status, scheduled_at)` — **零 persona / agent_profile 顶层列**
  - `agent_profile_snapshots` 表: id / profile_group_id / preset_id / fingerprint JSONB / created_at
  - 注释 (`COMMENT ON COLUMN`) 文档化 `attempts.browser_profile` 子字段 (Session 2' 写入), `attempts.rewrite_meta` 占位 (Session 2.1' 写入)

- **Y12 · Group G Harness 4 条 + selftest 数量上调** (`scripts/ci/harness_group_g.sh` + `harness_selftest.py`):
  - G1 `planner-matrix-row-count-23` — regex `/EXPECTED_EXPLICIT_ROW_COUNT\s*=\s*(\d+)/`, 捕获组 != '23' 即 block
  - G2 `planner-category-purity-guard-wired` — basename `topic_planner` 要求 token `validate_category_topic_purity`; `prompt_generator` 要求 `validate_category_prompt_purity`
  - G3 `query-execution-no-persona-column` — 扫 `alembic/versions/**.py` + `**.sql`, 含 `query_executions` 时黑名单 5 词
  - G4 `planner-no-hardcoded-engine-list` — 扫 `app/platform/planner/**`, 白名单 `intent_engine_locale_matrix.py`, 黑名单 3 种排列的 `['doubao', 'deepseek-CN', 'chatgpt']` 数组字面量
  - selftest `EXPECTED_POSITIVES` 从 Session 1.2' 终态 **10** (Session 1' 9 + F5 一枚) 扩到 **10+4=14**, 每条 G 规则配 1 fixture 自验。**数值溯源**: Session 0' baseline 3 (D8/D9/D10 ported from 决策 #24) → Session 1' +6 (F1/F2/F3/F4-1/F4-2/F4-3) → 9 → Session 1.2' +1 (F5) → 10 → 本 Session +4 (G1/G2/G3/G4) → **14**. 这是 Python pivot 的本地 selftest 链, 与 master TS 链无关

- **Y13 · pytest 9 套单测 + 1 套集成测 (覆盖率 ≥ 80%)**:
  - 单测 9 套见 §1.2 表
  - golden_beauty 套用 InMemory KG 写入 Estée Lauder / L'Oréal + Advanced Night Repair / 复颜真实 seed, 断言 (a) 3 维度齐备 (b) 品类零品牌泄漏 (c) Prompt fan-out == matrix `enabled` cell 并集 (d) navigational reduced_factor=0.3 (e) en-US Query 只落 ChatGPT (f) BUDGET_ALT_OF 关系挖出 (g) determinism 同 seed 两次跑结果完全一致
  - 集成测 1 套覆盖 3 admin endpoint (httpx AsyncClient + 已登录 admin cookie fixture)
  - 总目标 ≥ 80% statements / branches / functions / lines (ruff + mypy + pytest --cov 全绿)

- **Y14 · Preview env 可验 + Frank Layer 3 Phase Gate**:
  - 分支 `session-2prime` 从 main fork
  - 每个 Step 一个原子 commit, 末尾 push 触发 preview env 部署 (Render 后端 + Vercel 前端)
  - Frank 在 preview Admin URL 跑 `POST /admin/api/v1/platform/industries/beauty-personal-care/plan/generate?dry_run=true`, 看到 JSON 返回 ≥ 17 topics + ≥ 400 prompts + ≥ 2000 queries

### ❌ 本 Session 不做 (N1-N10, 显式延后)

- **N1 · LLM Refinement 三层 envelope** — 留给 Session 2.1' (`refine_topics_with_llm` / `naturalize_prompts_with_llm` / `rewrite_queries_for_profiles`), 本 Session 只在 `topic_pool.py` 留 `llm=None` 默认路径 + envelope 占位 `None` 字段
- **N2 · 用户态数据 API** — `/api/v1/industries/{slug}/topics` 等延到 Session 3' / 4a' (需 User / Project ACL)
- **N3 · MCP Server** — 延到 Session 3' (`genpano_get_citations` / `list_pr_targets` / `simulate_authority_boost`)
- **N4 · Response 采集 / 分析** — 延到 Session 3' (Celery worker 消费 query_executions)
- **N5 · Citation Tier CRUD** — 延到 Session 3' / A1'
- **N6 · 多轮对话 Query** — 决策 #26.C2 明确延到 Phase 2, 不开 `Query.follow_up_prompt_id`
- **N7 · Cost 监控告警** — 延到 Session 3' (PRD §4.9.4)
- **N8 · Frontend 任何改动** — 决策 #21 frontend 视为原型, IA v2.0 完整翻译留给 Session 4b'
- **N9 · Admin Tab UI** — 决策 #28.A 边界, Admin UI 延到 Session A1'; 本 Session 只交付 3 个只读 API endpoint, 无 UI
- **N10 · 跨 Session 历史数据回填** — 不消费 master TS Session 2 跑过的数据 (决策 #29 全 Python 反转), Planner 是纯函数, 数据靠 Session 1.5' 的 KG seed 现做现得

---

## §3 · STOP-Trigger Template

> **决策 #25 规则 12**: Type A (环境) / B (真相源) / C (范围) 三类 STOP 作为地板。

### Type A · 环境失败

- **A1** · `pyproject.toml` 缺基础依赖 (fastapi / sqlalchemy[asyncio] / asyncpg / alembic / pydantic / pytest / pytest-cov / httpx / ruff / mypy) → 不 STOP, Step 0 内 `pip install` 补齐 + commit
- **A2** · Session 1.5' KG 表不存在或 `app/platform/db/ports.py` 未 commit → STOP, 回到 Frank 确认依赖
- **A3** · Alembic 当前 head 与本 Session 拟新增 migration 冲突 (出现并行 head) → STOP, 处理 Alembic merge 后重启
- **A4** · Postgres preview DB 不可达 (`asyncpg.exceptions.CannotConnectNowError`) → STOP, 等待 preview env 恢复
- **A5** · `pytest --cov` 报 InMemoryKgRepositories 接口签名不兼容 (Session 1.5' 改了接口未同步) → STOP, 与 Session 1.5' 维护者对齐

### Type B · 真相源冲突

- **B1** · PRD §4.10.3.A 实际行数 != 23 → STOP, 暂停 Y1, 回 Frank 确认 PRD 是否变更
- **B2** · CLAUDE.md 决策 #26 与本 Prompt 的 Planner 模块名 / Harness G 段描述不一致 → STOP, 以 CLAUDE.md 为准, 改本 Prompt
- **B3** · DATA_MODEL §2.5 描述 `query_executions` 含 persona 顶层列 → STOP, 暂停 Y11, 与 Frank 确认是否回滚决策 #26.C1
- **B4** · 决策 #15 / #16 (品类配额 ≥ 40%) 与 PRD §4.6.0a 矛盾 → STOP, 走规则 4 双向同步
- **B5** · `app/engines/adapters/` 目录路径与 Session 1' 实际产出不符 (例如真实路径是 `app/adapters/engines/`) → STOP, 以代码现状为准修本 Prompt §1.2 表

### Type C · 范围溢出

- **C1** · 实施时发现需要顺手实现 LLM refinement (例如 InMemory test 跑出 query 太单调, 想加 LLM 美化) → STOP, 严格不做 (N1), 留给 Session 2.1'
- **C2** · 实施时发现需要写用户态 endpoint 才能让 frontend 通 (例如 4a' 同时进行) → STOP, 仍只交付 admin 只读 (Y10), 用户态等 4a'
- **C3** · 实施时发现 `query_executions.attempts` 设计太挤想加 `persona_snapshot` 顶层列 → STOP, 严格按决策 #26.C1, 走 attempts JSONB envelope; G3 fixture 兜底自验
- **C4** · 实施时发现 23 行矩阵想新增 1 行支持 Gemini → STOP, 决策 #28.G C4 锁 MVP 3 引擎, 不扩到 4 引擎
- **C5** · 实施时发现 pytest 覆盖率卡在 78%, 想降阈值 → STOP, 80% 阈值不可降 (REPLAN §6.5), 找未测分支补单测
- **C6** · golden_beauty 测试发现 KG seed 不够 (例如缺关系边), 想顺手往 Session 1.5' 的 seed 里加 → STOP, Session 1.5' 已封板, 另起 commit + 跨 Session ticket 解决

---

## §4 · Phase Gate 三层验收

> **决策 #25 规则 12 + #30 (preview env)**: 三层验收全过才能在 SESSION_PROGRESS.md 宣绿, 三层缺一即 Session 未完成。

### Layer 1 · 自动化脚本 (Claude Code 在 Linux 沙箱跑)

`scripts/verify-session-2prime.sh` (新建, ~20 行 bash):

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "L1.1 ruff format + lint"
ruff format --check app tests scripts
ruff check app tests scripts

echo "L1.2 mypy strict"
mypy app/platform/planner app/api/admin/v1/platform

echo "L1.3 pytest unit + coverage ≥ 80"
pytest tests/unit/platform/planner -v --cov=app/platform/planner --cov-report=term-missing --cov-fail-under=80

echo "L1.4 pytest integration admin endpoints"
pytest tests/integration/admin_api/test_platform_router.py -v

echo "L1.5 alembic upgrade head + downgrade smoke"
alembic upgrade head
alembic downgrade -1
alembic upgrade head

echo "L1.6 alembic schema check: query_executions has zero persona top-level cols"
psql "$DATABASE_URL" -tAc "SELECT column_name FROM information_schema.columns WHERE table_name = 'query_executions' AND column_name IN ('persona_snapshot','persona_profile','agent_profile_snapshot','agent_profile_id','persona_id')" | wc -l | grep -q '^0$'

echo "L1.7 harness Group G all green"
bash scripts/ci/harness_group_g.sh

echo "L1.8 harness selftest 14/14"
python scripts/ci/harness_selftest.py | tee /tmp/selftest.out
grep -q "selftest: PASS" /tmp/selftest.out

echo "L1.9 admin endpoints smoke (curl preview URL)"
curl -fsS "$ADMIN_PREVIEW_URL/admin/api/v1/platform/industries/beauty-personal-care/plan/generate?dry_run=true" \
  -X POST -H "Cookie: $ADMIN_COOKIE" \
  | python -c "import sys, json; d=json.load(sys.stdin); assert d['planner']['topic_count']>=17 and d['prompts']['count']>=400 and d['queries']['count']>=2000, d"

echo "L1 ALL GREEN"
```

通过条件: 9 步全部 exit 0。

### Layer 2 · Harness Selftest

`python scripts/ci/harness_selftest.py` 必须打印:

```
● selftest: PASS  (14 / 14 fixture expectations met)
```

新增 4 fixture:
- `tests/fixtures/__ci_fixtures__/G1_matrix_row_count_wrong.cifixture.py` 写 `EXPECTED_EXPLICIT_ROW_COUNT = 22`
- `tests/fixtures/__ci_fixtures__/G2_purity_guard_missing_topic_planner.cifixture.py` 文件名 basename 含 `topic_planner` 但内容**完全不出现** `validate_category_topic_purity` 字符串 (含 docstring 注释)
- `tests/fixtures/__ci_fixtures__/G2_purity_guard_missing_prompt_generator.cifixture.py` 同上, basename 含 `prompt_generator`, 不出现 `validate_category_prompt_purity`
- `tests/fixtures/__ci_fixtures__/G3_persona_column.cifixture.sql` 含 `ALTER TABLE query_executions ADD COLUMN persona_snapshot JSONB`
- `tests/fixtures/__ci_fixtures__/G4_hardcoded_engines.cifixture.py` 含 `ENGINES = ['doubao', 'deepseek-CN', 'chatgpt']` (非 lookup_matrix 派生)

> **fixture 编写陷阱**: G2 fixture 必须在文件首行写 `# DESIGN NOTE: this fixture intentionally OMITS the required identifier; do NOT add it back to "fix" the lint warning` — 否则未来 maintainer 误加 docstring 提到该 token 会让 `content.includes()` 自满足导致 selftest silent pass (memory `feedback_fixture_naming.md` 教训)。

### Layer 3 · Frank 在 Preview Env 验证 (S1-S6)

Frank 在 PR 描述里提供截图 + curl 输出证据:

- **S1** · `git checkout session-2prime && git pull` 拉到本地, 跑 `scripts/verify-session-2prime.sh` 全绿
- **S2** · 推 `session-2prime` 到 GitHub, GitHub Action `ci.yml` 全绿 (Render 后端 + Vercel 前端 preview 都 deploy 成功)
- **S3** · Frank 登录 preview Admin (https://genpano-admin-preview.example.com/admin/login, Session A0' 交付的 super_admin 账号), cookie 复制到 `ADMIN_COOKIE`
- **S4** · curl preview URL `POST .../industries/beauty-personal-care/plan/generate?dry_run=true` 返回 JSON, Frank 截图: `topic_count >= 17, prompt_count >= 400, query_count >= 2000`, 且 `dimensions: {"品类": >= 7, "品牌": >= 5, "产品": >= 5}` (品类 >= 40% 配额可见)
- **S5** · curl preview URL `GET .../industries/beauty-personal-care/topics` 返回完整 topic 列表, Frank 抽 5 条品类 topic 名肉眼复核**零品牌泄漏** (例如不出现 "雅诗兰黛 哪款 精华最好" 这种品牌混入品类的 topic)
- **S6** · curl preview URL `GET .../topics/<某品牌-topic-id>/prompts` 返回 prompts, 抽 1 条 navigational + 1 条 informational 复核, navigational 数量约为 informational 的 30% (reduced_factor 体现)

S1-S6 任一失败即 Layer 3 不绿, 回 Step N 修复后重跑。

---

## §5 · 12-Step 交付顺序 (原子 commit)

每个 Step 末尾 `git commit -m "Session 2' Step <N>: <主题>"` (ASCII 标题, 禁特殊 Unicode), commit 描述里附带本 Step 的 Phase Gate 部分证据。

| Step | 主题 | 关键产出 | Phase Gate 部分证据 |
|---|---|---|---|
| **0** | 分支 + 依赖補 | `git checkout -b session-2prime`; `pyproject.toml` 加 (若缺) `pytest-asyncio` `httpx[testing]`; `pip install -e .[dev]` | `pip list` 输出 |
| **1** | Pydantic types + matrix | `app/platform/planner/types.py` (PlannedTopic / PlannedPrompt / PlannedQuery / MatrixEntry / Intent / EngineId / Locale Pydantic v2 model) + `intent_engine_locale_matrix.py` 23 行 + `lookup_matrix` + `EXPECTED_EXPLICIT_ROW_COUNT=23` + 12 单测 (matrix 计数 / lookup 三元组穷举 / navigational reduced=0.3 / 单一禁 cell `MatrixCellNotEnabledError`) | matrix 12/12 单测过, ruff + mypy 绿 |
| **2** | category_purity | `category_purity.py` + 14 单测 (品牌别名 / 大小写 / 长短 alias 消歧 / Topic & Prompt 双向 validator / 决策 #15 护栏回归) | 14/14 单测过 |
| **3** | agent_profiles + sample_guard | `agent_profiles.py` (FNV-1a 确定性 hash + 8 preset) + `sample_guard.py` + 12+9 单测 | 21/21 单测过 |
| **4** | topic_planner | `topic_planner.py` (3 维度生成 + ≥40% 配额 + 锚 primary brand / flagship product) + 9 单测 (purity guard 实际被 wire) | 9/9 单测过, G2 fixture 已自验 |
| **5** | prompt_generator | `prompt_generator.py` (Topic × Intent + matrix `enabled` 过滤 + applies_to_engines + language) + 12 单测 (4 intent 覆盖 / 禁 cell 剔除 / zh-CN 全线 + en-US 仅 ChatGPT / navigational 降频) | 12/12 过 |
| **6** | query_assembler | `query_assembler.py` (Prompt × Engine × Profile + base_sample_range + reduced_factor + persona 进 attempts.browser_profile envelope) + 13 单测 | 13/13 过, G3 fixture 自验 (零顶层列) |
| **7** | topic_pool 上层编排 + seed | `topic_pool.py` (`generate_platform_plan` llm=None 默认) + `seed/profile_groups.py` 4 default + 7 单测 (端到端 + determinism + 3 维度齐备 + intents 参数窄化) | 7/7 过 |
| **8** | golden_beauty test | `tests/unit/platform/planner/test_golden_beauty.py` 13 例 (3 维度 / 零品牌泄漏 / Prompt fan-out 严格 == matrix 并集 / navigational 0.3 / en-US 仅 ChatGPT / BUDGET_ALT_OF 挖出 / determinism) — 用 Session 1.5' 的 InMemoryKgRepositories + 真实 seed | 13/13 过, coverage ≥ 80% |
| **9** | Alembic migration + DB CHECK | `alembic revision -m session_2prime_planner_baseline` + 4 表 (含 raw `op.execute()` CHECK) + downgrade 回滚 smoke | `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` 三步过 |
| **10** | 3 个 admin endpoint + 集成测 | `app/api/admin/v1/platform/{topics,prompts,plan_generate}_endpoint.py` + `router.py` + `tests/integration/admin_api/test_platform_router.py` (httpx AsyncClient + admin cookie fixture) | 3 endpoint 集成测全过, 含 require_admin_session gate 验证 |
| **11** | Harness Group G + selftest 14/14 | `scripts/ci/harness_group_g.sh` 4 grep + 5 fixture + selftest EXPECTED_POSITIVES 扩到 14 (Session 1.2' 终态 10 + G1/G2/G3/G4 = 14) | `uv run python scripts/python/ci-harness-selftest.py` 输出 `selftest: PASS (14/14)` |
| **12** | 文档同步 + 决策 #39 草稿 | `docs/SESSION_PROGRESS.md` 追加 "Session 2' 宣绿" + Layer 1-3 evidence; `docs/CLAUDE_CODE_SESSIONS_PYTHON.md` Session 2' 行改 delivered; `CLAUDE.md` 新加决策 #39 (含 C 段偏差 if any) + `docs/SESSION_2_PRIME_DELIVERY.md` 总结报告 | PR 描述链接到 SESSION_PROGRESS + 决策 #39 |

---

## §6 · Delivery Report Template (`docs/SESSION_2_PRIME_DELIVERY.md`)

```markdown
# Session 2' · Delivery Report (yyyy-mm-dd)

## Phase Gate 证据

### Layer 1 · 自动化
- [ ] L1.1 ruff format + lint  ➜ <commit hash>
- [ ] L1.2 mypy strict  ➜ <commit hash>
- [ ] L1.3 pytest unit ≥ 80% coverage  ➜ <coverage 截图>
- [ ] L1.4 pytest integration 3 endpoints  ➜ <pass log>
- [ ] L1.5 alembic upgrade + downgrade smoke  ➜ <output>
- [ ] L1.6 query_executions 零 persona 顶层列  ➜ `psql ... | wc -l == 0`
- [ ] L1.7 harness Group G all green  ➜ <output>
- [ ] L1.8 harness selftest 14/14  ➜ <output>
- [ ] L1.9 admin endpoint smoke 17/400/2000  ➜ <JSON 截图>

### Layer 2 · Selftest
[完整 `selftest: PASS (14/14)` 输出粘贴]

### Layer 3 · Frank Preview Env
- [ ] S1 verify-session-2prime.sh 本地全绿
- [ ] S2 GitHub Action ci.yml 全绿 + Render/Vercel deploy 链接
- [ ] S3 Admin login 截图
- [ ] S4 plan/generate JSON (≥17 topics / ≥400 prompts / ≥2000 queries) 截图
- [ ] S5 5 条品类 topic 肉眼复核零品牌泄漏 截图
- [ ] S6 navigational ≈ 30% × informational 截图

## 偏差登记 (决策 #25 规则 3)

> 实施中如有与真相源不可调和的冲突, 列在此; 同步登记进 CLAUDE.md 决策 #39 C 段。

- C1 (...) · ...
- C2 (...) · ...

## 真相源同步 (决策 #25 规则 4)

- [ ] CLAUDE.md 新加决策 #39 (含 C 段偏差 if any)
- [ ] CLAUDE_CODE_SESSIONS_PYTHON.md Session 2' 行改 delivered
- [ ] SESSION_PROGRESS.md 追加宣绿条目

## CLAUDE.md 决策 #39 草稿

```
39. **Session 2' · Planner Pipeline (Topic→Prompt→Query, Python 重写) 交付 (yyyy-mm-dd)**: 按 docs/SESSION_2_PRIME_PROMPT.md 范围, 复用 master Session 2 (决策 #26) 算法逻辑, 全 Python 重写 (FastAPI / SQLAlchemy 2.0 async / pytest), 落到合并仓 C:\Users\frank.wang\genpano。

    A. 模块清单 (app/platform/planner/): intent_engine_locale_matrix.py / category_purity.py / topic_planner.py / prompt_generator.py / query_assembler.py / agent_profiles.py / sample_guard.py / topic_pool.py + seed/profile_groups.py + types.py
    B. 3 个 Admin 只读 endpoint: /admin/api/v1/platform/industries/{slug}/topics + /admin/api/v1/platform/topics/{topic_id}/prompts + POST /admin/api/v1/platform/industries/{slug}/plan/generate
    C. Alembic migration: 4 张表 (platform_topics / platform_prompts / query_executions / agent_profile_snapshots), 严守决策 #26.C1 零 persona 顶层列
    D. Harness Group G 4 条 (G1-G4) Python 重写 + 5 self-seeded fixture, selftest 10→14 (Python pivot 链, 与 master TS 链无关)
    E. pytest: <NN>/<NN> 全过, coverage stmts/branches/funcs/lines 全 ≥ 80%
    F. Phase Gate Layer 3 Frank S1-S6 全绿截图存档于 docs/SESSION_2_PRIME_DELIVERY.md

    C 段偏差 (若有): ...
```

## §0 F1-F8 收尾验证

[粘贴 8 条 grep 命令 + 输出, 证明真相源在 Session 收尾时仍然成立]
```

---

## §7 · 收尾一致性回路 (Closing Loop, 决策 #25 规则 7)

Step 12 推 commit 之前, Claude Code 必须再跑一次 §0 F1-F8 8 条 grep, 把输出粘贴到 `SESSION_2_PRIME_DELIVERY.md` 末尾。任一与开工时差异显著 (例如 PRD 段号重排) → 暂停宣绿, 走规则 4 双向同步 + 规则 3 偏差登记。

---

## §8 · 10 条最终提醒 (Final Reminders)

1. **真相源不重抄** — `intent_engine_locale_matrix.py` 顶部注释只能 `# See PRD §4.10.3.A for the 23-row matrix; this file is the single executable mirror`, 不要把 PRD 表抄到注释里
2. **commit 标题 ASCII 不带特殊 Unicode** — `Session 2' Step <N>: <主题>`, 禁 § ✅ — 等字符 (memory `feedback_genpano_session_commit_rule.md`)
3. **常量单一入口** — `EXPECTED_EXPLICIT_ROW_COUNT` / `MIN_CATEGORY_QUOTA = 0.4` / `BASE_SAMPLE_RANGE_DEFAULT = (3, 8)` / `NAVIGATIONAL_REDUCED_FACTOR = 0.3` 全在 `intent_engine_locale_matrix.py` 或 `sample_guard.py`, 别处禁复制
4. **Pydantic v2 不要混用 v1 API** — 用 `model_validator` / `field_validator` / `ConfigDict`, 不要 `@validator` `class Config`
5. **SQLAlchemy 2.0 async 不要混 1.x sync** — 用 `select(...)` / `async with AsyncSession` / `await session.execute`, 不要 `Query.filter_by` / `session.query`
6. **零 query_executions 顶层列** — G3 锚点, 任何"persona 进表方便查询"的诱惑都走 attempts JSONB envelope (决策 #26.C1)
7. **零 frontend 改动** — 本 Session 完全后端 + admin API only, 不动 frontend/src/**
8. **InMemoryKgRepositories 是单测唯一来源** — 不在单测里直 touch SQLAlchemy session, 不接真 Postgres
9. **每个 Step 之后 verify-session-2prime.sh 跑通才能 commit** — Frank 验绿前不得有红色 Step
10. **收尾跑 §0 F1-F8 + §7 一致性回路** — 闭环, 才能宣绿

---

> **Frank 给 Claude Code 的最后一句话**: 严格按 §0 → §8 顺序读完后再动手, Step 0-12 顺序不可错位, Type A/B/C STOP 不可绕过, 决策 #26 复用算法但不可机械抄 TS — Python 风味 (Pydantic v2 / SQLAlchemy 2.0 async / pytest fixture / dependency-injection style) 比 TS 更优雅, 这是反转的全部回报。
