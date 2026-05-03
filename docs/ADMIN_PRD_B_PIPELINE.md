# ADMIN PRD §B — 数据管道 (Planner · Tracker · Analyzer)

> **状态**: v2 · 2026-04-19 · 全面重构。v1 的 13 个子页 (B1-B13) 按 data pipeline 生命周期重组为 **三大模块**。
>
> - **Planner** — "采什么、怎么采" — Topic → Prompt → Query 生成管线 + 资源调度
> - **Tracker** — "每次执行的全记录" — Query × Engine × Attempt 级追踪 + Debug + 重试
> - **Analyzer** — "采集质量如何" — 每条 Response 的指标分数 + 人工质检 + 趋势
>
> **配套**: `design/prototype-admin.html`

---

## 0. 重组动机

v1 的 13 个子页（引擎健康、账号池、代理池、重试中心、Prompt 模板、Response QA、Trace、变更审批、调度、Segment/Profile、生成管线……）是按 **运维资源** 分类的 — 适合基础设施工程师，但不适合需要"看一条 Query 从规划到结果全链路"的运营。

v2 按 **data pipeline 的生命周期** 重组：

```
┌─────────┐     ┌─────────┐     ┌──────────┐
│ Planner │ ──► │ Tracker │ ──► │ Analyzer │
│ 规划    │     │ 执行追踪│     │ 结果分析 │
└─────────┘     └─────────┘     └──────────┘
  采什么          每次怎么跑的      跑完质量如何
  怎么采          出错在哪          分数多少
  用什么资源      一键 debug        趋势如何
```

核心原则不变：**Detect → Locate → Decide → Act → Audit**。

### v1 → v2 映射表

| v1 子页 | v2 归属 | 说明 |
|---------|--------|------|
| B1 Pipeline 全景 | **Dashboard** (跨三模块) | 拆为 Planner/Tracker/Analyzer 各自的 summary，不再独立页 |
| B2 引擎健康 | Tracker §2.3 | 引擎维度的执行追踪 |
| B3 任务队列 | Tracker §2.2 | 合入 Attempt 列表 |
| B4 账号池 | Planner §1.5 | 采集资源管理 |
| B5 代理池 | Planner §1.5 | 采集资源管理 |
| B6 重试中心 | Tracker §2.2 | 失败 Attempt 的重试操作 |
| B7 Prompt 模板 | Planner §1.3 | Prompt 版本 + A/B |
| B8 Response QA | Analyzer §3.2 | 人工质检 |
| B9 Trace & Lineage | Tracker §2.4 | Query 全链路追溯 |
| B10 变更审批 | **横切** §4.3 | 跨模块的审批中心 |
| B11 调度 & Planner | Planner §1.1 | Pipeline 调度总控 |
| B12 Segment/Profile | Planner §1.4 | 画像管理 |
| B13 生成管线 | Planner §1.2 | Topic→Prompt→Query 生成 |

---

## 0.1 运营场景驱动设计（failure modes）

| # | 场景 | Primary Module | 动线 |
|---|------|---------------|------|
| F1 | 豆包账号池批量被风控 | Tracker → Planner (资源) | Tracker 看到 COOKIE_EXPIRED 激增 → Planner 账号池冻结 + 补号 |
| F2 | 代理出口 IP 被识别 | Tracker → Planner (资源) | Tracker 看到 CF_BLOCKED → Planner 代理池暂停区域 |
| F3 | Parser 解析在某类 Prompt 集中失败 | Tracker → Planner (Prompt) | Tracker 失败样本 → Planner Prompt 模板回滚 |
| F4 | 用户投诉"品牌提及率不对" | Tracker (Trace) → Analyzer | Tracker 链路追溯 → Analyzer 看分数 |
| F5 | Planner 故障，Topic 0 增量 | Planner | Planner 调度面板直接定位 |
| F6 | 单日成本异常飙升 | Tracker → Planner | Tracker 看执行量 → Planner 调度暂停 |
| F7 | 新 Prompt 模板灰度对比 | Planner → Analyzer | Planner A/B 配置 → Analyzer 质量对比 |
| F8 | 凌晨跑批失败需批量重跑 | Tracker | Tracker 批量选择失败 Attempt → 重试 |
| F9 | Response 有明显幻觉 | Analyzer → Tracker | Analyzer QA 标注 → Tracker 找原始 HAR |
| F10 | 引擎情感分类系统性偏差 | Analyzer | Analyzer 质量面板引擎对比 |
| F11 | 新 Segment 采样不均 | Planner → Analyzer | Planner 权重调整 → Analyzer 采样分布验证 |
| F12 | Query 生成覆盖度不足 | Planner | Planner 生成管线覆盖度检查 |

---

## 0.2 侧栏导航结构

```
数据管道
├── 📊 管道总览          /admin/pipeline/dashboard       (三模块 KPI 一屏)
├── ── Planner ──
│   ├── 📅 采集调度      /admin/pipeline/planner/scheduler
│   ├── 🔗 生成管线（单页，三层 Tab）      /admin/pipeline/planner/generation
│   ├── 📝 Prompt 模板   /admin/pipeline/planner/prompts
│   ├── 👥 Segment       /admin/planner-profiles
│   └── 🔑 采集资源      /admin/pipeline/planner/resources    (账号池 + 代理池)
├── ── Tracker ──
│   ├── 📋 执行追踪      /admin/pipeline/tracker/attempts     (核心: 每次 attempt)
│   ├── ⚡ 引擎健康      /admin/pipeline/tracker/engines
│   └── 🔍 链路追溯      /admin/pipeline/tracker/trace
├── ── Analyzer ──
│   ├── 📈 质量分析      /admin/pipeline/analyzer/quality
│   └── ✅ 人工质检      /admin/pipeline/analyzer/qa
└── 🛡️ 变更审批          /admin/pipeline/changes              (横切)
```

---

# 1. Planner — 规划模块

> **核心问题**: "今天采什么、怎么采、用什么资源"

Planner 覆盖 Pipeline 的上游：从知识图谱到 Topic → Prompt → Query 的完整生成链路，以及执行这些 Query 所需的账号、代理、Segment/Profile 等资源的管理。

## 1.1 采集调度总控 `/admin/pipeline/planner/scheduler`

**目的**。每日全量采集是 GENPANO 的心脏。本页一眼看清当日进度、Planner 状态、应急控制。

**IA**:

```
┌──────────────────────────────────────────────────────────────┐
│ [采集中 ●]  全局开关                        [立即运行 Planner] │
├──────────────────────────────────────────────────────────────┤
│ 今日批次进度                                                  │
│ ████████████████████░░░░ 78%   完成 31200 / 失败 420 / 待处理 8380 │
│                                                               │
│ 四层漏斗:  Topic 1560 → Prompt 8420 → Query 45820 → Response 31620  │
│                        (流失率: 0% → 0.1% → 0.02% → 31%)           │
│ KPI: 总成本预估 ¥ 2,840  |  剩余 ETA 2h 15m  |  最后更新 14:05      │
├──────────────────────────────────────────────────────────────┤
│ Planner 状态                                                  │
│ 最后运行: 06:00 ✅  |  Topics: 1560 (品类 42% ✅ / 品牌 35% / 产品 23%)  │
│ 来源: LLM 初始化 68% / Response 挖掘 32%                        │
├──────────────────────────────────────────────────────────────┤
│ 历史批次 (近 30 天)                                            │
│ 日期     | 状态   | 总量    | 成功率 | 成本   | 耗时          │
│ 04-19    | ● 运行中 | 40,000 | 78%   | ¥2.8k | 进行中        │
│ 04-18    | ✅ 完成 | 41,589 | 92%   | ¥3.1k | 4h 12m        │
│ ...                                                           │
└──────────────────────────────────────────────────────────────┘
```

**交互**:
- **全局采集开关** — 暂停 / 恢复。暂停 → confirm + reason → 新 Query 不分配，running 继续 → 审计
- **立即运行 Planner** — Modal: Full / By Industry / By Brand scope → 后端 enqueue → 进度条 → 完毕后刷新
- **漏斗层点击** → 跳转 Planner 生成管线对应层
- **历史批次行点击** → 抽屉显示该批次四层漏斗 breakdown

**边界**:
- Planner 2h 无增量 Topic → P0 告警 PIPE-04
- 当日 failed > 30% → P1 告警 PIPE-05 + 自动暂停新采集
- 品类 Topic 占比 < 40% → 橙色告警

**数据模型**:
```sql
CREATE TABLE pipeline_batches (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  batch_date DATE NOT NULL,
  status enum('pending','running','completed','partial','failed') NOT NULL,
  total_queries INT NOT NULL,
  completed INT DEFAULT 0,
  failed INT DEFAULT 0,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ON pipeline_batches (batch_date DESC);

CREATE TABLE planner_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  triggered_by enum('auto','manual') NOT NULL,
  scope enum('full','industry','brand') NOT NULL,
  industry_id UUID,
  brand_id UUID,
  topics_generated INT DEFAULT 0,
  category_topic_pct NUMERIC,
  other_topic_pct NUMERIC,
  topics_from_extraction INT DEFAULT 0,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  status enum('pending','running','completed','failed') NOT NULL DEFAULT 'pending',
  error_message TEXT,
  created_by UUID REFERENCES admin_users(id),
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE pipeline_global_pause (
  id SERIAL PRIMARY KEY,
  is_paused BOOLEAN DEFAULT FALSE,
  paused_by UUID REFERENCES admin_users(id),
  paused_at TIMESTAMPTZ,
  paused_reason TEXT,
  resumed_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ DEFAULT now()
);
```

**权限**: 运行 Planner / 暂停恢复 → super_admin + 理由 + 审计。

---

## 1.2 生成管线 `/admin/pipeline/planner/generation`

**目的**。Topic → Prompt → Query 三层生成的"配置、数量把控、质量门禁、候选审核和手动触发"。本页面向运营操作者，不在主视图展示内部生成路径、run artifact、候选表名或研发调试字段；这些信息如需保留，应进入某次运行记录的 Debug 抽屉。

**IA — 三层 Tab**:

### Tab 1: Topic 生成

- **运行配置**: 选择 Industry / Category 后，直接选择本次要生成 Topic 的 Brand 列表；此处不出现 competitor scope，竞品只作为 KG 关系和下游分析维度。
- **数量把控**: 每品牌 Topic 上限、总 Topic 上限、缺口优先级、超出上限策略。页面实时显示预计生成量。
- **质量门禁**: 发布覆盖、待审核、低置信、无 Prompt。主页面用运营语言解释指标，不展示 SQL 字段或阈值表达式；精确字段口径进入 Debug 抽屉。
- **按钮流程**:
  - "覆盖度检查" → 页面内展开覆盖缺口面板，列出品牌、覆盖率、缺口类型和优先级。
  - "生成 Topic" → 页面内展开生成任务面板，展示配置检查、缺口读取、候选生成、进入审核的状态。
  - "查看待处理" → 页面内展开候选审核列表，可通过 / 拒绝单条 Topic。
- **CTA 规则**: 主页面只保留一个主要"生成 Topic"入口；流程面板内的按钮只作为当前流程下一步。
- **列表与详情**: Topic KPI、筛选、Topic 列表、审核详情保留在主工作台。

### Tab 2: Prompt 生成

- **矩阵配置**: 直接选择本次要展开 Prompt 的 Topic 集合，不能用小型 checkbox 卡片承载。Topic 选择器必须支持搜索、品牌筛选、覆盖状态筛选、分页、当前页选择、全部匹配选择、清空当前页、清空全部，并在页面上持续显示已选数量和已选集合摘要；后端实现时按服务端分页返回 Topic，不一次性加载全量。
- **数量把控**: Intent 数、语言数、每 Topic 上限、总 Prompt 上限、超出上限策略。预计生成量按 `selected_topics × min(intent × language, per_topic_cap)` 计算。
- **质量门禁**: 意图覆盖、模板状态、品牌纯净、相似重复。主页面只展示运营能理解的解释，例如"每个 Topic 至少 2 类意图"、"品类题不混入品牌名"；后台字段和相似度阈值不直接露出。
- **按钮流程**:
  - "缺口列表" → 页面内展开 Topic × Intent / Language 缺口表。
  - "生成 Prompt" → 页面内展开生成任务面板，展示 Topic 校验、模板匹配、候选生成、进入审核。
  - "审查候选" → 页面内展开候选 Prompt 审核表，可通过 / 拒绝。
- **CTA 规则**: 主页面只保留一个主要"生成 Prompt"入口；统计/KPI 区不再重复放同名按钮。
- **运营视图**: 总 Prompt、覆盖率、无 Prompt Topic、Intent 分布、语言分布、Prompt 内容列表保留。
### Tab 3: Query 组装 / Query Pool

- **组装配置**: Query Pool 选择 Prompt 行，并配置 Segment/Profile 采样、`desired_engine_policy`、预算上限、入队窗口、去重策略和优先级。它不选择具体引擎数量，也不暴露每引擎执行控制。
- **数量控制**: 候选量为 `selected_prompts x profiles_per_prompt`，并受 `max_candidates` 上限保护。引擎展开、每引擎配额、并发、限速、账号/代理分配和重试都属于 Scheduler。
- **预检状态**: 页面展示「候选就绪」「渲染通过率」「Segment 覆盖」「Profile 覆盖」「重复待审」「调度接收」。这些指标必须来自 `POST /api/admin/query-pool/preflight` 或 `POST /api/admin/query-pool/assemble` 返回的 `preflight_summary`；未运行时显示空态，不允许静态 mock 数值。引擎成功率、按 Segment 的执行成功率、账号水位、代理失败率属于 Scheduler/Tracker。
- **按钮流程**:
  - 「预估成本」打开候选级粗估，并明确具体引擎成本延后到 Scheduler 估算。
  - 「组装 Query」展示 Prompt 校验、Segment/Profile 采样、Query 候选渲染和调度接收。
  - 「预检报告」展示模板变量、重复候选、Segment 权重和调度接收检查。
- **CTA 规则**: 主页面只保留一个主要「组装 Query」入口；KPI 区不重复放同名 CTA。
- **运营视图**: 保留「候选就绪」「渲染通过率」「Segment 覆盖」「Profile 覆盖」「重复待审」「调度接收」和「Query 候选列表」。queued/running/completed/failed 执行指标和每引擎暂停/恢复控制移动到 Scheduler/Tracker。
- **候选列表规模**: Query 候选列表必须支持 100M to 1B+ rows。它只渲染当前服务端游标窗口，使用 server-side cursor/keyset pagination，并在服务端运行搜索、状态、Segment、Profile 过滤。UI 不能加载全部候选、不能 deep-offset paginate、不能在浏览器内存里保留完整 `queryDetailList`。总数可以是 approximate。

**数据模型**:
Topic Plan 复用 §1.1 `planner_runs`，需记录 `industry_id`、`category_id`、`brand_ids`、`max_per_brand`、`max_topics`、`gap_priority`、`overflow_policy`、`topics_generated`、`pending_candidates`、`coverage_snapshot`。

```sql
CREATE TABLE prompt_generation_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  industry_id UUID,
  category_id UUID,
  topic_ids UUID[] NOT NULL,
  intent_count INT NOT NULL DEFAULT 2,
  language_count INT NOT NULL DEFAULT 2,
  max_per_topic INT NOT NULL DEFAULT 4,
  max_prompts INT NOT NULL DEFAULT 8000,
  overflow_policy TEXT NOT NULL DEFAULT 'split',
  intent_filter TEXT[],
  language_filter TEXT[],
  prompts_estimated INT DEFAULT 0,
  prompts_generated INT DEFAULT 0,
  prompts_failed INT DEFAULT 0,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  status enum('pending','running','completed','failed') NOT NULL DEFAULT 'pending',
  error_summary TEXT,
  created_by UUID REFERENCES admin_users(id),
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE query_generation_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  industry_id UUID,
  category_id UUID,
  prompt_ids UUID[] NOT NULL,
  segment_ids_selected UUID[],
  profiles_per_prompt INT NOT NULL DEFAULT 3,
  desired_engine_policy TEXT NOT NULL DEFAULT 'inherit',
  engine_panel_id TEXT,
  max_candidates INT NOT NULL DEFAULT 12000,
  overflow_policy TEXT NOT NULL DEFAULT 'split',
  candidates_estimated INT DEFAULT 0,
  candidates_assembled INT DEFAULT 0,
  estimated_cost NUMERIC,
  preflight_summary JSONB,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  status enum('pending','running','completed','failed') NOT NULL DEFAULT 'pending',
  created_by UUID REFERENCES admin_users(id),
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE query_generation_candidates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID NOT NULL REFERENCES query_generation_runs(id),
  candidate_seq BIGINT NOT NULL,
  prompt_id UUID NOT NULL,
  segment_id UUID,
  profile_id UUID,
  rendered_query TEXT NOT NULL,
  render_hash TEXT NOT NULL,
  candidate_status TEXT NOT NULL DEFAULT 'candidate',
  scheduler_intake_batch_id UUID,
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (run_id, candidate_seq)
);

CREATE INDEX ON prompt_generation_runs (created_at DESC);
CREATE INDEX ON query_generation_runs (created_at DESC);
CREATE INDEX ON query_generation_candidates (run_id, candidate_seq);
CREATE INDEX ON query_generation_candidates (run_id, candidate_status, candidate_seq);
CREATE INDEX ON query_generation_candidates (run_id, segment_id, profile_id, candidate_seq);
```

**Query Candidate pagination contract**:
- `POST /api/admin/query-pool/preflight` 使用同一组装逻辑做 dry-run，返回候选预估、预检摘要和 Scheduler Intake 状态，不写入 run/candidate。
- `POST /api/admin/query-pool/assemble` 创建 `query_generation_runs`，按 Segment/Profile 权重采样并写入 `query_generation_candidates`。返回 `{ success, run }`，其中 `run.id` 作为后续候选列表的 `run_id`。
- `GET /api/admin/query-pool/runs` 和 `GET /api/admin/query-pool/runs/:id` 读取最近组装运行与单次运行详情。
- Admin 页面调用 `GET /api/admin/query-pool/candidates?run_id=&status=&segment_id=&profile_id=&q=&limit=&cursor=&direction=`，返回 `{ success, rows, next_cursor, prev_cursor, approx_total }`。
- `POST /api/admin/query-pool/candidates/:id/review` 与 `POST /api/admin/query-pool/candidates/bulk-review` 将候选状态更新为 `candidate | review | ready`，只改变候选审核状态，不创建 Scheduler dispatch job。
- 产品网关兼容 `GET /admin/api/v1/pipeline/query-pool/candidates?run_id=&status=&segment_id=&profile_id=&q=&limit=&cursor=&direction=`，返回同一结构。
- Cursor is keyset-based, opaque to the client, and ordered by `(run_id, candidate_seq)` or an equivalent sharded monotonic key. Do not use offset pagination for large runs.
- Candidate storage should be partitioned by `run_id` or time bucket plus project/industry when needed; cold partitions can move to cheaper storage while the current run remains queryable.
- Search can use a bounded text index over `render_hash`, prompt id, Segment/Profile ids, and rendered text snippets; exact full corpus export belongs to offline jobs, not the Admin list.

**边界**:
- 某 Intent 的 Prompt 生成失败率 > 20% → 自动标 warning
- Prompt / Query 预计生成量超过上限 → 按 overflow_policy 自动拆批或进入审批
- Query 组装预估超过 `max_candidates` → 后端按 `overflow_policy` 自动拆批或进入审批；列表仍通过 cursor 读取当前窗口
- Prompt 版本已 deactivated → 新 Query 不绑定
- 主页面禁止展示 `*_run`、`*_candidates`、`*_release_set`、`rendered_queries` 等内部对象名；需要排障时从运行记录进入 Debug 抽屉

---

## 1.3 Prompt 模板 `/admin/pipeline/planner/prompts`

**目的**。Prompt 是管线里唯一**可由运营安全修改**的要素。需要灰度 + 对比 + 审批。

**IA**:
1. 模板列表: template_id / name / intent / language / engines / active_version / status(draft|active|archived)
2. 版本抽屉: 选中模板 → 历史 version + diff（`monaco-diff-viewer`）+ 创建人 + 响应统计
3. 新版本编辑器: Monaco + 变量 auto-complete (`{{brand_name}}` / `{{industry}}` / `{{competitor_ids}}`)
4. **灰度发布**: 全量 / A/B 5% / 限行业 / 限引擎。发布后 24h 观察期 → 升全量 / 回滚
5. **A/B 面板**: 覆盖率 / 解析成功率 / 平均 token / 成本 / precision@10 + z-test 显著性

**数据模型**:
```sql
CREATE TABLE prompt_templates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  intent TEXT NOT NULL,
  language TEXT NOT NULL,
  applies_to_engines TEXT[] NOT NULL,
  active_version_id UUID,
  status TEXT NOT NULL DEFAULT 'draft',
  created_by UUID REFERENCES admin_users(id),
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE prompt_template_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  template_id UUID NOT NULL REFERENCES prompt_templates(id),
  version INT NOT NULL,
  body TEXT NOT NULL,
  variables JSONB NOT NULL,
  rollout_plan JSONB,
  activated_at TIMESTAMPTZ,
  deactivated_at TIMESTAMPTZ,
  created_by UUID REFERENCES admin_users(id),
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(template_id, version)
);

CREATE TABLE prompt_ab_experiments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  template_id UUID NOT NULL,
  control_version_id UUID NOT NULL,
  treatment_version_id UUID NOT NULL,
  traffic_split NUMERIC NOT NULL,
  started_at TIMESTAMPTZ NOT NULL,
  ended_at TIMESTAMPTZ,
  conclusion TEXT
);
```

**边界**:
- 激活新版本前，强制 "回归 Prompt" 跑一组固定 brand+industry 组合，diff > 30% 需强制 confirm
- A/B 升全量按钮仅在达显著性后 enable
- Prompt 正文不可导出（防模板外泄）
- 所有 version 操作 → super_admin + 理由 + 审计，走变更审批

---

## 1.4 Segment & Profile `/admin/planner-profiles`

**目的**。Segment 是 Query 采样的人群分层，Profile 是某个 Segment 下的具体用户画像。Admin 操作者需要先管理品牌/行业对应的 Segment，再进入单个 Segment 管理 Profile 池，供 Query Pool 在 `Prompt x Segment x Profile candidate` 组装时采样。产品 UI 统一使用 **Segment**，不再对运营展示 `ProfileGroup`。

**当前 Admin 前端 IA**:
1. **Segment 列表页**:
   - 顶部仅在外层列表页展示 Segment 概览: Segment 数、Profile 总数、active Profile 数、当前选中 Profile 数。
   - 操作区: `导入 Segment`、`LLM 生成 Segment`、`手动新建`。
   - Segment 搜索: 按 Segment 名称、行业、状态、备注搜索。
   - Segment 表格: ID / Segment 名称与状态 / 行业 / Profile 数与 active 数 / 采样权重 / 采样范围 / 操作。
   - 点击 Segment 行或 `Profile` 操作按钮，进入该 Segment 的 Profile 子页。
2. **LLM 生成 Segment**:
   - 入口在 Segment 列表页。
   - 输入: 品牌、行业、生成数量、默认状态、品牌定位/产品线、覆盖目标、约束。
   - 输出: Segment 草稿列表，含 ID、名称、状态、权重、年龄段、收入、区域、采样率、说明。
   - 操作者确认后将草稿加入 Segment 列表；新增 Segment 默认创建空 Profile 池。
3. **Segment 手动 CRUD / 导入**:
   - 手动新建/编辑字段: ID、名称、行业、状态、权重、年龄段、收入、区域、采样率、备注。
   - 删除 Segment 时必须同时处理其 Profile 池；正式后端实现必须软删除，不能破坏历史 Query lineage。
   - 导入支持 CSV/JSON 粘贴，字段需兼容 `id,name,industry,status,weight,age_range,income,regions,sampling_rate,note`。
4. **Profile 子页**:
   - 子页顶部只保留一条紧凑上下文栏: 返回 Segment、当前 Segment ID、状态、Profile 数、active 数、Segment 名称和说明。
   - 子页不再重复展示外层 Segment banner 或大型 Segment 指标卡，主体应直接是 Profile 列表。
   - 操作区: `LLM 生成 Profile`、`导出`、`导入`、`新建 Profile`。
   - Profile 搜索: 仅搜索当前 Segment 下的 Profile。
   - Profile 表格: ID / Profile 名称与状态 / 画像 / 需求 / 权重 / 操作。
5. **LLM 生成 Profile**:
   - 入口在单个 Segment 的 Profile 子页。
   - 输入: 品牌、数量、生成目标、约束。
   - 生成结果直接进入当前 Segment 的 Profile 池，初始状态可为 draft。
   - 注意: Profile 子页不提供 `LLM 生成 Query` 按钮，Query 生成归 Query Pool 页面负责。
6. **Profile CRUD / 导入 / 导出**:
   - 手动新建/编辑字段: ID、名称、画像、需求、权重、状态。
   - 删除 Profile 在原型中可直接移除；正式后端实现需保留历史引用。
   - 导入支持当前 Segment 的 Profile CSV/JSON。
   - 导出当前 Segment 的 Profile CSV，字段至少包括 `id,segment_id,name,demographic,need,weight,status`。

**海量数据要求**:
- Segment 列表与 Profile 列表正式实现必须使用服务端搜索、筛选、排序和分页；前端不可一次性加载全量。
- 默认分页建议: Segment 每页 50；Profile 每页 100。需要支持当前页选择、全部匹配选择、清空当前页、清空全部时，选择状态必须以服务端过滤条件表达，不依赖浏览器内全量数据。
- 搜索输入需要 debounce；分页、搜索、状态筛选应进入 URL query，便于刷新和分享。
- Profile 子页应保持紧凑布局，保证表格可视区域优先，避免 banner/卡片挤压列表。

**术语与兼容**:
- UI、文案、路由统一叫 Segment；不再出现 `ProfileGroup`。
- 如果后端沿用旧表 `profile_groups`，需要在 API 层映射为 Segment，不把旧术语泄漏到前端。
- App/Analyzer 中已有 `profileGroup` query 参数可作为兼容字段保留，但 Admin 新接口应优先暴露 `segment_id` / `segment_ids`。

**数据模型**:
```sql
CREATE TABLE segments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code TEXT UNIQUE,
  name TEXT NOT NULL,
  industry_id UUID REFERENCES kg_industries(id),
  status TEXT NOT NULL DEFAULT 'draft',
  weight NUMERIC NOT NULL DEFAULT 0,
  age_range TEXT,
  income TEXT,
  regions TEXT,
  sampling_rate TEXT,
  note TEXT,
  is_deleted BOOLEAN DEFAULT FALSE,
  created_by UUID REFERENCES admin_users(id),
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_by UUID REFERENCES admin_users(id),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE profiles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  segment_id UUID NOT NULL REFERENCES segments(id),
  code TEXT,
  name TEXT NOT NULL,
  demographic TEXT,
  need TEXT,
  weight NUMERIC NOT NULL DEFAULT 1.0,
  status TEXT NOT NULL DEFAULT 'draft',
  persona_json JSONB NOT NULL DEFAULT '{}',
  is_deleted BOOLEAN DEFAULT FALSE,
  created_by UUID REFERENCES admin_users(id),
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_by UUID REFERENCES admin_users(id),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE profile_generation_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  segment_id UUID NOT NULL REFERENCES segments(id),
  llm_model TEXT NOT NULL,
  prompt_used TEXT,
  profiles_generated INT DEFAULT 0,
  profiles_skipped INT DEFAULT 0,
  tokens_used INT DEFAULT 0,
  estimated_cost NUMERIC,
  created_by UUID REFERENCES admin_users(id),
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE segment_generation_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID,
  brand_name TEXT,
  industry_id UUID,
  llm_model TEXT NOT NULL,
  prompt_used TEXT,
  segments_generated INT DEFAULT 0,
  segments_skipped INT DEFAULT 0,
  tokens_used INT DEFAULT 0,
  estimated_cost NUMERIC,
  created_by UUID REFERENCES admin_users(id),
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX ON segments (industry_id, status);
CREATE INDEX ON profiles (segment_id, status);
```

**API 方向**:
- `GET /admin/api/segments?page=&per_page=&q=&status=&industry_id=`
- `POST /admin/api/segments`
- `PUT /admin/api/segments/:id`
- `DELETE /admin/api/segments/:id` soft delete
- `POST /admin/api/segments/import`
- `POST /admin/api/segments/generate`
- `GET /admin/api/segments/:id/profiles?page=&per_page=&q=&status=`
- `POST /admin/api/segments/:id/profiles`
- `PUT /admin/api/segments/:id/profiles/:profile_id`
- `DELETE /admin/api/segments/:id/profiles/:profile_id` soft delete
- `POST /admin/api/segments/:id/profiles/import`
- `GET /admin/api/segments/:id/profiles/export`
- `POST /admin/api/segments/:id/profiles/generate`

**边界**:
- 30 天采样 < threshold → PIPE-12 告警。
- 删除 Segment/Profile 只做 soft delete，不破坏已有 Query lineage。
- Segment 权重全为 0 时，Query Pool 组装必须阻断并提示。
- LLM 生成 Segment/Profile 必须保存生成参数、prompt、模型、成本和操作者。
- LLM 生成结果进入草稿态，正式入池前允许人工编辑。
- Query 组装只消费 active Segment/Profile。

---

## 1.5 采集资源 `/admin/pipeline/planner/resources`

**目的**。账号和代理是 Pipeline 执行的基础资源。合并为一个页面，两个 Tab。

### Tab 1: 账号池

管理 3 个引擎的账号生命周期：

**状态机**:
```
pending_register → registered → warming → active → cooldown → frozen
                                   ↓          ↑
                                banned ←──────┘
```

**IA**:
1. 引擎水位摘要: ChatGPT/豆包/DeepSeek 各 active/total + 健康均分 + 预计耗尽时间
2. 账号列表: ID / 引擎 / 状态 / 健康分[0-100] / 标签 / 上次使用 / 成功率 / 操作
3. 轮换策略配置: 每引擎的轮换间隔 / 同时使用上限 / 冷却时间（可编辑，走变更审批）
4. 自动退役规则: 连续失败阈值 / cooldown 级联 / 启用开关 + "影响预览"
5. "导入 JSON" 按钮: 粘贴 cookie → 验证可用性 → 入库（批量支持，max 1000）

**数据模型**:
```sql
CREATE TABLE account_tags (
  id SERIAL PRIMARY KEY,
  account_id UUID NOT NULL REFERENCES accounts(id),
  tag_name TEXT NOT NULL,
  tagged_at TIMESTAMPTZ DEFAULT now(),
  tagged_by UUID REFERENCES admin_users(id),
  UNIQUE(account_id, tag_name)
);

CREATE TABLE account_retirement_rules (
  id SERIAL PRIMARY KEY,
  engine TEXT NOT NULL,
  consecutive_failures_threshold INT NOT NULL DEFAULT 3,
  cooldown_cascade_count INT NOT NULL DEFAULT 3,
  is_enabled BOOLEAN DEFAULT TRUE,
  updated_by UUID REFERENCES admin_users(id),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(engine)
);

CREATE TABLE account_execution_stats (
  id BIGSERIAL PRIMARY KEY,
  account_id UUID NOT NULL REFERENCES accounts(id),
  query_id UUID NOT NULL,
  execution_at TIMESTAMPTZ DEFAULT now(),
  status enum('success','failed','captcha','timeout','other') NOT NULL,
  error_type TEXT,
  response_time_ms INT
);
CREATE INDEX ON account_execution_stats (account_id, execution_at DESC);

CREATE MATERIALIZED VIEW account_health_score AS
SELECT
  a.id AS account_id,
  a.engine,
  ROUND(
    100.0 * SUM(CASE WHEN s.status = 'success' THEN 1 ELSE 0 END)::NUMERIC
    / GREATEST(COUNT(*), 1), 0
  )::INT AS health_score
FROM accounts a
LEFT JOIN LATERAL (
  SELECT status FROM account_execution_stats
  WHERE account_id = a.id ORDER BY execution_at DESC LIMIT 50
) s ON TRUE
GROUP BY a.id, a.engine;
```

**边界**:
- Cookie / Session 字段 pgcrypto + KMS 加密，UI 只显示 masked hash
- 批量导入 max 10MB / 1000 条，每行独立验证（`/whoami`）
- 轮换策略修改需 0 running query 该引擎，否则后端返回 409
- 健康分 < 60 自动标红 + `unhealthy` 标签

### Tab 2: 代理池 (Ninja Clash)

**IA**:
1. 订阅配置: URL / 状态 / 最大并发 / 已用并发 / "立即刷新"
2. 节点聚合: 按区域分组 — 节点数 / 在线数 / p95 延迟 / 暂停开关
3. 节点详情抽屉: IP / 延迟 / 最后使用 / 黑名单状态

**数据模型**:
```sql
CREATE TABLE proxy_subscriptions (
  id SERIAL PRIMARY KEY,
  provider TEXT NOT NULL,
  subscription_url TEXT NOT NULL,    -- encrypted
  status enum('valid','expired','invalid') NOT NULL,
  last_sync_at TIMESTAMPTZ,
  last_node_count INT,
  max_concurrent_connections INT,
  used_connections INT,
  updated_by UUID REFERENCES admin_users(id),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE proxy_nodes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  subscription_id INT REFERENCES proxy_subscriptions(id),
  ip_address INET NOT NULL,
  region TEXT NOT NULL,
  protocol TEXT,
  latency_ms INT,
  is_online BOOLEAN DEFAULT TRUE,
  last_check_at TIMESTAMPTZ,
  last_failure_at TIMESTAMPTZ,
  failure_reason TEXT,
  is_region_paused BOOLEAN DEFAULT FALSE,
  synced_at TIMESTAMPTZ
);
```

**边界**:
- 订阅链接失效 → P0 PIPE-11 + 禁止新 Query
- 区域节点 < 3 → P1 PIPE-03
- 国内引擎禁止分配代理

**权限**: 所有资源变更 → super_admin + 理由 + 审计。敏感操作走变更审批。

---

# 2. Tracker — 执行追踪模块

> **核心问题**: "每条 Query 的每次执行发生了什么"

Tracker 是本次重构的**最大新增**。v1 将执行细节散落在队列、重试中心、引擎健康等多个页面。v2 将它们统一为一个以 **Attempt（执行尝试）** 为核心单元的追踪系统。

**核心数据实体 — `query_execution_attempts`**:

一条 Query 会发送给多个引擎（ChatGPT / 豆包 / DeepSeek），每个引擎可能重试多次。每次尝试都是一条 Attempt 记录：

```
Query Q-1234
├── Attempt #1  ChatGPT  US-West  ACC-001  ✅ success  3.2s  [HAR] [HTML] [Screenshot]
├── Attempt #2  豆包      —       ACC-005  ❌ TIMEOUT   90s  [HAR]
├── Attempt #3  豆包      —       ACC-005  ✅ success  4.8s  [HAR] [HTML] [Screenshot]
└── Attempt #4  DeepSeek  SG      ACC-006  ❌ CAPTCHA  12s  [HAR] [Screenshot]
    └── Attempt #5  DeepSeek  JP  ACC-007  ✅ success  5.1s  [HAR] [HTML] [Screenshot]
```

## 2.1 核心数据模型 — `query_execution_attempts`

```sql
CREATE TABLE query_execution_attempts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  query_id UUID NOT NULL REFERENCES queries(id),
  engine TEXT NOT NULL,                          -- chatgpt | doubao | deepseek
  attempt_number INT NOT NULL,                   -- 1, 2, 3... (per query × engine)
  
  -- 执行上下文
  account_id UUID REFERENCES accounts(id),
  proxy_node_id UUID REFERENCES proxy_nodes(id),
  proxy_region TEXT,
  profile_id UUID REFERENCES profiles(id),
  segment_id UUID REFERENCES segments(id),
  prompt_version_id UUID REFERENCES prompt_template_versions(id),
  adapter_mode TEXT,                             -- web | api
  
  -- 执行结果
  status enum('pending','running','success','failed','retrying','waiting_manual','dlq') NOT NULL DEFAULT 'pending',
  error_code TEXT,                               -- ADAPTER_CONTRACT §6: CAPTCHA_UNSOLVED / CF_BLOCKED / PARSER_FAIL / etc.
  error_subcategory TEXT,                        -- e.g. captcha_type=turnstile, selector=article-body
  error_message TEXT,
  
  -- 响应数据
  response_text TEXT,                            -- AI 回答原文
  response_tokens INT,
  response_time_ms INT,
  
  -- Debug 凭据 (文件路径指向 object storage)
  har_path TEXT,                                 -- HTTP Archive 文件
  raw_html_path TEXT,                            -- 爬取到的完整 HTML
  screenshot_path TEXT,                          -- 页面截图
  console_log_path TEXT,                         -- 浏览器 console 日志
  
  -- 重试链
  retry_of_attempt_id UUID REFERENCES query_execution_attempts(id),  -- 指向重试的原 attempt
  retry_strategy TEXT,                           -- same / rotate_proxy / rotate_account / dlq
  
  -- 时间戳
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- 高频查询索引
CREATE INDEX idx_attempts_query ON query_execution_attempts (query_id, engine, attempt_number);
CREATE INDEX idx_attempts_status ON query_execution_attempts (status, created_at DESC);
CREATE INDEX idx_attempts_error ON query_execution_attempts (error_code, created_at DESC) WHERE status = 'failed';
CREATE INDEX idx_attempts_engine ON query_execution_attempts (engine, status, created_at DESC);
CREATE INDEX idx_attempts_account ON query_execution_attempts (account_id, created_at DESC);

-- 引擎健康 5 分钟聚合视图
CREATE MATERIALIZED VIEW engine_health_5min AS
SELECT
  date_trunc('5 minutes', started_at) AS window,
  engine,
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE status = 'success') AS success,
  ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'success') / NULLIF(COUNT(*), 0), 1) AS success_rate,
  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY response_time_ms) AS p50_ms,
  PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY response_time_ms) AS p95_ms,
  COUNT(*) FILTER (WHERE error_code = 'CAPTCHA_UNSOLVED') AS captcha_count,
  COUNT(*) FILTER (WHERE error_code = 'CF_BLOCKED') AS cf_blocked_count,
  COUNT(*) FILTER (WHERE error_code = 'TIMEOUT') AS timeout_count
FROM query_execution_attempts
WHERE started_at > NOW() - INTERVAL '24 hours'
GROUP BY 1, 2;
```

**这是 Tracker 模块的唯一核心表**。v1 的 `query_execution_failures`（重试中心）、`queries` 的 status/retry 字段、引擎健康数据源，全部统一到这张表。

---

## 2.2 执行追踪 `/admin/pipeline/tracker/attempts`

**目的**。Tracker 的核心页面。看到每条 Query 的每次 Attempt，快速 debug，一键重试。

**IA**:

```
┌─────────────────────────────────────────────────────────────────┐
│ 筛选栏: [引擎 ▼] [状态 ▼] [错误码 ▼] [时间范围] [搜索 Query ID] │
├─────────────────────────────────────────────────────────────────┤
│ 汇总条: 总 Attempt: 128,540  成功: 118,200 (92%)               │
│         失败: 10,340  重试中: 420  待人工: 980  DLQ: 430        │
├─────────────────────────────────────────────────────────────────┤
│ ☐ | Attempt ID | Query ID | 引擎    | #  | Prompt 摘要        │
│   | 账号      | 代理区域  | 状态    | 错误码              | 耗时 │
│   | HAR | HTML | 截图 | 日志 | 开始时间 | 操作              │
│───────────────────────────────────────────────────────────────  │
│ ☐ | ATT-48210 | Q-1234 | ChatGPT | #3 | 推荐一款抗衰老精华  │
│   | ACC-003  | US-West  | ✅ 成功  | —                    | 3.2s │
│   | 📎 | 📄 | 🖼️ | 📋 | 14:02:10 | [详情]              │
│───────────────────────────────────────────────────────────────  │
│ ☐ | ATT-48209 | Q-1234 | ChatGPT | #2 | 推荐一款抗衰老精华  │
│   | ACC-001  | US-East  | ❌ 失败  | CAPTCHA_UNSOLVED     | 12s  │
│   | 📎 | — | 🖼️ | 📋 | 13:58:22 | [重试] [详情]        │
│───────────────────────────────────────────────────────────────  │
│ ☐ | ATT-48205 | Q-5678 | 豆包    | #1 | 奢侈品包包保值排名  │
│   | ACC-005  | —        | ⏳ 重试中 | TIMEOUT             | 90s  │
│   | 📎 | — | — | 📋 | 13:40:05 | [取消] [详情]        │
└─────────────────────────────────────────────────────────────────┘
```

**关键交互**:

1. **Attempt 详情抽屉** — 点击任意行展开，多 Tab:
   - **概要 Tab**: Query 全文 / Prompt 模板版本 / Profile 画像 / 引擎 / 账号 / 代理 / adapter mode
   - **Response Tab**: AI 回答全文渲染（成功时）/ 错误详情（失败时）
   - **HAR Tab**: HTTP Archive 查看器（请求 / 响应头 / 时间线瀑布图）
   - **HTML Tab**: 爬取的原始 HTML 渲染（iframe sandbox）+ DOM 高亮关键元素
   - **截图 Tab**: 页面截图（可放大）+ 时间戳水印
   - **日志 Tab**: 浏览器 console log（按 warn/error 过滤）
   - **重试链 Tab**: 该 Query 在该引擎上的所有 Attempt 时间线（#1 → #2 → #3），每次用了什么策略

2. **手动重试** — 对 failed/waiting_manual 的 Attempt:
   - 单条重试: 选择策略(same / rotate_proxy / rotate_account) → 立即执行
   - 批量重试: 多选 → 选策略 → ≥50 条时显示成本预览 → 确认

3. **批量操作**: 批量重试 / 批量送 DLQ / 批量忽略（≥200 条自动拆分 50/批 + 进度条）

4. **错误码快筛** — 顶栏 chip:
```
全部 (10,340) | CAPTCHA (980) | CF_BLOCKED (310) | PARSER_FAIL (220)
PROXY_DEAD (140) | TIMEOUT (100) | COOKIE_EXPIRED (50) | EXTRACT_EMPTY (30) | PAGE_CRASHED (0)
```

5. **实时更新**: SWR 5s revalidate + 页面可见性检测

### 2.2.1 自动重试规则

自动重试规则内嵌在 Tracker 中，作为"执行追踪"页面的设置面板（齿轮图标展开）:

```sql
CREATE TABLE retry_strategy_rules (
  id SERIAL PRIMARY KEY,
  failure_category TEXT NOT NULL,
  failure_subcategory TEXT,
  strategy enum('same','rotate_proxy','rotate_account','dlq') NOT NULL,
  max_retries INT NOT NULL,
  backoff_base_seconds INT NOT NULL DEFAULT 30,
  backoff_max_seconds INT NOT NULL DEFAULT 300,
  cooldown_window_minutes INT NOT NULL DEFAULT 5,
  is_system_default BOOLEAN DEFAULT FALSE,
  is_enabled BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_by UUID REFERENCES admin_users(id),
  updated_at TIMESTAMPTZ DEFAULT now()
);
```

**7 条系统默认规则**:

| 错误码 | 策略 | 最大重试 | 退避 | 说明 |
|--------|------|---------|------|------|
| TIMEOUT | same | 3 | 30s→240s | 原参数重试 |
| CF_BLOCKED | rotate_proxy | 2 | 60s→600s | 换代理区域 |
| PROXY_DEAD | rotate_proxy | 2 | 10s→60s | 换代理 |
| COOKIE_EXPIRED | rotate_account | 1 | 0s | 换账号 |
| CAPTCHA_UNSOLVED | rotate_account | 2 | 120s→600s | 换号换验证类型 |
| PARSER_FAIL | 0 重试 | — | — | 入 `parse_failures` 审核队列；Analyzer 独立兜底（不进 Tracker 重试池）。需人工更新 adapter selector 或 HAR snapshot 后重新 parse。 |
| EXTRACT_EMPTY | dlq | 0 | — | 直入 DLQ（selector 过期需人工） |
| PAGE_CRASHED | same | 1 | 5s→10s | 重启 context |

**PARSER_FAIL 特殊处理说明**: PARSER_FAIL 由 engine 端 DOM 结构变更引起，重跑 adapter 不解决；需定位到 HAR / selector 层修复。因此不进入 Tracker 重试池，而是独立进入 Analyzer 的 `parse_failures` 审核队列，由人工更新 adapter selector 或 HAR snapshot 后重新执行。

**DLQ（死信队列）** — 重试上限后仍失败 / 规则直接路由:

```sql
CREATE VIEW dead_letter_queue AS
SELECT * FROM query_execution_attempts WHERE status = 'dlq';
```

DLQ SLA 告警:
- 滞留 > 3天 → P2 PIPE-09a
- 滞留 > 7天 → P1 PIPE-09b + 阻塞新 Query
- > 500条 → P0 PIPE-09c

DLQ 处置三选一: 归档(+原因) / 标 Bug(+issue) / 强制重试(super_admin)

---

## 2.3 引擎健康 `/admin/pipeline/tracker/engines`

**目的**。单引擎维度的"一眼看清并一键处置"。数据来自 `query_execution_attempts` 聚合。

**IA**（每引擎一张大卡）:

```
┌─────────── ChatGPT (web + api fallback) ──────────────┐
│ 🟡 降级                               成功率 78%       │
│────────────────────────────────────────────────────── │
│ p50/p95: 3.2s / 8.4s    QPS: 12.4    样本 24h: 18k   │
│ Adapter: web  [切换到 api]  Running: 240 / Paused: 0  │
│                                                        │
│ 错误分布 (24h):                                        │
│   CAPTCHA 42% ████████████                             │
│   TIMEOUT 28% ████████                                 │
│   PARSER  18% █████                                    │
│   BLOCK    8% ██                                       │
│   OTHER    4% █                                        │
│                                                        │
│ Circuit Breaker: closed ● ● ● ● ● ● ○ (7/20)         │
│                                                        │
│ [查看失败样本] [切换 adapter] [手动半开] [停采]       │
└────────────────────────────────────────────────────────┘
```

**交互**:
- **切换 adapter** → 写 `engine_runtime_config.adapter_mode` → 二次确认 + 理由 + 审计
- **手动半开** → 强制 circuit breaker half-open
- **停采** → `is_paused = true` → running 继续，新任务不调度
- **查看失败样本** → 跳转 Tracker §2.2 并筛选该引擎 + failed

**数据模型**:
```sql
ALTER TABLE engine_runtime_config
  ADD COLUMN circuit_state enum('closed','open','half_open') NOT NULL DEFAULT 'closed',
  ADD COLUMN circuit_last_transition_at TIMESTAMPTZ,
  ADD COLUMN circuit_failure_threshold INT NOT NULL DEFAULT 10,
  ADD COLUMN circuit_window_size INT NOT NULL DEFAULT 20,
  ADD COLUMN api_key_id UUID REFERENCES admin_secrets(id);

CREATE TABLE circuit_breaker_events (
  id BIGSERIAL PRIMARY KEY,
  engine TEXT NOT NULL,
  transition TEXT NOT NULL,
  trigger TEXT NOT NULL,
  window_failure_count INT,
  operator_id UUID REFERENCES admin_users(id),
  reason TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);
```

---

## 2.4 链路追溯 `/admin/pipeline/tracker/trace`

**目的**。用户投诉时 90 秒内定位问题 Response 的完整链路。

**IA**:
1. 搜索框: Response ID / 品牌 ID + 日期 / User email + 时间窗口
2. Sankey 图 (D3): `brand → topic → prompt_template(version) → query(profile) → response → parsed_mentions`
3. 节点点击 → 右侧抽屉全部字段 + 审计 log
4. **从 Sankey 跳到 Attempt**: 选中 Response 节点 → "查看所有执行尝试" → 跳 §2.2 并筛选该 query_id

**数据 Lineage**:
```sql
ALTER TABLE topics ADD COLUMN lineage_trace_id UUID;
ALTER TABLE prompts ADD COLUMN lineage_trace_id UUID;
ALTER TABLE queries ADD COLUMN lineage_trace_id UUID;
ALTER TABLE ai_responses ADD COLUMN lineage_trace_id UUID;
CREATE INDEX ON ai_responses (lineage_trace_id);
```

**边界**: D3 Sankey 节点 ≤ 200（超过自动裁剪 + 提示缩窄范围）。不允许导出 PDF。

---

# 3. Analyzer — 结果分析模块

> **核心问题**: "采集到的数据质量如何"

## 3.1 质量分析 `/admin/pipeline/analyzer/quality`

**目的**。每条 Response 经过 Parser 后产出结构化指标（品牌提及、情感、引用等），本页聚合展示这些指标的质量趋势。

**IA**:

### 3.1.1 Per-Query 分析结果面板

核心视图: 可搜索 / 可筛选的 **Query 分析结果列表**:

```
┌──────────────────────────────────────────────────────────────┐
│ 筛选: [引擎 ▼] [行业 ▼] [日期范围] [搜索 Query/Brand]       │
├──────────────────────────────────────────────────────────────┤
│ Query ID | Prompt 摘要       | 引擎    | 品牌命中数 | 情感    │
│          | 引用数 | 提及位置 | PANO A  | 解析状态   | 时间    │
│──────────────────────────────────────────────────────────────│
│ Q-1234   | 推荐抗衰老精华    | ChatGPT | 5 brands  | 正面 82% │
│          | 3 citations       | top/mid | 78.5      | ✅ 完成  │
│──────────────────────────────────────────────────────────────│
│ Q-5678   | 奢侈品包包保值    | 豆包    | 8 brands  | 中性 64% │
│          | 0 citations       | mid/tail| 42.1      | ⚠ 缺引用 │
└──────────────────────────────────────────────────────────────┘
```

**点击展开 Query 分析详情抽屉**:
- **品牌提及**: 检测到的品牌列表 + 位置(top/middle/tail) + 提及原文高亮
- **情感分析**: 每个品牌的情感分数 + 分类(positive/neutral/negative) + 置信度
- **引用分析**: Citation URL + Tier 分级 + Authority Score + 归因方式(official_domain/co_occurrence/text_match)
- **PANO Score 分解**: 提及率 / SoV / 情感 / 引用份额 / 排名 — 每个维度的原始值
- **原始 Response 对照**: 左列分析结果，右列 Response 原文（高亮对应片段）
- **跳转 Tracker**: "查看执行详情" 按钮 → 跳到 Tracker Attempt 抽屉（看 HAR / HTML / 截图）

### 3.1.2 质量趋势仪表盘

- **解析成功率趋势** (7d): 按引擎叠加的 AreaChart
- **品牌识别 Precision** (7d): 自动解析 vs 人工标注对比（来自 QA 数据）
- **引擎间偏差**: 3 引擎的情感分类分布对比（是否有系统性偏差？）
- **引用覆盖率**: 有引用的 Response 占比趋势
- **异常检测**: 某日某引擎的某指标偏离 2σ → 自动标红 + 告警

### 3.1.3 分析结果数据模型

```sql
-- ai_responses 表扩展（Analyzer 视角字段）
ALTER TABLE ai_responses
  ADD COLUMN IF NOT EXISTS parse_status enum('pending','completed','partial','failed') DEFAULT 'pending',
  ADD COLUMN IF NOT EXISTS brands_detected JSONB,       -- [{brand_id, name, position, sentiment, confidence}]
  ADD COLUMN IF NOT EXISTS citations_detected JSONB,     -- [{url, tier, authority_score, attribution_method}]
  ADD COLUMN IF NOT EXISTS overall_sentiment NUMERIC,    -- 0-1
  ADD COLUMN IF NOT EXISTS pano_score_breakdown JSONB,   -- {mention_rate, sov, sentiment, citation_share, rank}
  ADD COLUMN IF NOT EXISTS parse_errors TEXT[];

-- 质量聚合视图（每日刷新）
CREATE MATERIALIZED VIEW response_quality_daily AS
SELECT
  DATE(created_at) AS day,
  engine,
  industry,
  COUNT(*) AS total_responses,
  COUNT(*) FILTER (WHERE parse_status = 'completed') AS parsed_ok,
  ROUND(100.0 * COUNT(*) FILTER (WHERE parse_status = 'completed') / NULLIF(COUNT(*), 0), 1) AS parse_success_rate,
  AVG(overall_sentiment) AS avg_sentiment,
  AVG(jsonb_array_length(COALESCE(brands_detected, '[]'))) AS avg_brands_per_response,
  AVG(jsonb_array_length(COALESCE(citations_detected, '[]'))) AS avg_citations_per_response,
  COUNT(*) FILTER (WHERE jsonb_array_length(COALESCE(citations_detected, '[]')) > 0) * 100.0 / NULLIF(COUNT(*), 0) AS citation_coverage_pct
FROM ai_responses
WHERE created_at > NOW() - INTERVAL '30 days'
GROUP BY 1, 2, 3;
```

---

## 3.2 人工质检 `/admin/pipeline/analyzer/qa`

**目的**。自动管线解决不了系统性偏差 — 需要人工抽样打标做校准。

**IA**:
1. KPI 面板: 本周抽样数 / 已标注 / 待标注 / Overall Precision
2. 待审队列: 每行一条 Response — Prompt 摘要 / 引擎 / 自动识别品牌 / 情感 / 引用
3. **三栏对比抽屉**:
   - 左: 原始 Response 文本
   - 中: 自动抽取结果（可编辑修正）
   - 右: 反馈表单 (correct / wrong_brand / wrong_sentiment / missed_mention / hallucination / bad_citation)
4. 校准回写: 人工标注写入 `response_qa_labels`，每周汇总 precision/recall
5. **与 Tracker 联动**: 从 QA 样本点击 "查看执行详情" → 跳 Tracker Attempt 详情

**数据模型**:
```sql
CREATE TABLE response_qa_samples (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  response_id UUID NOT NULL,
  engine TEXT NOT NULL,
  industry TEXT NOT NULL,
  sampled_at TIMESTAMPTZ DEFAULT now(),
  assigned_to UUID REFERENCES admin_users(id),
  status enum('pending','in_review','labeled','skipped') NOT NULL DEFAULT 'pending',
  labeled_at TIMESTAMPTZ
);

CREATE TABLE response_qa_labels (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  sample_id UUID NOT NULL REFERENCES response_qa_samples(id),
  labeler_id UUID NOT NULL REFERENCES admin_users(id),
  overall_correct BOOLEAN,
  error_categories TEXT[],
  corrected_brands JSONB,
  corrected_sentiment TEXT,
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE MATERIALIZED VIEW response_qa_weekly AS
SELECT
  date_trunc('week', labeled_at) AS week,
  engine,
  COUNT(*) FILTER (WHERE overall_correct) * 1.0 / NULLIF(COUNT(*), 0) AS precision_overall,
  SUM((error_categories @> ARRAY['wrong_brand'])::int) * 1.0 / NULLIF(COUNT(*), 0) AS wrong_brand_rate
FROM response_qa_labels
GROUP BY 1, 2;
```

**边界**: 每日自动抽样 200 条（按引擎/行业分层）。标注数据不直接改 `ai_responses`，离线校准回写。

---

# 4. 横切模块

## 4.1 管道总览 Dashboard `/admin/pipeline/dashboard`

**目的**。一屏看清三大模块健康状态。不做深度下钻，只做触发器。

**IA**:
1. **告警条** (顶部): 最多 3 条 P0/P1，一行一条，"定位"按钮跳对应模块
2. **Planner 摘要**: 今日批次进度条 + Planner 最后运行状态 + 品类 Topic 占比
3. **Tracker 摘要**: 24h Attempt 成功率 + 3 引擎迷你卡 + 失败 Top 3 错误码 + DLQ 数量
4. **Analyzer 摘要**: 解析成功率 + 品牌识别 Precision(本周) + 待标注 QA 数量
5. **14 天趋势**: 成功率 + 成本双轴折线
6. **Reaper 状态**: footer 显示 "last run: 3m ago · cleaned 12"

## 4.2 敏感数据保护

| 数据 | 存储 | Admin UI 可见度 | 导出限制 |
|------|------|----------------|---------|
| 账号 cookie/session | pgcrypto + KMS | masked hash | 严禁导出 |
| Prompt 模板正文 | 明文 | 可见 | 严禁导出 |
| User email | 明文 | masked | super_admin + 理由 |
| Response 文本 | 明文 | 可见 | super_admin + 理由 |
| HAR / HTML / 截图 | Object Storage | Tracker 内可见 | 不可批量导出 |

## 4.3 变更审批中心 `/admin/pipeline/changes`

**目的**。跨三模块的高危操作审批。

**5 种必审变更**: adapter_switch / prompt_activate / engine_pause / retry_rule / proxy_toggle / account_add

**IA**:
1. 列表: Pending / Approved / Rejected / Rolled-back
2. 详情抽屉: 变更类型 / 影响范围 / 发起人 / 理由 / diff + dry-run
3. "Approve & Apply" / "Reject" / 30 天回滚

**数据模型**:
```sql
CREATE TABLE pipeline_change_requests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  change_type TEXT NOT NULL,
  target_resource TEXT NOT NULL,
  diff JSONB NOT NULL,
  requested_by UUID NOT NULL REFERENCES admin_users(id),
  requested_at TIMESTAMPTZ DEFAULT now(),
  requested_reason TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  approved_by UUID REFERENCES admin_users(id),
  approved_at TIMESTAMPTZ,
  applied_at TIMESTAMPTZ,
  rolled_back_at TIMESTAMPTZ,
  rollback_reason TEXT,
  dry_run_result JSONB
);
```

**Solo 模式**: 创建者 = 审批者可以（强制勾选"我已审查" + 写理由）。Phase 2 强制 two-eyes。

## 4.4 Reaper (僵尸任务清理)

- Running 超过 `engine.p99 × 3` 无结果 → cron 5min 标 TIMEOUT → 送重试
- 状态显示在 Dashboard footer

## 4.5 Pipeline UI 文案边界

UI 不使用"本页不做 X / 严禁 X / 请去 Y 页"这类内部约束文案。页面边界通过导航跳转和动作可用/不可用状态表达。

---

# 5. API 契约

全部位于 `/admin/api/v1/pipeline/*`。所有非 GET 接口必须经过 `withAudit` 中间件。

## 5.1 Planner API

```
-- 调度
GET    /admin/api/v1/pipeline/scheduler/overview
GET    /admin/api/v1/pipeline/scheduler/batches        ?range=7d&cursor=
POST   /admin/api/v1/pipeline/scheduler/planner/trigger { scope, industry_id?, brand_id? }
GET    /admin/api/v1/pipeline/scheduler/planner/status
GET    /admin/api/v1/pipeline/scheduler/pause
POST   /admin/api/v1/pipeline/scheduler/pause           { action:'pause'|'resume', reason }

-- 生成管线
GET    /admin/api/v1/pipeline/generation/prompts
POST   /admin/api/v1/pipeline/generation/prompts/trigger { scope, industry_id?, topic_id?, intent_filter[], language_filter[] }
GET    /admin/api/v1/pipeline/generation/prompts/failures ?page=&limit=
POST   /admin/api/v1/pipeline/generation/prompts/retry   { failure_ids[], reason }
GET    /admin/api/v1/pipeline/generation/prompts/coverage
GET    /admin/api/v1/pipeline/generation/queries
GET    /admin/api/v1/pipeline/generation/queries/queue   ?status=&page=&limit=
POST   /admin/api/v1/pipeline/generation/queries/trigger { scope, from_date?, to_date?, segment_ids[], reason }
POST   /admin/api/v1/pipeline/generation/queries/engine-control { engine, action:'pause'|'resume', reason }

-- Prompt 模板
GET    /admin/api/v1/pipeline/prompts                    ?status=&intent=&language=
POST   /admin/api/v1/pipeline/prompts/:id/versions       { body, variables, rollout_plan }
POST   /admin/api/v1/pipeline/prompts/:id/versions/:v/activate { reason }
POST   /admin/api/v1/pipeline/prompts/ab/:id/conclude    { decision }

-- Segment / Profile
GET    /admin/api/segments                               ?page=&per_page=&q=&status=&industry_id=
POST   /admin/api/segments                               { name, industry_id?, status, weight, age_range?, income?, regions?, sampling_rate?, note? }
GET    /admin/api/segments/:id
PUT    /admin/api/segments/:id                           { ... }
DELETE /admin/api/segments/:id                           soft delete
POST   /admin/api/segments/import                         { format, rows }
POST   /admin/api/segments/generate                       { brand_id?, brand_name, industry_id?, count, status, positioning, goal, constraints }
GET    /admin/api/segments/:id/profiles                   ?page=&per_page=&q=&status=
POST   /admin/api/segments/:id/profiles                   { name, demographic, need, weight, status, persona_json? }
PUT    /admin/api/segments/:id/profiles/:profile_id       { ... }
DELETE /admin/api/segments/:id/profiles/:profile_id       soft delete
POST   /admin/api/segments/:id/profiles/import            { format, rows }
GET    /admin/api/segments/:id/profiles/export            CSV
POST   /admin/api/segments/:id/profiles/generate          { brand_name, count, goal, constraints, llm_model?, reason }

-- 资源
GET    /admin/api/v1/pipeline/accounts                   ?engine=&tags=&health_min=
POST   /admin/api/v1/pipeline/accounts/:id/actions       { action:'freeze'|'unfreeze'|'retire', reason }
POST   /admin/api/v1/pipeline/accounts/:engine/ingest    { cookies_jwe, tags }
POST   /admin/api/v1/pipeline/accounts/import/batch      [multipart/form-data]
GET    /admin/api/v1/pipeline/accounts/tags
POST   /admin/api/v1/pipeline/accounts/:id/tags          { tag_names[], action }
POST   /admin/api/v1/pipeline/accounts/rotation-config/:engine { ...config, reason }
POST   /admin/api/v1/pipeline/accounts/retirement-rules/:engine { ...rules, reason }
GET    /admin/api/v1/pipeline/proxies                    ?region=
POST   /admin/api/v1/pipeline/proxies/regions/:region/toggle { action:'pause'|'enable', reason }
POST   /admin/api/v1/pipeline/proxies/subscription       { url, reason }
POST   /admin/api/v1/pipeline/proxies/sync               (立即刷新节点)
```

## 5.2 Tracker API

```
-- Attempts (核心)
GET    /admin/api/v1/pipeline/tracker/attempts           ?engine=&status=&error_code=&query_id=&from=&to=&cursor=
GET    /admin/api/v1/pipeline/tracker/attempts/:id       (详情 + 重试链)
GET    /admin/api/v1/pipeline/tracker/attempts/:id/har   (HAR 文件下载)
GET    /admin/api/v1/pipeline/tracker/attempts/:id/html  (原始 HTML)
GET    /admin/api/v1/pipeline/tracker/attempts/:id/screenshot (截图)
GET    /admin/api/v1/pipeline/tracker/attempts/:id/console (Console log)
POST   /admin/api/v1/pipeline/tracker/attempts/:id/retry { strategy, reason }
POST   /admin/api/v1/pipeline/tracker/attempts/batch-retry { ids[], strategy, reason }
POST   /admin/api/v1/pipeline/tracker/attempts/batch-dlq { ids[], reason }
GET    /admin/api/v1/pipeline/tracker/attempts/summary   (汇总: 总量/成功/失败/retrying/manual/dlq)
GET    /admin/api/v1/pipeline/tracker/attempts/error-distribution (8 错误码分布)

-- 重试规则
GET    /admin/api/v1/pipeline/tracker/retry-rules
POST   /admin/api/v1/pipeline/tracker/retry-rules        { ...rule } → change_request
PUT    /admin/api/v1/pipeline/tracker/retry-rules/:id    { ...rule } → change_request
DELETE /admin/api/v1/pipeline/tracker/retry-rules/:id    (system_default 不可删)

-- DLQ
GET    /admin/api/v1/pipeline/tracker/dlq                (列表 + 统计 + SLA)
POST   /admin/api/v1/pipeline/tracker/dlq/:id/archive    { reason }
POST   /admin/api/v1/pipeline/tracker/dlq/:id/link-bug   { bugId, reason }
POST   /admin/api/v1/pipeline/tracker/dlq/:id/force-retry { reason } → super_admin

-- 引擎健康
GET    /admin/api/v1/pipeline/tracker/engines
POST   /admin/api/v1/pipeline/tracker/engines/:engine/actions { action, reason }

-- Trace
GET    /admin/api/v1/pipeline/tracker/trace              ?response_id= | ?brand_id=&from=&to= | ?user=&from=&to=
```

## 5.3 Analyzer + 变更审批 + Dashboard API

```
-- Analyzer 质量
GET    /admin/api/v1/pipeline/analyzer/quality           ?engine=&industry=&from=&to=&cursor=
GET    /admin/api/v1/pipeline/analyzer/quality/:query_id (Per-query 分析详情)
GET    /admin/api/v1/pipeline/analyzer/quality/trend     ?days=7
GET    /admin/api/v1/pipeline/analyzer/quality/engine-comparison

-- Analyzer 质检
GET    /admin/api/v1/pipeline/analyzer/qa/samples        ?status=&engine=
POST   /admin/api/v1/pipeline/analyzer/qa/:id/label      { overall_correct, error_categories, ... }
GET    /admin/api/v1/pipeline/analyzer/qa/weekly-stats

-- 变更审批
GET    /admin/api/v1/pipeline/changes                    ?status=
POST   /admin/api/v1/pipeline/changes                    { change_type, target_resource, diff, reason }
POST   /admin/api/v1/pipeline/changes/:id/dry-run
POST   /admin/api/v1/pipeline/changes/:id/approve        { reason }
POST   /admin/api/v1/pipeline/changes/:id/reject         { reason }
POST   /admin/api/v1/pipeline/changes/:id/apply
POST   /admin/api/v1/pipeline/changes/:id/rollback       { reason }

-- Dashboard
GET    /admin/api/v1/pipeline/dashboard
```

---

# 6. 观测与告警

| Rule ID | 条件 | 等级 | 模块 |
|---------|------|------|------|
| PIPE-01 | 引擎 5min 成功率 < 70% 持续 10min | P0 | Tracker |
| PIPE-02 | 账号池 active/total < 30% | P1 | Planner (资源) |
| PIPE-03 | 代理区域节点 < 3 | P1 | Planner (资源) |
| PIPE-04 | Topic 层 1h 增量 = 0 (Planner 故障) | P0 | Planner |
| PIPE-05 | 当日失败 > 30% | P1 | Dashboard |
| PIPE-06 | Prompt 灰度 precision drop > 10% | P1 | Planner |
| PIPE-07 | Reaper 无法连接 worker > 15min | P0 | Dashboard |
| PIPE-08 | Response QA weekly precision < 85% | P2 | Analyzer |
| PIPE-09a | DLQ > 3天 | P2 | Tracker |
| PIPE-09b | DLQ > 7天 | P1 | Tracker |
| PIPE-09c | DLQ > 500条 | P0 | Tracker |
| PIPE-10 | Change request pending > 4h | P2 | 变更审批 |
| PIPE-11 | 代理订阅失效 | P0 | Planner (资源) |
| PIPE-12 | Segment 30天采样 < threshold | P2 | Planner |
| PIPE-14 | Attempt 重试队列积压 > 1000 | P1 | Tracker |
| PIPE-15 | Attempt 失败率 > 20% 持续 30min | P0 | Tracker |

---

# 7. Session 拆分

| Session | 交付 | 工时估算 (AI/human) |
|---------|------|---------|
| **A2** (重写) | Dashboard + Planner (§1.1 调度 + §1.2 生成管线 + §1.5 资源) + 基础数据模型 | 12h / 3h |
| **A2.1** | Planner §1.3 Prompt 模板 (含 A/B + 回归) + §1.4 Segment/Profile | 6h / 2h |
| **A2.2** | Tracker §2.1 核心表 + §2.2 Attempt 列表 + §2.3 引擎健康 | 10h / 3h |
| **A2.3** | Tracker §2.4 Trace & Lineage + 变更审批中心 | 5h / 2h |
| **A2.4** | Analyzer §3.1 质量分析 + §3.2 人工质检 | 6h / 2h |

Phase Gate: A-Gate 2 在 A2 完成后触发；A-Gate 2a 在 A2.1-A2.2 完成后触发；A-Gate 2b 全模块一体化。

---

# 8. Open Questions

| # | 问题 | 默认取舍 |
|---|------|---------|
| Q1 | Attempt 的 HAR/HTML/截图存多久？ | 默认 30 天，DLQ 中的 90 天 |
| Q2 | `query_execution_attempts` 量级大（日均 10w+），分区策略？ | 按月 range partition on `created_at` |
| Q3 | 截图是每次 Attempt 都截还是仅失败时？ | 默认仅失败 + 成功时随机 10% 抽样 |
| Q4 | Analyzer 的 per-query 分数是实时还是异步？ | 异步（Response 入库后由 worker 计算） |
| Q5 | Tracker 实时性用 SWR polling 还是 WebSocket？ | MVP 用 SWR 5s polling，Phase 2 可选 WS |
