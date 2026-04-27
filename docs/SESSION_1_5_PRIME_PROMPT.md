# Session 1.5' · 行业知识图谱冷启动 (Python 重写) — Prompt for Claude Code

> **使用说明**: 本文档是给 Claude Code 的 Session Prompt, Frank 直接复制本文件全部内容到 Claude Code 即可启动 Session 1.5'。
> 本 Prompt 严格遵守 `CLAUDE.md` 决策 #25 的 12 条 Prompt 编写公约 (规则 1-7 + 10/11/12)。
>
> **角色**: 你 (Claude Code) 是 GENPANO Platform Layer 知识图谱架构师, 负责把 master Session 1.5 (TS 算法决策 #23) 的所有逻辑**重写为 Python**, 落地到 `backend/app/platform/**` 标准目录, 同时通过 Alembic migration 建 7 张 KG 表 + 一份端到端 seed 脚本, 让 4 个 MVP 行业 (beauty-personal-care / luxury / food-beverage / fashion-apparel) 的 Industry → Category (3 级) → Brand → Product 节点 + 6 种关系边 (COMPETES_WITH / SAME_GROUP / SUBSTITUTES / PAIRS_WITH / UPGRADES_TO / BUDGET_ALT_OF) 在 preview DB 中可见。
>
> **历史依据**: master Session 1.5 (决策 #23, TS 实现, 219 单测全绿, coverage 95.81%) 已废止 (决策 #29 全 Python pivot)。本 Session 是 TS 算法逻辑的 Python 等价重写, **算法不动 (语义真相源)**, 只换语言 + ORM (Prisma → SQLAlchemy 2.0 async) + LLM transport (fetch → httpx)。Platform Layer 边界 (决策 #28.A) 仍生效: 知识图谱是平台层资产, App + Admin 共享, 用户 Project 只是视角过滤器, 不存监测数据。

---

## §0 前置 Grep 契约 (规则 2)

**开工第一批动作**: 必须先跑下列 grep 自证真相源仍与本 Prompt 引用一致, 任一不一致 → 停下 alignment 不写代码 (规则 7 闭环回路也复用本组命令)。

```bash
# F1: 决策 #25 (12 条公约) / #29 (Python pivot) / #30 (preview) / #31 (branch-per-session) 仍在 CLAUDE.md
grep -nE "决策 #(25|29|30|31|32)" CLAUDE.md | head -12

# F2: 决策 #23 (Session 1.5 TS) + 决策 #28.A (Platform Layer 边界) 仍在 CLAUDE.md (作为算法/架构真相源)
grep -nE "决策 #23|#28\.A|Platform Layer|EVIDENCE_DECAY|kg_mined_relations|confidenceFromEvidence|maxCalls.*50|平台层资产" CLAUDE.md | head -15

# F3: PRD §4.0.1 知识图谱 + DATA_MODEL §1.x KG 表结构仍齐全 (语义真相源)
grep -nE "^## 4\.0|^### 4\.0\.1|kg_industries|kg_categories|kg_brands|kg_products|kg_brand_relations|kg_product_relations|kg_mined_relations" docs/PRD.md docs/DATA_MODEL.md 2>&1 | head -25

# F4: REPLAN §4 Session 1.5' 范围 + Phase Gate 描述仍存在 (preview Admin URL 看到品牌列表)
grep -nE "^### Session 1\.5'|seed_platform_data|admin/kg/industries|≥ 20 brands" docs/REPLAN_2026_04_26.md | head -10

# F5: SESSION_PROGRESS.md Session 1.5' ⬜ 未启动 (上游 Session 0' + 1' 已绿)
grep -nE "1' .*✅|1\.5' .*⬜|Session 1\.5' " docs/SESSION_PROGRESS.md | head -8

# F6: Session 0' 已交付 (Alembic 已就位 + ai_responses baseline) + Session 1' 已交付 (parsers 可复用)
ls backend/app/__init__.py backend/alembic.ini backend/app/engines/parsers/brand_matcher.py backend/app/engines/parsers/normalize.py backend/app/engines/parsers/citation_extractor.py 2>&1 | head -10

# F7: backend/app/platform/ 目录尚未存在 (本 Session 首次落地; Session 1' 的 accounts 目录在 engines/ 下, 不在 platform/ 下)
ls backend/app/platform/ 2>&1 | head -3

# F8: pyproject.toml 已含 sqlalchemy / asyncpg / httpx / alembic (Session 0' 锚定)
grep -nE "sqlalchemy|asyncpg|httpx|alembic|tldts" pyproject.toml | head -10
```

如果任一 grep 返回 0 行或路径不存在, 立即停止并报告偏离 (规则 11 freshness check 已经被 Frank 在发 Prompt 前 30min 内执行过, 本 grep 是开工再次 self-verify)。**特别留意 F7**: `backend/app/platform/` 目录是本 Session 创建的, 已存在则可能是历史污染或遗留代码, 必须先确认无冲突再写。

---

## §1 真相源索引 (规则 5 / 6)

### 引用真相源 (本 Session 不修改, 只翻译/落地)

| 文件 | 段号 | 标签 | 用途 |
|------|------|------|------|
| `CLAUDE.md` | 决策 #23 (Session 1.5 TS 交付) | [引用-语义真相源] | §A 两层架构 / §B 目录与模块 / §C 端到端编排脚本 / §D Vitest 覆盖率 / §F acceptance / §H 硬约束 — 算法逻辑全部翻译为 Python 等价 |
| `CLAUDE.md` | 决策 #28.A (Platform Layer 边界) | [引用-架构真相源] | 三层架构 (契约层/Platform Layer/Consumers); 本 Session 落 Platform Layer; Admin / App 不重写算法, 只 import |
| `CLAUDE.md` | 决策 #25 (12 条 Prompt 公约) | [引用] | 本 Prompt 自身遵守 |
| `CLAUDE.md` | 决策 #29 (Python pivot) | [引用] | TS 后端代码已弃; 全 Python; SQLAlchemy 2.0 async + asyncpg + Pydantic v2 + httpx |
| `CLAUDE.md` | 决策 #30 (preview env each Session) | [引用] | 本 Session Phase Gate 包含 Frank 在 preview Admin URL 看到品牌列表 (REPLAN §4 明示) |
| `CLAUDE.md` | 决策 #31 (branch-per-session) | [引用] | 本 Session 分支 = `session-1.5prime`, 从 main fork |
| `CLAUDE.md` | 决策 #32 (工作仓) | [引用] | `C:\Users\frank.wang\genpano` |
| `docs/PRD.md` | §4.0 行业知识图谱定义 | [引用] | Industry → Category (3 级) → Brand → Product + 6 种关系边语义 |
| `docs/PRD.md` | §4.0.1 KG 构建方式 | [引用] | LLM 初始化 (冷启动) + Response 挖掘 (持续迭代) 双轨 |
| `docs/PRD.md` | §4.0.1a Planner Bottom-Up | [引用] | Topic Pool stub 接口形状仅 (Session 2' 才填充实现); 本 Session 只导出空 stub 供编排器 import |
| `docs/PRD.md` | §4.10 国际化 (China-first global-ready) | [引用] | Brand/Product 模型必须含 `name_zh` / `name_en` / `aliases` (jsonb 数组) |
| `docs/DATA_MODEL.md` | §1.1-§1.5 (kg_industries / categories / brands / products / brand_relations) | [引用-Schema 真相源] | 表名 / 字段 / 索引 / 约束 — Alembic migration 必须 1:1 翻译 |
| `docs/DATA_MODEL.md` | §1.9 (kg_mined_relations 新表 + 公式) | [引用-Schema 真相源] | `confidence_score = min(1.0, 1 - 0.85^evidence_count)` + 晋升规则 (≥0.70 ∧ ≥5 → auto / [0.50,0.70) ∧ ≥3 → manual_review) — 本 Session 唯一 EVIDENCE_DECAY 入口 |
| `docs/REPLAN_2026_04_26.md` | §4 Session 1.5' 范围 + Phase Gate | [引用] | 本 Session 范围+ ❌-out 边界 + Phase Gate 接受标准 |
| `docs/REPLAN_2026_04_26.md` | §6.5 Harness 群组 (Group H 留 Session 2'.1) | [引用] | 本 Session **不**新增 harness rule; KG 守护 (LLM call budget / EVIDENCE_DECAY 锁定) 走 pytest assertion + 代码层常量 |
| `docs/REPLAN_2026_04_26.md` | §7 不变量 (4 行业 / 3 引擎 / 单轮 Query / Platform Layer 资产) | [引用] | 本 Session 4 行业 seed = beauty-personal-care / luxury / food-beverage / fashion-apparel |
| `docs/HARNESS_ENGINEERING.md` | §10.5 Schema 守护 / §10.7 Mock 真实性 | [引用] | KG seed 数据真实度 (品牌名/aliases/category 关联) 必须真实可查, 禁 placeholder; mock LLM transport 默认走 canned, 不允许"假数据"绕过 |
| `geo_tracker/` 路径 | (无, exclude in pyproject) | [引用-反向工程禁区] | 本 Session **不复用** geo_tracker, 因 KG 是 master Session 1.5 全新构建; geo_tracker 实战代码侧重 query 执行, 与 KG 冷启动不重叠 |

### 修改真相源 (本 Session 落库, 后续 Session 必须遵守)

| 文件 | 段号/位置 | 标签 | 修改内容 |
|------|----------|------|----------|
| `backend/alembic/versions/<timestamp>_session_1_5prime_kg_baseline.py` | (新建 migration) | [新建] | 7 张 KG 表 + CHECK 约束 + 索引 (kg_industries / kg_categories / kg_brands / kg_products / kg_brand_relations / kg_product_relations / kg_mined_relations); upgrade + downgrade 都必须实现 |
| `backend/app/platform/__init__.py` | (新建) | [新建] | 顶层包标识, exports 关键模块 |
| `backend/app/platform/llm/client.py` | (新建) | [新建] | 火山 Ark async wrapper (httpx + openai-compatible payload), `transport: Callable` 可注入, `call_json()` 强制 JSON, `LlmCallBudgetExceededError`, 内建 `doubao-1-5-pro` / `deepseek-v3` / `gpt-4o` 定价表 |
| `backend/app/platform/db/ports.py` | (新建) | [新建] | `KgRepositories` Protocol (industries/categories/brands/brand_relations/products/product_relations/mined_relations/discovery_logs); 每表独立 Repository; 所有 upsert 返回行 id |
| `backend/app/platform/db/memory_repo.py` | (新建) | [新建] | `InMemoryKgRepositories` 单测专用, dict-based, key 按自然唯一键组合 (e.g. `f"{industry_id}::{primary_name}"`); 字段命名守约 (内部 dict 用 `_by_key` 后缀, public attribute 不冲突) |
| `backend/app/platform/db/sqlalchemy_repo.py` | (新建) | [新建] | `make_sqlalchemy_kg_repositories(session)` 生产版, 用 SQLAlchemy 2.0 async session + ON CONFLICT upsert; 在 pytest coverage **exclude** 列表 (集成测试用 testcontainers PG 容器单独覆盖) |
| `backend/app/platform/discovery/{types,prompts,category_tree,brand_discovery,product_discovery,dedupe}.py` | (6 个文件新建) | [新建] | 翻译决策 #23 §B `discovery/*.ts` 算法; 中英双语 prompt 模板; LLM 输出 JSON schema 强制; 容错 (per-brand throw skip + budget exhausted 部分返回) |
| `backend/app/platform/knowledge_graph/{confidence,brand_relations,product_relations,relation_extractor}.py` | (4 个文件新建) | [新建] | `confidence_from_evidence(n) = min(1.0, 1 - 0.85^n)` 唯一公式入口; `EVIDENCE_DECAY = 0.85` 模块级常量; `classify_promotion(score, n) -> 'auto' \| 'manual_review' \| 'hold'`; 对称边 vs 有向边写入策略 |
| `backend/app/platform/scheduler/platform_scheduler.py` | (新建) | [新建] | `assign_tiers(brands, percentiles=(0.2, 0.8))` + `build_enqueue_plan(brands, config, now)`; cadence high=24h / medium=72h / low=168h; cost cap 触发 deferred_by_budget |
| `backend/app/platform/seed/mvp_industries.py` | (新建) | [新建] | 4 行业静态种子 (beauty-personal-care / luxury / food-beverage / fashion-apparel), 每行业 4-5 L1 + 2-5 L2 children + `seed_brands_by_category` 提示集 |
| `backend/app/platform/planner/topic_pool.py` | (新建 stub) | [新建-stub] | `TopicPoolNotImplementedError`; `generate_platform_topics(...)` 抛错; 只导出接口形状供 Session 2' 实现 (规则 6 最小单元锚定到决策 #23 §B `planner/topic-pool.ts` Session 2 stub 行为) |
| `backend/scripts/seed_platform_data.py` | (新建 CLI) | [新建] | argparse: `--dry-run` / `--industry=<slug>` / `--llm-tree` / `--max-llm-calls=N` / `--product-brands=N`; dry-run transport 内置 canned JSON 按 prompt 子串模式匹配; live transport 要求 `VOLC_API_KEY` |
| `backend/tests/unit/platform/**/*.py` | (~10 个测试文件新建) | [新建-pytest] | 翻译决策 #23 §D 219 vitest 例为 pytest, 覆盖 llm/client + knowledge_graph 4 模块 + discovery 5 模块 + db/memory_repo + scheduler; ≥ 80% coverage |
| `pyproject.toml` | `[tool.coverage.run] omit` | [追加] | 加 `backend/app/platform/db/sqlalchemy_repo.py` (依赖真实 PG, 单测 exclude) / `backend/app/platform/planner/topic_pool.py` (Session 2' stub) / `backend/app/platform/seed/mvp_industries.py` (纯常量) |
| `docs/SESSION_PROGRESS.md` | Session 1.5' 行 | [追加] | ⬜ → ✅ 状态翻转, 提交 evidence (alembic upgrade head 输出 / pytest 覆盖率 / preview Admin URL 截图) |
| `docs/CLAUDE_CODE_SESSIONS_PYTHON.md` | Session 1.5' 段 | [追加] | 总览描述链接到本 Prompt + commit hashes |
| `CLAUDE.md` | 决策 #36 (Session 1.5' 交付) 新条目 | [追加] | 本 Session 完成时, 在 CLAUDE.md 末尾 append 决策 #36 块, 含 §A 算法翻译 / §B 目录 / §C 偏离 (C1/C2/...) / §D pytest 覆盖率 / §E Phase Gate 实测; 决策号沿用 Session 1' 后下一个数字 (Session 1' = #35, 故本 Session = #36) |

### 版本警告 (规则 4 双向同步, 实施时必须留意)

1. **EVIDENCE_DECAY = 0.85 是不可变常量**: 决策 #23 §H 明文 "动则发 DB migration note"; 本 Session 唯一入口 = `backend/app/platform/knowledge_graph/confidence.py` 模块顶级常量; 任何调整需先发 PR 改 DATA_MODEL §1.9 公式 + 跑历史 evidence 重算 migration; pytest 必须断言 `confidence_from_evidence(5) ≈ 0.5563 ± 0.0001` 锁定数值。
2. **LLM call budget ≤ 50/industry 是硬上限**: 决策 #23 §H + §B `llm/client.ts` 实现细节; 本 Python 重写必须用 `LlmClient(max_calls=50, ...)` 强制, 超过抛 `LlmCallBudgetExceededError`; orchestrator catch → 部分结果 + `budget_exhausted: true` 返回, 不抛到顶层。
3. **mined-relation 必须先进 kg_mined_relations**: 决策 #23 §H 第三条 "晋升到 kg_brand_relations / kg_product_relations 走 classify_promotion 的双阈值"; LLM bootstrap 写关系**绝不**直接落 kg_brand_relations (会污染高置信度真表); brand_discovery / product_discovery 期间发现的关系初始 `evidence_count=1`, `confidence ≈ 0.15`, 待 Response 挖掘累积 evidence 后才晋升。
4. **Platform Layer 不读 User/Project 表**: 决策 #28.A 边界纪律; `backend/app/platform/**` 任何模块 import `app.users.*` 或 `app.projects.*` 都是 regression; ruff 规则 + pytest import smoke 锁定。
5. **InMemoryKgRepositories 字段命名陷阱**: 决策 #23 §B 警告 — 内部 dict 与 public attribute 同名会出现 `'NoneType' object is not subscriptable` (Python 等价于 TS `this.xxx.get is not a function`); 内部 dict 一律用 `_by_key` 后缀 (e.g. `self._categories_by_key: dict[str, CategoryRow]`), public attribute 用 Repository 接口暴露的方法 (e.g. `self.categories.get(...)`); pytest 必须有 1 例 "实例化 + 多 industry insert 不互相污染" 验证。
6. **NFKD + NFKC 归一化双轨**: 决策 #23 §B `discovery/dedupe.ts` 警告 — primaryName 归一化是 NFKD (decompose 重音) → 小写, 然后比对相等; alias 归一化按 (language, normalized value) 合并; 本 Python 重写用 `unicodedata.normalize("NFKD", s).lower()` 统一入口, 禁止散写。
7. **未来 git mv 已知**: 决策 #28.A 提到 "Admin Session A2 Tab 1 账号池" 需要 import `@/accounts/**`; 本 Session 落 `backend/app/platform/` 是 KG 部分, 不动 `backend/app/engines/accounts/`; Session A1' 才考虑把 accounts 从 engines/ 迁到 platform/。**本 Session 不做这次 git mv**, 只保证 KG 落 `backend/app/platform/` 不串味。

---

## §2 MVP 范围 (规则 10)

### ✅ 本 Session 做 (18 项 deliverable)

| # | 工作项 | 锚点 | 验收标准 |
|---|--------|------|----------|
| 1 | Alembic migration `<timestamp>_session_1_5prime_kg_baseline.py` 建 7 表 | DATA_MODEL §1.1-§1.5 + §1.9 | `alembic upgrade head` 在 preview PG 跑通 + downgrade 也跑通 (双向幂等) |
| 2 | `app/platform/llm/client.py` 火山 Ark async wrapper | 决策 #23 §B llm/client.ts | `LlmClient(api_key, base_url, max_calls=50, transport=httpx_async)`; `call_json()` 解析失败抛 `LlmJsonParseError`; `estimate_cost_usd()` 内建 3 模型定价 |
| 3 | `app/platform/db/ports.py` Protocol 接口 | 决策 #23 §B db/ports.ts | `KgRepositories` Protocol + 8 子 Repository (每表 1 个); 所有 upsert 返回 id |
| 4 | `app/platform/db/memory_repo.py` 单测专用 | 决策 #23 §B db/memory-repo.ts | `InMemoryKgRepositories()` 默认空; 内部 dict 后缀 `_by_key`; pytest 多 industry 隔离测试 ≥ 1 例 |
| 5 | `app/platform/db/sqlalchemy_repo.py` 生产版 | 决策 #23 §B db/prisma-repo.ts | `make_sqlalchemy_kg_repositories(session: AsyncSession)`; ON CONFLICT upsert 用 PG dialect insert + on_conflict_do_update |
| 6 | `app/platform/discovery/{types,prompts,category_tree,brand_discovery,product_discovery,dedupe}.py` 6 模块 | 决策 #23 §B discovery/*.ts 全部 | category-tree 容错 level-4+ drop; brand-discovery 跨 category dedupe; product-discovery resolveCategoryId 三级回退; dedupe 用 NFKD+lowercase 唯一入口 |
| 7 | `app/platform/knowledge_graph/{confidence,brand_relations,product_relations,relation_extractor}.py` 4 模块 | 决策 #23 §B knowledge-graph/*.ts | `EVIDENCE_DECAY = 0.85` 模块级; `confidence_from_evidence` / `classify_promotion`; 对称边写两行 / 有向边写一行 / self-loop skip / 缺端点 missing[] 不抛 |
| 8 | `app/platform/scheduler/platform_scheduler.py` | 决策 #23 §B scheduler/platform-scheduler.ts | 纯函数 `assign_tiers` + `build_enqueue_plan`; `now: datetime` 注入便于测试; cadence/budget 配置可注入 |
| 9 | `app/platform/seed/mvp_industries.py` | 决策 #23 §B seed/mvp-industries.ts | 4 行业 dataclass 静态常量, 含 4-5 L1 + 2-5 L2; `seed_brands_by_category` Mapping[str, list[str]] |
| 10 | `app/platform/planner/topic_pool.py` Session 2' stub | 决策 #23 §B planner/topic-pool.ts | `class TopicPoolNotImplementedError(NotImplementedError)`; `generate_platform_topics(...) -> NoReturn`; 仅导出类型供 import; Session 2' 才填实现 |
| 11 | `backend/scripts/seed_platform_data.py` 端到端编排 CLI | 决策 #23 §C seed-platform-data.ts | argparse 5 flag; dry-run transport canned-pattern matching; live transport 要求 `VOLC_API_KEY` env |
| 12 | `app/platform/__init__.py` + 子包 `__init__.py` | (新建) | exports 关键 entrypoints (`LlmClient`, `KgRepositories`, `InMemoryKgRepositories`, `confidence_from_evidence`, `seed_industries`, etc.) |
| 13 | pytest ≥ 10 个测试文件 | 决策 #23 §D vitest 219 例 | 覆盖 llm/client (≥15 例) / confidence + relations + relation_extractor (≥30 例) / discovery 全模块 (≥30 例) / memory_repo (≥18 例) / scheduler (≥15 例); 总 ≥ 110 例 |
| 14 | pytest 覆盖率 ≥ 80% | REPLAN §4 + 决策 #29 工程质量 | `pytest --cov=backend/app/platform --cov-fail-under=80`; sqlalchemy_repo / topic_pool / mvp_industries 在 omit 列表 |
| 15 | Session 0' 已交付的 ci-harness 拓展 (无新规则但需新增 platform/ 扫描路径) | REPLAN §6.5 (Group H 留 Session 2'.1) | `scripts/python/ci-harness.py` 现有 Group F 规则的 file glob 加 `backend/app/platform/**` (避免漏扫); selftest 仍 9/9 不增 fixture (本 Session 不引入新 harness) |
| 16 | preview env Alembic head + admin Phase Gate URL 联通 | 决策 #30 + REPLAN §4 Phase Gate | preview deployment 跑 `alembic upgrade head` 不报错; Frank 浏览器访问 `https://genpano-preview.vercel.app/admin/kg/industries/beauty-personal-care` 看到品牌列表 (即使是占位 UI 渲染从 `/admin/api/v1/platform/industries/<slug>/brands` 拿到 ≥ 20 行 JSON) |
| 17 | Admin 只读端点 stub `GET /admin/api/v1/platform/industries/{slug}/brands` (FastAPI router) | 决策 #23 §G "本 Session 不交付 (留 Admin Session A2)" 提早做最小读路径 | 仅 `requireAdminSession()` 后调 `make_sqlalchemy_kg_repositories(session).brands.list_by_industry(slug)` 返回 JSON; 本 Session 唯一 HTTP 端点; CRUD/编辑/审核留 Session A1' Admin 用户管理 |
| 18 | branch `session-1.5prime` ≤ 12 commits + ruff/mypy/pytest 全绿 | 决策 #31 | 每个 atomic commit 通过 `make verify` 三件套 (ruff strict / mypy strict / pytest with coverage); 最后 commit `Session 1.5' Step 12: docs sync (Phase Gate green)` |

### ❌ 本 Session 不做 (12 项 deferred)

| # | 不做项 | 原因 | 留给哪个 Session |
|---|--------|------|------------------|
| N1 | Topic Pool 真实实现 (Topic 三维度生成 / 配额看门狗 / Bottom-Up 算法) | 决策 #23 §G 明示 "Session 2 stub" + 决策 #26 落地 | Session 2' (Planner Pipeline) |
| N2 | Prompt × Intent × Language 扇出 | Session 2' 范围 | Session 2' |
| N3 | Query × Profile × Engine 装配 | Session 2' 范围 | Session 2' |
| N4 | Planner LLM Refinement (refine_topics_with_llm 等 3 层 envelope) | 决策 #27 (Session 2.1) 范围 | Session 2.1' |
| N5 | Response 采集 (Camoufox launch / page.goto / parser 真跑) | Session 1.2' 范围 | Session 1.2' |
| N6 | KG Response 挖掘 (从真 ai_responses 表挖关系) | 依赖 ai_responses 有数据, 本 Session 仅落 `relation_extractor.py` 算法但不 wire 到 worker | Session 3' (分析引擎) |
| N7 | Admin KG CRUD UI / 审核工作流 (`change_type` 8 种 / Trust Score 11 边界) | 决策 #21.E A2.2/A2.3/A2.4 范围 + ADMIN_PRD_C_KG.md | Session A1' (Admin Beta) 后续的 KG 管理子 Session |
| N8 | MCP Server / 用户态 API (`/api/v1/brands/{id}` 等) | 决策 #26.C3 + Session 3' 范围 | Session 3' |
| N9 | Citation Tier 参数表 / `pr_score` / `basePriceByTier` 参数服务 | 决策 #19 (Session A5) 范围 | Session A5' (Citation Tier CRUD) |
| N10 | LLM live smoke (跑真 VOLC_API_KEY) | 决策 #27 §G C1 同样 deferred 模式; 本 Session Phase Gate 接受 dry-run canned-transport 作为等效证据; live smoke 是手工后续任务 | (无明确 Session, 手工任务) |
| N11 | accounts/ 从 engines/ 迁到 platform/ 的 git mv | 本 Session 落 platform/ 仅 KG 部分, accounts/ 不动 (决策 #28.A 未来再迁) | Session A1' 或更晚 |
| N12 | Frontend (前端展示 KG / Admin UI 真渲染) | 决策 #29 工程质量原则 backend-first; Phase Gate 接受 JSON 端点 + 占位 UI | Session 4b' (JSX→TSX + IA v2.0) 重构 + Session A1' Admin Beta |

---

## §3 STOP Triggers (规则 12)

下列任一触发即停止实施, 报告 Frank 等待决策, 不要尝试自己绕开。

### Type A · 环境失败 (必须停)

- **A1**: `alembic upgrade head` 在 preview PG 报错 (除非是已知的 Session 0' baseline 漂移, 那就先回 Session 0' 修)
- **A2**: pyproject.toml 缺 sqlalchemy[asyncio] / asyncpg / httpx / alembic / pydantic v2 任一; 不要自行 `pip install`, 必须改 pyproject.toml + 报告 Frank
- **A3**: Python 版本 < 3.11 (本 Session 用 PEP 695 type alias + Self type)
- **A4**: `backend/app/platform/` 已存在但内容与本 Prompt 期望冲突 (历史污染)
- **A5**: Session 0' 提供的 `backend/app/db/session.py` (AsyncSession factory) 不存在或 import 失败
- **A6**: Session 1' 的 `backend/app/engines/parsers/normalize.py`(`registrable_domain` / `normalize_brand_name` 双入口) import 失败 — KG dedupe 需要复用这个模块, 不能写第二份

### Type B · 真相源冲突 (必须停)

- **B1**: DATA_MODEL §1.9 `kg_mined_relations` 表结构与本 Prompt 期望不同 (e.g. confidence_score 列类型 / 公式 / 晋升阈值变了) — 改 DATA_MODEL 是真相源 PR, 不能在本 Session 内改
- **B2**: 决策 #23 §H "EVIDENCE_DECAY = 0.85" 与 PRD/DATA_MODEL 中的描述不一致 — 必须先对齐真相源
- **B3**: PRD §4.10 国际化字段 (name_zh/name_en/aliases) 列表与本 Prompt 期望偏离 (e.g. 多了一个 name_jp)
- **B4**: REPLAN §4 Session 1.5' 的 4 行业 slug (beauty-personal-care / luxury / food-beverage / fashion-apparel) 任一与 PRD §4.0 行业枚举不符
- **B5**: 决策 #23 §H 5 条硬约束任一描述被改动 — 必须先回 CLAUDE.md decision history 对齐

### Type C · 范围溢出 (必须停)

- **C1**: 实施过程发现 Topic Pool stub 不够, 必须实现部分 Topic 才能跑通 seed 脚本 — STOP, 报告 Frank, **不要**偷跑 Session 2' 范围
- **C2**: 实施过程发现 Response 挖掘 (`relation_extractor.py`) 不接 worker 就跑不通 e2e — STOP; 本 Session 只落算法, wire 到 worker 留 Session 3'
- **C3**: 实施过程想给 4 行业之外加第 5 个行业 (e.g. consumer-electronics) — STOP, 4 行业是 MVP 锁定 (REPLAN §7 不变量)
- **C4**: 实施过程 pytest 覆盖率难以达 80% (sqlalchemy_repo 真实跑要起 PG container) — 把 sqlalchemy_repo 加 omit 是允许的; 但其他模块 < 80% 必须 STOP 增测试, 不要降阈值
- **C5**: 实施过程发现需要新 harness rule 拦截某种回归 (e.g. EVIDENCE_DECAY 被硬编码) — STOP, 在 Phase Gate 中报告需求, 由 Frank 决定是否在 Session 1.5' 范围内增 harness 或留到 Session 2'.1 Group H

---

## §4 Phase Gate (3 层验收)

### L3/L4 Phase Gate 卡控 (Hard Fail, 决策 2026-04-26)

**真相源**: `docs/REPLAN_2026_04_26.md §5` L3/L4 测试覆盖矩阵 + §5.3 Hard Fail 卡控规范.

**Hard Fail 强制**: 下列 L3/L4 任一未跑绿, GitHub Actions branch protection 拦截 merge. 不允许 soft warning, 不允许临时跳过.

**本 Session 必跑 L3 集成测试 (3 项)**:
- 火山 Ark client (`callJson`/budget exceeded/3 模型定价); category_tree 3 级 + level-4 容错丢弃; brand_discovery 跨 category 去重 + COMPETES_WITH/SAME_GROUP 边写入

**本 Session 必跑 L4 E2E 测试**: 本 Session 无 L4 (无 UI 端到端)

**补救测试**: **TS#1.5 → Python pytest 154+** (master 132 例覆盖 llm/db/discovery/knowledge_graph/scheduler 全部翻译)

**Phase Gate 通过条件 (在原有 Layer 1-3 基础上追加)**:
- G_L3.1: 火山 Ark client + category_tree + brand_discovery 3 项集成测试全部绿
- G_Remedial.1: master TS 132 例测试翻译完整, pytest 测试数 ≥ 154

### Layer 1 · CI 自动验收 (`bash scripts/verify-session-1.5prime.sh`)

| Check | 命令 | 期望输出 |
|-------|------|----------|
| L1.1 ruff strict | `uv run ruff check backend/app/platform/ backend/scripts/seed_platform_data.py backend/tests/unit/platform/` | 0 errors |
| L1.2 mypy strict | `uv run mypy --strict backend/app/platform/ backend/scripts/seed_platform_data.py` | 0 errors |
| L1.3 pytest platform unit + coverage ≥ 80% | `uv run pytest backend/tests/unit/platform/ --cov=backend/app/platform --cov-fail-under=80 -v` | 全绿, 覆盖率行打印 ≥ 80% |
| L1.4 alembic upgrade + downgrade 双向幂等 | `cd backend && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head` | 三次跑通无报错 |
| L1.5 ci-harness 现有 9 规则 (Group F) 仍绿 + selftest 9/9 | `python scripts/python/ci-harness.py && python scripts/python/ci-harness-selftest.py` | 全绿; selftest `PASS  (9 / 9 fixture expectations met)` |
| L1.6 import smoke (Platform Layer 不漏 import) | `python -c "from backend.app.platform import LlmClient, KgRepositories, InMemoryKgRepositories, confidence_from_evidence, classify_promotion, EVIDENCE_DECAY"` | 无 ImportError |
| L1.7 EVIDENCE_DECAY 锁定 + 数值正确 | `python -c "from backend.app.platform.knowledge_graph.confidence import EVIDENCE_DECAY, confidence_from_evidence; assert EVIDENCE_DECAY == 0.85; assert abs(confidence_from_evidence(5) - 0.5563) < 0.001"` | 无 AssertionError |
| L1.8 LLM call budget guard | `python -c "from backend.app.platform.llm.client import LlmClient, LlmCallBudgetExceededError; print('budget guard OK')"` | 打印 budget guard OK |
| L1.9 Platform Layer 不读 User/Project (静态扫描) | `! grep -rE "from backend\.app\.users|from backend\.app\.projects|from app\.users|from app\.projects" backend/app/platform/` | 无任何匹配 (! 前缀确保零匹配返 0) |
| L1.10 dry-run seed 脚本 (canned LLM transport) | `cd backend && uv run python scripts/seed_platform_data.py --dry-run --industry=beauty-personal-care --max-llm-calls=20 --product-brands=5` | 输出 ≥ 20 brands + ≥ 5 products + 0 errors; exit code 0 |

### Layer 2 · Harness selftest (本 Session 不增 fixture, 复测 9/9)

本 Session **不引入新 harness rule** (REPLAN §6.5 把 KG 守护放 Group H 留 Session 2'.1)。但需要确保:

- Group F 的现有 6 fixture (F1/F2/F3/F4-1/F4-2/F4-3) 仍 pass (`python scripts/python/ci-harness-selftest.py` 报 `PASS  (9 / 9)`, 含 Session 0' 的 3 + Session 1' 的 6)
- 现有 ci-harness.py 的 file glob 必须包含 `backend/app/platform/**`, 否则 Platform Layer 写了违规代码 (e.g. F1 bare playwright import) 不会被扫到
- 本 Session 未在 `backend/app/platform/` 下引入任何 playwright import (F1) / inline prompt literal (F3 — 因为 KG seed 全走 prompt 模板文件 `discovery/prompts.py`, 不内联到测试)
- 若本 Session 测试代码意外触发 F2 (HAR 泄漏) 是 **bug**, 因为 KG 不涉及 HAR 录制; STOP 排查

### Layer 3 · Frank 静态产品审查 (preview env 必查 5 项, REPLAN §4 Phase Gate 显式要求)

| # | 审查项 | 期望证据 |
|---|--------|----------|
| S1 | preview deployment alembic head 跑通 (CI/CD 日志) | Vercel preview build log 含 `alembic upgrade head ... OK`, 无 ERROR |
| S2 | preview env Admin URL 看到品牌列表 | Frank 浏览器开 `https://genpano-preview.vercel.app/admin/kg/industries/beauty-personal-care` (登录 Admin), DevTools Network panel 看 `/admin/api/v1/platform/industries/beauty-personal-care/brands` 返回 200 + JSON `[{"id":..., "name_zh":"雅诗兰黛", "name_en":"Estée Lauder", ...}, ...]` 长度 ≥ 20 |
| S3 | seed 脚本输出真实度 (无 placeholder/Lorem) | Frank 看 `python scripts/seed_platform_data.py --dry-run --industry=beauty-personal-care` stdout, 验证 brand 名 (e.g. "雅诗兰黛", "兰蔻", "欧莱雅") + product 名 (e.g. "小棕瓶", "小黑瓶") 真实可查 — 决策 #21 mock 真实性原则 |
| S4 | 4 行业 seed coverage (preview DB 看 kg_industries 表) | Frank 在 preview Admin 或 SQL 工具 `SELECT slug, name_zh, name_en FROM kg_industries ORDER BY slug` 看到 4 行 (beauty-personal-care, fashion-apparel, food-beverage, luxury) |
| S5 | mined relation 不污染高置信度真表 | 看 preview DB `SELECT relation_type, COUNT(*) FROM kg_brand_relations GROUP BY 1` (本 Session 仅写 LLM bootstrap 高置信度 COMPETES_WITH/SAME_GROUP) + `SELECT relation_type, COUNT(*), AVG(confidence_score) FROM kg_mined_relations GROUP BY 1` (Response 挖掘累积低置信度); 两表 schema 隔离 |

---

## §5 12 步交付顺序

每步独立 commit, 信息格式 `Session 1.5' Step <N>: <主题>` (无 emoji, 无 `§` / `→` 等特殊 Unicode, 决策 #25 Phase 2 commit 规则)。

- **Step 0** Branch + pyproject.toml omit 列表追加 + Alembic baseline migration 文件骨架 (空 upgrade/downgrade)
- **Step 1** 7 张 KG 表 Alembic migration 全实现 (kg_industries / categories / brands / products / brand_relations / product_relations / mined_relations) + CHECK 约束 + 索引 + UNIQUE 约束; alembic upgrade/downgrade 双向幂等测试通过
- **Step 2** `app/platform/llm/client.py` LlmClient + LlmCallBudgetExceededError + LlmJsonParseError + estimate_cost_usd; pytest ≥ 15 例 (httpx mock 走 respx)
- **Step 3** `app/platform/db/ports.py` Protocol + `app/platform/db/memory_repo.py` 单测专用; pytest ≥ 18 例 (字段命名陷阱 + 多 industry 隔离 + key 组合)
- **Step 4** `app/platform/db/sqlalchemy_repo.py` 生产版; 写好 ON CONFLICT upsert 但 **不写单测** (留集成测试 Session, 加 omit)
- **Step 5** `app/platform/knowledge_graph/{confidence,brand_relations,product_relations,relation_extractor}.py` 4 模块; pytest ≥ 30 例 (EVIDENCE_DECAY 锁定 + classify_promotion 边界 + 对称/有向边 + relation_extractor 正则匹配)
- **Step 6** `app/platform/discovery/{types,prompts,dedupe}.py` 3 模块 (类型/Prompt 模板/去重纯函数); pytest ≥ 12 例 (NFKD + alias 合并 + primaryName 归一化)
- **Step 7** `app/platform/discovery/{category_tree,brand_discovery,product_discovery}.py` 3 个 LLM-driven 编排器; pytest ≥ 18 例 (level-4+ 容错 + budget exhausted 部分返回 + per-brand throw skip + resolveCategoryId 三级回退)
- **Step 8** `app/platform/scheduler/platform_scheduler.py` + `app/platform/seed/mvp_industries.py` + `app/platform/planner/topic_pool.py` (stub); pytest ≥ 15 例 (assign_tiers + build_enqueue_plan + cost cap 触发 deferred)
- **Step 9** `backend/scripts/seed_platform_data.py` argparse + dry-run canned-transport pattern matching + live transport 占位; 端到端跑通 dry-run for beauty-personal-care
- **Step 10** Admin 只读端点 `GET /admin/api/v1/platform/industries/{slug}/brands` (FastAPI router) + requireAdminSession 复用 (Session A0' 的 `app/admin/auth/dependencies.py`); pytest 端到端 ≥ 3 例 (200 + JSON shape + 401 unauthorized + 404 unknown industry)
- **Step 11** `scripts/verify-session-1.5prime.sh` 全 10 check 跑通; ci-harness 现有 9 规则的 file glob 加 `backend/app/platform/**`; selftest 仍 9/9
- **Step 12** docs sync: `SESSION_PROGRESS.md` Session 1.5' ⬜ → ✅ + `CLAUDE_CODE_SESSIONS_PYTHON.md` 加 commit hashes + `CLAUDE.md` append 决策 #36 块 + `docs/SESSION_1_5_PRIME_DELIVERY.md` 新建交付报告 (按 §6 模板)

---

## §6 交付报告模板 (Step 12 写到 `docs/SESSION_1_5_PRIME_DELIVERY.md`)

```markdown
# Session 1.5' 交付报告 (2026-04-XX)

## A. Phase Gate 实测

- L1.1 ruff: <PASS/FAIL, n errors>
- L1.2 mypy: <PASS/FAIL, n errors>
- L1.3 pytest: <X passed / 0 failed>, coverage <Y.YY%>
- L1.4 alembic 双向: <PASS/FAIL>
- L1.5 ci-harness Group F: <PASS/FAIL>; selftest <9/9 PASS>
- L1.6 import smoke: <PASS/FAIL>
- L1.7 EVIDENCE_DECAY 锁定: <PASS/FAIL>
- L1.8 budget guard: <PASS/FAIL>
- L1.9 Platform Layer 不读 User/Project: <PASS/FAIL>
- L1.10 dry-run seed: brands=<N>, products=<M>; 0 errors

L3 (Frank 静态审查 5 项): S1-S5 各打 PASS/FAIL + 1 行证据

## B. 偏离登记 (规则 3)

- C1 (...): 描述 + 理由 + 真相源同步去向
- C2 (...): 同上
[... 实施过程任何与真相源不一致的细节都要登记 ...]

## C. 真相源同步

- DATA_MODEL §1.x: <无变化 / 同步段号 + 改动摘要>
- PRD §4.0.x: <无变化 / 同步段号 + 改动摘要>
- 决策 #36 已 append 到 CLAUDE.md

## D. CLAUDE.md 决策 #36 (Session 1.5' 交付)

[完整 §A-§E 块, 含算法翻译表 / 目录 / 偏离 / pytest 实测覆盖率 / Phase Gate evidence; 沿用决策 #23 §A-§H 编号风格]

## E. 下一 Session 依赖确认

- Session 2' (Planner Pipeline) 入口确认: `backend/app/platform/planner/topic_pool.py` 已 stub, Session 2' 替换实现; `app/platform/seed/mvp_industries.py` 4 行业可消费; `app/platform/db/sqlalchemy_repo.py` 提供 KgRepositories 给 Planner
- Session 1.2' (Camoufox + Live) 不直接依赖本 Session, 但 Session 3' (分析引擎 wire `relation_extractor` 到 worker) 依赖本 Session §B `knowledge_graph/relation_extractor.py` 算法落地
- Session A1' (Admin Beta) 的 KG 子 Session 依赖本 Session §17 的 Admin 端点 stub 作为 CRUD UI 起点
```

---

## §7 闭环回路 (规则 7 收尾一致性检查)

Session 收尾前最后一步, **重新跑 §0 的 F1-F8 8 条 grep**, 验证:

- 真相源段号未漂移 (e.g. 决策 #23 在 CLAUDE.md 第 N 行仍能 grep 到)
- 本 Session 修改的真相源 (`SESSION_PROGRESS.md` / `CLAUDE_CODE_SESSIONS_PYTHON.md` / `CLAUDE.md` 决策 #36) 已 commit + push
- 本 Session 引用的真相源 (PRD §4.0 / DATA_MODEL §1.x / 决策 #23 §H) 仍存在且未被本 Session 误改
- 若发现新偏离, 回 §6 报告 C 段补登记

---

## §8 10 条最终提醒

1. **真相源不重抄**: 本 Prompt §1 表格已锚定 PRD §4.0 / DATA_MODEL §1.x / 决策 #23 §B 等具体段号; 实施代码注释里只引用段号, 不重抄定义。EVIDENCE_DECAY = 0.85 这个 magic number 必须有注释 `# 见 DATA_MODEL §1.9 + 决策 #23 §H` 而不是重新解释公式。
2. **commit 信息纯文本**: `Session 1.5' Step <N>: <主题>` 格式, 禁 emoji, 禁 `§` / `→` / `✅` 特殊 Unicode (决策 #25 Phase 2 + auto-memory `feedback_genpano_session_commit_rule.md`); 标题 ≤ 72 字符; body 引 CLAUDE.md 决策号或 PRD/DATA_MODEL 段号。
3. **常量单一入口**: EVIDENCE_DECAY = 0.85 唯一在 `app/platform/knowledge_graph/confidence.py` 顶级; LLM call budget 50 唯一在 `app/platform/llm/client.py` 默认参数; 4 行业 slug 唯一在 `app/platform/seed/mvp_industries.py` 顶级 dict; 任何重复定义触发 STOP Type B (B5)。
4. **NFKD/NFKC 归一化**: 任何品牌名/产品名相等比较都必须先经 `unicodedata.normalize("NFKD", s).lower()`; 唯一入口 `app/platform/discovery/dedupe.py` 的 `normalize_for_match()`; 测试必须有 1 例 `"Estée Lauder" == "estee lauder"` 锁定。
5. **httpx mock 走 respx**: LLM client 单测必须用 `respx.mock` 拦截火山 Ark URL, 禁止真实网络调用; 测试启动前 fixture 设 `VOLC_API_KEY="test"` env, 但 transport 替换为 mock; CI 默认 dry-run + canned, live 留手工。
6. **kg_mined_relations 是低置信度入口**: brand_discovery / product_discovery 期间 LLM 抽到的关系**绝不**直接写 `kg_brand_relations` / `kg_product_relations`; 必须先 `mined_relations.bump_evidence(...)` (evidence_count += 1, confidence 重算), 待累积到双阈值才 promote; pytest 必须有 1 例 "evidence_count=1 时 confidence ≈ 0.15, 不 promote" 锁定。
7. **Platform Layer 边界严守**: `backend/app/platform/**` 任何文件不得 `from app.users.*` / `from app.projects.*`; ruff 自定义规则或 pytest import smoke 双轨守护; ci-harness L1.9 已锁定。Admin 端点是唯一例外 (它在 `backend/app/api/admin/**` 而非 `backend/app/platform/**`)。
8. **零 Frontend 修改**: 本 Session 不动 `frontend/`; Phase Gate Layer 3 S2 的"看到品牌列表"是 Admin 后台占位 UI 渲染 JSON 端点结果, 不要求精美; 真渲染 + IA v2.0 留 Session 4b'。
9. **每个 commit 都过 verify**: `bash scripts/verify-session-1.5prime.sh` 全绿才能 push; 中途 commit 也要保证 ruff + mypy + pytest 三件套绿 (即使 pytest 因为还未写完某模块覆盖率没到 80%, 也要在该 commit 内补足或加 `# pragma: no cover` 标注)。
10. **闭环必跑**: §7 的 §0 grep 重跑是最后一个步骤, 不要漏; 任何 grep 失配立即回 §6 偏离登记表新增 C 行 + 同步 CLAUDE.md 决策 #36 的 §C 段 (偏离段)。
