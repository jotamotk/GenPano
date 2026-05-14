# GenPano App 端后端补齐计划

> 2026-05-08 update (PR #386): Phase R.4 (admin_console → FastAPI) is complete.
> The Flask `admin_console/` package has been deleted; Admin APIs now live
> under `backend/app/api/admin/*`, the SPA shell at `backend/static/admin.html`,
> and the four shared modules (`topic_plan.py`, `prompt_matrix.py`,
> `segment_profiles.py`, `_layer_classifier.py`) under `backend/app/services/`.
> References below describing `admin_console/*` are historical context for
> the plan; the migration tasks themselves are done.

## Context

GenPano App 端 = 用户侧产品 web app（与橙色 `/admin` 运营控制台对立）。
此次计划要解决的痛点：

- **前端页面已基本就绪**：`frontend/src/pages/` 共 21 个 page + 7 个 component，
  Brand Mode（9 子页）、Industry Mode（4 子页）、Auth、Onboarding、Reports、
  Diagnostics、Settings 视觉与交互全部到位。
- **但页面全部读 `frontend/src/data/mock.js`**（21 page + 7 component 引用），
  没有任何产品 API 接入，登录之外的功能无法在真实数据下运行。
- **后端 FastAPI 仅完成 Auth**：`backend/app/api/v1/auth/` 有 14 个端点，
  其余产品 API（`/v1/projects/*`、`/v1/brands/*`、`/v1/industries/*` …）
  在 `docs/openapi.yaml` 已规划，但**没有任何实现**。
- 与此同时，**采集 + 分析 pipeline 早已跑通**（`geo_tracker/`），
  `admin_console/app.py`（15,391 行 Flask）已经把 `brand_mentions`、
  `response_analyses`、`geo_score_daily`、`industry_benchmark_daily`、
  `product_score_daily`、`citation_sources` 等核心分析表写满；
  Topic Plan / Prompt Matrix / Query Pool / Segment / Profile 等运营写流程
  也都在 admin 完成。

因此本计划的核心目标 = **先做选择性重构（Phase R）打好规范基础，再补齐 FastAPI
`/api/v1/*` 产品 API**，让前端页面从 mock 切换到真实数据。pipeline / analyzer
不重写，但 Flask `admin_console` 迁移到 FastAPI、所有迁移并入 Alembic、前端
统一 TypeScript。

### 已确认的架构选择（2026-05-04）

| 维度 | 选择 | 影响 |
| --- | --- | --- |
| 重构范围 | 选择性重构 | 新增 Phase R（≈ 2 周）做地基整理 |
| 服务边界 | Admin 也迁到 FastAPI | `admin_console/app.py` 15391 行 Flask → `backend/app/api/admin/*`；Flask 退役 |
| 前端栈 | Vite + React 全 TypeScript | Phase R 内把 21 个 `.jsx` page → `.tsx`；Vite 不动 |
| Schema SSOT | 全部并入 backend Alembic | `migrations/0xx*.sql` 转 alembic 版本；唯一 head；ORM 单源 |

> 名词：**Project** = 用户在 App 端创建的"我要监测的事"，包含主品牌、行业、
> 竞品池、偏好；多租户隔离的边界。一个用户可有多个 Project。

---

## 现状速查（避免重复劳动）

### ✅ 已完成（不要重写）

| 资产 | 路径 | 说明 |
| --- | --- | --- |
| Auth API | `backend/app/api/v1/auth/router.py` | 14 端点：lookup/register/login/setup/forgot/reset/me/google… |
| 数据采集（3 adapter） | `geo_tracker/agent/` | ChatGPT / 豆包 / DeepSeek |
| Analyzer 骨架（半成品 ⚠️） | `geo_tracker/analyzer/` | brand_detector / sentiment / citation / geo_scorer / aggregator / llm_analyzer 跑得起来，但**关键字段未填、零单测、6 处 TODO**，详见下方 §"Analyzer 完成度审计" |
| 调度 | `geo_tracker/tasks/{scheduler.py,celery_tasks.py}` | Celery + Redis |
| ORM 模型（写权限） | `geo_tracker/db/models.py` | 完整 schema mirror |
| 后端 ORM（分析表只读） | `backend/app/models/analyzer.py` | 与 SQL migration 1:1，可直接 select |
| 分析表 schema 存在 | DB | `brand_mentions`、`sentiment_drivers`、`citation_sources`、`response_analyses`、`product_feature_mentions`、`geo_score_daily`、`industry_benchmark_daily`、`product_score_daily` 表结构齐 — **但 analyzer 没把所有字段填好**（如 `citation_rate=0.0`、`attribution_method=NULL`、`page_type=NULL`） |
| 上游表 CRUD（操作员侧） | `admin_console/app.py` | `/api/admin/{topic-plan,prompt-matrix,query-pool}` 全套 + brands/products/users/segments/profiles |
| 可复用工具模块 | `admin_console/{topic_plan.py(700), prompt_matrix.py(1076), segment_profiles.py(568), _layer_classifier.py(118)}` | LLM safety gate、layer 分类、intent/language 校验 |

### 🛠️ Analyzer 完成度审计（基于 2026-05-04 代码 audit）

| 模块 | LOC | 完成度 | 已完成 | 缺失（必须补） |
| --- | --- | --- | --- | --- |
| `aggregator.py` | 474 | 85% | 日聚合、industry ranking、top brand JSON | `citation_rate` 硬编码 0.0；无 weekly；无 attribution / page_type / domain_authority 聚合；无 cross-brand 维度 |
| `brand_detector.py` | 128 | 95% | rule-based + alias + CJK/Latin 分词 + context | 单测 0；error path 弱 |
| `citation_mapper.py` | 166 | 90% | URL→domain、5 类 source_type、品牌关联 | 无 `attribution_method`、`page_type`、`authority_tier` 三字段写入 |
| `geo_scorer.py` | 121 | 100% | 4 维 GEO 分（visibility/sentiment/SoV/citation） | 无（算法层完整） |
| `llm_analyzer.py` | 232 | 95% | Ark/DouBao + json_repair 解析 + 维度抽取 | error 类型粗糙（全部失败 → empty）；retry 策略弱；硬编码 ARK_API_KEY env |
| `sentiment_analyzer.py` | 122 | 90% | 火山 NLP + 关键词 fallback | fallback 仅关键词无 ML；无缓存；batch=8 无优化 |
| `cli.py` | 493 | 80% | run-daily / aggregate / reanalyze 全 3 阶段编排 | 无 weekly 命令；无 CSV/PDF 报告；无日期切片；无 diagnostics 触发 |
| `prompts.py` | 87 | 100% | 模板齐 | — |
| **总计** | **1823** | **88% 平均** | — | **0% 单测**：`tests/test_analyzer/` 不存在，仅 CLI 集成测试 |

### ❌ 缺失（本计划要补齐 — 不止 6 张表）

| 缺口 | 后果 |
| --- | --- |
| 产品 API 路由树（`/api/v1/projects` / `/brands` / `/industries` / `/topics` / `/citations` / `/products` / `/competitors` / `/reports` / `/diagnostics` / `/leads` / `/crawl`） | FE 无法接真实数据 |
| 多租户层（`projects`、`project_competitors`、`project_topic_pins`、`commercial_leads`、`report_jobs`、`crawl_requests` 6 张新表） | 没有 user → data 的归属链 |
| `current_user` / `current_project` 依赖 + RFC 7807 错误统一 | 越权风险 + 错误形状不一致 |
| Celery 任务：`reports.generate`、`crawl.user_request`、`leads.notify` | 报告 / 用户手动采集 / 线索通知都没异步链路 |
| **Analyzer 半成品：6 个新模块 + 5 个旧模块补齐 + 3 张新表 + 0 单测**（详见 Phase A） | 多个 FE 图表无真实数据可读 |
| FE 21 个 page 切 mock → React Query | 视觉完成但跑不动 |

### ⚠️ 历史包袱（Phase R 解决）

| 问题 | 位置 | 处理 |
| --- | --- | --- |
| 双前端入口 | `frontend/src/{App.jsx, App.tsx, main.jsx, main.tsx}` | 仅保留 `App.tsx + main.tsx`，删除 `.jsx` |
| 废弃页面 | `pages/{DashboardPage.linear.jsx, LandingPageLegacy.jsx, IndustryPage.jsx, QueriesPage.jsx}` | 删 |
| 21 page 是 `.jsx` | `frontend/src/pages/**/*.jsx` | 全部转 `.tsx`，强类型 |
| 双 contexts 目录 | `frontend/src/{context/, contexts/}` | 合并到 `contexts/`，命名一致 |
| Flask + FastAPI 双进程 | `admin_console/app.py` (Flask) + `backend/app/main.py` (FastAPI) | admin 迁 FastAPI，单 Python 进程 |
| SQL + Alembic 双源 | `migrations/0xx*.sql` + `backend/alembic/versions/` | 全部转 alembic，单 head |
| Tracker / backend ORM 重复 | `geo_tracker/db/models.py` + `backend/app/models/analyzer.py` | 抽 `genpano_models` 共享包；tracker / backend 都从这个包 import |
| ProfileGroup vs Segment 命名 | mixed | UI 统一 Segment；DB 表名保持 `profile_groups`（不动），ORM 类名 `Segment` |
| 路由 IA v2 + 大量 301 redirect | `frontend/src/App.tsx` | Phase R 留；Phase 2 末删除老 301 |

---

## 图表数据覆盖度（Pipeline ↔ FE Charts 现实性检查）

对 `frontend/src/data/mock.js` 中 51 个导出常量与现有 pipeline schema 做了一次
对照，结果如下（详细映射见审计 agent 输出）：

| 等级 | 数量 | 说明 |
| --- | --- | --- |
| ✅ Direct | 6 | `PROJECTS` `INDUSTRIES` `BRANDS` `PRODUCTS` `TOPICS` `ENGINES` 直接命中表 |
| 🔧 Aggregable | 17 | 趋势 / SoV / 情感分布 / 引用 / Mention list 等，对 `geo_score_daily` `brand_mentions` `sentiment_drivers` `citation_sources` `response_analyses` GROUP BY 即可 |
| 🧩 Composable | 2 | `BRAND_RELATIONS` `PRODUCT_RELATIONS` 需 KG 表（见 Phase K） |
| ⚠️ Partial | 6 | `DIAGNOSTICS` `AUTHORITY_SHARE_SERIES` `MENTION_POSITION_DATA` `SENTIMENT_DISTRIBUTION` `PROFILE_GROUPS` `TIER2_COVERAGE_MATRIX` — 服务层补一些计算即可 |
| ❌ GAP（**BLOCKER**） | 4 + KG 主体 | 见下表（KG 完全未实现，独立见 Phase K） |

### ❌ 4 个 BLOCKER（必须在 FE 切真实数据前补齐）

| # | 缺口 | 影响的 FE 数据 / 页面 | 解决方案 |
| - | --- | --- | --- |
| G1 | **citation 归因方法**（official_domain / co_occurrence / text_match）未分类 | `ATTRIBUTION_MISMATCH_DIAGNOSTIC`、`AUTHORITY_SHARE_SERIES`；`/brand/citations`、`/brand/diagnostics` | 给 `citation_sources` 加 `attribution_method VARCHAR(32)`；analyzer extend `citation_mapper.py` 加分类逻辑（见 Phase A.3） |
| G2 | **domain authority tier 表** 不存在（Tier 0-4: Unknown/Official/Tier2/KOL/UGC） | `PR_TARGETS`、`KOL_SCORECARDS`、`AUTHORITY_RADAR_DATA`、`TIER2_COVERAGE_MATRIX`；`/brand/citations`、`/brand/diagnostics` | 新表 `domain_authorities`；≈ 200 条种子；周聚合（见 Phase A.4 + A.8） |
| G3 | **响应来源 page type 分类**（评测页 / 榜单页 / KOL 文 / 知识百科 / 产品页）未做 | `CONTENT_GAP_PAGE_TYPE_DISTRIBUTION`；`/brand/diagnostics` | analyzer 扩展（见 Phase A.5） |
| G4 | **品牌集团关系**（同集团 / 母公司 / 共享域名）未建表 | `SAME_GROUP_SHARED`；`/brand/overview` 同集团对比卡 | 新表 `brand_groups` + `brand_group_members`；analyzer 周聚合共享域名（见 Phase A.6） |

### ❌ KG（知识图谱）主体未实现 — 独立见 Phase K

PRD §4.0.1a 规定 5 张 `kg_*` 表 + LLM 关系边推断，**当前一行真实数据都没有**。
影响：`/industry/knowledge-graph` 整页（FE 自带硬编码 `RAW_NODES`/`RAW_LINKS`）、
`BRAND_RELATIONS` `PRODUCT_RELATIONS` `CATEGORIES` mock 常量、
`getCompetitors(brandId)` 辅助函数。
解决：Phase K 7 个子任务（K1 schema → K7 FE 切真实），≈ 3.5 周。

> 这些缺口不是"加端点就行"，而是 pipeline 本身没产出这些信号。
> 必须在 Phase 4（报告/诊断）之前**或同时**补齐。
> Phase 2 的 `/brand/overview`、`/brand/citations`、`/brand/diagnostics` 三页可以
> **先做 ✅/🔧/🧩 部分**，BLOCKER 模块在 Phase A / K 上线后再切。
> Phase 3 的 `/industry/knowledge-graph` 必须等 Phase K 完。

---

## Phase P — PRD 完善 + 契约固化（≈ 1.5 周，**先于所有实现**，新增）

为什么先做：现有 `docs/PRD.md`（7487 行）只覆盖到原始 13 子页 + 原始 5 张分析表，
本计划新增 30+ 张表、约 95 个端点、6 个 phase（A/K/D/RP/M/N/E）的设计决策，
团队若不先把 PRD / DATA_MODEL / OpenAPI / ADR 锁定，每个 phase 都会重新发明轮子
和返工。投入 1.5 周买后续 11 周不返工。

### P1. PRD 主文档增补章节（≈ 0.7 周）

#### P1.1 用户产品 PRD（`docs/PRD.md`）

- **§4.7 Diagnostics 完整规则集** — 25+ 条 rule_id × category × severity 矩阵
- **§4.7.1 Diagnostic 数据结构** — 与 `DIAGNOSTICS` mock 完全对齐的字段表
- **§4.7.2 Reports 4 type × 10 section × 3 reader 矩阵** — `SECTION_MATRIX` +
  lead_diagnostic 独立 4 layer view
- **§4.7.3 Alerts 触发规则 + Notifications** — alert source 枚举、quiet hours、
  3 个 SettingsPage toggle 精确语义、邮件模板规范
- **§4.7.4 Exports** — 8 种 exportType schema、配额、AuthPromptModal hook
- **§4.7.5 Brand Submission 用户侧** — 提交字段、审核流、入 KG 的链路、status 状态机
- **§4.7.6 Simulator** — 公式 + tier delta 上限 + base_price_equivalent 行业参数表
- **§4.5.2 MCP 完整契约**（已有但补强）— 9 tools + 3 resources 的 input/output schema，
  API key scope 模型 + rate limit + usage stats

#### P1.2 Admin 运营 PRD（`docs/ADMIN_PRD.md`）

ADMIN_PRD 已有 §4.2 + §4.3 + §4.4 13 子模块的高层设计，本 phase 补**字段级 schema +
端点契约 + 状态机**：

- **§4.2.1-4.2.6** Pipeline Overview / Engines / Queue / Pool / Proxies / Retry — 加
  `engine_health_daily` / `proxy_health_daily` 字段表 + retry-center 状态机
- **§4.3.6** KG Discovery Logs — `discovery_log` 字段 + 幻觉率定义
- **§4.4.1** 成本看板 — `cost_events` 写入点矩阵（pipeline / kg / mcp / reports
  各 source 列表）+ `budget_scope` 预算硬约束规则
- **§4.4.2** 告警中心 — alerts 表 `scope='operator'` 子集；6 类运营 alert 触发
  规则 + 告警 SLA（P0 5min / P1 1h / P2 24h）
- **§4.4.4** 公告 & 邮件 — `comms_announcements` 字段 + audience / channel 枚举
- **§4.4.5** 商务线索 admin 视图 — 状态机（new → contacted → closed）
- **§4.4.6** MCP 运营 — `mcp_call_log` partition + 配额自动暂停规则
- **§4.4.7** 审计日志 — `admin_audit_log` 字段 + audit_decorator 接入清单
  + 高风险 mutation 必审名单
- **§5.7 Audit Decorator 规范**（新增）— 统一 audit 注入接口

### P2. DATA_MODEL.md 全量更新（≈ 0.5 周）

`docs/DATA_MODEL.md` 当前缺很多新表。新增：

| 来源 | 表数 | 关键表 |
| --- | --- | --- |
| Phase 0 | 6 | `projects` / `project_competitors` / `project_topic_pins` / `commercial_leads` / `report_jobs` / `crawl_requests` |
| Phase A | 8 | `brand_official_domains` / `domain_authorities` / `brand_groups` / `brand_group_members` / `brand_group_shared_domains` / `competitor_mention_daily` / `geo_score_weekly` / `citation_weekly_by_domain` / `industry_topic_daily` |
| Phase K | 6 | `kg_categories` / `kg_brands` / `kg_products` / `kg_brand_relations` / `kg_product_relations` / `kg_relation_candidates` |
| Phase D | 1 | `diagnostics` |
| Phase RP | 2 | `report_schedules` / `report_share_tokens`（+ `report_jobs` 扩列）|
| Phase M | 2 | `user_api_keys` / `organizations`（+ users.default_org_id / projects.org_id 等）|
| Phase N | 3 | `alerts` / `alert_rules` / `user_notification_preferences` |
| Phase E | 2 | `export_jobs` / `brand_submissions` |
| **Phase O** | **6** | **`engine_health_daily` / `proxy_health_daily` / `discovery_log` / `cost_events` / `admin_audit_log` / `mcp_call_log` / `comms_announcements`** |

**总 ≈ 36 张新表 + 8 列 ALTER**。每表写：

- 字段（类型 / 默认 / 约束 / 注释）
- 索引（PK + 业务索引 + 复合索引）
- FK（+ ON DELETE 行为）
- 唯一约束
- 数据保留期 / 归档策略
- 多租户字段（`org_id`）位置
- ER 图（dbml 或 PlantUML）

### P3. OpenAPI 契约固化（≈ 0.5 周）

`docs/openapi.yaml` 当前 1557 行，把所有新端点写齐：

| 端点来源 | 估端点数 |
| --- | --- |
| Phase 0-3 产品 API 12 子包 | ≈ 60 |
| Phase D / RP / M / N / E 新端点 | ≈ 35 |
| **Phase O 9 个运营模块** | **≈ 35** |
| admin 迁 FastAPI 后所有 admin API（含 O 新增） | ≈ 135+ |

每端点写：req schema / resp schema / 4xx + 5xx error code + 1+ example +
stability tier（`stable` / `beta` / `experimental`）。

CI 在每 phase 末跑 `test_openapi_sync.py`：FastAPI 自动 schema vs YAML，
diff 白名单（`info.version` / `servers`）外即 fail。

### P4. ADR 落地（≈ 0.2 周）

新建 `docs/ADR/`，**只记必要决策**（每条 1 页内 — context / decision /
consequences / alternatives 各一段）：

| ADR | 决策 |
| --- | --- |
| ADR-001 | Admin Flask → FastAPI 单进程 |
| ADR-002 | Schema SSOT 单 Alembic head（`migrations/0xx*.sql` 转入）|
| ADR-003 | 前端全 TS + 单入口 `main.tsx`（删 `App.jsx`/`main.jsx`）|
| ADR-004 | ORM 共享包 `genpano_models`（顶级包，三处共享）|
| ADR-005 | 多租户 `org_id` 预留位（每用户默认 personal org）|
| ADR-006 | MCP 鉴权 = API key + Bearer（不上 OAuth）|
| ADR-007 | Analyzer 三新维度（attribution_method / page_type / authority_tier）落 `citation_sources` 列而非新表 |
| ADR-008 | Diagnostics 规则引擎 + LLM causal chain（缓存 24h，50 次/天/project 上限）|
| ADR-009 | Reports 4 type × 10 section × 3 reader matrix 服务端实现，不抽通用模板引擎 |
| ADR-010 | Alerts 与 Diagnostics 联动（severity ≥ P1 自动建 alert）|
| ADR-011 | KG `kg_brands`/`kg_products` 1:1 映射现有 `brands`/`products`，不复制业务字段 |
| ADR-012 | KG 关系边走 staging `kg_relation_candidates` → admin 审核 → `kg_*_relations` |
| ADR-013 | Admin 运营 `alerts.scope='operator'` 与用户 `scope='user'` 共表不同视图 |
| ADR-014 | Audit Decorator 统一注入：所有 admin 写操作必经 `@audit(action, severity)` |
| ADR-015 | `cost_events.scope` 四值（pipeline/kg/mcp/reports）独立预算硬约束告警 |

### P5. PRD ↔ FE Page 交叉表（≈ 0.1 周）

新建 `docs/PRD_PAGE_MAP.md`：21 page × {PRD 章节, 端点, 数据表, 测试链路} 矩阵。
任何后续 PR 改某 page 必须同步检查该表，缺则补；CI 加
`test_prd_page_links.py` 校验所有 page 注释中的 `PRD §X.Y` 锚点存在。

### Phase P 验收

- ✅ PRD §4.7.1-§4.7.6 + §4.5.2（重写）章节齐；
  ADMIN_PRD §4.2 + §4.3 + §4.4 字段级 schema 齐；
  DATA_MODEL.md 含 36 张新表 + ER 图；
  openapi.yaml 含 ≥ 230 端点；
  ADR 15 条全落。
- ✅ 21 page × PRD 章节 + 9 admin 模块 × ADMIN_PRD 章节交叉表完成。
- ✅ 启动会发"新设计 = PRD vNext"，相关方签字。
- ✅ CI 加 `test_prd_links_valid.py` + `test_openapi_sync.py` 进绿灯。

### Phase P 时间表

W0.0-0.7：P1.1 PRD §4.7.x + P1.2 ADMIN_PRD §4.2/§4.3/§4.4 章节增补（PM/tech lead 主笔）。
W0.5-1.0：P2 DATA_MODEL.md 36 表全量 + ER 图（DB engineer 主笔）。
W0.5-1.0：P3 OpenAPI 契约 230 端点（Backend lead 主笔）— 与 P2 并行。
W1.0-1.5：P4 ADR 15 条 + P5 PRD-Page 交叉表 + 启动会。

**与 Phase R.1 并行** — FE 改造（删 .jsx / TS 化）不依赖 PRD 决策，可与 W0.0-1.5
同时启动；但业务后端代码（Phase A/K/D/RP/M/N/E/O/0/1/2/3/4/5）必须等 Phase P
完成 + ADR 签字后才能开工。

---

## Phase R — 选择性重构（≈ 2 周，**新增**）

打好工程地基，再补齐业务功能。每条重构都有立即可验证的成果，不允许"先合后修"。

### R1. 前端入口收敛 + TypeScript 全量化（≈ 4 天）

**任务**：

- 物理删除：`frontend/src/{App.jsx, main.jsx, pages/DashboardPage.linear.jsx,
  pages/LandingPageLegacy.jsx, pages/IndustryPage.jsx, pages/QueriesPage.jsx}`。
- `frontend/index.html` 引用切到 `main.tsx`。
- 把 `App.tsx` 升级到完整路由（合并目前 `App.jsx` 的所有 route，包括
  Brand/Industry IA + 301 redirects + auth gates）。
- 把 21 个 `.jsx` page 与 7 个 `.jsx` component 全部改 `.tsx`，逐个加类型；
  以 `BrandPanoramaPanel` 为模板，定义 prop interface。
- 合并 `frontend/src/context/` ↔ `frontend/src/contexts/`，统一到
  `contexts/`，所有引用同步更新。
- `tsconfig.json` 启用 `"strict": true`、`"noUncheckedIndexedAccess": true`、
  `"exactOptionalPropertyTypes": true`；`"allowJs": false` 终态；
  过渡阶段保留 `allowJs` 但 lint 报警。
- 加 `eslint-plugin-import` `no-restricted-imports`：
  禁止 `pages/**` `import .. from '../data/mock'`（warn）。

**验收**：

- `find frontend/src -name "*.jsx"` 0 命中。
- `npm run build` 通过；`tsc --noEmit` 0 错误。
- `npm run dev` 视觉无回归（手测：landing → login → dashboard）。

### R2. Schema SSOT 收口 — 全部并入 backend Alembic（≈ 2 天）

**任务**：

- 把 `migrations/{001_analyzer_tables,002_scheduler_and_binding_tables,
  003_products}.sql` 转成 alembic 版本，写到
  `backend/alembic/versions/2026_05_xx_legacy_sql_into_alembic.py`：
  对**已存在**的表用 `op.execute("CREATE TABLE IF NOT EXISTS ...")` 并
  `mark_existing` 不重复建表，对**列与索引**用 `op.add_column / op.create_index`
  with `IF NOT EXISTS` 守卫。`downgrade()` 不实际删表（保留数据），但记录步骤。
- 验证现有数据库 `alembic upgrade head` 不重复建表、不丢数据。
- `migrations/` 目录改名为 `migrations.legacy/` 并加 `README.md` 说明
  "已转入 backend/alembic/versions/，不再追加"。
- 在 `backend/Makefile` 加 `make migrate`、`make migrate-down`。
- CI 在 fresh DB 上 `alembic upgrade head` → `alembic downgrade -1` →
  `alembic upgrade head`，确保可逆。

**验收**：

- 现网 DB（dev / preview）跑 `alembic upgrade head` 无变更（idempotent）。
- 全新空 DB 跑 `alembic upgrade head` 后表结构与现网一致。
- `geo_tracker/db/models.py` 与 `backend/app/models/analyzer.py` 字段集 diff 为 0。

### R3. ORM 共享包（≈ 2 天）

**任务**：

- 新建 `genpano_models/`（顶级包，与 `backend/`、`geo_tracker/`、`admin_console/`
  同级），把所有 ORM 模型集中：
  ```
  genpano_models/
    __init__.py
    base.py                 # DeclarativeBase
    user.py                 # 从 backend/app/models/user.py 移
    analyzer.py             # 从 backend/app/models/analyzer.py 移
    brand.py    industry.py    topic.py    prompt.py    query.py
    llm_response.py    profile.py    segment.py    llm_account.py
    proxy.py    browser_profile.py    scheduler.py    product.py
    project.py    project_competitor.py    project_topic_pin.py    # 新表
    commercial_lead.py    report_job.py    crawl_request.py        # 新表
  ```
- `backend/app/models/__init__.py` 与 `geo_tracker/db/models.py` 改为
  `from genpano_models import *`。
- `pyproject.toml` 把 `genpano_models` 作为本地路径依赖（`uv` workspace）。
- `admin_console/app.py` 也改用 `genpano_models`（R5 内做）。

**验收**：

- 三处 import 全切；`grep -R "from app.models" backend/`、
  `grep -R "from geo_tracker.db.models" geo_tracker/` 都改成
  `from genpano_models`。
- 后端、tracker、admin 所有 test 仍通过。

### R4. Admin Flask → FastAPI 迁移（≈ 5 天，最大块）

`admin_console/app.py` 15,391 行：拆解成模块化 FastAPI 路由器。

**目录设计**（在 `backend/app/api/admin/` 下）：

```
backend/app/api/admin/
  __init__.py
  router.py                       # 顶层 include 所有子 router
  session/router.py               # /api/admin/{session,login,logout}
  brands/router.py                # /api/admin/brands  /products
  topic_plan/router.py            # /api/admin/topic-plan/*
  prompt_matrix/router.py         # /api/admin/prompt-matrix/*
  query_pool/router.py            # /api/admin/query-pool/*
  scheduler/router.py             # /api/scheduler/*
  segments/router.py              # /api/segments/* (= profile_groups)
  profiles/router.py              # /api/profiles/*
  accounts/router.py              # /api/accounts/*
  users/router.py                 # /api/users/* (admin user moderation)
  analyzer/router.py              # /api/analyzer/*
  artifacts/router.py             # /api/{html,html_files,screenshot,task_status}
  stats/router.py                 # /api/stats /queries /prompts /topics
  templates/                      # 直接 mount 现有 Jinja /admin html 模板（保留 UI 不变）
```

**任务**：

- 在 `backend/app/main.py` 加 `app.include_router(admin_router, prefix="")`
  （admin 路由包含完整路径，不加 prefix）。
- 路由迁移按"一次一个 router 子包"渐进：每迁完一个，admin_console Flask
  侧的对应 route 先 deprecation log，preview 验证 1-2 天后删除。
- 复用模块（不重写）：
  - `admin_console/topic_plan.py` (700 LOC) → `backend/app/services/topic_plan.py`
  - `admin_console/prompt_matrix.py` (1076 LOC) → `backend/app/services/prompt_matrix.py`
  - `admin_console/segment_profiles.py` (568 LOC) → `backend/app/services/segment_profiles.py`
  - `admin_console/_layer_classifier.py` (118 LOC) → `backend/app/services/layer_classifier.py`
- Admin auth：把现 Flask session 改成 FastAPI cookie session
  （`itsdangerous.Signer` 或 `starlette.middleware.sessions.SessionMiddleware`），
  保留 `secret_key` 兼容（只换实现，不让管理员重新登录）。
- 模板：`admin_console/templates/admin.html` 移到
  `backend/app/templates/admin/admin.html`，FastAPI Jinja2Templates 渲染；
  CSS / JS 静态资源 mount 到 `/static/admin/`。
- nginx：`/admin` 改为指向 backend FastAPI :4000（不再单独起 admin :5000）。
- `admin_reset_password.py`、`analyze_estee_for_mock.py` 转 backend CLI
  （`backend/app/cli/admin_reset_password.py` 等）。
- 完成后归档 `admin_console/` → `legacy/admin_console_flask/`，仅留 README
  指向新路径；`docker-compose.yml` 删除 admin 服务定义。

**验收**：

- 单进程：仅 `backend` FastAPI（含 auth + admin + 产品 API），不再有 Flask。
- 所有原有 admin URL 在新进程下行为一致（用 Postman / `curl` 比对 200 个采样响应）。
- Admin UI 视觉无回归（截图比对）。
- 部署：`docker-compose.yml` 简化（admin 服务移除）；nginx 一处 upstream。

### R5. 共享开发体验（≈ 1 天）

- 仓库根加 `Makefile`：`make dev`（同时起 backend + worker + frontend）、
  `make ci`（汇总三处 CI）、`make migrate`。
- `pre-commit`：扩 frontend lint + backend ruff + alembic check（如新模型
  无新版本即报警）。
- CI matrix：python 3.11 / node 20；`workflow_dispatch` 加 `db: fresh|preview`。

### Phase R 验收

- ✅ 前端：仅 `.tsx`，单入口；`tsc --noEmit` 0 错。
- ✅ 数据库：单一 Alembic head；现网 DB 升级幂等；新 DB 一键起。
- ✅ ORM：单一 `genpano_models` 包；三处共用。
- ✅ 后端：单 FastAPI 进程，admin 路由全部迁过；旧 Flask 归档。
- ✅ 工程：`make dev` / `make ci` 一键起；CI 矩阵跑通。

---

## Phase 0 — 产品 API 骨架 + 新表迁移（≈ 1 周）

### 后端

新建路由骨架（每模块独立子包，先 501 占位）：

```
backend/app/api/v1/
  projects/       brands/        industries/    topics/
  citations/      products/      competitors/   reports/
  diagnostics/    leads/         crawl/         _meta/
```

每个子包 3 文件：`router.py`（FastAPI APIRouter） + `_dto.py`（Pydantic v2 schemas）
+ `service.py`（DB 查询与业务逻辑）。`backend/app/main.py` 一次 `include_router`，
统一 `prefix="/api/v1"`。

新建核心模块：

- `backend/app/core/security.py` — `current_user(token)` + `current_project(project_id)`
  依赖；非归属一律 404（不泄露存在性）。
- `backend/app/core/errors.py` — `problem+json` helpers（`unauthorized`、
  `forbidden`、`not_found`、`conflict`、`validation_error`），统一 `code` 字段
  供前端 i18n lookup。
- `backend/app/core/pagination.py` — cursor + limit 通用分页。
- `backend/app/core/filters.py` — 通用 query：`from`/`to`/`engine`/`profileGroup`
  解析为 SQLAlchemy where。

### 数据库

Alembic 新版本 `2026_05_xx_app_product_tables.py`，**仅新增**（不动 tracker 旧表）：

```
projects                (id UUID PK, user_id FK→users, name, industry_id FK→industries,
                         primary_brand_id FK→brands, is_active, preferred_engines TEXT[],
                         default_profile_group_id, created_at, updated_at, deleted_at?,
                         UNIQUE(user_id, name))
project_competitors     (project_id FK→projects ON DELETE CASCADE, brand_id FK→brands,
                         pinned_at, PK(project_id, brand_id))   -- 容量上限 10 在 service 层
project_topic_pins      (project_id, topic_id, state {'tracked'|'ignored'}, pinned_at,
                         PK(project_id, topic_id))
commercial_leads        (id UUID PK, user_id, project_id, source, context JSONB, status, created_at)
report_jobs             (id UUID PK, project_id, type {'pdf'|'csv'}, scope JSONB,
                         status {'queued'|'running'|'done'|'failed'}, output_url, error,
                         scheduled_cron, created_by, created_at, finished_at)
crawl_requests          (id UUID PK, project_id, brand_id, scope JSONB,
                         status, attempts, result_summary JSONB,
                         created_by, created_at, finished_at)
```

新增 ORM：`backend/app/models/{project.py, project_competitor.py, project_topic_pin.py,
commercial_lead.py, report_job.py, crawl_request.py}`。

引入 **read-only mirrors** 到 `backend/app/models/` 用于产品 API 查询（不参与写）：
`brand.py`、`industry.py`、`topic.py`、`prompt.py`、`query.py`、`llm_response.py`。
字段集只声明产品 API 用得到的列，与 `geo_tracker/db/models.py` 保持兼容。
后续 `models_drift_check.py`（CI）比对漂移。

### 前端配套

- 删除 / 归档：`frontend/src/{App.tsx,main.tsx}`、`pages/DashboardPage.linear.jsx`、
  `LandingPageLegacy.jsx`、`IndustryPage.jsx`、`QueriesPage.jsx`(0 字节)。
- 抽 `frontend/src/lib/apiClient.ts`：Bearer 注入、401 → `/login?redirect=`、
  RFC 7807 解析、`Accept-Language` 跟随 LocaleContext。
- 引入 TanStack Query v5 `QueryClientProvider`。
- 重新生成 `frontend/src/lib/api-types.d.ts`（`npm run gen:api-types`）。
- ESLint：`pages/**` 禁止 `from '../data/mock'`（warn → 后续 error）。

### 文档清理

- 旧文档 `docs/APP_FRONTEND_PLAN.md` 是误导名（在本计划起草过程产生），
  退出 plan 模式后删除或重命名为 `APP_BACKEND_PLAN.md`，避免后续 agent 误以为
  仅前端任务。

### Phase 0 验收

- `uv run uvicorn app.main:app` 启动；`/api/v1/_meta/routes` 列出 12 个新路由（暂返 501）。
- `alembic upgrade head` 成功；6 张新表存在。
- FE：`grep -R "from '../data/mock'" frontend/src/pages` ≤ 当前数（不再增）；
  `apiClient` 单测（401 / problem+json / 网络错）通过。

---

## Phase 1 — Project 生命周期（≈ 1 周）

让"用户拥有 Project，Project 决定看到的所有数据"立起来。

### 后端

`backend/app/api/v1/projects/router.py`：

- `GET /v1/projects` — 当前用户 project 列表（按 active desc, created_at desc）。
- `POST /v1/projects` — 创建：`name`、`industry_id?`、`primary_brand_id?`、
  `preferred_engines?`、`competitor_brand_ids?`（≤ 10 在 service 层校验）。
- `GET /v1/projects/:id` — 详情，embed industry / primary brand / competitors。
- `PATCH /v1/projects/:id` — 改名 / 改主品牌 / 改 active / 偏好。
- `DELETE /v1/projects/:id` — 软删（`deleted_at`）。
- `POST /v1/projects/:id/competitors` — 添加竞品（capacity 10 + 30s debounce）。
- `DELETE /v1/projects/:id/competitors/:brand_id` — 移除竞品。

`backend/app/api/v1/industries/router.py`（Onboarding 用）：

- `GET /v1/industries` — 全量行业（公共数据）。
- `GET /v1/industries/:id/top-brands?n=3` — 行业 Top N（按今日 GeoScore）。
- `GET /v1/brands?industryId=&q=&limit=` — 品牌检索。

数据来源：`projects` / `project_competitors`（新表） + `industries`、`brands`、
`geo_score_daily`（read-only mirror）。

### 前端

`frontend/src/contexts/ProjectContext.jsx` 改为 React Query 驱动：
`useProjects` / `useActiveProject` / `useCreateProject` / `useUpdateProject` /
`useDeleteProject` / `useAddCompetitor` / `useRemoveCompetitor`，保留原
optimistic + rollback + 30s debounce + 10 cap 契约。

`frontend/src/pages/OnboardingPage.jsx`：拉 `useIndustriesWithTopBrands`，
点选 → `useCreateProject({ industry_id })` → 跳 `/brand/overview`。
`RequireAuth`：登录后若 `projects.length === 0` 自动跳 `/onboarding`。

`frontend/src/pages/ProjectSettingsPage.jsx`：接 `PATCH/DELETE /v1/projects/:id`。

### 验收

- 新用户从 0 经 onboarding 落到 `/brand/overview`，刷新仍生效。
- 多 project 用户顶栏切换；URL `?projectId=` 持久化。
- 用户 A 调 `/v1/projects/<B 的 ID>` → 404（多租户单测覆盖）。

---

## Phase 2 — Brand Mode 读 API（≈ 2-3 周，9 子页）

按 `frontend/src/App.jsx` 中 IA v2.0 顺序，逐子页交付。每页 5 步：

1. 后端端点（DTO + service + router + 多租户测试）
2. 前端 hook（`src/hooks/useBrandX.ts` + React Query）
3. 页面切 mock → hook（同时挂 4 态：loading / empty / error / 401）
4. e2e smoke
5. OpenAPI YAML 同步（CI 校验）

| # | 路由 | 后端端点 | 数据来源 |
| - | --- | --- | --- |
| 1 | `/brand/overview` | `GET /v1/projects/:id/overview` | `geo_score_daily`、`brands`、`response_analyses` |
| 2 | `/brand/visibility` | `GET /v1/projects/:id/metrics?series=mention,sov,rank` | `geo_score_daily`、`brand_mentions` |
| 3 | `/brand/topics` | `GET /v1/projects/:id/topics`、`PATCH/DELETE …/:tid` | `topics`、`project_topic_pins`、`prompts` |
| 4 | `/brand/sentiment` | `GET /v1/projects/:id/sentiment[/keywords\|drivers]` | `response_analyses`、`sentiment_drivers` |
| 5 | `/brand/citations` | `GET /v1/projects/:id/citations[/domains\|pages]` | `citation_sources`、`response_analyses` |
| 6 | `/brand/products[/:pid]` | `GET /v1/projects/:id/products[/:pid]` | `products`、`product_score_daily`、`product_feature_mentions` |
| 7 | `/brand/competitors` | `GET /v1/projects/:id/competitors/metrics` | `project_competitors`、`geo_score_daily` |
| 8 | `/brand/diagnostics` | `GET /v1/projects/:id/diagnostics` | `response_analyses`、`citation_sources` + 规则引擎 |
| 9 | `/brand/reports` | 见 Phase 4 | `report_jobs` |

### 服务层约定

- 所有读端点支持统一 query：`from`、`to`、`engine`、`profileGroupId`。
- 返回结构：`{ items, meta: {total, from, to}, state: 'ok'|'empty'|'partial' }`。
- 多租户：`Depends(current_project(project_id))` 一道闸；非自己 → 404。
- 性能：热路径必须命中已有索引（`geo_score_daily(brand_id, stat_date)`、
  `response_analyses(brand_id, created_at)`）；用 `selectinload` 防 N+1。

### 前端约定

- 图表组件保持 dumb，从 props 拿数据。
- 时间窗口走全局 `useFilters` context。
- "立即采集" CTA 一律 `useCreateCrawlRequest()`（Phase 4 上线后启用）。

### 验收

- 9 个子页 `import 'data/mock'` 0 命中（ESLint 升 error）。
- 4 态可演示；多租户单测 + e2e 通过。
- p95 端点 < 200ms（PRD §7.2）；超出列入 backlog。

---

## Phase 3 — Industry Mode 读 API（≈ 1-1.5 周，4 子页）

| # | 路由 | 后端端点 | 数据来源 |
| - | --- | --- | --- |
| 1 | `/industry/overview` | `GET /v1/industries/:iid/overview` | `industry_benchmark_daily`、`brands` |
| 2 | `/industry/ranking` | `GET /v1/industries/:iid/ranking` | `geo_score_daily`、`brands` |
| 3 | `/industry/topics` | `GET /v1/industries/:iid/topics` | `topics`、`prompts` |
| 4 | `/industry/knowledge-graph` | `GET /v1/industries/:iid/kg` | `brands`、`brand_relations`*、`product_relations`*、`products` |

\* `brand_relations` / `product_relations` 由 admin 维护（在 Tracker schema 中），
   App 端只读。

### 前端

`frontend/src/pages/industry/{IndustryOverviewPage,IndustryRankingPage,
IndustryTopicsPage}.jsx` + `KnowledgeGraphPage.jsx` 切 hook。
KG 节点 > 1000 用流式 / 抽稀；分类筛选与 URL `?cat=` 同步。

### 验收

- KG 1000+ 节点 ≥ 30 fps；行业切换不强绑当前 Project（PRD §4.1.1b）。
- 排名页支持 offset 分页、跳页。

---

## Phase A — Analyzer 收尾（≈ 4 周，并行可压到 2.5 周，**新增**）

把 analyzer 从 88% 半成品做到生产可用。Adapter 不动。**所有任务交付时必须带单测**
（当前 0%，目标 ≥ 70%）。

### A1. 修旧模块（≈ 1 周）

| 模块 | 任务 | 验收 |
| --- | --- | --- |
| `aggregator.py:163` | 实现 `citation_rate = citation_count / total_queries`（当前硬编码 0.0） | `geo_score_daily.citation_rate` 写入有值；30 天回填后 KPI 卡显示真实数字 |
| `aggregator.py` | 新增 `category_rank` / `industry_rank` 由 `dimension_category`（response_analyses）回填 | Industry / category ranking 端点真实数据 |
| `llm_analyzer.py` | 区分 `LLMTimeoutError` / `LLMRateLimitError` / `LLMParseError` 三类异常；3 次重试指数退避；ARK_API_KEY 走 `core/config.py` | 单测覆盖 3 类异常 + retry 序列；不再静默吞错 |
| `sentiment_analyzer.py` | 关键词 fallback 升级为 SnowNLP 中文 + Vader 英文小模型；批 8 → 32 + 缓存（Redis 24h） | 准确率金标 200 case ≥ 80%；耗时下降 ≥ 50% |
| `cli.py` | 新增 `weekly` 命令、`--from / --to` 日期切片、`--export-csv` / `--export-pdf` | 通过子命令一键产出 30 天 CSV |
| `cli.py` | 新增 `diagnostics` 命令调 `diagnostics_rules.py`（A9） | CLI 输出 JSON 诊断结果 |

### A2. 单测基础设施（≈ 1 周，与 A1 并行）

- 新建目录 `geo_tracker/tests/test_analyzer/`，每模块一个文件：
  `test_brand_detector.py`、`test_citation_mapper.py`、`test_sentiment.py`、
  `test_geo_scorer.py`、`test_aggregator.py`、`test_llm_analyzer.py`、`test_cli.py`。
- pytest fixtures：mock `LLMResponse`、`Brand`、`Citation` 工厂；用
  `pytest-postgresql` 起独立 DB schema 跑集成。
- 金标数据集：`geo_tracker/tests/fixtures/golden/`：
  - 100 条 `llm_response → expected_brand_mentions` 对。
  - 200 条 `text → expected_sentiment` 对。
  - 80 条 `url → expected (domain, source_type, page_type, attribution_method)` 对。
- CI：`pytest geo_tracker/tests/ -m analyzer --cov=geo_tracker.analyzer --cov-fail-under=70`。

### A3. 新模块：`attribution_classifier.py`（≈ 0.3 周）

为 G1 BLOCKER 服务。

- 新文件 `geo_tracker/analyzer/attribution_classifier.py`（≈ 100 LOC）：
  - 输入：`CitationSource` + 品牌名 + `brand_official_domains` 表查询。
  - 输出：`attribution_method ∈ {official_site, official_mention, co_occurrence, text_match, unattributed}`。
  - 规则：
    1. URL host 命中品牌官方域名 → `official_site`。
    2. URL 在第三方但 title 含品牌全称 → `official_mention`。
    3. URL title / context 同时命中目标品牌 + 至少一个竞品 → `co_occurrence`。
    4. 仅文本匹配品牌名，无域名归属 → `text_match`。
    5. 其他 → `unattributed`。
- DDL（Phase 0 同时加）：
  - `ALTER TABLE citation_sources ADD COLUMN attribution_method VARCHAR(32);`
  - 新表 `brand_official_domains(brand_id INT FK, domain VARCHAR(256), is_primary BOOL,
    PRIMARY KEY (brand_id, domain));`（admin 维护）。
- 集成：`citation_mapper.py` 跑完之后调 `attribution_classifier`，写回 `citation_sources`。
- 回填：写 `geo_tracker/scripts/backfill_attribution.py` 跑 30 天历史。
- 单测：金标 80 case 5 类各 ≥ 95% 准确率。

### A4. 新模块：`domain_authority_lookup.py` + 新表（≈ 0.7 周）

为 G2 BLOCKER 服务。

- 新表（Alembic 新版本）：
  ```
  domain_authorities (
    domain VARCHAR(256) PRIMARY KEY,
    tier SMALLINT NOT NULL,             -- 0=unknown 1=official 2=tier2 3=kol 4=ugc
    confidence FLOAT DEFAULT 1.0,
    site_type VARCHAR(32),              -- review / ranking / kol / wiki / product / news / other
    notes TEXT,
    reviewed_by INT,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ
  );
  ```
- 种子：`backend/seeds/domain_authorities_seed.sql` ≈ 200 条头部域名
  （小红书 / B 站 / 知乎 / 36kr / 虎嗅 / 雷锋网 / Wired / TheVerge / Wikipedia /
   头部品牌官网）。
- 新文件 `geo_tracker/analyzer/domain_authority_lookup.py`（≈ 150 LOC）：
  - `lookup(domain) → (tier, site_type, confidence)`，DB 命中 + Redis 缓存 24h。
  - 未命中 → 标 tier=0，写入 `domain_authorities(tier=0, confidence=0.5)` 供 admin
    审核（管理员可批量 review）。
- 集成：`citation_mapper.py` 跑完调 `lookup`，把 `tier` 缓存到 `citation_sources.authority_tier`。
- DDL：`ALTER TABLE citation_sources ADD COLUMN authority_tier SMALLINT, ADD COLUMN site_type VARCHAR(32);`。
- admin 端点：`GET/POST/PATCH/DELETE /api/admin/domain-authorities` + bulk import。
- 单测：lookup 命中 / 未命中 / 缓存 / fallback；CRUD 集成测试。

### A5. 新模块：`page_type_classifier.py`（≈ 0.4 周）

为 G3 BLOCKER 服务。

- 新文件 `geo_tracker/analyzer/page_type_classifier.py`（≈ 120 LOC）：
  - 输入：`(url, title, source_type, html_head?)`。
  - 输出：`page_type ∈ {review, ranking, kol_blog, wiki, news_article, product_page,
    forum, comparison, how_to, case_study, other}`。
  - 规则：URL pattern + title 关键词 + `domain_authorities.site_type` 三层判定。
- DDL：`ALTER TABLE citation_sources ADD COLUMN page_type VARCHAR(32);`。
- 集成：`citation_mapper.py` 内联调用。
- 单测：金标 50 case ≥ 90% 准确率。

### A6. 新模块：`brand_group_aggregator.py` + 2 张新表（≈ 0.5 周）

为 G4 BLOCKER 服务。

- 新表：
  ```
  brand_groups (id SERIAL PK, name VARCHAR(256) NOT NULL, parent_company VARCHAR(256));
  brand_group_members (group_id INT FK, brand_id INT FK, role VARCHAR(32),
                       PRIMARY KEY (group_id, brand_id));
  brand_group_shared_domains (group_id INT, domain VARCHAR(256), brand_count INT,
                              total_mentions INT, last_seen_at TIMESTAMPTZ,
                              PRIMARY KEY (group_id, domain));
  ```
- 种子：手工初始化 10-20 个高频集团（雅诗兰黛 / LVMH / 资生堂 / 欧莱雅 …）。
- admin CRUD：`/api/admin/brand-groups[/members]`。
- 新文件 `geo_tracker/analyzer/brand_group_aggregator.py`（≈ 80 LOC）：
  - 周聚合 Celery task：每 group 跑 `SELECT domain, COUNT(DISTINCT brand_id), SUM(mentions)
    FROM citation_sources JOIN brand_group_members USING (brand_id) GROUP BY group_id,
    domain HAVING brand_count >= 2`，落 `brand_group_shared_domains`。
- 单测：fixture 多 group + cross-brand share 验证。

### A7. 新模块：`competitor_aggregator.py` + 新表（≈ 0.7 周）

新发现：`COMPETITOR_MENTION_MATRIX` / `COMPETITOR_SENTIMENT_BUBBLE` 需要
**cross-brand 维度**，现 `geo_score_daily` 是按单品牌独立聚合，没有
"我品牌 vs 竞品 X 在同一场 query 中的 co-mention" 维度。

- 新表：
  ```
  competitor_mention_daily (
    brand_id INT, competitor_id INT, date DATE, target_llm VARCHAR(64),
    co_mention_count INT, my_mention_count INT, comp_mention_count INT,
    avg_sentiment_diff FLOAT, sov_diff FLOAT,
    PRIMARY KEY (brand_id, competitor_id, date, target_llm)
  );
  ```
- 新文件 `geo_tracker/analyzer/competitor_aggregator.py`（≈ 150 LOC）：
  - 日聚合：对每对 (brand, competitor)，扫 `brand_mentions` 同 `response_id`
    出现的对，统计共现 / 排名差 / 情感差。
- 集成：在 `aggregator.py` daily run 末尾调用。
- 单测：fixture 3 brand × 3 competitor × 多 response 共现场景。

### A8. 新模块：`weekly_aggregator.py` + 新表（≈ 0.8 周）

`TIER2_COVERAGE_MATRIX` / `KOL_SCORECARDS` 需周维度。

- 新表：
  ```
  geo_score_weekly (
    brand_id INT, week_start DATE, target_llm VARCHAR(64),
    avg_geo_score FLOAT, avg_authority_tier FLOAT,
    top_authority_domains_json JSONB,    -- [{domain, tier, count}, ...]
    tier1_citation_count INT, tier2_citation_count INT, tier3_citation_count INT,
    PRIMARY KEY (brand_id, week_start, target_llm)
  );
  citation_weekly_by_domain (
    brand_id INT, domain VARCHAR(256), week_start DATE,
    citation_count INT, avg_position_rank FLOAT,
    PRIMARY KEY (brand_id, domain, week_start)
  );
  ```
- 新文件 `geo_tracker/analyzer/weekly_aggregator.py`（≈ 200 LOC）：
  ISO 周聚合，按 brand × domain × tier 卷展。
- Celery：每周一凌晨 cron `analyzer.weekly_aggregation`。
- 单测：fixture 2 周数据 + 边界（月末跨周）。

### A9. Diagnostics rules 入口骨架（详见独立 Phase D）

Phase A.9 仅交付 `backend/app/diagnostics/rules.py` 的最小框架（rule loader、
evaluator 入口、rule context dict 构造），让 Phase 2.3 的端点能挂上空跑。
完整的 25+ 条规则、causal chain、industry benchmark、reader hint、anchor questions
的实现在 **Phase D — Diagnostics 完整后端**。

### A10. Industry topic 分类法（≈ 0.5 周）

- `response_analyses.dimension_category` 字段已有但未消费 → 新建 `industry_topics` 视图：
  按 `industry × category × topic` 组合排序 hot topics，喂 `/industry/:iid/topics`。
- 在 `aggregator.py` daily run 内 UPSERT `industry_topic_daily` 表。

### A11. 30 天历史回填（≈ 0.5 周）

- 写一次性脚本 `geo_tracker/scripts/backfill_full.py`：
  对历史 `citation_sources` / `brand_mentions` / `response_analyses` 跑：
  - attribution_classifier
  - domain_authority_lookup
  - page_type_classifier
  - competitor_aggregator
  - brand_group_aggregator
  - weekly_aggregator
- 增量保护：每张表加 `analyzer_version` 列，回填只跑旧版本行。
- 跑前 dump DB 备份。

### Phase A 验收

- ✅ 8 模块（5 改 + 6 新中的 5 个）完成；A11 历史回填跑过；
  A6 / A8 周维度 cron 上线。
- ✅ Analyzer 单测覆盖 ≥ 70%（pytest --cov-fail-under=70）。
- ✅ 4 BLOCKER 数据可被 `/brand/citations` `/brand/diagnostics`
  `/brand/overview`（同集团卡）端点消费返回真实非空数据。
- ✅ `geo_score_daily.citation_rate` 不再是 0.0；`competitor_mention_daily`
  / `geo_score_weekly` / `brand_group_shared_domains` 持续产出。
- ✅ `diagnostics_rules.py` 至少 12 条规则可触发 + 单测全过。
- ✅ CLI `weekly` / `--export-csv` / `diagnostics` 子命令可用。
- ✅ 准确率门槛：归因 5 类金标 ≥ 95%、page_type 金标 ≥ 90%、
  sentiment 升级 ≥ 80%。

### Phase A 时间表（4 周日历，2 工程师并行）

| 周 | 工程师 1（旧模块） | 工程师 2（新模块） |
| --- | --- | --- |
| AW1 | A1 修旧 + A2 测试基建 | A3 attribution_classifier + DDL |
| AW2 | A2 收尾 + A10 industry_topic | A4 domain_authority + admin 路由 |
| AW3 | A9 diagnostics_rules（前 6 条） | A5 page_type + A6 brand_group |
| AW4 | A9 收尾（后 6 条 + 单测） | A7 competitor + A8 weekly + A11 回填 |

可压缩到 2.5 周如有 3 工程师；不可压缩点：A2 单测基建 + A11 回填验证。

---

## Phase K — Knowledge Graph 构建（≈ 3.5 周，并行可压到 2 周，**新增**）

KG（Industry → Category → Brand → Product + 关系边）是 PRD §4.0.1a 规定的核心数据
资产，但**当前完全未实现**：5 张 `kg_*` 表都没建、admin 没有 CRUD 端点、analyzer
没有关系边推断、`KnowledgeGraphPage.jsx` 自带硬编码 `RAW_NODES` + `RAW_LINKS`。

Phase A 的 A6 brand_group_aggregator 只覆盖 KG 的"同集团 + 共享域名"一小块，
Phase K 补齐 KG 主体。Phase K 与 Phase A 同时开工，共享 pipeline 工程师。

### K1. KG schema 落库（≈ 0.3 周）

新表（合入 Phase R.2 的 alembic 单一 head）：

```sql
kg_categories (
  id BIGSERIAL PK,
  industry_id INT FK→industries(id),
  parent_id BIGINT FK→kg_categories(id) NULL,
  name_zh VARCHAR(128) NOT NULL,
  name_en VARCHAR(128),
  level SMALLINT,
  slug VARCHAR(64),
  UNIQUE (industry_id, parent_id, slug)
);

kg_brands (
  id BIGSERIAL PK,
  brand_id INT FK→brands(id) UNIQUE,           -- 1:1 映射现有 brands；保留 brands 作业务表
  industry_id INT FK→industries(id),
  primary_name VARCHAR(256) NOT NULL,
  name_zh VARCHAR(256),
  name_en VARCHAR(256),
  aliases JSONB,
  official_domains JSONB,                       -- 与 brand_official_domains 二选一，建议合并
  group_id INT FK→brand_groups(id) NULL,        -- 复用 Phase A.6 表
  status VARCHAR(16) DEFAULT 'approved',        -- pending|approved|rejected
  created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ
);

kg_products (
  id BIGSERIAL PK,
  product_id INT FK→products(id) UNIQUE,        -- 1:1 映射现有 products
  brand_id INT FK→brands(id),
  category_id BIGINT FK→kg_categories(id),
  primary_name VARCHAR(256) NOT NULL,
  name_zh VARCHAR(256), name_en VARCHAR(256),
  aliases JSONB,
  status VARCHAR(16) DEFAULT 'approved',
  created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ
);

kg_brand_relations (
  id UUID PK,
  brand_a_id INT FK→brands(id),
  brand_b_id INT FK→brands(id),
  type VARCHAR(32) NOT NULL,                    -- COMPETES_WITH | SAME_GROUP
  confidence FLOAT NOT NULL,
  source VARCHAR(32) NOT NULL,                  -- analyzer | admin | import
  evidence JSONB,                               -- {response_ids: [...], snippets: [...]}
  reviewed_by INT, reviewed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (brand_a_id, brand_b_id, type)
);

kg_product_relations (                         -- 结构同上
  id UUID PK,
  product_a_id INT FK→products(id),
  product_b_id INT FK→products(id),
  type VARCHAR(32) NOT NULL,                    -- COMPETES_WITH | SUBSTITUTES | UPGRADES_TO | BUDGET_ALT_OF | PAIRS_WITH
  confidence FLOAT, source VARCHAR(32), evidence JSONB,
  reviewed_by INT, reviewed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (product_a_id, product_b_id, type)
);

kg_relation_candidates (                       -- analyzer 自动推断的候选边，待 admin 审核
  id UUID PK,
  entity_kind VARCHAR(8),                       -- 'brand' | 'product'
  a_id INT, b_id INT, type VARCHAR(32),
  confidence FLOAT, evidence JSONB,
  status VARCHAR(16) DEFAULT 'pending',         -- pending | approved | rejected | merged
  created_at TIMESTAMPTZ
);
```

设计要点：
- `kg_brands` / `kg_products` 通过 `brand_id` / `product_id` 1:1 映射现有
  `brands` / `products`，**不重复存业务字段**；KG 表仅承担"图谱属性"（aliases、
  关系、status）。这避免与 admin 现有 brand/product CRUD 冲突。
- `brand_official_domains`（Phase A.3 引入）与 `kg_brands.official_domains`
  二选一 — 推荐合并到 `kg_brands.official_domains JSONB`。

### K2. 数据种子 ETL（≈ 0.3 周）

新脚本 `backend/scripts/seed_kg.py`：

- 把现有 `brands` 全量映射为 `kg_brands(brand_id, status='approved')`。
- 把现有 `products` 全量映射为 `kg_products(product_id, brand_id, status='approved')`。
- 从 `topics` 表的 `tags` JSONB（已有 PR #104 加的字段）+
  `response_analyses.dimension_category` 抽取去重后落 `kg_categories`，
  按 `industry_id` 分组建二级树。
- 把现有 `competitors` 表（每行 = 用户标记的竞品）转换为
  `kg_brand_relations(type=COMPETES_WITH, source=admin, confidence=1.0)`。

跑前 dump DB；跑后人工抽检 100 行。

### K3. Admin KG CRUD（≈ 1 周）

在 Phase R.4 已迁好的 admin FastAPI 下加：

```
backend/app/api/admin/kg/
  categories/router.py     # /api/admin/kg/categories  CRUD + tree view
  brands/router.py         # /api/admin/kg/brands       CRUD + bulk import + alias merge
  products/router.py       # /api/admin/kg/products     CRUD + bulk import
  brand_relations/router.py# /api/admin/kg/brand-relations CRUD + 软删
  product_relations/router.py
  candidates/router.py     # /api/admin/kg/candidates 列表 + approve/reject/bulk-review
                           # 喂从 K5 推断的候选边
  diff/router.py           # /api/admin/kg/diff?since= 24h 变更摘要（ADMIN_PRD §C8）
  quality/router.py        # /api/admin/kg/quality 总览（孤立节点 / 弱关系 / 别名冲突，§C9）
```

复用 admin 鉴权 + audit log（admin 模块已有）。
模板：admin.html 已有 KG 相关 UI mockup（搜索 `kg_brand` / `KG`），
迁移到 backend 模板时改成读真端点。

### K4. Category 树自动聚合（≈ 0.3 周）

在 `geo_tracker/analyzer/aggregator.py` daily run 末尾加：
- 扫 `response_analyses.dimension_category` 新增值 → UPSERT 到
  `kg_categories(industry_id, name_zh, level, status='unverified')`，
  status=unverified 的需 admin 审核后转 approved。

### K5. Relation Extractor（≈ 1 周，最重）

新模块 `geo_tracker/analyzer/relation_extractor.py`（≈ 250 LOC）：

- 输入：一批 `llm_responses.response_text`。
- 步骤：
  1. 文本模式提取（regex + spaCy NER）：
     - "A 和 B 哪个好" / "A vs B" / "比较 A 和 B" → 候选 `COMPETES_WITH(a, b)`
     - "A 是 B 的平替" / "A 比 B 便宜" → 候选 `BUDGET_ALT_OF(a, b)`
     - "A 升级到 B" / "B 是 A 的进阶版" → 候选 `UPGRADES_TO(a, b)`
     - "A 隶属于 B 集团" / "A 是 B 旗下" → 候选 `SAME_GROUP(a, b)`
     - "A + B 一起用" / "A 搭配 B" → 候选 `PAIRS_WITH(a, b)`
  2. 实体识别：用 `brand_detector.py`（已有）解析 A、B 是哪个 brand_id 或 product_id。
  3. 置信度：基于命中模式 + 出现频次（同对在 ≥ 3 个 response 出现 → 0.8；
     ≥ 10 个 → 0.95）。
  4. 写到 `kg_relation_candidates(status='pending')` + `evidence` 含 response_id 列表。
- 集成：在 `aggregator.py` daily run 末尾或 `llm_analyzer.py` 跑完后调用。
- admin 通过 K3 candidates 端点审核 → 合并到 `kg_brand_relations` /
  `kg_product_relations`。
- 单测：金标 30 条 (text → expected_relation) ≥ 90% 准确率。

### K6. App-end KG 端点（≈ 0.3 周）

`backend/app/api/v1/industries/router.py` 加：

```python
GET /v1/industries/:iid/kg?focus=&depth=2
```

返回结构（喂 `@antv/g6`）：

```json
{
  "nodes": [
    {"id": "ind-{iid}", "label": "...", "type": "industry"},
    {"id": "cat-{cid}", "label": "...", "type": "category", "level": 1},
    {"id": "br-{bid}",  "label": "...", "type": "brand", "group_id": ..., "panoScore": 82},
    {"id": "pr-{pid}",  "label": "...", "type": "product", "brand_id": ...}
  ],
  "edges": [
    {"source": "...", "target": "...", "type": "BELONGS_TO|IN_CATEGORY|HAS_PRODUCT|COMPETES_WITH|SAME_GROUP|...", "confidence": 0.92}
  ],
  "categories_tree": [...],            // 与 nodes 重复，便于左侧 panel 渲染
  "meta": {"node_count": ..., "edge_count": ..., "industry": {...}}
}
```

服务层 LEFT JOIN 全 5 张 `kg_*` + `geo_score_daily`（取 panoScore 给品牌节点）。
节点 > 1000 时按 `focus` 节点 BFS 限制 `depth`。

### K7. FE KG page 切真实数据（≈ 0.3 周）

`frontend/src/pages/KnowledgeGraphPage.jsx`（先在 Phase R 转 `.tsx`）：
- 删除内部 `RAW_NODES` (51 行) + `RAW_LINKS` (45 行) +
  `GRAPH_BRAND_TO_GLOBAL_ID` 映射。
- 改用 `useIndustryKG(industryId, { focus, depth })` hook。
- `@antv/g6` 渲染逻辑保持不动（只是数据源换）。
- 节点点击跳 `/brand/overview?brandId=...`（用 K6 返回的真实 brand_id，
  不再需要 `GRAPH_BRAND_TO_GLOBAL_ID` 映射表）。
- 4 态：loading / empty (industry 还没采集) / error / success。
- mock.js 的 `BRAND_RELATIONS` `PRODUCT_RELATIONS` `CATEGORIES` `getCompetitors`
  在 Phase 5 mock 退役时删除。

### Phase K 验收

- ✅ 5 张 `kg_*` + `kg_relation_candidates` 表存在；K2 种子跑过，
  brand 全量进 `kg_brands`，category 树有 ≥ 30 类。
- ✅ admin K3 全 7 个子模块 CRUD 可用；KG Diff / Quality 页面（按
  ADMIN_PRD §C8/C9）能看 24h 变更与孤立节点。
- ✅ K5 Relation Extractor 跑过 30 天历史，`kg_relation_candidates`
  ≥ 100 条候选；admin 审核通过率 ≥ 70%。
- ✅ `GET /v1/industries/:iid/kg` 返回真实 nodes/edges；KG 1000 节点 ≥ 30 fps。
- ✅ FE KG page 不再 import `RAW_NODES` / `RAW_LINKS` / `mock.js`；
  4 态可演示。
- ✅ 单测：K5 关系抽取金标 ≥ 90%；K6 端点 6 case 集成；K7 RTL 4 态。

### Phase K 时间表（与 Phase A 共用 pipeline 工程师，3-4 周日历）

| 周 | 工程师 1（Phase A） | 工程师 2（Phase K） |
| --- | --- | --- |
| AW1 | A1 + A2 测试基建 | K1 schema + K2 种子 |
| AW2 | A3 attribution + DDL | K3 admin CRUD（categories / brands / products） |
| AW3 | A4 domain_authority + admin | K3 收尾（relations / candidates / diff / quality）+ K4 |
| AW4 | A5 + A6 + A7 + A8 | K5 relation_extractor + 30 天回填 |
| AW5 (overlap with W7) | — | K6 + K7 联调 |

K6 + K7 必须在 Phase 3（W8）之前完成，给 `/industry/knowledge-graph` 切真实数据用。

可压缩到 2 周：K3 admin CRUD 拆 7 个子 router 双开，K5 与 K3 并行。

---

## Phase D — Diagnostics 完整后端（≈ 2 周，**新增 / 从 Phase A.9 扩展**）

PRD §4.7 + §4.7.0-a + §4.8.6 + DiagnosticsPage.jsx 实际数据需求**远超** A.9 的 12
规则雏形。`DIAGNOSTICS` mock 每条诊断包含 4 大块（observation / explanation /
direction / CTA），3 类（brand/product/industry），4 严重度（P0-P3），
3 reader hint（operator/manager/branding），13+ category。完整后端必须独立成 Phase。

### D1. 数据模型（≈ 0.3 周）

新表（合入 Phase R.2 alembic）：

```sql
diagnostics (
  id UUID PK,
  project_id UUID FK→projects(id) ON DELETE CASCADE,
  brand_id INT FK→brands(id) NULL,
  product_id INT FK→products(id) NULL,
  industry_id INT FK→industries(id) NULL,
  category VARCHAR(64) NOT NULL,         -- visibility_decline | sentiment_drop | citation_attribution_mismatch
                                          -- competitor_overtake | topic_loss | narrative_drift |
                                          -- persona_keyword_change | negative_keyword_growth | content_gap |
                                          -- pano_score_drop | citation_authority_low | wiki_missing | ...
  severity VARCHAR(4) NOT NULL,          -- P0 | P1 | P2 | P3
  type VARCHAR(16) NOT NULL,             -- brand | product | industry
  title VARCHAR(512) NOT NULL,
  description TEXT,
  engine VARCHAR(32),                    -- 触发引擎，跨引擎为 NULL
  focus_area VARCHAR(256),
  direction TEXT,                         -- 方向性建议（不是 playbook）
  reader_hints VARCHAR[] NOT NULL,       -- ['operator','manager','branding']
  decision_prompt TEXT,                  -- "是否在下 4 周启动 X 项目?"
  evidence JSONB NOT NULL,               -- {metric, currentValue, previousValue, changePercent, timeRange,
                                          --  affectedQueries[], affectedEngines[], 子结构按 category 不同}
  causal_chain JSONB,                    -- {triggerMetrics[], hypothesizedMechanism, supportingEvidence[],
                                          --  confidenceLevel, alternativeHypotheses[]}
  industry_benchmark JSONB,              -- {metric, myValue, industryMedian, industryTop10Avg, topCompetitor}
  time_series JSONB,                     -- 30 天指标点序列，给 Layer 2 趋势图
  anchor_questions JSONB,                -- {operator: [...], manager: [...], branding: [...]}
  if_untreated TEXT,                     -- "若不处理，预期 X 周后..."
  status VARCHAR(16) DEFAULT 'open',     -- open | acknowledged | ignored | resolved
  detected_at TIMESTAMPTZ DEFAULT now(),
  acknowledged_at TIMESTAMPTZ, acknowledged_by INT,
  resolved_at TIMESTAMPTZ, resolved_by INT,
  rule_id VARCHAR(64) NOT NULL,          -- 触发的规则 id（如 'visibility_decline_v1'）
  rule_version VARCHAR(16),
  alert_id UUID NULL                      -- 联动 alerts.id（Phase N），P0/P1 自动创建
);
CREATE INDEX ON diagnostics (project_id, severity, status, detected_at DESC);
CREATE INDEX ON diagnostics (project_id, brand_id, category);
```

### D2. Evaluator 引擎（≈ 0.3 周）

新模块 `backend/app/diagnostics/evaluator.py`（≈ 200 LOC）：

- 输入：`project_id` + 时间窗口（默认昨天）。
- 步骤：
  1. 拉 project context：brand_ids、industry_id、competitor_ids、preferred_engines、
     30 天 `geo_score_daily` / `response_analyses` / `citation_sources` / `sentiment_drivers`。
  2. 装载注册的所有规则（D3）。
  3. 对每条规则 `rule.evaluate(context)` → 返回 `[Diagnostic 候选]` 或 `[]`。
  4. **去重 / 升级**：同 `(project_id, brand_id, category, rule_id)` 已 open 状态 →
     更新 `evidence` 不重复创建；severity 升级（P2 → P1）写一行变更记录。
  5. UPSERT `diagnostics` 表。
  6. severity ≥ P1 → 触发 alert（Phase N）。
- Celery 任务 `diagnostics.daily_evaluate(project_id)` — 每日凌晨 cron，所有 active
  project 跑一遍。
- 单 project 手动触发：`POST /v1/projects/:id/diagnostics/refresh`。

### D3. 规则注册表（≈ 1 周，最重）

新目录 `backend/app/diagnostics/rules/`，每条规则独立文件：

```
backend/app/diagnostics/rules/
  __init__.py                      # registry: rule_id → class
  base.py                          # BaseRule 抽象（evaluate/category/severity_for/build_evidence）
  visibility_decline.py            # 提及率 / SoV / rank 30d 下滑触发
  sentiment_drop.py                # 平均情感分 / negative_rate 下滑
  citation_attribution_mismatch.py # official_domain 占比 < 阈值（依赖 A.3）
  competitor_overtake.py           # 竞品 SoV/rank 反超
  topic_loss.py                    # 单 topic mention_rate 显著下滑
  narrative_drift.py               # branding_narrative LLM 比对（branding reader 主用）
  persona_keyword_change.py        # 用户画像关键词频次变化
  negative_keyword_growth.py       # 负面关键词增长
  content_gap.py                   # 高 gap_ratio topic（依赖 A.5 page_type）
  pano_score_drop.py               # GEO 总分 30d 下滑
  citation_authority_low.py        # tier2 引用占比 < 阈值（依赖 A.4）
  wiki_missing.py                  # 知识百科类 page_type 缺失
  product_feature_negative.py      # 产品特性负面占比 > 阈值
  product_remission.py             # 产品被竞品反超
  industry_lag_top10.py            # 行业 Top10 距离差距过大
  same_group_share_low.py          # 同集团共享域少于阈值（依赖 A.6）
  monitoring_outage.py             # 24h 没新数据流入
  llm_engine_anomaly.py            # 单引擎数据异常归零
  ... # 共 25+ 条
```

每条规则结构：

```python
class VisibilityDecline(BaseRule):
    rule_id = 'visibility_decline_v1'
    category = 'visibility_decline'
    triggers_on = ['mention_rate', 'sov']

    def evaluate(self, context) -> list[DiagnosticPayload]:
        # 1. 计算指标
        # 2. 阈值判定（severity 由 change_percent 大小决定）
        # 3. 构造 evidence + causal_chain + industry_benchmark + reader_hints
        # 4. 返回 0+ 个 DiagnosticPayload
```

### D4. Causal Chain LLM 辅助（≈ 0.3 周）

`backend/app/diagnostics/causal_llm.py`：

- 输入：`{rule_id, evidence, recent_responses_sample}`。
- 用 LLM（豆包 / DeepSeek，复用 `geo_tracker.analyzer.llm_analyzer`）生成
  `hypothesizedMechanism` + `alternativeHypotheses`（每条 1-2 句）。
- 缓存 24h（key=`(project_id, rule_id, brand_id, day)`），同一天不重复调。
- LLM 失败 → 用规则自带的 fallback 文案。
- 成本控制：每 project 每天 ≤ 50 次 LLM 调用。

### D5. Anchor Questions（≈ 0.2 周）

`backend/app/diagnostics/anchor_questions.py`：
- 静态映射：`category × reader_hint → [question_template]` i18n key。
- 例 (`visibility_decline` × `manager`)：`[
  '{brand} 在 {topic} 主题的 SoV 下滑 {pct}%, 是否需要重新分配 PR 预算?',
  '竞品 {top_competitor} 在同主题 SoV {comp_pct}%, 我们投放预算是否需要追赶?',
]`
- 服务层把当前诊断的具体数字 fill in。

### D6. Industry Benchmark 比对（≈ 0.2 周）

`backend/app/diagnostics/benchmark.py`：
- 按规则 `triggers_on` 指标，从 `industry_benchmark_daily` 读 my brand vs 行业
  median / top10Avg；TOP 1 竞品从 `geo_score_daily` 拉。
- 输出 `industryBenchmark` JSONB 字段。

### D7. 端点（≈ 0.2 周）

`backend/app/api/v1/diagnostics/router.py`：

- `GET /v1/projects/:id/diagnostics?severity=&category=&type=&status=&from=&to=&cursor=`
  — 列表（默认 status='open' + severity DESC + detected_at DESC）。
- `GET /v1/projects/:id/diagnostics/:diag_id` — 详情（含 causal / benchmark / time_series / anchor）。
- `POST /v1/projects/:id/diagnostics/refresh` — 手动触发 evaluator。
- `PATCH /v1/projects/:id/diagnostics/:diag_id` — 标记 acknowledged / ignored /
  resolved；记 `acknowledged_by` / `resolved_by`。

服务层把 D1 表的 row 拼成 `DiagnosticCard.jsx` 期望的形状（Layer 1/2/3 都齐）。

### D8. Alert 联动（与 Phase N 接口）

severity ≥ P1 的 diagnostic 创建后自动调 `alerts_service.create_from_diagnostic(diag)`，
写 `alerts(source='diagnostic', ref_id=diag.id, severity, ...)`。
diagnostic 状态变 resolved → alert 自动 resolved。

### Phase D 验收

- ✅ `diagnostics` 表 + `evaluator` Celery 跑通；25+ 条规则注册。
- ✅ `/v1/projects/:id/diagnostics` 端点返回与 `DIAGNOSTICS` mock 完全同构的数据。
- ✅ `DiagnosticCard.jsx` 4 layer + reader badge + anchor questions 全部 rendering。
- ✅ Causal LLM 缓存 24h，每 project 每天 ≤ 50 次调用。
- ✅ 单测：每条规则 happy + 不触发 + 边界（25 × 3 = 75 case）；evaluator 去重 / 升级
  / 降级；causal LLM mock；anchor question fill；benchmark 计算。
- ✅ severity ≥ P1 → 自动建 alert（联动 Phase N 测试）。

---

## Phase RP — Reports 完整后端（≈ 2.5 周，**新增 / 从 Phase 4 拆分扩展**）

PRD §4.7.1 / §4.7.2 + ReportsPage.jsx 的 `SECTION_MATRIX` 揭示：报告系统是
**4 reportType × 10 section × 3 variant × 3 reader perspective × 3 insight stack
layer × 多语言 narrative**，不是 "3 模板套" 能搞定的。

### RP1. 数据模型（≈ 0.3 周）

扩 `report_jobs` 表 + 新两表：

```sql
ALTER TABLE report_jobs ADD COLUMN report_type VARCHAR(32),  -- weekly | monthly | on_demand | lead_diagnostic
                       ADD COLUMN section_config JSONB,       -- 每 section 的 variant / reader / layers 覆盖
                       ADD COLUMN locale VARCHAR(8) DEFAULT 'zh-CN',
                       ADD COLUMN narrative_data JSONB,       -- 生成时缓存的 narrative 文本
                       ADD COLUMN markdown_url TEXT,
                       ADD COLUMN json_url TEXT;

report_schedules (
  id UUID PK,
  project_id UUID FK→projects(id) ON DELETE CASCADE,
  report_type VARCHAR(32),
  cron VARCHAR(64),                       -- '0 8 * * 1' weekly Mon 8AM
  recipients TEXT[],                      -- emails
  enabled BOOLEAN DEFAULT TRUE,
  next_run_at TIMESTAMPTZ,
  last_run_at TIMESTAMPTZ, last_run_id UUID FK→report_jobs(id),
  locale VARCHAR(8) DEFAULT 'zh-CN',
  created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ
);

report_share_tokens (
  token VARCHAR(64) PRIMARY KEY,
  report_id UUID FK→report_jobs(id) ON DELETE CASCADE,
  expires_at TIMESTAMPTZ NOT NULL,
  view_count INT DEFAULT 0,
  created_by INT FK→users(id),
  created_at TIMESTAMPTZ DEFAULT now()
);
```

### RP2. Section 渲染框架（≈ 0.5 周）

`backend/app/reports/sections/`，每 section 一文件：

```
backend/app/reports/sections/
  base.py                          # BaseSection (variant: full|simple|p01_only|optional)
  executive_summary.py
  pano_score.py
  industry_landscape.py
  brand_performance.py
  product_competitiveness.py
  competitor_comparison.py
  diagnostic_summary.py            # 拉 Phase D 的 diagnostics
  anchor_actions.py                # 拉 D7 的 anchor_questions 聚合
  branding_narrative.py            # branding reader 专属
  cta.py                           # 转化 CTA → CommercialLead
```

每 section 接口：

```python
class BaseSection:
    section_type: str              # 'executive_summary'
    def render(self, ctx: ReportContext, variant: str, reader: str, layers: list[int]) -> SectionData:
        # 返回结构化 dict + chart spec + table rows
```

`ReportContext`：`project, scope (date range), brand_ids, locale, prior_period_data`。

### RP3. SECTION_MATRIX 服务端实现（≈ 0.3 周）

把 ReportsPage.jsx 中 `SECTION_MATRIX` 的逻辑搬到 backend：

```python
SECTION_MATRIX = {
  'weekly':         {...},       # 与 FE 一致
  'monthly':        {...},
  'on_demand':      {...},
  'lead_diagnostic': {'__use_lead_view': True},
}
SECTION_ORDER = [...]            # 10 sections fixed order
```

`backend/app/reports/builder.py`：根据 `report_type` 查 matrix → 跑各 section.render()
→ 拼 ReportPayload。lead_diagnostic 走独立 4 layer view（不用 matrix）。

### RP4. Narrative 多语言生成（≈ 0.5 周）

`backend/app/reports/narratives.py`：

- 模板：`messages.{zh,en}.json` 加 `reports.narratives.*` namespace（与 FE 共用 i18n key）。
- LLM 填空：把 placeholder 留给 LLM（豆包），输入 section data + 上下文 → 生成
  叙事段落（每段 80-200 字）。
- 缓存：`(report_type, section, period_id, brand_id, locale)` → narrative 文本，
  下次 same period 直接命中。
- fallback：LLM 失败用纯模板（无 LLM 润色）。
- 成本控制：每报告 ≤ 10 段 narrative × 2 locale = 20 次 LLM。

### RP5. 渲染管线（≈ 0.3 周）

`backend/app/reports/renderers/`：

- `pdf.py` — `weasyprint`（HTML→PDF），HTML 由 Jinja2 模板（`templates/reports/{type}.html`）
  + section data 渲染。
- `markdown.py` — section data → MD（用于 `genpano_generate_report` MCP tool）。
- `json.py` — 直出 ReportPayload（machine consumable）。
- `csv.py` — 数据表导出（与 Phase E.1 通用 CSV 共享）。

### RP6. 端点（≈ 0.2 周）

`backend/app/api/v1/reports/router.py`：

- `GET /v1/projects/:id/reports?type=&status=&cursor=` — 列表。
- `POST /v1/projects/:id/reports` — 即时生成 `{report_type, scope, locale, sections_override?}` →
  `report_jobs(status='queued')` → 入队 `reports.generate`。
- `PATCH /v1/projects/:id/reports/:rid` — 取消。
- `GET /v1/projects/:id/reports/:rid` — 状态 + 元数据。
- `GET /v1/projects/:id/reports/:rid/download?format=pdf|md|json|csv` — 302 → 签名 URL。
- `GET /v1/projects/:id/report-schedules` — 列调度（PRD §3353）。
- `PUT /v1/projects/:id/report-schedules` — 设/改调度。
- `POST /v1/projects/:id/reports/:rid/share` — 生成 share token，返回 URL。
- `DELETE /v1/projects/:id/reports/:rid/share/:token` — 撤销分享。
- `GET /reports/public/:token` — **无 auth** 公开访问（PRD §830）；记 view_count；
  过期返 410。

### RP7. Celery 任务（≈ 0.3 周）

- `reports.generate(report_id)` — 编排 RP3 builder + RP4 narratives + RP5 renderer。
- `reports.run_schedules()` — 每 5min 扫 `report_schedules.next_run_at <= now()`，
  enqueue generate + 更新 `next_run_at`。
- `reports.expire_share_tokens()` — 每天清过期 token。

### RP8. lead_diagnostic 独立视图（≈ 0.2 周）

`backend/app/reports/lead_diagnostic_builder.py`：
- 不走 SECTION_MATRIX，直出 4 layer view（Layer 1: 现状一句话 + 关键指标卡 ×4，
  Layer 2: Top 3 P0/P1 诊断卡 + 行业对比，Layer 3: 一句方向总结，
  Layer 4: 引导联系顾问 CTA）。
- 用于"用户提交线索后自动生成 PDF 报告发给 BD 团队"（PRD §6871）。

### RP9. CTA Section + Lead 联动

`cta.py` section 渲染时如果用户填了 lead form → 写 `commercial_leads` +
触发 `leads.notify` Celery（邮件给 sales 团队）。

### Phase RP 验收

- ✅ 4 reportType × 10 section 全部能渲染；FE `ReportsPage.jsx` 4 viewer 模式
  （preview / markdown / json / pdf）都能加载。
- ✅ Narrative 多语言（zh / en）双语 fallback 工作。
- ✅ 即时生成 30 天 monthly 报告 < 60s（PRD §7.2）；调度任务 cron 准时。
- ✅ 公开分享链接 `/reports/public/:token` 可访问，view_count 递增，过期 410。
- ✅ lead_diagnostic 报告由用户提交线索自动触发，BD 邮箱收到。
- ✅ 单测：每 section happy/empty + builder + narrative LLM mock + share token
  生命周期 + cron 调度 + 4 渲染器（PDF/MD/JSON/CSV）。

---

## Phase 4 — 写 API + 异步任务（缩减为 Crawl + Leads，≈ 1 周）

报告 / 诊断已拆到 Phase RP / D。Phase 4 仅保留：

### 用户手动采集

- `POST /v1/projects/:id/crawl-requests` — `{brand_id, scope: {engines, prompts?}}`，
  写 `crawl_requests(status='queued')`，入队 `crawl.user_request`。
- `GET /v1/projects/:id/crawl-requests/:rid` — 状态轮询。
- Celery `crawl.user_request(request_id)` 复用 `geo_tracker/tasks/celery_tasks.py`；
  HIGH 优先级 + 用户日上限保护（默认 5 次/天，可配）。
- 队列：`-Q crawl,reports,notify` 与 Tracker `collection`/`analysis` 物理隔离。

### 商业线索

- `POST /v1/leads` — `{source, context, brand_id?, project_id?}`，写 `commercial_leads`。
- `leads.notify` Celery → 邮件给 sales。
- admin 端点（在 admin 模块加）：`GET /api/admin/leads` 列表 + 状态流转。
- lead 提交后自动触发 lead_diagnostic 报告（Phase RP.8）。

### 验收

- 用户手动采集 5min 内 done + brand_mentions 当日有新行；
  日上限触发 429 + i18n 文案。
- Lead 写库后 admin 即时可见 + lead_diagnostic 报告生成 + sales 邮件送达。

---

## Phase M — MCP Server + Team 预留位（≈ 2 周，**新增**）

PRD 把 MCP 当 Agent-native 立身之本（§1.3 / §2858），但**当前零实现**。
团队管理 MVP 阶段不做 UI（PRD §38），但需要预留 schema 防后续重构。

### M1. API Key 体系（≈ 0.3 周）

新表：

```sql
user_api_keys (
  id UUID PK,
  user_id INT FK→users(id) ON DELETE CASCADE,
  name VARCHAR(64),
  hash VARCHAR(128) NOT NULL,            -- bcrypt
  prefix VARCHAR(16),                    -- 'gp_sk_xxx' 前 8 位明文便于识别
  scope JSONB,                           -- {tools: ['*'] | [...], resources: ['*']}
  last_used_at TIMESTAMPTZ,
  usage_count INT DEFAULT 0,
  rate_limit_per_minute INT DEFAULT 60,
  created_at TIMESTAMPTZ DEFAULT now(),
  revoked_at TIMESTAMPTZ
);
```

端点：

- `POST /v1/users/me/api-keys` — 生成（name），返回**仅一次**完整 key。
- `GET /v1/users/me/api-keys` — 列表（不含 hash，仅 prefix + meta）。
- `DELETE /v1/users/me/api-keys/:id` — 撤销。
- `GET /v1/users/me/api-keys/:id/usage` — 用量统计（per day / per tool）。

`backend/app/core/security.py` 加 `current_api_principal()` 依赖：cookie session
**或** Bearer api key 都接受，区分 principal type 给后续审计用。

### M2. MCP Server 框架（≈ 0.4 周）

新模块 `backend/app/mcp/`：

```
backend/app/mcp/
  __init__.py
  server.py                      # JSON-RPC over SSE
  registry.py                    # @mcp_tool / @mcp_resource 装饰器
  errors.py                      # MCP_AUTH_REQUIRED / TOOL_UNKNOWN / PARAMS_INVALID
  middleware.py                  # Bearer 校验 + rate limit + audit log
```

入口 `backend/app/api/mcp/router.py`：
- `POST /mcp/v1` — JSON-RPC endpoint（initialize / tools/list / tools/call /
  resources/list / resources/read）。
- `GET /mcp/v1/sse` — SSE 长连接（用于 streaming response）。

未带 Bearer → 401 + `code=MCP_AUTH_REQUIRED`（PRD §687 契约）。

### M3. 6 个核心 Tools（≈ 0.5 周）

复用 Phase 2/3 service 层：

- `genpano_get_brand_visibility` → `/v1/projects/:id/metrics?series=mention,sov`
- `genpano_compare_brands` → 多 brand metrics 聚合
- `genpano_get_industry_trends` → `/v1/industries/:iid/overview`
- `genpano_get_product_ranking` → `/v1/projects/:id/products`
- `genpano_generate_report` → 入队 `reports.generate`，同步等结果或返回 job_id
- `genpano_get_optimization_insights` → `/v1/projects/:id/diagnostics` filter

每 tool：DTO + 多租户校验（API key → user → project access）+ 6 case 测试。

### M4. 3 个 Citation Tools（≈ 0.4 周，依赖 Phase A.3 + A.4）

- `genpano_get_citations` → `/v1/projects/:id/citations[/domains|pages]`
- `genpano_list_pr_targets` → 服务层基于 `domain_authorities` + 当前覆盖度排序
- `genpano_simulate_authority_boost` → 调 simulator service（与 Phase E.4 共享）

### M5. 3 个 Resources（≈ 0.2 周）

- `genpano://projects/{id}/dashboard` → 拼 Phase 2 多端点 → JSON
- `genpano://brands/{id}/report` → 拼 brand profile + recent diagnostics
- `genpano://industry/{name}/benchmark` → industry_benchmark_daily

### M6. FE 入口（≈ 0.3 周）

- `/settings/api-keys` 完善（SettingsPage 已有 mock UI）。
- 品牌详情页"在 MCP 中查询此品牌"按钮 + AuthPromptModal `hookKey=mcp_apikey`。
- `/docs/mcp` 静态文档（tools / resources 清单 + 接入示例）。

### M7. Team 预留位（≈ 0.3 周）

新表 + 默认 personal org per user：

```sql
organizations (
  id UUID PK,
  name VARCHAR(120),
  slug VARCHAR(64) UNIQUE,
  plan VARCHAR(16) DEFAULT 'free',       -- free | pro | enterprise
  created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE users ADD COLUMN default_org_id UUID FK→organizations(id);
ALTER TABLE projects ADD COLUMN org_id UUID FK→organizations(id);
ALTER TABLE commercial_leads ADD COLUMN org_id UUID;
ALTER TABLE report_jobs ADD COLUMN org_id UUID;
-- 迁移：每个 user 建一个 personal org，所有 project / lead / report 落到该 org
```

`current_project()` 依赖升级：归属判断从 `project.user_id == user.id`
改为 `project.org_id IN user.org_ids`（personal org 一对一兼容）。
**不**上 invitation / member / role UI — Phase T 再做（不在本计划范围）。

### Phase M 验收

- ✅ API Key 可生成 / 列表 / 撤销 / 用量统计；FE `/settings/api-keys` 可用。
- ✅ 9 个 MCP tools + 3 个 Resources 通过 `mcp` Python SDK / Claude CLI 端到端调通。
- ✅ 401 → `MCP_AUTH_REQUIRED`；rate limit 60/min/key；越权 → 403。
- ✅ `organizations` 表存在，所有现有数据落到 personal org，多租户单测继续 pass。
- ✅ 单测：API key 生成 / 校验 / 撤销 / 过期；每 tool 6 case；resources read。
- ✅ 文档 `docs/MCP_GUIDE.md` 完整。

---

## Phase N — Alerts + Notifications（≈ 2 周，**新增**）

PRD §3576 顶栏铃铛 + Project §1534 alertConfig + SettingsPage 3 toggle 都在
FE 等后端，**完全未实现**。

### N1. 数据模型（≈ 0.3 周）

```sql
alerts (
  id UUID PK,
  project_id UUID FK→projects(id) ON DELETE CASCADE,
  brand_id INT FK→brands(id) NULL,
  source VARCHAR(32) NOT NULL,           -- diagnostic | citation_mismatch | monitoring_outage | manual | system
  source_ref_id VARCHAR(64),             -- diagnostic.id 等
  severity VARCHAR(4) NOT NULL,          -- P0 | P1 | P2 | P3
  title VARCHAR(512),
  body TEXT,
  status VARCHAR(16) DEFAULT 'unread',   -- unread | read | ignored | resolved
  triggered_at TIMESTAMPTZ DEFAULT now(),
  read_at TIMESTAMPTZ, read_by INT,
  resolved_at TIMESTAMPTZ
);
CREATE INDEX ON alerts (project_id, status, triggered_at DESC);

alert_rules (
  id UUID PK,
  user_id INT,                            -- NULL = system default
  project_id UUID NULL,                   -- NULL = applies to all user projects
  rule_type VARCHAR(32),                  -- p0_diagnostic | p1_diagnostic | citation_mismatch | competitor_overtake | weekly_digest
  conditions JSONB,                       -- {threshold: ..., metric: ..., window: ...}
  channels VARCHAR[] DEFAULT '{email,inapp}',  -- email | inapp | webhook (Phase 2)
  enabled BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ
);

user_notification_preferences (
  user_id INT PRIMARY KEY,
  p0p1_alerts BOOLEAN DEFAULT TRUE,       -- 对应 SettingsPage toggle 1
  weekly_report BOOLEAN DEFAULT TRUE,     -- toggle 2
  competitor_alert BOOLEAN DEFAULT FALSE, -- toggle 3
  email_locale VARCHAR(8) DEFAULT 'zh-CN',
  quiet_hours JSONB,                      -- {start: '22:00', end: '08:00', tz: 'Asia/Shanghai'}
  updated_at TIMESTAMPTZ
);
```

### N2. 触发器（≈ 0.4 周）

- `backend/app/alerts/triggers.py`：
  - `on_diagnostic_created(diag)` — Phase D evaluator 创建 P0/P1 时调；
    检 user notification_pref + alert_rules → 写 alerts + 入队 `notify.send`。
  - `on_monitoring_outage()` — 独立 Celery hourly：扫 24h 没新 `llm_responses`
    的 brand → P1 alert。
  - `on_citation_mismatch_threshold()` — Phase A.3 attribution 写完调；
    official_domain 占比 14d < 阈值 → P2 alert。
  - `on_competitor_overtake(brand_a, brand_b)` — competitor_aggregator (Phase A.7)
    检测到反超 → 按 user.competitor_alert 偏好触发。

### N3. 端点（≈ 0.3 周）

`backend/app/api/v1/alerts/router.py`：

- `GET /v1/alerts?status=&severity=&project_id=&cursor=` — 列表（顶栏 dropdown 用 limit=5）。
- `GET /v1/alerts/unread-count` — 顶栏角标数字。
- `PATCH /v1/alerts/:id` — `{status: 'read'|'ignored'|'resolved'}`。
- `POST /v1/alerts/mark-all-read` — 一键全部已读。

`backend/app/api/v1/users/me/notifications/router.py`：

- `GET /v1/users/me/notifications` — 当前偏好。
- `PATCH /v1/users/me/notifications` — 更新（Settings 3 toggle + locale + quiet hours）。

`backend/app/api/v1/users/me/alert-rules/router.py`：

- `GET / POST / PATCH / DELETE /v1/users/me/alert-rules` — 自定义规则。

### N4. 邮件 / 站内通知（≈ 0.4 周）

复用 `backend/app/user_auth/email.py` 基础：

- `backend/app/notifications/templates/`：`alert_p0.html` / `alert_p1.html` /
  `weekly_digest.html`，i18n 支持 zh/en。
- `backend/app/tasks/notify.py`：
  - `notify.send(alert_id)` — 检 quiet_hours / 用户 channel 偏好 → 发 email +
    inapp（写 alerts.read=false 即站内）。
  - `notify.weekly_digest()` — 每周一发周报摘要（依赖 Phase RP weekly report）。

### N5. FE 顶栏铃铛（≈ 0.3 周）

`frontend/src/components/topbar/AlertBell.tsx`（新建）：
- 角标数字 ← `useUnreadAlerts()` polling 30s。
- 点击展开 dropdown：Top 5 unread alerts（`useAlerts(limit=5)`）。
- 单 alert 点击 → 跳 `/brand/diagnostics?alertId=xxx&diagnosticId=...`。
- "查看全部" → `/alerts` 页（新建简单列表）。

### N6. SettingsPage notifications 联通（≈ 0.2 周）

`SettingsPage.jsx` 3 toggle：
- 加 hook `useNotificationPreferences()` → 拉 N3 偏好端点。
- toggle 改动 → `useUpdateNotificationPreferences()` → PATCH。
- 加 quiet_hours 配置区（PRD §1534 隐含）。

### Phase N 验收

- ✅ Phase D 触发 P0/P1 → alerts 写库 → 邮件送达 + 顶栏铃铛角标 +1。
- ✅ Settings 3 toggle 持久化；quiet_hours 内不发邮件。
- ✅ `/alerts` 列表分页 + 标记 read/ignored 可用。
- ✅ Citation mismatch / monitoring outage / competitor overtake 三类自动触发可观测。
- ✅ 单测：3 触发器 happy + edge；邮件模板渲染（zh/en）；quiet hours 计算；
  alert rule CRUD 多租户。

---

## Phase E — 通用 CSV Export + Brand Submission + Simulator + Public Stats（≈ 1.5 周，**新增**）

补 PRD 中 FE 已写但后端缺的 4 个零散模块。Public Stats（P3）按用户决定**不做**。

### E1. 通用 CSV Export（≈ 0.5 周，PRD §4.6.4）

```sql
export_jobs (
  id UUID PK,
  project_id UUID FK→projects(id) ON DELETE CASCADE,
  user_id INT FK→users(id),
  export_type VARCHAR(32) NOT NULL,      -- mention_list | sentiment_list | citation_list | competitor_matrix |
                                          -- topic_coverage | industry_ranking | products_list | report_data
  scope JSONB,                            -- {from, to, brand_ids, engines, profile_group_id, filters}
  status VARCHAR(16) DEFAULT 'queued',
  output_url TEXT,
  row_count INT,
  created_at TIMESTAMPTZ, finished_at TIMESTAMPTZ
);
```

端点：
- `POST /v1/projects/:id/exports` — `{export_type, scope}` → 入队 `exports.generate`。
- `GET /v1/projects/:id/exports/:eid` — 状态轮询。
- `GET /v1/projects/:id/exports/:eid/download` — 302 → 签名 URL。

Celery `exports.generate(eid)`：复用 Phase 2/3 service 层取数据 →
`pandas.to_csv(streaming=True)` 写 S3/local → 更新 status。

配额：每用户每天 ≤ 20 次 export（PRD §5281），超限 429 + i18n。

FE：`AuthPromptModal hookKey=export_csv`，登录后 `?action=export_csv&exportType=...`
回到原页面自动触发 `useCreateExport()`。

### E2. Brand Submission 用户侧（≈ 0.3 周）

PRD §284 用户在 `/brands` 集市搜不到品牌时点"提交新品牌"。
admin 已有 `/admin/v1/brands/submissions`（Phase R.4 迁过）— 这里加用户侧入口。

```sql
brand_submissions (
  id UUID PK,
  user_id INT FK→users(id),
  org_id UUID FK→organizations(id),
  proposed_name VARCHAR(256),
  proposed_industry_id INT,
  proposed_aliases JSONB,
  proposed_official_domains JSONB,
  notes TEXT,
  status VARCHAR(16) DEFAULT 'pending',  -- pending | approved | rejected | duplicate
  reviewer_id INT, reviewed_at TIMESTAMPTZ,
  resulting_brand_id INT FK→brands(id) NULL,    -- 审核通过后入 brands 表
  created_at TIMESTAMPTZ DEFAULT now()
);
```

端点：
- `POST /v1/brands/submissions` — 用户提交。
- `GET /v1/users/me/brand-submissions` — 列表（看自己提交进度）。
- 审核通过 → admin 调用合并 → 触发 KG 入库（Phase K K3 candidates 流程）。

FE：`BrandsPage.jsx` 搜索无结果时显示 "没找到？提交新品牌 →" CTA → 弹模态。

### E3. BrandSimulator 端点（≈ 0.3 周）

`BrandSimulatorPage.jsx`（333 行）已写好 FE，调
`POST /api/brands/:id/simulate-authority-boost`（FE 中暴露的端点路径）。

新建 `backend/app/api/v1/simulator/router.py`：

- `POST /v1/projects/:id/simulator/run` — `{brand_id, delta_by_tier: {1: N, 2: N, 3: N},
  confidence_override?}` → 调 simulator service（依赖 Phase A.4 domain_authorities）→
  返回 `{current_pano_a, simulated_pano_a, delta, base_price_equivalent}`。

`backend/app/simulator/authority_boost.py`：
- 公式：基于当前 brand 在各 tier 的 citation count + 注入 delta → 重算 PANO A 子分。
- 行业参数表（base_price_equivalent）：admin 维护小表 `industry_pricing_params`。

与 Phase M.4 MCP tool `genpano_simulate_authority_boost` **共享同一 service 函数**。

### E4. Public Stats（**砍掉，按 P3 决定**）

不做。Roadmap 待定。

### Phase E 验收

- ✅ 8 种 exportType 各能下载 CSV；超配额 429 + 文案。
- ✅ 用户提交品牌 → admin 审核流程通；通过后入 KG candidates。
- ✅ Simulator 调多个 tier delta 返回新分；与 MCP tool 输出一致。
- ✅ 单测：export quota 限速；submission 状态流转；simulator 公式 + 行业参数。

---

## Phase O — Admin 运营模块（≈ 2 周，**新增**）

补 `docs/ADMIN_PRD.md` §4.2 + §4.3 + §4.4 中**已设计但未实现**的 9 个运营模块。
Phase R.4 只迁移 admin_console 现有路由；本 Phase 在迁移好的 FastAPI admin 基础上
**新增**这 9 个模块。

### O1. 运营诊断（≈ 0.8 周，对应 ADMIN_PRD §4.2 + §4.3.6）

#### O1.1 Pipeline 全景 `/admin/pipeline/overview`

- 24h funnel：`query_executions` → `attempts` → `llm_responses` → `response_analyses`，
  各阶段 success/fail/pending 计数 + 异常率。
- 引擎分布饼图（来自 `geo_score_daily.target_llm`）。
- 顶部 KPI 卡：今日总查询 / 完成率 / 平均延迟 / 失败堆积。
- 数据：复用现有 `query_executions`（admin_console 已写）。

#### O1.2 引擎健康 `/admin/pipeline/engines`

- 新表 `engine_health_daily(engine VARCHAR(64), date DATE, total_attempts INT,
  success_count INT, success_rate FLOAT, p50_latency_ms INT, p95_latency_ms INT,
  cookie_status VARCHAR(16), captcha_count INT, ip_blocked_count INT, last_updated)`
- Celery hourly task `engine_health.aggregate()` 扫 `attempts` 表聚合。
- 列表 + 30d 趋势图（每引擎 success_rate / latency）。
- 异常告警：success_rate < 80% 触发 P1 alert（接 Phase N）。

#### O1.3 失败重试中心 `/admin/pipeline/retry-center`

- 列表 `query_executions WHERE status='failed'` + 筛选（adapter / error_code / time）。
- 操作：单条 retry / 批量 retry / mark_failed_permanent。
- 失败原因分类（基于 `attempts.error_code`：timeout / captcha / rate_limit / parse_error）。
- 每次 retry 写 `admin_audit_log`（O2.2）。

#### O1.4 代理池状态 `/admin/pipeline/proxies`

- 列表 `proxies` 表（已有）+ 加 `last_health_check_at` 列 + 速度 / 成功率统计
  （新增 `proxy_health_daily` 聚合）。
- 操作：禁用 / 启用 / 强制重测。

#### O1.5 KG Discovery Logs `/admin/kg/discovery-logs`（与 Phase K 联动）

- 列出 Phase K K5 `relation_extractor` 推断历史 + 幻觉率统计。
- 新表 `discovery_log(id UUID, source VARCHAR(32), candidate_id UUID FK,
  llm_model VARCHAR(64), confidence FLOAT, hallucination_flag BOOLEAN,
  occurred_at TIMESTAMPTZ)`。
- 30d 幻觉率 → ADMIN_PRD §C9 KG Quality 一项指标。

### O2. 运营报告（≈ 0.7 周，对应 ADMIN_PRD §4.4.1 + §4.4.7 + §4.4.6）

#### O2.1 成本看板 `/admin/cost/daily`

- 新表 `cost_events(id UUID, scope VARCHAR(16), amount NUMERIC(10,4),
  source VARCHAR(64), event_type VARCHAR(32), reference_id VARCHAR(64),
  occurred_at TIMESTAMPTZ)` — `scope ∈ {pipeline, kg, mcp, reports}`。
- 写入点：
  - 每次 LLM analyzer 调用（豆包 / DeepSeek）→ `pipeline`
  - Phase D causal LLM → `pipeline` 子项 `diagnostics`
  - Phase RP narrative LLM → `pipeline` 子项 `reports`
  - Phase K K5 relation_extractor LLM → `kg`
  - MCP tool 调用 → `mcp`（按 token 估算）
- 看板视图：今日 / 7d / 30d 趋势 + 按 scope 堆叠 + 按 source 明细。
- 预算告警：`budget_scope` 单日超阈值 → P0 alert（接 Phase N）。

#### O2.2 审计日志 `/admin/audit-log`

- 新表 `admin_audit_log(id UUID, operator_id INT FK→users, action VARCHAR(64),
  resource_type VARCHAR(32), resource_id VARCHAR(64), severity VARCHAR(8),
  before JSONB, after JSONB, ip INET, user_agent TEXT, occurred_at TIMESTAMPTZ)`
  — 已在 ADMIN_PRD §5.2 规范。
- 写入点：所有 admin 写操作通过统一 `audit_decorator` 注入：
  freeze / unfreeze / brand_merge / brand_approve / batch_retry / config_change /
  cookies_import / account_reset / segment_delete / topic_plan_review。
- 列表 + 筛选（operator / action / resource / time）+ 导出 CSV（复用 Phase E.1）。
- 高风险操作（freeze / brand_merge / batch_trigger）必审 — `audit_decorator`
  自动加 P1 标记。

#### O2.3 MCP 运营 `/admin/mcp-ops`

- 新表 `mcp_call_log(id BIGINT, api_key_id UUID FK→user_api_keys, user_id INT,
  tool VARCHAR(64), status VARCHAR(16), latency_ms INT, error_code VARCHAR(64),
  cost_estimate NUMERIC(10,4), occurred_at TIMESTAMPTZ)` (partition by month)。
- 视图：今日 top users + top tools + 错误率 + 平均延迟。
- 配额监控：检测 user 超 60/min/key 限速 → 自动暂停 24h（接 Phase M.1
  rate_limit_per_minute）。
- 复用 Phase M user_api_keys 表 + Phase O 数据。

### O3. 运营行动（≈ 0.3 周，对应 ADMIN_PRD §4.4.2 + §4.4.4 + §4.4.5）

#### O3.1 告警中心 `/admin/alerts`（与 Phase N 共享 alerts 表）

- `alerts` 表加 `scope VARCHAR(16) DEFAULT 'user'` 列：
  - `scope='user'` 用户产品端可见（Phase N）
  - `scope='operator'` 仅 admin 可见
- 运营 alert 来源：
  - engine_health success_rate 跌（O1.2）
  - monitoring_outage（24h 没新数据）
  - cost_overrun 预算超限（O2.1）
  - kg_quality 总分 < 80（O1.5）
  - admin 高风险 mutation 自动告警
- 操作：acknowledge / assign to operator / mark resolved / link to runbook。

#### O3.2 公告 & 邮件 `/admin/comms`

- 新表 `comms_announcements(id UUID, title VARCHAR(256), body TEXT,
  channel VARCHAR(16), audience VARCHAR(32), scheduled_at TIMESTAMPTZ,
  sent_at TIMESTAMPTZ, sent_count INT, created_by INT)`
  — `channel ∈ {inapp, email}`，`audience ∈ {all, paid, free, by_org}`。
- 端点：CRUD + `POST /admin/comms/:id/send`（入队邮件批发送）+ 草稿预览。
- 模板：`backend/app/notifications/templates/admin_comms_*.html`。

#### O3.3 商务线索 `/admin/commercial/leads`

- 复用 Phase 4 `commercial_leads` 表 + 加 `assigned_to INT`、`closed_reason VARCHAR(64)` 列。
- admin 视图：list + 状态流转（new → contacted → closed）+ 备注 + 导出 CSV。
- 联动：Phase RP.8 lead_diagnostic 报告 PDF 链接显示在线索详情。

### O4. 调度配置（≈ 0.2 周，对应 ADMIN_PRD §4.4.3）

升级 admin_console 已有的 `/admin/schedule` 路由（R.4 迁过）：

- cron 编辑 UI（FE 模板新加 visual cron builder）。
- 历史 run 查询 + 失败任务一键重跑。
- 调度规则触发预览（"明天 03:00 会跑 X 任务"）。

### O5. FE 模板（≈ 0.4 周）

`backend/app/templates/admin/`（Phase R.4 已迁好基础）扩 9 个新页：

```
pipeline_overview.html         # O1.1
pipeline_engines.html          # O1.2
pipeline_retry_center.html     # O1.3
pipeline_proxies.html          # O1.4
kg_discovery_logs.html         # O1.5
cost_daily.html                # O2.1
audit_log.html                 # O2.2
mcp_ops.html                   # O2.3
alerts_admin.html              # O3.1（与 user-side alerts 不同视图）
comms.html                     # O3.2
commercial_leads.html          # O3.3
```

复用现有 admin.html 的 Stripe/Linear 设计 token + JS chart 库（D3，已 in template）。
统一通过 admin 顶部导航 §3.1 接入。

### O6. 端点 + 数据模型

总 ≈ 35 个 admin 端点（每模块 3-5 个 CRUD + action）。
新表（合入 Phase R.2 alembic）：6 张

```
engine_health_daily        # O1.2
proxy_health_daily         # O1.4
discovery_log              # O1.5（与 Phase K 联动）
cost_events                # O2.1
admin_audit_log            # O2.2
mcp_call_log               # O2.3 (monthly partition)
comms_announcements        # O3.2
```

### Phase O 验收

- ✅ ADMIN_PRD §4.2.1 / §4.2.2 / §4.2.6 / §4.4.1 / §4.4.2 (operator scope) /
  §4.4.4 / §4.4.5 / §4.4.6 / §4.4.7 全部上线。
- ✅ Frank 可通过 admin 完成"发现失败任务 → 看 artifact → retry → 验证"
  全闭环（< 5 click）。
- ✅ 成本看板每日产出 + 预算告警；审计日志含全部高风险 mutation 自动入库；
  MCP 运营有用量趋势 + 配额自动暂停。
- ✅ 公告功能 dev 测试：admin 发公告 → 用户站内 / 邮箱收到 + 模板渲染正确。
- ✅ 单测：每端点 admin only（非 admin → 401）+ 6 case 集成 + 高风险 mutation
  必审 + audit_decorator 测试 + 限速测试。

### Phase O 时间表（与 Phase 2/3/E 并行，2 周日历）

由 1 backend + 1 frontend(template) 工程师专做：

| 周 | 后端 | FE 模板 |
| --- | --- | --- |
| OW1 | O1 + O2 数据模型 + Celery aggregator | O1 + O2 模板 |
| OW2 | O3 + O4 + O6 端点 + audit_decorator | O3 + O4 + O5 模板 + 联调 |

---

## Phase 5 — 硬化 + mock 退役（≈ 1 周）

### 后端硬化

- Rate limit（PRD §7.1）：登录/注册 10/min/IP；通用 60/min/user，新建
  `backend/app/core/rate_limit.py`（基于 Redis token bucket）。
- CORS：仅前端域 + admin 域。
- HTTPS：preview / live test env 强制（nginx）。
- 多租户审计：每 endpoint 都有"用户 A 访问 B 的 project → 404" 测试。
- OpenAPI 同步：FastAPI 自动 schema vs `docs/openapi.yaml` CI 校验。

### 前端硬化

- 21 page 全部切完后，`frontend/src/data/mock.js` 内容迁到
  `frontend/src/__ci_fixtures__/sampleData.ts`（仅给 Vitest）。
- ESLint `no-restricted-imports` 禁止 `pages/**` 与 `components/**` 引用 mock。
- i18n 扫描：`grep -E "[\\u4e00-\\u9fa5]"` 仅 `i18n/**` 命中。
- Lighthouse a11y ≥ 95；375/768/1280 三档断点 visual snapshot。

### 测试 / 部署

- 后端：`backend/make ci`（ruff + mypy + pytest，覆盖率 ≥ 70% 服务层）。
- 前端：`npm run ci`（unit + harness + contracts + selftest）。
- e2e：`auth × 5` + `onboarding` + `brand-overview` + `switch-project` + `report-export`。
- `frontend/nginx.conf`：SPA fallback、`/api`、`/admin`、index.html `Cache-Control: no-store`。
- 文档更新：`README.md`、`DEPLOY_GUIDE.md`、`docs/openapi.yaml`、
  `docs/PRD_CODEX_READY.md`（标注 App-end backend 已完成）。
- 退出 plan 模式后，**删除 `docs/APP_FRONTEND_PLAN.md`** 或重命名为
  `docs/APP_BACKEND_PLAN.md`，避免误导。

---

## 后端架构与代码约定

### 包结构

```
backend/app/
  main.py                          # FastAPI app factory; include routers
  api/v1/
    auth/                          # 已有
    projects/      brands/        industries/    topics/
    citations/     products/      competitors/   reports/
    diagnostics/   leads/         crawl/
    _meta/                         # GET /v1/_meta/routes
  core/
    config.py    security.py    errors.py    pagination.py
    filters.py   rate_limit.py
  diagnostics/rules.py             # 规则引擎
  reports/{pdf.py, csv.py}         # 渲染
  models/
    user.py        analyzer.py     # 已有
    project.py     project_competitor.py    project_topic_pin.py
    commercial_lead.py    report_job.py    crawl_request.py
    brand.py    industry.py    topic.py    prompt.py    query.py
    llm_response.py                 # read-only mirror of tracker
  tasks/
    health.py                       # 已有
    reports.py    crawl.py    leads.py
  alembic/versions/2026_05_xx_app_product_tables.py
```

### 约定

- 路由：全部 `/api/v1/...`，资源用复数。
- 时间统一 ISO8601 UTC；分页 cursor + limit（排名页 offset 例外）。
- 多租户：`Depends(current_user)` + `Depends(current_project(project_id))`。
- 错误：RFC 7807，含 `code` 字段供 FE i18n。
- ORM：写表归 backend；Tracker 写的表 backend 端只读 mirror，CI drift check。
- Celery：复用 `REDIS_URL`，新 queue `reports/crawl/notify` 与 Tracker 物理隔离。

---

## 关键文件清单

### 新建（后端）

```
backend/app/api/v1/{projects,brands,industries,topics,citations,products,
                    competitors,reports,diagnostics,leads,crawl,_meta}/
  {router.py, _dto.py, service.py}        # 12 × 3 = 36 文件
backend/app/core/{security.py, errors.py, pagination.py, filters.py, rate_limit.py}
backend/app/models/{project.py, project_competitor.py, project_topic_pin.py,
                    commercial_lead.py, report_job.py, crawl_request.py,
                    brand.py, industry.py, topic.py, prompt.py, query.py,
                    llm_response.py}
backend/app/diagnostics/rules.py
backend/app/reports/{pdf.py, csv.py}
backend/app/tasks/{reports.py, crawl.py, leads.py}
backend/alembic/versions/2026_05_xx_app_product_tables.py
```

### 新建（前端）

```
frontend/src/lib/{apiClient.ts, emailDomains.ts}
frontend/src/api/{projects.ts, brands.ts, industries.ts, topics.ts, citations.ts,
                  products.ts, competitors.ts, reports.ts, diagnostics.ts,
                  leads.ts, crawl.ts}
frontend/src/hooks/{useProjects.ts, useBrandOverview.ts, useBrandVisibility.ts,
                    useBrandTopics.ts, useBrandSentiment.ts, useBrandCitations.ts,
                    useBrandProducts.ts, useBrandCompetitors.ts, useBrandDiagnostics.ts,
                    useIndustryOverview.ts, useIndustryRanking.ts, useIndustryTopics.ts,
                    useIndustryKG.ts, useReports.ts, useSubmitLead.ts,
                    useCreateCrawlRequest.ts}
frontend/src/components/ui/{Skeleton.tsx, EmptyState.tsx, ErrorState.tsx}
```

### 修改（前端，逐页切 mock → hook）

`frontend/src/pages/{DashboardPage.jsx, OnboardingPage.jsx, ProjectSettingsPage.jsx,
SettingsPage.jsx, BrandsPage.jsx, ReportsPage.jsx, DiagnosticsPage.jsx,
KnowledgeGraphPage.jsx, TopicsPage.jsx,
brand/{BrandVisibilityPage,BrandSentimentPage,BrandCitationsPage,
       BrandProductsPage,BrandCompetitorsPage}.jsx,
industry/{IndustryOverviewPage,IndustryRankingPage,IndustryTopicsPage}.jsx,
BrandProductDetailPage.jsx, BrandSimulatorPage.jsx, BrandDetailPage.jsx}`

### 删除 / 归档

`frontend/src/{App.tsx, main.tsx}`、`pages/{DashboardPage.linear.jsx,
LandingPageLegacy.jsx, IndustryPage.jsx, QueriesPage.jsx}`、
`docs/APP_FRONTEND_PLAN.md`（退 plan 模式后处理）。

---

## 可复用代码（来自 admin_console / geo_tracker）

| 模块 | 路径 | 复用方式 |
| --- | --- | --- |
| Layer classifier | `admin_console/_layer_classifier.py` (118 LOC) | 诊断规则中检测 topic/prompt/query 层级 |
| Topic 校验 | `admin_console/topic_plan.py` (700 LOC) | 取 schema 校验 / 去重逻辑（不取 LLM 调用部分） |
| Prompt intent / language 校验 | `admin_console/prompt_matrix.py` (1076 LOC) | 同上 |
| Segment / Profile schema | `admin_console/segment_profiles.py` (568 LOC) | App 端 segment 视图所需 |
| 分析表 ORM | `backend/app/models/analyzer.py` | 已存在，直接 select |
| Adapter dispatch | `geo_tracker/tasks/celery_tasks.py` | `crawl.user_request` 内部调用，不重写 |
| 完整 schema mirror | `geo_tracker/db/models.py` | 抄字段定义到 `backend/app/models/` 只读 mirror |

**禁止重写**：Topic Plan / Prompt Matrix / Query Pool 生成 pipeline、
账号池调度、用户冻结审计 — 这些是 admin operator 专属。

---

## 风险与依赖

| 风险 | 缓解 |
| --- | --- |
| Tracker 与 backend ORM 漂移 | CI `models_drift_check.py` 比对字段；新表 backend 独占 |
| 用户多租户越权 | `current_project` 依赖 + 单测覆盖；端点默认 404 |
| Adapter 数据稀疏 → UI 长期 empty | 标准 EmptyState + "立即采集" CTA → `crawl.user_request` |
| 报告生成阻塞 web | Celery 异步 + FE polling |
| OpenAPI 与实现漂移 | CI 比对 FastAPI auto schema vs `docs/openapi.yaml` |
| 用户手动采集挤压定时采集 | 队列物理隔离 + 用户日上限 |
| 邮箱黑名单前后端不同步 | `frontend/src/lib/emailDomains.ts` 单一来源 |

---

## 时间表（含 Phase P + R + A + K + D + RP + M + N + E + O）

总计算法（9 工程师并行：1 PM/tech lead + 2 backend + 1 frontend + 2 pipeline +
1 KG/MCP + 1 reports/diagnostics + 1 admin ops）：

| 周 | PRD/工程 | 后端 API | 前端 | A | K | M | N | D | RP | E | **O** |
| - | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| W0.0-0.5 | **P1 PRD + ADMIN_PRD** | — | R.1 删 .jsx | — | — | — | — | — | — | — | — |
| W0.5-1.0 | **P2 DATA_MODEL + P3 OpenAPI** | — | R.1 .tsx 化 | — | — | — | — | — | — | — | — |
| W1.0-1.5 | **P4 ADR + P5 交叉表 + 启动会** | — | R.1 收尾 | — | — | — | — | — | — | — | — |
| W2 | — | R.2 SQL→Alembic | R.3 contexts 合并 | A1 | K1+K2 | — | — | — | — | — | — |
| W3 | — | R.4 admin 迁前 6 子包 | TS 严格 0 错 | A2+A3 | K3 cat/brand/product | — | — | — | — | — | — |
| W4 | — | R.4 收尾 + R.5 Makefile | apiClient + Query | A4 | K3 收尾+K4 | M1 | — | D1+D2 | — | — | — |
| W5 | — | Phase 0 骨架 + 6 表 | — | A5+A6 | K5 | M2 | — | D3 (10 条) | RP1+RP2 | — | — |
| W6 | — | Phase 1 projects + industries | ProjectContext + Onboarding | A7+A8+A11 | K5 收尾+回填 | M3 6 tools | N1+N4 | D3 剩余+D4 | RP3 (6/10) | E1 框架 | — |
| W7 | — | Phase 2.1 overview / metrics | Brand Overview / Visibility | A9+A10 | K6+K7 | M4 3 tools | N2+N3 | D5+D6 | RP3 剩余+RP4 | E3 | **OW1 O1+O2** |
| W8 | — | Phase 2.2 topics/sentiment/citations | Brand T/S/C | — | — | M5+M6 | N5 收尾 | D7+D8 | RP5+RP6+RP7 | E4+E1 收尾 | **OW2 O3+O4+O5** |
| W9 | — | Phase 2.3 + Phase 3 industry × 4 | Brand P/C/D + Industry × 4 | — | — | M7 | N6 | D9 测试 | RP8+RP9 | E 测试 | O 联调测试 |
| W10 | — | Phase 4 crawl + leads | Reports / Lead / Simulator FE | — | — | — | — | — | RP10 测试 | — | — |
| W11 | — | Phase 5 硬化 | mock 退役 + a11y + i18n | — | — | — | — | — | — | — | — |
| W12 | — | preview smoke + 文档归档 | — | — | — | — | — | — | — | — | — |
| W14.5 | — | release 准备 / 发布 | — | — | — | — | — | — | — | — | — |

> **总日历：14.5 周（≈ 3.6 个月），9 工程师并行**。
> 7 工程师配置则 ≈ 17 周；5 工程师 ≈ 23 周。

### 关键并行 / 依赖

- **Phase P 与 R.1 并行**：FE TS 化不依赖 PRD 决策；但业务后端 W2 才能开工。
- **Phase A + K 与 Phase 0/1/2 重叠 5-6 周**：W7 之前 4 BLOCKER + KG 主体已落，
  Brand 9 + Industry 4 页能在 W7-W9 完整切真实数据。
- **Phase D 必须先于 Phase RP.diagnostic_summary section**：W6-W8 D 完成 →
  RP 才能拼诊断章节。
- **Phase N 依赖 Phase D**：D8 alert 联动 + N2 触发器需要 diagnostics 数据流入。
- **Phase M.4 Citation tools 依赖 Phase A.3 + A.4**。
- **Phase E.3 brand_submission 依赖 Phase K candidates 流程**（W4 K3 完即可 unblock）。
- **Phase E.4 simulator 与 Phase M.4 共享 service**：同周交付。

### 可压缩点

- Phase R.4 admin 13 子 router 可 3 人并行 → 2 → 1 周。
- Phase 2 的 9 页 BE/FE 双开。
- Phase A 可加 1 工程师压到 2.5 周（4 → 2.5）。
- Phase K K3 + K5 双开 → 2 周。
- Phase D 25+ 规则可 2 工程师双开。
- Phase RP 10 sections 可 2 工程师双开。

### 不可压缩

- Phase P 启动会与 ADR 签字（多方对齐成本）。
- 每页"四态 + 单测 + e2e smoke"。
- Phase R.2 alembic 迁移幂等性验证。
- Phase A 准确率门槛（归因 ≥ 95%、page_type ≥ 90%、sentiment ≥ 80%）。
- Phase A.11 + K5 30 天历史回填验证（数据正确性比速度重要）。
- Phase K K5 关系抽取金标 ≥ 90%。
- Phase D causal LLM 准确率与缓存命中率验证。
- Phase RP narrative LLM 双语 fallback 验证。
- Phase M MCP 端到端联调（Claude / GPT 客户端实测）。
- Phase N 邮件送达率 + quiet hours 测试。

### 完整依赖图

- `/brand/overview` 同集团卡 → A6 完
- `/brand/citations` 归因模块 → A3 + A4 完
- `/brand/diagnostics` 内容缺口 / KOL / Tier2 → A3+A4+A5+A8+D 全完
- `/brand/competitors` 竞品矩阵 / 气泡 → A7 完
- `/brand/diagnostics` 完整 4 layer → D1-D9 全完
- `/brand/reports` 含 narrative 双语 → RP1-RP10 全完
- `/industry/knowledge-graph` → K1+K2+K3+K6+K7 完（K5 LLM 推断未完时显示"运营录入边"）
- `BRAND_RELATIONS` `PRODUCT_RELATIONS` mock 退役（Phase 5）→ Phase K 完
- 顶栏 🔔 铃铛 + Settings 3 toggle 持久化 → Phase N 完
- "在 MCP 中查询此品牌"按钮 + `/settings/api-keys` → Phase M 完
- 任意表 CSV 下载 → Phase E.1 完
- `/reports/public/:token` → Phase RP.7 完
- 用户提交品牌 → Phase E.2 完
- `BrandSimulatorPage` → Phase E.4 完
- Admin 9 个运营页（Pipeline / Cost / Audit / MCP-Ops / Comms / Leads / 等）→ Phase O 完，依赖 R.4 完成 admin 迁移
- Admin Audit 决策器（高风险 mutation 自动入审）→ Phase O.2.2，要求 R.4 后所有 admin 写操作经 `@audit` 装饰器
- 运营成本告警（预算超限 P0）→ Phase O.2.1 + Phase N（共享 alerts 表 scope='operator'）
- 其余页面与 Phase A/K/D/RP/M/N/E/O 无依赖，可独立交付（基础数据来自 0/1/2/3）

---

## 不在范围

- 橙色 `/admin` 控制台（swimlane C）。
- Adapter 内部逻辑与采集策略（swimlane D）。
- Tracker SQL → Alembic 整合（独立 follow-up）。
- 移动端原生 App / 小程序。
- 邮件订阅 / Slack 分发 — 列 Roadmap。

---

## 测试计划

### 测试金字塔

```
        ┌──────────────────┐
        │  E2E (Playwright)│   ~10 主链路（auth/onboarding/brand/industry/reports）
        └──────────────────┘
       ┌────────────────────┐
       │  Visual / a11y     │   3 页 snapshot × 3 断点 + axe-core
       └────────────────────┘
      ┌──────────────────────┐
      │  Integration (BE)    │   pytest + httpx AsyncClient + 真 PostgreSQL
      └──────────────────────┘
     ┌────────────────────────┐
     │  Contract / Schema     │   FastAPI auto schema vs openapi.yaml；TS types drift
     └────────────────────────┘
    ┌──────────────────────────┐
    │  Component (RTL)         │   每个数据驱动 page 的 4 态
    └──────────────────────────┘
   ┌────────────────────────────┐
   │  Unit (Vitest / pytest)    │   service 层、hook、util、规则引擎
   └────────────────────────────┘
```

### A. 后端测试

**框架**：`pytest` + `pytest-asyncio` + `httpx.AsyncClient` + `pytest-postgresql`
（或 docker-compose 起的真 Postgres） + `factory_boy` 造数据。
现有：`backend/tests/`、`backend/Makefile` `make ci` 入口。

#### A1. 单元测试

| 模块 | 路径 | 测试内容 | 目标覆盖 |
| --- | --- | --- | --- |
| 核心安全 | `core/security.py` | `current_user` 解 JWT 成功 / 过期 / 篡改；`current_project` 归属/非归属/不存在 | 100% 分支 |
| 错误工具 | `core/errors.py` | RFC 7807 形状；`code` 透传 | 100% |
| 分页 | `core/pagination.py` | cursor 编解码、边界（首页 / 末页 / 空） | 100% |
| 过滤器 | `core/filters.py` | `from`/`to` 解析、引擎枚举校验、profile group | 100% |
| Rate limit | `core/rate_limit.py` | token bucket 限速、Redis 失效降级 | 100% |
| 诊断规则 | `diagnostics/rules.py` | 每条规则 happy + 不触发；空数据降级 | ≥ 90% |
| 报告渲染 | `reports/{pdf.py, csv.py}` | 模板渲染 / fixture 数据 / 异常 | ≥ 80% |
| Celery 任务 | `tasks/{reports,crawl,leads}.py` | 任务 happy / 重试 / 失败回写 status | ≥ 80% |

#### A2. 集成测试（端点）

每个 `/api/v1/*` 端点必跑 6 case：

1. **happy path**：合法用户 + 合法参数 → 200/201 + payload schema 校验。
2. **未认证**：无 Authorization → 401 + `code=unauthorized`。
3. **多租户拒绝**：用户 A 访问 B 的 project → 404（不泄露 ID 存在性）。
4. **参数校验**：非法 `from`/`to`/`engine` → 422 + `code` 含字段名。
5. **空数据**：fixture 给"项目刚建无数据"场景 → 200 `state='empty'`。
6. **错误形状**：故意触发 5xx → `application/problem+json` + `code=internal_error`。

写操作端点额外补：

7. **capacity / 唯一约束**：项目竞品 ≥ 10 → 409 `code=competitor_capacity_full`。
8. **debounce**：30s 内同 `(project, brand)` 两次添加 → 第二次 429。
9. **乐观更新冲突**：并发 PATCH `/v1/projects/:id` → 409 或最后写赢（决定后单测）。

#### A3. 多租户安全套件

新建 `backend/tests/test_multitenancy.py`：
- 参数化 fixture：用户 A、B 各持 1 个 project。
- 对所有 `current_project` 依赖的端点循环跑：A 用 B 的 project_id → 404；
  A 用不存在的 UUID → 404（区别仅在 log）。
- 跨用户读公共数据（`/v1/industries`、`/v1/brands`）→ 200，不带 user_id 过滤。

#### A4. 数据 / Schema 漂移

- `backend/tests/test_models_drift.py`：对 read-only mirror 的字段，
  比对 `geo_tracker/db/models.py` 中同名表的字段集，缺字段或类型不一致即 fail。
- `backend/tests/test_openapi_sync.py`：FastAPI `app.openapi()` 与
  `docs/openapi.yaml` 用 `deepdiff` 比对，差异白名单（version/server）外即 fail。

#### A5. 性能基线

`backend/tests/test_perf_baseline.py`（标记 `@pytest.mark.perf`，CI 可选跑）：
- 准备 30 天 fixture（约 100k `geo_score_daily` 行）。
- 对 9 个 Brand Mode + 4 个 Industry Mode 端点跑 100 次，p95 < 200ms。
- `/industries/:iid/kg`（KG）p95 < 1s（数据量大）。
- `pytest-benchmark` 可选输出 baseline.json，PR 比对回归 > 30% 即报警。

#### A6. CI

`backend/Makefile` `make ci` 已存在；扩展为：

```
make lint        # ruff + black --check
make typecheck   # mypy app/
make test-unit   # pytest -m "not integration and not perf"
make test-int    # pytest -m integration   (起 Postgres + Redis)
make test-multi  # pytest tests/test_multitenancy.py
make test-drift  # pytest tests/test_models_drift.py tests/test_openapi_sync.py
make ci          # 上述全部 + coverage ≥ 70%
```

### B. 前端测试

**框架**：`vitest` + `@testing-library/react` + `@playwright/test`
+ `axe-core/playwright`。
现有：`frontend/vitest.config.ts`、`frontend/playwright.config.ts`、
`frontend/src/__ci_fixtures__/`、`npm run ci` 入口。

#### B1. 单元测试（Vitest）

| 模块 | 测试内容 |
| --- | --- |
| `lib/apiClient.ts` | 401 → 跳 login；problem+json 解析；超时；Bearer 注入；Accept-Language 跟随 |
| `lib/emailDomains.ts` | 黑名单命中 / 不命中 / 大小写 / 子域 |
| `hooks/use*` | mock fetch（MSW） → 验证 loading / data / error / refetch；项目切换触发 invalidate |
| `contexts/ProjectContext.jsx` | optimistic update / rollback / 30s debounce / capacity 10 |
| `i18n/{zh,en}.ts` | 两个文件 key 集合一致；占位符 `{var}` 数量一致 |
| 工具函数 | 时间区间格式化、数字格式化（zh-CN vs en-US 千分位） |

目标覆盖：lib + hooks + contexts ≥ 80%。

#### B2. 组件测试（RTL）

每个数据驱动 page 至少一个测试文件，覆盖**4 态**：

```
beforeEach: render with QueryClient + MSW handlers
- loading: handler delay → 期望渲染 Skeleton
- empty:   handler 返回 state='empty' → 渲染 EmptyState + CTA
- error:   handler 返回 500 → 渲染 ErrorState + Retry
- success: handler 返回 fixture → 关键元素（KPI 数字、图表 testid）出现
```

模板：`frontend/src/__tests__/_helpers/renderWithQuery.tsx` 提供统一 wrap。

#### B3. E2E（Playwright）

`frontend/tests/e2e/` 新建，每条链路一个文件：

| # | 文件 | 链路 |
| - | --- | --- |
| 1 | `auth-register.spec.ts` | register → email-sent → setup-token → 落 onboarding |
| 2 | `auth-login.spec.ts` | login 二步流程 + 错误密码 + 忘记密码 |
| 3 | `auth-reset.spec.ts` | forgot → email-sent → reset → reset-success |
| 4 | `auth-oauth.spec.ts` | mock Google callback → 落 brand/overview |
| 5 | `onboarding.spec.ts` | 选行业 → 创建 project → 落 brand/overview |
| 6 | `brand-overview.spec.ts` | 真实 KPI 渲染 + 时间筛选 |
| 7 | `brand-competitors.spec.ts` | 添加竞品（capacity / debounce / rollback） |
| 8 | `industry-kg.spec.ts` | KG 节点拖拽 + 分类筛选 + URL 同步 |
| 9 | `report-export.spec.ts` | 立即生成报告 → polling → 下载 PDF |
| 10 | `multi-project.spec.ts` | 创建第二个 project + 切换 + URL 持久化 |

测试帐号：用 `/api/auth/dev-seed` 在测前清库 + 建 fixture 用户。
真后端：`docker-compose.preview.yml` 起 backend + worker + Postgres + Redis。

#### B4. Visual Regression

`playwright.config.ts` 新增 `visual` project：

- 截图 3 页 × 3 断点（375 / 768 / 1280）= 9 baseline。
- Page：`/brand/overview`、`/industry/overview`、`/industry/knowledge-graph`。
- `npm run test:visual:update` 更新基线；CI 比对 > 0.1% 像素差即 fail。

#### B5. 可访问性 Lighthouse / axe-core

- Playwright e2e 中每个 page 跑 `axe.analyze()`，无 `serious` / `critical` violation。
- CI 跑 Lighthouse（`@lhci/cli`）目标：a11y ≥ 95，performance ≥ 80（preview 环境）。

#### B6. 契约 / Schema

- `npm run gen:api-types`：CI 重新生成后跑 `git diff --exit-code`，
  drift 即 fail（强制 PR 同步）。
- `frontend/scripts/check-data-contracts.mjs`（已存在 `npm run check:contracts`）
  扩展为校验 fixture JSON 形状符合 `api-types.d.ts` 类型。

#### B7. CI

`frontend/package.json` `npm run ci` 已存在；扩展：

```
ci:harness        # check-harness（已存在）
ci:contracts      # check-contracts（已存在）
ci:selftest       # check-selftest（已存在）
ci:unit           # vitest --run
ci:e2e            # playwright test（在 docker-compose preview 环境跑）
ci:visual         # playwright visual project
ci:lh             # lighthouse-ci
ci                # 全部
```

PR / push 默认跑 `ci:unit + ci:contracts + ci:harness`；
e2e + visual + LH 在 nightly + release branch 跑。

### C. 端到端验收链路（preview 环境手动 smoke）

每次发布前手测以下 7 条链路（也是 Playwright 自动化集合）：

1. **Auth**：`/register` → 邮件预览 URL → `/setup` → 自动登录 → 落 `/onboarding`。
2. **Onboarding**：选择行业 → `POST /v1/projects` → 落 `/brand/overview`。
3. **Brand Overview**：KPI 与 DB `geo_score_daily` 当日数字对得上。
4. **多租户**：另一用户 `curl /v1/projects/<别人 ID>` → 404。
5. **Reports**：`POST /v1/projects/:id/reports` → 60s 内 status=done →
   `GET .../download` 拉到 PDF；CSV 同。
6. **手动采集**：`POST /v1/projects/:id/crawl-requests` → 5min 内
   `crawl_requests.status='done'` + `brand_mentions` 当日有新行。
7. **Lead**：`POST /v1/leads` → admin `/api/admin/users/<id>/actions` 可查到。

### D. 测试数据 / Fixtures 策略

- `backend/tests/fixtures/`：YAML 描述场景（"new-project-empty"、"30d-with-data"、
  "multi-tenant-pair"），`pytest` autouse fixture 在事务里 seed → rollback。
- `frontend/src/__ci_fixtures__/sampleData.ts`：从 `mock.js` 抽取
  最小子集（每实体 ≤ 5 条），仅 Vitest / Storybook 使用，**不打入生产 bundle**。
- E2E：`/api/auth/dev-seed` 端点（已有）+ 新增 `/api/v1/_test/seed-project`
  （仅 `GENPANO_ENVIRONMENT=development|test` 启用）一键造完整 project。

### E. 覆盖率目标

| 层 | 目标 |
| --- | --- |
| Backend service 层 | line ≥ 70%, branch ≥ 60% |
| Backend core/security/errors | 100% |
| Frontend lib + hooks + contexts | line ≥ 80% |
| Frontend pages（4 态组件测试） | 每页至少 4 case |
| E2E 链路 | 7 条 happy path + 关键失败路径 |

CI 报告：`backend/coverage.xml` + `frontend/coverage/lcov.info` 上传到
Codecov / 自建（按团队选择）。

### F. 每 Phase 测试交付物

| Phase | 必交付测试 |
| --- | --- |
| **P** | **`test_prd_links_valid.py`（21 page 的 PRD 锚点全部存在）+ `test_openapi_sync.py`（FastAPI auto schema vs YAML diff = 0 白名单外）+ DATA_MODEL ER 图与 alembic head 一致校验** |
| R | TS 严格编译 0 错；admin 路由迁移前后行为比对（200 endpoint diff=0）；alembic 升降级幂等 |
| 0 | apiClient 单测 + core/security 单测 + alembic 升降级测试 |
| 1 | `/v1/projects` CRUD 集成 + 多租户 + ProjectContext 单测 + onboarding e2e |
| 2 | 9 子页：每页 4 态 RTL + 后端 6 case 集成 + brand-overview e2e |
| 3 | industry × 4 同上 + kg e2e |
| **A** | analyzer 8 模块单测覆盖 ≥ 70%；金标准确率：归因 5 类 ≥ 95% / page_type ≥ 90% / sentiment 升级 ≥ 80%；A11 回填幂等；A4/A6 admin CRUD 集成；A7/A8 cross-brand / weekly cron 集成 |
| **K** | K1 5 张 kg_* 表迁移幂等；K2 种子脚本 idempotent；K3 admin CRUD 7 个子模块各 6 case 集成；K4 category 树 UPSERT 幂等；K5 关系抽取金标 30 case ≥ 90%；K6 端点 6 case + KG 1000 节点性能 < 1s；K7 RTL 4 态 + KG e2e 节点拖拽 / 分类筛选 |
| **D** | **25+ 条规则各 happy + 不触发 + 边界（≈ 75 case）；evaluator 去重 / 升级 / 降级；causal LLM mock + 缓存命中；anchor question fill；benchmark 计算；D8 alert 联动；GET /v1/projects/:id/diagnostics 6 case + diag 详情 RTL** |
| **RP** | **10 section × 4 reportType happy + 3 variant 切换；narrative LLM mock + zh/en fallback；4 渲染器（PDF/MD/JSON/CSV）输出 schema；share token 生命周期（创建 / 访问 / 过期 410）；cron 调度；report-export e2e；lead_diagnostic 4 layer 独立 view** |
| **M** | **API key 生成/列表/撤销/过期；rate limit 60/min/key；9 tools 各 6 case + 3 resources read；MCP 端到端用 Claude CLI 实测；401 → MCP_AUTH_REQUIRED；多租户（org_id）单测全过；scope 限制（read_only key 不能调 generate_report）** |
| **N** | **3 触发器 happy + edge（diagnostic / monitoring outage / citation mismatch）；邮件模板渲染（zh / en）；quiet hours 计算；alert rule CRUD 多租户；顶栏铃铛 RTL + 角标实时；Settings 3 toggle 持久化端到端** |
| **E** | **8 种 exportType 各能下载 CSV；超配额 429；submission 状态机（pending → approved → KG 入库）；simulator 公式 + 行业参数表；MCP simulator tool 与 REST endpoint 输出 byte-equal** |
| **O** | **9 个 admin 模块每端点 admin-only（非 admin → 401）+ 6 case 集成；audit_decorator 自动注入测试（每高风险 mutation 必审）；engine_health 聚合 cron；cost_events 6 source 写入点全覆盖；预算超限触发 P0 alert；MCP 配额自动暂停；comms 邮件批发送；admin 高风险 mutation 必审名单单测** |
| 4 | crawl/leads happy + Celery 任务单测 + crawl 日上限 429 |
| 5 | 多租户全套 + perf baseline + visual snapshot + a11y + Lighthouse |

每个 PR 必须保持 CI 绿；不允许"先合后修"。

---

## 单 Session 切片建议

- **Session 1**：Phase 0 + Phase 1（≈ 1 周）— 收口 + Project CRUD + Onboarding 联调，
  不碰 Brand/Industry 业务 endpoint。交付 Auth + Onboarding e2e。
- **Session 2**：Brand Overview 样板（≈ 0.5 周）— 第一个完整 service + hook + 4 态 +
  e2e，定型模板供 Phase 2 后续 8 页复制。
- **Session 3+**：每页/每模块独立 PR；测试用例按 §F 表对照交付。

---

## Verification（最终发布前）

- 上述 7 条 e2e 链路全绿。
- `backend/make ci`、`frontend/npm run ci` 全绿。
- `npm run test:e2e` + `test:visual` + Lighthouse a11y ≥ 95、performance ≥ 80。
- 多租户安全套件无失败。
- `models_drift_check` + `openapi_sync` 无飘移。
- p95 端点 < 200ms；KG 1000 节点 ≥ 30 fps；报告 30 天 < 60s。
- 安全：401 → `/login?redirect=`；403 → toast；越权 → 404；
  rate limit 登录/注册 10/min/IP，通用 60/min/user；HTTPS 在 live test env 强制。

---

*文档维护：GenPano App 端研发组（FE + BE 联合）*
*最近更新：2026-05-04*
*下次评审：每完成一个 Phase 后回填进度*
