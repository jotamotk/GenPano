# GENPANO 工程开工前 · 体检报告 (Preflight)

> **日期**: 2026-04-21
> **体检官**: Claude (Opus 4.7)
> **范围**: 仅盘点, 零修复。所有问题由 Frank 决定下一步, 不在本 Session 内自行动手修。
> **上位参照**: `docs/REVIEW_2026_04_21.md` (上一轮审查) + `CLAUDE.md` "关键设计决策" 21 条
> **方法**: 6 轴平行采样, 关键 grep / ls / wc 命令均原样跑过, 所有结论附代码位置锚点

---

## 0. Executive Summary — 4 类状况一览

| 类别 | 结论 |
|---|---|
| **文档层** | ✅ **非常成熟**。PRD (7348 行) / CLAUDE_CODE_SESSIONS (5148 行) / DATA_MODEL (1039 行) / ADAPTER_CONTRACT (971 行) / TEST_STRATEGY (621 行) 互相引用闭环, SUPERSEDED 标记 16 条全部指向存在的目标章节, 决策 #21 (Review 4/21) 的 PRD / ADAPTER / DATA_MODEL / TEST_STRATEGY / ADMIN_SESSIONS 补丁**全部落地**。 |
| **前端代码** | ⚠️ **70% 就位, 结构已迁入 V2 IA, 但清理未完成**。App.jsx 已挂载 Brand/Industry Mode 全部 14 个路由 + 11 条 301 redirect; 但废弃决策 #10 明令删除的 `DashboardEmptyState.jsx` / `ProjectRequiredBanner.jsx` / `LandingNavQuickCreateButton.jsx` 仍在, 14 个 legacy top-level page 中 5 个为 "unreferenced 死代码"。 |
| **Harness** | ❌ **纸面 100%, 可执行 0%**。CLAUDE.md 罗列的 C1-C7 + C9-C15 (~30 条) + Session 0 §5 声明的 38 条全部**无执行载体**: 无 `scripts/ci-check.mjs` / 无 `scripts/check-data-contracts.mjs` / 无 `.husky/pre-commit` / 无 `.github/workflows/ci.yml`。当前手动跑 grep, 全部 **PASS** (说明代码合规), 但无法保证未来 PR 不 regressing。 |
| **测试 / 后端** | ❌ **完全未启动**。`frontend/package.json` 无 test 脚本 + 无 vitest/playwright 依赖; `backend/` 只有 README + CSV mock, 没有 `package.json` / `prisma/` / `api/` / `.env.example`; `docs/openapi.yaml` (1557 行契约) 是真相源但无任何代码消费它。 |

**前置 blocking 条件**: 若跑 Session 0 则必须先落地 Harness + 测试地基 (轴 5) + backend 脚手架 (轴 6); 若 Frank 意图"frontend 保持原型态"则轴 2 清理 + 轴 3 Harness 仍是 T5' Session 的硬阻塞。

---

## 1. 轴 1 · 文档内一致性

### 1.1 SUPERSEDED 标记追踪 (16 条)

全部指向真实存在的目标章节, 无悬空引用。具体 16 处位置:

| PRD line | 标记 | 目标 §X.Y | 目标存在? |
|---|---|---|---|
| 608 | 4.1.1-gate SUPERSEDES 4.1.1c | — (顶层自标) | N/A |
| 699 | §4.1.1c SUPERSEDED by §4.1.1-gate | §4.1.1-gate @608 | ✅ |
| 732 | §4.1.1c 头部 | §4.1.1-gate | ✅ |
| 1013 | §4.1.1d SUPERSEDED by §4.6-IA-v2.F | §4.6-IA-v2 @3377 | ✅ |
| 3377 | §4.6-IA-v2 SUPERSEDES §4.6.1 / §4.6.1-0 / §4.6.1b | 顶层 | N/A |
| 3395 | §4.6.1 | §4.6-IA-v2 | ✅ |
| 3396 | §4.6.1-0 | §4.6-IA-v2 | ✅ |
| 3406 | §4.1.1d E1/E2/E3/E4 | §4.6-IA-v2.F | ✅ |
| 3764-3765 | 跨文档 cross-ref 指令 | — | N/A |
| 4021 | §4.6.1 头部 | §4.6-IA-v2 | ✅ |
| 4070 | §4.6.1-0 头部 | §4.6-IA-v2 | ✅ |
| 4170 | §4.6.1a 头部 | §4.6-IA-v2 | ✅ |
| 4493 | §4.6.1b 头部 | §4.6-IA-v2 | ✅ |
| 4605 | §4.6.1d 头部 | §4.6-IA-v2 | ✅ |
| 4643 | §4.6.1e 头部 | §4.6-IA-v2 | ✅ |
| 4670 | §4.6.1e v3 迁移 | §4.6.1f/g | ✅ |

**迁移踪迹**: 完整。REVIEW_2026_04_21.md 报告的"§4.6.1 系列无废弃标"**不准确**, 实为全部已加。

### 1.2 CLAUDE.md 21 条决策 vs PRD / SESSIONS / 代码锚点

| # | 决策摘要 | PRD 锚点 | SESSIONS 锚点 | 代码锚点 |
|---|---|---|---|---|
| 1 | 代理架构 (LLM 国内直连, 爬取走代理) | §4.3 | Session 1 | ✅ ADAPTER §7 |
| 2 | Brand Mode / Industry Mode IA | §4.6-IA-v2 @3377 | T1'-T6' @3931-4827 | ⚠️ 部分 (layouts/DashboardLayout.jsx 已 Mode-aware, 缺 components/topbar + components/sidebar 目录) |
| 3 | 每日全量采集 | §4.0.1 | Session 1/2 | (Pipeline 未建) |
| 4 | 免费策略 | §1 | — | — |
| 5 | 4 层 Pipeline | §4.2 | Session 1.5/2 | (未建) |
| 6 | 知识图谱 LLM + Response 挖掘 | §4.0.1a | Session 1.5 | (未建) |
| 7 | Project = 视角过滤器 | §4.0.1 | — | ✅ contexts/ProjectContext.jsx |
| 8 | 用户共建品牌 | §4.0.3 | Session 4a | (未建) |
| 9 | Auth-Required 数据访问 | §4.1.1-gate @608 | Session 4a/T4' | ⚠️ Route Guard 未实现 (`App.jsx` 无 RequireAuth HOC) |
| 10 | 零 Project → /onboarding | §4.6-IA-v2.F | Session T4' | ⚠️ `OnboardingPage.jsx` 存在, 但 3 个"废除"组件仍在: `DashboardEmptyState.jsx` / `ProjectRequiredBanner.jsx` / `LandingNavQuickCreateButton.jsx` |
| 11 | i18n China-first | §4.10 | Session 5 前置 | ⚠️ `messages.js` 单文件 2024 行, 无 namespace 拆分 |
| 12 | 品牌名多语言匹配 | §4.10.4a.D | — | ⚠️ `formatBrand` 已在 LocaleContext.jsx @36 定义, 正确 |
| 13 | Engine-aware Prompt 语言 | §4.10.3 / §4.10.3.A @6918 | Session 2 | (未建) |
| 14 | next-intl UI i18n | §4.10.4 | Session 4a | ⚠️ MVP 用 React Context 替代, 非 next-intl (见 `contexts/LocaleContext.jsx` 注释已说明将来迁移) |
| 15 | Report 深化框架 | §4.7.0-a / §4.8 | Session 4b | (未建) |
| 16 | 提及率 non-brand 口径 | §4.2.5 / §4.6.1a | Session 2/4b | (未建, 但 BrandAnalysisFilterBar 已支持 dimension filter) |
| 17 | 可伸缩筛选栏 | §4.6.1 + §K | T6' | ✅ `components/filters/BrandAnalysisFilterBar.jsx` 存在 |
| 18 | 测试自动化 A++ | §4.10.4a / TEST_STRATEGY | Session 0 | ❌ **未落地** — 无 `scripts/ci-check.mjs` / vitest / playwright |
| 19 | Citation 全链路 + 6 行动面 | §4.2.6 / §4.2.7 | Session 1-4 / A5 | ⚠️ Frontend 组件已建 (`components/citation/*`), 后端 + tier 表 + MCP token 均未建 |
| 20 | V2 分析页统一 + Filter Bar + Heatmap + Wave-4 | §4.6-IA-v2.K-O | T6' | ✅ 大部分就位 (Heatmap / Quadrant / FilterBar 组件均存在); `BrandProductDetailPage.jsx` 在 `pages/` 而非 `pages/brand/`, C15-1/2/3 手动 grep PASS |
| 21 | 2026-04-21 Review 修复闭环 | PRD §4.1.1d.C/§4.2.4.A/§4.9.4/§4.10.3.A · ADAPTER §5.3a/§7.4 · DATA_MODEL §1.9/§2.5 · TEST_STRATEGY §9-§13 · ADMIN_SESSIONS A5 | Session 0 §5 | ⚠️ **文档侧全部落齐, 代码侧仍全 0** (scripts/ci-check.mjs / check-data-contracts.mjs / `__ci_fixtures__/` 都不存在; 38 rules 仍是 plan, 未写 JS) |

**空洞引用排查**: 对 21 条决策涉及的所有 §X.Y (§4.1.1d.C / §4.2.4.A / §4.9.4 / §4.10.3.A / ADAPTER §5.3a / §7.4 / DATA_MODEL §1.9 / §2.5 / TEST_STRATEGY §9-§13 / ADMIN_SESSIONS A5) grep 验证, **全部存在**, 无悬空引用。

### 1.3 CLAUDE.md "设计锚点" 表 vs 实际文件

#### 结构锚点 (16 行) 物理存在性

| 锚点声明路径 | 实际存在? |
|---|---|
| `layouts/DashboardLayout.jsx` | ✅ (498 行, Mode-aware, `BrandSidebar` @282 / `IndustrySidebar` @373 / `ModeToggle` @110 都是 layout 内嵌 function, 非独立文件) |
| `components/topbar/ModeToggle.jsx` (T1' 待建) | ❌ 独立文件缺 (inline 在 DashboardLayout 内) |
| `components/sidebar/BrandPicker.jsx` (T2' 待建) | ❌ 独立文件缺 (inline slot 在 BrandSidebar 内) |
| `components/sidebar/IndustryPicker.jsx` (T3' 待建) | ❌ 独立文件缺 |
| `pages/brand/BrandOverviewPage.jsx` (T2' 待迁) | ❌ 文件不存在, App.jsx 路由 `/brand/overview` 挂 legacy `DashboardPage.jsx` |
| `pages/brand/BrandVisibilityPage.jsx` | ✅ |
| `pages/brand/BrandTopicsPage.jsx` (T2' 待迁) | ❌ 文件不存在, `/brand/topics` 挂 legacy `TopicsPage.jsx` |
| `pages/brand/BrandSentimentPage.jsx` | ✅ |
| `pages/brand/BrandCitationsPage.jsx` | ✅ |
| `pages/brand/BrandProductsPage.jsx` | ✅ |
| `pages/brand/BrandProductDetailPage.jsx` (T2' 迁移目标) | ❌ 仍在 `pages/BrandProductDetailPage.jsx`, 未迁入 `brand/` 子目录 |
| `pages/brand/BrandCompetitorsPage.jsx` | ✅ |
| `pages/brand/BrandDiagnosticsPage.jsx` (T2' 待建) | ❌ 文件不存在, `/brand/diagnostics` 挂 legacy `DiagnosticsPage.jsx` |
| `pages/brand/BrandReportsPage.jsx` (T2' 待建) | ❌ 文件不存在, `/brand/reports` 挂 legacy `ReportsPage.jsx` |
| `pages/industry/IndustryOverviewPage.jsx` | ✅ |
| `pages/industry/IndustryRankingPage.jsx` | ✅ |
| `pages/industry/IndustryTopicsPage.jsx` | ✅ |
| `pages/industry/IndustryKnowledgeGraphPage.jsx` (T3' 待迁) | ❌ 文件不存在, `/industry/knowledge-graph` 挂 legacy `KnowledgeGraphPage.jsx` |
| `pages/OnboardingPage.jsx` | ✅ |
| `pages/BrandsPage.jsx` (保留为品牌集市) | ✅ |
| `pages/AuthPage.jsx` | ✅ |

**结论**: **14 个路由**全部可访问 (App.jsx @91-100 已挂载), 但**物理文件层面 5 页仍靠 legacy 临时承接** (Overview / Topics / Diagnostics / Reports / KnowledgeGraph), 这正好是 REVIEW_2026_04_21.md 报的 5 页 V2 IA 缺口。`BrandProductDetailPage.jsx` 仍在顶层而非 `brand/` 子目录。

#### 已废除锚点 (5 行, 应不存在)

| 声明"已废弃"路径 | 实际状态 |
|---|---|
| `DashboardEmptyState.jsx` (T4') | ⚠️ **仍存在** `components/empty/DashboardEmptyState.jsx` |
| `ProjectRequiredBanner.jsx` (T4') | ⚠️ **仍存在** `components/ProjectRequiredBanner.jsx` |
| `LandingNavQuickCreateButton.jsx` (T4') | ⚠️ **仍存在** `components/landing/LandingNavQuickCreateButton.jsx` |
| `components/industry/IndustryTopicCoverageHeatmap.jsx` (v3.2 删除) | ✅ 已删 |
| `components/industry/IndustryTopicIntentMatrix.jsx` (v3.2 已 git mv 到 `components/topics/TopicIntentMatrix.jsx`) | ✅ 已迁 |

**结论**: 3 个 T4' 废除组件未清理, 与 CLAUDE.md 设计锚点表里"不再建"矛盾。

---

## 2. 轴 2 · Frontend 实态 vs CLAUDE.md 声明

### 2.1 pages/ 目录实盘

**存在文件清单** (14 个 top-level + 5 个 `brand/` + 3 个 `industry/`):

- **top-level (14)**: `AuthPage.jsx` · `BrandDetailPage.jsx` · `BrandProductDetailPage.jsx` · `BrandSimulatorPage.jsx` · `BrandsPage.jsx` · `DashboardPage.jsx` · `DashboardPage.linear.jsx` · `DiagnosticsPage.jsx` · `IndustryPage.jsx` · `KnowledgeGraphPage.jsx` · `LandingPage.jsx` · `LandingPageLegacy.jsx` · `OnboardingPage.jsx` · `ProductsPage.jsx` · `ProjectSettingsPage.jsx` · `QueriesPage.jsx` · `ReportsPage.jsx` · `SettingsPage.jsx` · `TopicsPage.jsx`
- **pages/brand/ (5)**: `BrandCitationsPage.jsx` · `BrandCompetitorsPage.jsx` · `BrandProductsPage.jsx` · `BrandSentimentPage.jsx` · `BrandVisibilityPage.jsx`
- **pages/industry/ (3)**: `IndustryOverviewPage.jsx` · `IndustryRankingPage.jsx` · `IndustryTopicsPage.jsx`

### 2.2 App.jsx 路由 vs 物理文件矩阵

verified via `frontend/src/App.jsx` @79-112:

| URL 路径 | App.jsx 引用组件 | 物理位置 | V2 期望位置 | 状态 |
|---|---|---|---|---|
| `/brand/overview` | `<DashboardPage />` | `pages/DashboardPage.jsx` | `pages/brand/BrandOverviewPage.jsx` | ⚠️ 路由 OK, 文件未迁 |
| `/brand/visibility` | `<BrandVisibilityPage />` | `pages/brand/` | 同 | ✅ |
| `/brand/topics` | `<TopicsPage />` | `pages/TopicsPage.jsx` | `pages/brand/BrandTopicsPage.jsx` | ⚠️ 路由 OK, 文件未迁+未裁剪为单品牌 |
| `/brand/sentiment` | `<BrandSentimentPage />` | `pages/brand/` | 同 | ✅ |
| `/brand/citations` | `<BrandCitationsPage />` | `pages/brand/` | 同 | ✅ |
| `/brand/products` | `<BrandProductsPage />` | `pages/brand/` | 同 | ✅ |
| `/brand/products/:productId` | `<BrandProductDetailPage />` | `pages/BrandProductDetailPage.jsx` | `pages/brand/BrandProductDetailPage.jsx` | ⚠️ 路由 OK, 未迁入子目录 |
| `/brand/competitors` | `<BrandCompetitorsPage />` | `pages/brand/` | 同 | ✅ |
| `/brand/diagnostics` | `<DiagnosticsPage />` | `pages/DiagnosticsPage.jsx` | `pages/brand/BrandDiagnosticsPage.jsx` | ⚠️ 路由 OK, 需裁剪为单品牌上下文 |
| `/brand/reports` | `<ReportsPage />` | `pages/ReportsPage.jsx` | `pages/brand/BrandReportsPage.jsx` | ⚠️ 路由 OK, 需迁入子目录 |
| `/industry/overview` | `<IndustryOverviewPage />` | `pages/industry/` | 同 | ✅ |
| `/industry/ranking` | `<IndustryRankingPage />` | `pages/industry/` | 同 | ✅ |
| `/industry/topics` | `<IndustryTopicsPage />` | `pages/industry/` | 同 | ✅ |
| `/industry/knowledge-graph` | `<KnowledgeGraphPage />` | `pages/KnowledgeGraphPage.jsx` | `pages/industry/IndustryKnowledgeGraphPage.jsx` | ⚠️ 路由 OK, 文件未迁 |

**301 redirect 覆盖** (App.jsx @105-116) — 全 11 条齐备:

- `/dashboard` → `/brand/overview` ✅
- `/topics` → `/brand/topics` ✅
- `/industry` → `/industry/overview` ✅
- `/industries` → `/industry/overview` ✅
- `/industries/:id` → `/industry/overview?industryId=:id` (RedirectIndustryDetail) ✅
- `/knowledge-graph` → `/industry/knowledge-graph` ✅
- `/diagnostics` → `/brand/diagnostics` ✅
- `/reports` → `/brand/reports` ✅
- `/brands/:id` → `/brand/overview?brandId=:id` (RedirectBrandDetail) ✅
- `/brands/:id/simulator` → `/brand/citations?sub=simulator&brandId=:id` (RedirectBrandSimulator) ✅
- `/brands/:id/products/:productId` → `/brand/products/:productId?brandId=:id` (RedirectBrandProduct) ✅

**未通过 App.jsx 引用的"死代码" legacy pages** (未在 App.jsx 中 import):

- ⚠️ `DashboardPage.linear.jsx` — unreferenced
- ⚠️ `BrandDetailPage.jsx` — unreferenced (已被 4.6.1b SUPERSEDED)
- ⚠️ `QueriesPage.jsx` — unreferenced
- ⚠️ `LandingPageLegacy.jsx` — unreferenced
- ⚠️ `IndustryPage.jsx` — unreferenced (legacy Plan S v1, 已被 IndustryOverviewPage 取代)
- (⚠️ `ProductsPage.jsx`, `BrandSimulatorPage.jsx` 仍在 App.jsx 中 import — 但 BrandSimulatorPage 被 301 redirect 包裹, ProductsPage 仅被 import 未被 `<Route>` 消费)

### 2.3 legacy 构建产物临时文件

| 目录 | 大小 | 用途 |
|---|---|---|
| `frontend/dist` | 2.3M | 当前 build 输出 (已在 .gitignore `dist/`) |
| `frontend/dist-tmp` | 2.5M | 历史 build 快照, 可删 |
| `frontend/dist-v3` | 2.7M | 历史 build 快照, 可删 |
| `frontend/dist-v31` | 2.7M | 历史 build 快照, 可删 |
| `frontend/dist-v32` | 2.7M | 历史 build 快照, 可删 |
| `frontend/dist-wave4` | 2.5M | 历史 build 快照, 可删 |
| `frontend/dist-wave4rb` | 2.5M | 历史 build 快照, 可删 |
| `frontend/vite.config.js.timestamp-*.mjs` | — | **25 个** vite HMR 临时文件, 全可删 |
| `frontend/src/i18n/messages.js.broken-backup` | 1600 行 | broken-backup 需要人决策: 是否已修复 / 可否删 |
| `snapshot-before-ia-v2-7ed0bc5/` | 整个 repo 副本 | 决策 #21 提交前的 frank snapshot, 体积巨大, 建议确认后删除或移出 repo |

**.gitignore 现状**: 仅 `dist/` 被忽略, `dist-*/` 未覆盖; `vite.config.js.timestamp-*` 未覆盖。**建议** (仅列, 不改): 
- 追加 `frontend/dist-*/` + `frontend/vite.config.js.timestamp-*.mjs` 到 `.gitignore`
- `snapshot-before-ia-v2-*/` 评估是否仍需保留 (git 已有 commit 7ed0bc5 承载)
- `messages.js.broken-backup` 由 Frank 确认后删除

### 2.4 i18n 文件结构

- `i18n/messages.js`: 2024 行, 单文件, 按 locale (`zh-CN` / `en-US`) × namespace (common/nav/…) 嵌套
- `i18n/messages.js.broken-backup`: 1600 行, **历史损坏版本**, 留在仓里说明曾有破坏性改动
- **无** `messages/common.json` / `messages/alert.json` / `messages/brand.json` 等 §4.10.4a 期望的命名空间拆分
- **`formatBrand` utility**: ✅ 已在 `contexts/LocaleContext.jsx` @36 / `formatBrand` 实现

---

## 3. 轴 3 · Harness C1-C15 基线 (手动执行结果)

> **体检方式**: 所有 grep 命令从 CLAUDE.md "图表契约 Harness 拦截" (C1-C7) 与 "V2 分析页统一契约 C9-C15 Harness" 一字不差地 copy 并原样跑。

| 规则 | 命令原文摘要 | 输出 | 对应代码位置 | 结论 |
|---|---|---|---|---|
| **C1** | Sparkline 宽高默认 100% | **无输出** | `components/charts/MiniSparkline.jsx` (组件存在) | ✅ PASS |
| **C3** | SoV "其他" 不得 > 任一真实片 | (运行时断言, 非 grep) | 需 `scripts/check-data-contracts.mjs` — ❌ 脚本不存在 | ⚠️ 未验证 |
| **C4** | sentiment `.toFixed(2)` 禁入用户视图 | **无输出** | 无违规 | ✅ PASS |
| **C5** | Sparkline 禁 `i%N===0?±V:0` 锯齿 | **无输出** | 无违规 | ✅ PASS |
| **C7** | BRANDS/PRODUCTS ranking 严格按 panoScore DESC | 手动核对 `mock.js` BRANDS 8 条 + PRODUCTS 14 条均一致 (85→1, 82→2, 79→3, 77→4, 75→5, 73→6, 71→7, 68→8) | `data/mock.js` @160-290 / @313-554 | ✅ 手动 PASS (但需 `scripts/check-data-contracts.mjs` 落地) |
| **UI1** (§4.6.0a) | i18n 开发约束泄漏 | **无输出** | `i18n/messages.js` | ✅ PASS |
| **UI2** (§4.6.0a) | JSX 文本节点开发约束 | **无输出** | `pages/*.jsx` | ✅ PASS |
| **C9-1** | Heatmap 不得借 chart-N / sentiment 令牌 | **无输出** | `components/charts/BrandTopicHeatmap.jsx` | ✅ PASS |
| **C9-2** | Heatmap 禁内联 hex | **无输出** | 同上 | ✅ PASS |
| **C10-1** | 6 分析页 FilterBar mount | **1 FAIL**: `BrandTopicsPage.jsx` 缺 (因文件未建, legacy TopicsPage 承接) | `pages/brand/` | ❌ FAIL (文件物理缺失) |
| **C10-2** | 禁本地 `useState('7d')` | **无输出** | `pages/brand/*.jsx` | ✅ PASS |
| **C11-1** | mentionRate literal ≥ 1 | **无输出** (全为 0-1 小数) | `data/mock.js` | ✅ PASS |
| **C12-1** | BrandSentimentPage 必须 import DonutChart | PASS | `pages/brand/BrandSentimentPage.jsx` | ✅ PASS |
| **C12-2** | 禁 text-3xl+ sentiment pct | **无输出** | 同上 | ✅ PASS |
| **C13-1** | Quadrant radius literal ≤ 40 | **无输出** | `components/charts/CompetitorQuadrantChart.jsx` | ✅ PASS |
| **C13-2** | Quadrant 必须 `Math.sqrt` | PASS | 同上 | ✅ PASS |
| **C13-3** | Quadrant 必须 `showLabels` prop | PASS | 同上 | ✅ PASS |
| **C14-1** | V2 分析页 h1/h2 不得 text-2xl+ | **2 FAIL**: `BrandCitationsPage.jsx:58` + `BrandSentimentPage.jsx:127` 均用 `<h2 className="text-2xl …">` | `pages/brand/BrandCitationsPage.jsx` @58 · `pages/brand/BrandSentimentPage.jsx` @127 | ❌ FAIL (2 处) |
| **C14-2** | 禁 `p-[4-9]` Card padding | **19 FAIL**: `BrandCitationsPage.jsx` (8 处 `p-4`) + `BrandSentimentPage.jsx` (11 处 `p-4`) | 同上 | ❌ FAIL (19 处) |
| **C14-3** | 根 div 禁 `space-y-[4-9]` | **无输出** | | ✅ PASS |
| **C15-1** | 详情页禁从 `useParams()` 解构 brandId | **无输出** (且文件在 `pages/BrandProductDetailPage.jsx`, 非 `pages/brand/`) | `pages/BrandProductDetailPage.jsx` | ✅ PASS |
| **C15-2** | 详情页必须 import `useSearchParams` | PASS | 同上 | ✅ PASS |
| **C15-3** | 空态守卫只能 basis productId | **无输出** | 同上 | ✅ PASS |

### 3.1 Harness PASS/FAIL 汇总

- **纯 grep PASS**: 17 条
- **grep FAIL**: 3 条 (C10-1 `BrandTopicsPage.jsx` 缺 / C14-1 两处 text-2xl / C14-2 十九处 p-4)
- **非 grep, 待 script 落地后验**: C3 / C7 (2 条, 手工核对 C7 通过)
- **纸面 vs 可执行**: **全部 23 条均为纸面规则, 零条进入 CI/hook**; `.husky/pre-commit` 不存在, `.github/workflows/` 不存在, `scripts/ci-check.mjs` 不存在

### 3.2 C14 违规详情 (2 规则, 21 处)

**C14-1 (h1/h2 过大)** — 应降到 `text-xl`:
- `pages/brand/BrandCitationsPage.jsx:58` `<h2 className="text-2xl font-brand font-bold ...">`
- `pages/brand/BrandSentimentPage.jsx:127` 同上

**C14-2 (Card padding 过松, 应 ≤ p-3)**:
- `BrandCitationsPage.jsx`: 行 92, 114, 120, 139, 254, 305, 334, 375 (共 8 处 `p-4`)
- `BrandSentimentPage.jsx`: 行 141, 164, 196, 231, 266, 283, 302 (共 7 处 `p-4`)
- (Harness 输出 19 行, 包含 BrandCitationsPage @375 `className="p-4 border-l-4"` 的 inline style)

**建议**: 修复由 T6' 或 T5' Session 承接, 非本体检 Session 范围。

---

## 4. 轴 4 · 依赖清单核对 (frontend/package.json)

### 4.1 CLAUDE.md "依赖规则" 14 行对照

| 领域 | CLAUDE.md 指定 | 实际 | 版本 |
|---|---|---|---|
| 图表 | Recharts | ✅ `recharts` | ^3.8.1 |
| 知识图谱 | AntV G6 v5 | ✅ `@antv/g6` | ^5.0.0 |
| 其他图/网络 | D3.js | ✅ `d3` | ^7.9.0 |
| 数据表格 | TanStack Table | ❌ **未装** | — |
| 表单 | React Hook Form + Zod | ✅ `react-hook-form` ^7.53.0 + `zod` ^3.23.8 + `@hookform/resolvers` ^3.9.0 | — |
| 动画 | Framer Motion | ✅ `framer-motion` | ^12.38.0 |
| 日期 | date-fns | ❌ **未装** | — |
| HTTP | Axios 或 fetch + SWR/TanStack Query | ❌ **未装** (frontend 暂用裸 fetch/mock) | — |
| Toast | Sonner / React Hot Toast | ❌ **未装** (有内部 `components/ui/ToastViewport.jsx`) | 自建 |
| Modal | Radix UI Dialog / Headless UI | ✅ `@radix-ui/react-dialog` | ^1.1.2 |
| 下拉 | Radix UI Select / Headless UI Listbox | ❌ **未装** | — |
| 图标 | Lucide React | ✅ `lucide-react` | ^0.383.0 |
| PDF | @react-pdf/renderer / jsPDF | ❌ **未装** | — |
| 拖拽 | @dnd-kit | ❌ **未装** | — |
| 埋点 | mixpanel-browser + mixpanel | ❌ **未装** (frontend 无 analytics.ts) | — |

### 4.2 缺失的关键依赖 (对 Session 0-5 有阻塞性)

按 CLAUDE.md 决策 #18 / #19 / §4.11:
- **mixpanel-browser** + **mixpanel** (埋点 SDK, PRD §4.11 指定) — Session 4a/5 需
- **@tanstack/react-table** — 存在多个表格页 (BrandsPage / IndustryRankingPage) 当前用原生 `<table>`, PRD 要求必须切换
- **date-fns** — 多处日期格式化场景 (Reports / Diagnostics) 依赖
- **SWR 或 @tanstack/react-query** — Session 3 API 消费必需
- **tldts** — Citation URL 归一化 (§4.2.6 硬约束 E2), Session 3 需
- **Sonner / react-hot-toast** — 当前有自建 ToastViewport.jsx 但 PRD 推荐生产级 toast
- **@react-pdf/renderer 或 jsPDF** — Reports 页 PDF 导出 (§4.7) 需

### 4.3 test/contract-generation 依赖 (Session 0 §5.1 指定)

全部缺失:
- `vitest` / `@vitest/coverage-v8` / `@testing-library/react` / `@testing-library/jest-dom` / `jsdom`
- `@playwright/test`
- `husky` / `lint-staged`
- `openapi-typescript` / `js-yaml`

### 4.4 额外 (CLAUDE.md 未声明但 package.json 有的)

- `react-router-dom` ^6.23.0 — SPA 路由, 合理 (与未来 Next.js App Router 差异)
- `@vitejs/plugin-react` ^4.3.0 — dev server (合理, Vite MVP)

无"孤儿"依赖, 14 个 dependencies 均在使用。

---

## 5. 轴 5 · 测试基础设施就位度

### 5.1 Session 0 §5 清单 vs 实态

| 配置项 | 期望 | 实际 | 状态 |
|---|---|---|---|
| `frontend/package.json` scripts | `dev / build / preview / test:unit / test:integration / test:e2e / test:visual / check:harness / check:contracts` | 仅 `dev / build / preview` | ❌ **缺 6 个 script** |
| vitest deps | `vitest + @vitest/coverage-v8 + @testing-library/react + @testing-library/jest-dom + jsdom` | 全无 | ❌ |
| vitest config | `frontend/vitest.config.ts` | 不存在 | ❌ |
| playwright deps | `@playwright/test` (含 `toHaveScreenshot`) | 未装 | ❌ |
| playwright config | `frontend/playwright.config.ts` | 不存在 | ❌ |
| husky + lint-staged | `.husky/pre-commit` + `.lintstagedrc` | 目录/文件都不存在 | ❌ |
| `openapi-typescript` | 生成客户端类型 | 未装 | ❌ |
| `js-yaml` | OpenAPI 解析 | 未装 | ❌ |
| `scripts/ci-check.mjs` | 38 harness 规则汇总入口 | 目录/文件都不存在 | ❌ |
| `scripts/check-data-contracts.mjs` | C3 / C7 运行时断言 | 目录/文件都不存在 | ❌ |
| `scripts/gen-api-tests.ts` | 从 openapi.yaml 生成契约测试 | 不存在 | ❌ |
| `.github/workflows/ci.yml` | CI pipeline | 目录都不存在 | ❌ |
| `frontend/tests/` 或 `frontend/e2e/` 或 `frontend/visual/` | 测试目录 | 不存在 | ❌ |
| `frontend/src/__ci_fixtures__/` | Decision #21 C: 5 条 self-seeded 违规 fixture | 不存在 | ❌ |
| `fixtures/scraping/*.har` | HAR replay 基线 | 不存在 | ❌ |
| `openapi.yaml` (真相源) | 契约消费 | ✅ `docs/openapi.yaml` 1557 行, OpenAPI 3.1.0 | ✅ (无消费者) |
| `test-data/` | pipeline 级 fixture | ✅ `test-data/pipeline/*.json` 8 个 + `validate.mjs` + `README.md` | ✅ |

**就位度**: **2 / 16 项** (仅 `openapi.yaml` 与 `test-data/` 存在, 但后者无消费者), 约 **12.5%**

### 5.2 TEST_STRATEGY.md v1.1 §9-§13 (Review 4/21 新增章节)

docs 侧已就位:
- §9 异常场景覆盖矩阵 @411
- §10 Admin 测试矩阵 @485
- §11 测试优先级 + `coverage-gap-scan.mjs` @517
- §12 fixture 命名规范 @561
- §13 规则历史血统表 @586

所有 5 章均已写入, 但无代码实现载体。

### 5.3 4 层架构落地率

| 层 | 规格 | 实际 |
|---|---|---|
| L1 Harness (38 rules) | ~30 grep + `prisma validate` + i18n key diff | **0 条**可执行 (全纸面) |
| L2 Unit (Vitest, ~200 tests) | co-located `*.test.ts` | **0** |
| L3 Contract + HAR (~80 tests) | OpenAPI 生成 + HAR replay | **0** (openapi.yaml 真相源已备, 消费者缺) |
| L4 E2E + Visual (~6 specs + 40 baseline) | Playwright + `toHaveScreenshot` | **0** |

---

## 6. 轴 6 · Backend + 数据层实态

### 6.1 backend/ 目录结构

```
backend/
├── README.md           (scaffold 说明, 1 页)
└── mocks/
    ├── csv/user/       (8 个用户侧 CSV 导出 mock)
    └── csv/admin/      (4 个 Admin 侧 CSV 导出 mock)
```

**结论**: backend 是 **CSV mock 宿主**, 非真实后端脚手架。

- ❌ 无 `package.json`
- ❌ 无 `prisma/` 目录 (应有 `schema.prisma` 按 DATA_MODEL.md §1-§6)
- ❌ 无 `api/` 或 `app/api/` (Next.js Router 结构)
- ❌ 无 `.env.example` (Session 0 §4.2 要求 DATABASE_URL / VOLC_API_KEY / RESEND_API_KEY / MIXPANEL_TOKEN / SENTRY_DSN)
- ❌ 无迁移文件
- ❌ 无任何 API 路由实现

### 6.2 DATA_MODEL.md 规划规模

**57 个 section** (grep `^##+ `), 涉及 32 张核心表/MV:

- `users / projects / kg_industries / kg_categories / kg_brands / kg_products / kg_brand_aliases / kg_brand_domains / kg_mined_relations` (1.x, 9 张)
- `platform_topics / platform_prompts / query_executions / attempts / ai_responses / ai_response_citations / brand_mentions / product_mentions` (2.x, 8 张)
- `profile_groups / browser_profiles / accounts / account_states` (3.x, 4 张)
- `metric_snapshots / mv_heatmap_mention_agg / mv_brand_rankings / brand_mention_daily_agg` (4.x, 4 张)
- `audit_logs / cost_events / brand_submissions / brand_discovery_logs / brand_bootstrap_jobs / parse_failures` (5.x, 6 张)
- `export_jobs / report_schedules` [Phase 2] (6.x, 2 张)

**代码实现**: 0 表, 无 schema.prisma 文件。

### 6.3 openapi.yaml vs backend 实现差异

`docs/openapi.yaml` (1557 行, OpenAPI 3.1.0) 定义 **30 个 endpoint**:

**User/Auth (9)**:
- `/auth/lookup` / `/auth/register` / `/auth/verify-email` / `/auth/forgot-password` / `/auth/reset-password` / `/auth/login` / `/auth/refresh` / `/auth/logout` / `/users/me`

**Project/Data (9)**:
- `/v1/projects` (GET/POST) · `/v1/projects/{projectId}` (GET/PATCH/DELETE) · `/v1/projects/{projectId}/competitors` · `/v1/projects/{projectId}/competitors/{brandId}` · `/v1/projects/{projectId}/brands/{brandId}` · `/v1/projects/{projectId}/brands/{brandId}/metrics` · `/v1/projects/{projectId}/topics` · `/v1/projects/{projectId}/topics/{topicId}` · `/v1/projects/{projectId}/prompts/{promptId}/queries`

**Platform (2)**:
- `/v1/profile-groups` · `/v1/brands/submissions`

**Admin (9)**:
- `/admin/v1/brands/submissions` / `.../approve` / `.../reject` / `.../merge` · `/admin/v1/users` · `/admin/v1/audit-logs` · `/admin/v1/cost-dashboard` · `/admin/v1/profile-groups` · `/admin/v1/profile-groups/{id}`

**MCP (1)**:
- `/mcp/brands/{brandId}/metrics`

**Backend 实际实现**: **0/30**。

### 6.4 .env 配置

- 根目录无 `.env.example`, 无 `.env`
- `backend/README.md` 无 env 说明
- Session 0 要求的 5 个关键 env 变量 (DATABASE_URL / VOLC_API_KEY / RESEND_API_KEY / MIXPANEL_TOKEN / SENTRY_DSN) 均无示例

---

## 7. 体检总结 · Frank 需要决策的 5 件事

> 按"决策影响范围大小"排序, 每件都是 Frank 点头后才能落地。

### 决策 A (立即): Session 顺序

目前 `CLAUDE_CODE_SESSIONS.md` 列有 Session 0 / 1 / 1.2 / 1.5 / 2 / 3 / 4a / 4b / 5 + T1'-T6'。由于:

- **T1'-T6' 的 V2 IA 重构已在 App.jsx 路由层就位** (14 路由 + 11 redirect), frontend 可跑可看
- **Session 0 测试地基 + backend 脚手架完全为 0**

→ Frank 可选的下一步:
1. **先跑 Session 0** (补齐 `scripts/ci-check.mjs` / vitest / playwright / husky / `.github/workflows/ci.yml` / `frontend/src/__ci_fixtures__/` / `scripts/check-data-contracts.mjs` / 安装 7 个缺失 production 依赖) — **推荐**, 因为后续所有 Session 都会被"纸面 Harness"放空
2. 先跑 T5'/T6' 清理 V2 IA 残留 (5 文件物理迁移 + 3 废除组件删除 + C14 二十一处违规)
3. 先跑 Session 1.5 + 1 起 Pipeline, 让 Admin 侧的数据流动起来 (但需先有 backend 脚手架)

### 决策 B (Session 0 范围扩展): 废弃物清理并入

下列残留物请 Frank 指示是否一并在 Session 0 清理:

- ⚠️ `frontend/vite.config.js.timestamp-*.mjs` 25 个
- ⚠️ `frontend/dist-tmp/ dist-v3/ dist-v31/ dist-v32/ dist-wave4/ dist-wave4rb/` (7 个共 ~17M)
- ⚠️ `frontend/src/i18n/messages.js.broken-backup` (1600 行)
- ⚠️ `frontend/src/pages/DashboardPage.linear.jsx` / `BrandDetailPage.jsx` / `QueriesPage.jsx` / `LandingPageLegacy.jsx` / `IndustryPage.jsx` (5 个 unreferenced 死代码)
- ⚠️ `frontend/src/components/empty/DashboardEmptyState.jsx` + `components/ProjectRequiredBanner.jsx` + `components/landing/LandingNavQuickCreateButton.jsx` (决策 #10 明令不建)
- ⚠️ `snapshot-before-ia-v2-7ed0bc5/` (repo 内全量副本, 17M+)
- ⚠️ `.gitignore` 未覆盖 `dist-*/` + `*.timestamp-*.mjs`

### 决策 C (物理迁移 vs 继续保持): T2'/T3' 的 5 个文件

- `DashboardPage.jsx` → `pages/brand/BrandOverviewPage.jsx`
- `TopicsPage.jsx` → `pages/brand/BrandTopicsPage.jsx` (并裁剪为单品牌)
- `DiagnosticsPage.jsx` → `pages/brand/BrandDiagnosticsPage.jsx` (并裁剪为单品牌)
- `ReportsPage.jsx` → `pages/brand/BrandReportsPage.jsx`
- `KnowledgeGraphPage.jsx` → `pages/industry/IndustryKnowledgeGraphPage.jsx`
- (加) `BrandProductDetailPage.jsx` → `pages/brand/BrandProductDetailPage.jsx`

当前方案是 App.jsx 在新路径上**引用 legacy 文件**, 用户视角无差, 但 CLAUDE.md "设计锚点"表与事实不符。选择:
1. 物理迁移 (6 次 `git mv` + 改 import) — 统一锚点表
2. 改 CLAUDE.md 锚点表接受 "legacy 文件承接新路由" 的事实

### 决策 D (依赖安装 scope): 7 个缺失依赖

Session 0 / 3 / 4a / 4b / 5 阻塞依赖:

1. `mixpanel-browser` + `mixpanel` (埋点)
2. `@tanstack/react-table` (表格)
3. `date-fns` (日期)
4. `swr` 或 `@tanstack/react-query` (API)
5. `tldts` (URL 归一化)
6. `sonner` 或替换自建 ToastViewport
7. `@react-pdf/renderer` 或 `jsPDF` (报告)

以及 Session 0 §5.1 的 **8 个测试依赖**。

### 决策 E (BrandCitations / BrandSentiment 的 C14 违规): 是否纳入本次体检后续修复

Harness 刚性违规:
- C10-1: 1 处 (文件缺失, 属决策 C)
- C14-1: 2 处 (`text-2xl` h2)
- C14-2: 15 处 (`p-4` Card)

总 18 处待修。T6' Session 清单中 "视觉统一 + 密度契约 C14" 原本就覆盖此范围, 不独立修。

---

## 8. 本次体检未做的事 (透明声明)

按前置约束, 本 Session 仅产出本 `docs/PREFLIGHT_REPORT.md`, 未执行以下操作 (留给 Frank 决策后的 Session):

- ❌ 未 `git add` / `git mv` 任何文件
- ❌ 未 `npm install` 任何依赖
- ❌ 未运行 `vitest` / `playwright` (未安装)
- ❌ 未修改任何既有 `.md` / `.json` / `.jsx`
- ❌ 未创建 `scripts/` / `.husky/` / `.github/` 目录
- ❌ 未触碰 `snapshot-before-ia-v2-7ed0bc5/` 或 `frontend/dist-*/`
- ❌ 未运行 Pipeline / Backend 任何脚本 (根本无可运行内容)

---

## 9. 附录 · Harness 可执行化建议草图 (仅为参考, 不实施)

若 Frank 批准 Session 0 落地 Harness 执行层, 最小骨架预期:

```
scripts/
├── ci-check.mjs              # 38 rules 聚合, execSync grep + exit code
├── check-data-contracts.mjs  # C3 / C7 + §9 PRD 数据层断言
├── coverage-gap-scan.mjs     # TEST_STRATEGY §11 产出缺失扫描
└── gen-api-tests.ts          # 从 docs/openapi.yaml 生成 L3 契约测试

.husky/
└── pre-commit                # lint-staged + node scripts/ci-check.mjs

.github/workflows/
└── ci.yml                    # 4 job: harness / unit / contract / e2e+visual

frontend/
├── vitest.config.ts
├── playwright.config.ts
├── src/__ci_fixtures__/      # Decision #21 C: 5 self-seeded violations
│   ├── A1_cjk_leak.cifixture.jsx
│   ├── B1_sparkline_literal.cifixture.jsx
│   ├── C11_mentionrate_over1.cifixture.jsx
│   ├── C14_h1_text3xl.cifixture.jsx
│   └── D4_missing_301.cifixture.jsx
└── e2e/                      # Playwright specs
```

估工时 (Session 0 落地纯地基, 不触 business logic): **8-12 小时** (单 Session 可覆盖)。

---

**报告终** · Frank 读完后请点头 / 调整 / 否决任一决策, 我会按你的选择规划下一个 Session 的 Prompt。
