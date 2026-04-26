# Session 4b' · IA v2.0 完整化 — JSX→TSX + 真实 FastAPI 集成 (M4 收尾, MVP 完成)

> **Status**: Phase A 规划锁定 (2026-04-26) — 由 `docs/REPLAN_2026_04_26.md` §4 触发的 Python pivot **第 11/11 个**, 也是**最后一个** Session Prompt
>
> **Description**: 在已就位的 App 后端 (Sessions 0' / A0' / 4a' / 1' / 1.5' / 1.2' / 2' / 2.1' / 3') + Admin 全部 (A0' + A1') 之上, 落地 **App 端 18 个 React+TSX 页面** — Brand Mode 9 子页 (overview / visibility / topics / sentiment / citations / products / competitors / diagnostics / reports) + Industry Mode 4 子页 (overview / ranking / topics / knowledge-graph) + 横切 5 页 (landing / register / login (AuthPage Email-first) / onboarding 4-step / settings) — 全部接入 Sessions 1'-3' + 4a' 的真实 FastAPI 端点, 构建 IA v2.0 完整产品形态。
>
> **Dependencies (硬前置)**:
>   - **Session 4a'** Auth + Onboarding (`POST /api/v1/auth/*` + `GET/POST /api/v1/onboarding/*` + `DraftProject` 72h TTL + Route Guard)
>   - **Session 3'** 分析引擎 + CSV export + MCP API (`/api/v1/brands/*` / `/api/v1/industries/*` / `/api/v1/topics/*` / `/api/v1/citations/*` / `/api/v1/csv/export?type=*`)
>   - **Session 2.1'** Planner LLM Refinement (Topic / Prompt / Query 数据已存在并可被读取展示)
>   - **Session 1.5'** KG Platform Layer (Industry / Category / Brand / Product 节点 + 关系边可读)
>   - **Session 1.2'** Adapter live (真实 ai_responses 数据驱动 Brand Mode 5 KPI)
>   - **Session A1'** Admin (`admin.preview.genpano.dev` 子域已独立; **本 Session 不动 admin 子域**, 只动 `app.preview.genpano.dev`)
>   - **Session 0'** CI/CD + preview env (Vercel app subdomain + Render API service)
>
> **Milestone**: M4 (MVP 完成) — 4b' Phase Gate Frank 接受标准 = 在 `app.preview.genpano.dev` 上注册新用户 → 完成 4-step onboarding → 落到 `/brand/overview` 看见**真实** mention rate / SoV / sentiment / citation share / industry rank 5 KPI; 切到 `/brand/visibility` 看 Topic Heatmap 渲染真实 mentionRate; 切到 `/industry/topics` 看 Topic × Intent 矩阵; 任一 Brand Mode 页点 CSV 导出能下载真实 utf-8 csv。**4b' 完成 = MVP 完成**, 不再有后续 MVP Session。
>
> **Branch (决策 #31)**: `session-4bprime` 从 main fork (在 A1' 已合 main 之后); **不 cherry-pick** 历史 claude/* 分支 TS-era JSX 代码 — claude/* 分支可作为**视觉参考只读**, 但所有 TSX 代码从空白文件夹基于 `docs/PRD.md §4.6-IA-v2` + `docs/DESIGN_TOKENS.md` C1-C15 重写; 所有提交按 §5 12-Step Delivery 原子化, 每步独立 commit
>
> **Truth Source Authority**: 本 Session 以 `docs/PRD.md` (master) + `docs/DESIGN_TOKENS.md` (视觉契约 C1-C15) + `docs/CLAUDE_CODE_SESSIONS.md` (Session 实施约束, 旧 TS 版本 4b 任务清单作 IA reference) 三份为唯一真相源, **不引用 ADMIN_PRD.md** (`feedback_genpano_app_truth_source.md`)。Citation 行为细节 cross-ref `docs/PRD.md §4.2.6 / §4.2.7`。

---

## §0 Pre-Flight Grep Contract (决策 #25 Rule 2 + Rule 11)

**开工第一批动作必须先跑下列 12 条 grep, 输出与本 Prompt §1 真相源索引一致才能进入 §5 实施步骤; 不一致则停在 §3 STOP Type B 等 Frank alignment, 严禁推进。**

```bash
# F1. 确认 PRD §4.6-IA-v2 IA v2.0 master 段未漂移 (Brand Mode 9 + Industry Mode 4)
rg -n "§4\.6-IA-v2" docs/PRD.md | head -10
rg -n "/brand/(overview|visibility|topics|sentiment|citations|products|competitors|diagnostics|reports)" docs/PRD.md | head -20
rg -n "/industry/(overview|ranking|topics|knowledge-graph)" docs/PRD.md | head -10

# F2. 确认 PRD §4.6.4 CSV export 8 接入点 + 8 exportType 未变
rg -n "ExportCsvButton|exportType" docs/PRD.md | head -20

# F3. 确认 DESIGN_TOKENS C1-C15 全部存在 + 行号锚点
rg -n "^### C\d{1,2}" docs/DESIGN_TOKENS.md | head -20

# F4. 确认 Sessions 4a'/3'/A1' 已 PASS (CLAUDE.md 决策号已落)
rg -n "决策 #(3[2-3]|3[4-9])" CLAUDE.md | head -10

# F5. 确认 4a' Onboarding 路由契约 (Route Guard `302 /onboarding?resumeStep=`)
rg -n "/onboarding\?resumeStep" docs/PRD.md docs/SESSION_4A_PRIME_PROMPT.md 2>/dev/null | head -10

# F6. 确认 3' API 端点契约 (FastAPI route paths)
rg -n "@router\.(get|post)\(.\/" backend/app/api/v1/ 2>/dev/null | head -30

# F7. 确认 main 分支 frontend/ 是空 (决策 #31, claude/* 分支不 cherry-pick)
ls frontend/src/pages/ 2>/dev/null || echo "EMPTY (expected)"
ls frontend/src/admin/pages/ 2>/dev/null && echo "A1' DELIVERED — keep, do not touch"

# F8. 确认 pyproject.toml / package.json 前端栈是 vite + react 19 + typescript 5.x + @types/react + tailwindcss + recharts + tldts (URL 归一化, 决策 #19) + msw (mock service worker for dev)
rg -n '"(react|typescript|vite|tailwindcss|recharts|@tanstack/react-query|tldts|msw|@playwright/test)"' frontend/package.json 2>/dev/null

# F9. 确认 PRD §4.1.1-form AuthPage Email-first 2-step 仍是契约
rg -n "§4\.1\.1-form" docs/PRD.md | head -5

# F10. 确认 PRD §4.10.4a i18n 覆盖矩阵 (UI / Alerts / Settings 全双语)
rg -n "§4\.10\.4a|formatBrand" docs/PRD.md | head -10

# F11. 确认 PRD §4.11 埋点事件 (#63-#65 保留, #44/#45/#46 弃用, #70 onboarding_step_completed 新增)
rg -n "事件 #(44|45|46|63|64|65|70)" docs/PRD.md | head -10

# F12. CLAUDE.md 最近 3 条决策对 4b' 范围影响 (Rule 11) + .auto-memory 近 7 天
rg -n "^\d+\." CLAUDE.md | tail -3
ls -lt .auto-memory/feedback_*.md 2>/dev/null | head -5
```

**Pre-flight 失败的 per-grep STOP 映射 (决策 #25 规则 12 + 规则 11)**:

| Grep | 失败条件 | STOP 类型 | 处置 |
|---|---|---|---|
| F1 | PRD §4.6-IA-v2 Brand Mode 9 sub-views 或 Industry Mode 4 sub-views 路径漂移 | **Type B** | 走 §3 STOP B1; IA v2.0 是 master, 不可偏离 |
| F2 | PRD §4.6.4 CSV export 8 exportType 数量 ≠ 8 (字段加减或重排) | **Type B** | 走 §3 STOP B2; 决策 N18 是否需要重排, Frank 决定 |
| F3 | DESIGN_TOKENS.md C1-C15 任一缺失或被重命名 (Frank 删 / 重命名) | **Type B** | 走 §3 STOP B3; tokens 是视觉契约, 任一删除会让前端漏渲 |
| F4 | Sessions 4a' / 3' / A1' 任一未 PASS (CLAUDE.md 决策 #32-#39 任一缺) | **Type A** (依赖未就绪) | 暂停实施, 等前置 Session 宣绿; 不做 best-effort |
| F5 | 4a' Onboarding `?resumeStep=` 契约不符 PRD §4.1.1d.C | **Type B** | 走 §3 STOP B4; 走规则 4 双向同步 |
| F6 | Session 3' API 端点路径不在 `/api/v1/brands/:id/*` 命名空间 | **Type B** | 走 §3 STOP B5; 端点契约迁移走规则 4 |
| F7 | main 分支 `frontend/src/pages/` 已存在 (违反决策 #31 expected empty) | **Type B** | 走 §3 STOP B6; 决议 cherry-pick 还是按决策 #31 重写 |
| F8 | `frontend/package.json` 缺 react@19 / vite / typescript / tailwindcss / recharts / tldts / msw / @playwright/test 任一 | **Type A** | Step 0 `pnpm add` 补齐, 不 STOP; 但若 react 主版本 (e.g. 18) 不一致 → STOP Type B (架构选型) |
| F9 | PRD §4.1.1-form AuthPage Email-first 被回退 (Step 0 设计漂移) | **Type B** | 走 §3 STOP B7; 决策 #29 (AuthPage Email-first) 是硬约束 |
| F10 | PRD §4.10.4a i18n 覆盖矩阵 + `formatBrand` 单一入口契约不存在 | **Type B** | 走 §3 STOP B1; i18n 是 day-1 架构契约 (决策 #11/#14) |
| F11 | PRD §4.11 埋点事件 #44/#45/#46 仍存在 (应弃用) 或 #70 未落 | **Type B** | 走规则 4 双向同步, 检查决策 #10 / #20 是否被回滚 |
| F12 | CLAUDE.md 最新 3 条决策对 4b' 范围有影响 (规则 11) | **不一定 STOP** | 列变化清单进 §1 freshness check; 若变更涉及 IA / 路由 / DESIGN_TOKENS → Type B; 仅 cosmetic 可继续 |

**任一 F1-F11 STOP 立即停下, 写 alignment note 给 Frank; F12 列 diff 进 §1。**

---

## §1 Truth Source Index (决策 #25 Rule 5)

### 引用 (Read-only, 本 Session 不修改)

| 真相源 | 段号 / 文件 | 用途 |
|---|---|---|
| PRD.md | §4.6-IA-v2 | **IA master**: Brand Mode 9 + Industry Mode 4 sub-views; topbar pill toggle 🎯 ⇌ 🌍; URL prefix `/brand/*` vs `/industry/*` (不落 localStorage); BrandPicker; Engine Compare Segmented Control (view transform, 不是路由) |
| PRD.md | §4.6-IA-v2.K-N + M.5/M.6 | V2 6 深度分析页 (Visibility / Topics / Sentiment / Citations / Products / Competitors) FilterBar 唯一出口 + Heatmap + Tier 2 引用域矩阵 + Same-Group 卡 + 决策 #20 全部约束 |
| PRD.md | §4.6-IA-v2.O | BrandProductDetailPage `?brandId=` query string 契约 (Wave-4 终版, 决策 #20 + DESIGN_TOKENS C15) |
| PRD.md | §4.6.4 | CSV export 8 接入点 + 8 exportType + AuthPromptModal + return_to allowlist + UTF-8 BOM + 1k 行 confirm dialog + 10k 行 413 + 5/min rate limit + `export_log` 表 90d 清理 |
| PRD.md | §4.1.1-form | AuthPage Email-first 2-step (identifier-first 状态机, lookup ≥400ms anti-enum) — `/login` `/register` 都 mount AuthPage 从 Step 0 起步 |
| PRD.md | §4.1.1-gate | Auth-Required (决策 #9): Landing + /auth + /register 是仅有匿名页; Brand 直链 `/brand/overview?brandId=` 未登录 → `/register?redirect=&brandHint=` |
| PRD.md | §4.1.1d.C | Onboarding 4-step `DraftProject` 72h TTL + Route Guard `302 /onboarding?resumeStep=` + 事件 #70 |
| PRD.md | §4.1.1e | 登出 6 步契约 (track 先于 mixpanel.reset) + L1 UserMenu / L2 SettingsPage inline / L3 SessionExpiredModal + BroadcastChannel 跨 tab |
| PRD.md | §4.2.4 / §4.2.4.A | Sentiment 0.5 tiebreak `[0,0.45] neg / (0.45,0.55) neutral / [0.55,1.0] pos`; 单一入口 `classifySentiment()`; UI Donut size=180 不文本百分比 (DESIGN_TOKENS C12) |
| PRD.md | §4.2.5 | Brand Topics (TopicIntentMatrix 共享给 Brand Mode + Industry Mode, v3.2 决策) |
| PRD.md | §4.2.6 (A-H) | Citation 原始层: 5 级 Tier / brand-attributed share / PANO A 公式 / `citation_source_loss` T-14d / `citation_attribution_mismatch` 互斥诊断 |
| PRD.md | §4.2.7 (A-H) | Citation 行动面 6 条: 归因诊断 / 内容策略 (`/brand/citations?tab=content-gap`) / 外联 PR / 竞品解构 (Authority Radar 5 维 + Same-Group + Acquisition v1.1) / Simulator (推 v1.1, MVP 4b' **不开**) / 3 MCP 工具 |
| PRD.md | §4.5.2 | MCP API 工具列表 (4b' 只展示 token 状态 + 文档 link, **不实现 token 签发** — 推 A5'/Phase 2) |
| PRD.md | §4.6.0a | UI 禁止开发约束语泄漏 (rate limit / DOM selector / retry 等技术词) |
| PRD.md | §4.7.0-a / §4.8.x | 报告 Stack (L1 观察 / L2 解释 + causalChain + confidence / L3 方向 + anchorQuestions + ifUntreated) + 三读者视角 (operator/manager/branding); MVP 4b' **只渲染** 后端已生成的 report JSON, **不实现 PDF 生成** (推 Phase 2) |
| PRD.md | §4.10.3.A | Intent × Engine × Locale 23 行决策矩阵 (4b' 不修改, 只读取 Topic.intent / Engine.id 映射展示) |
| PRD.md | §4.10.4a | i18n 覆盖矩阵: messages.json + Alerts 双语 + formatBrand 唯一入口 + CI 三条 grep |
| PRD.md | §4.11 埋点 | 事件 #50-#56 Citation / #57-#61 AuthPage / #63-#65 Auth-Required gate / #70 onboarding_step_completed; **#44/#45/#46 弃用** (E1-E4 Empty State 废除, 决策 #10) |
| DESIGN_TOKENS.md | C1 | Sparkline 100% 默认 (无固定 scale) |
| DESIGN_TOKENS.md | C2 | 排行 / 分布柱图: 单色 + 标签 (避免 chart-N 引擎色混用) |
| DESIGN_TOKENS.md | C3 | SoV "其他" 不大于任一真实品牌片 (mock 数据契约) |
| DESIGN_TOKENS.md | C4 | Sentiment 整数百分比, 不 `.toFixed(2)` 给用户 |
| DESIGN_TOKENS.md | C5 | 锯齿模数禁: 禁 `i % N === 0 ? ±V : 0` 正弦波 |
| DESIGN_TOKENS.md | C6 | Hero 排行变体 (顶部 KPI 栏渲染规则) |
| DESIGN_TOKENS.md | C7 | BRANDS.ranking ≡ panoScore DESC 严格 (mock + UI 双向锚点) |
| DESIGN_TOKENS.md | C8 | Drawer 契约 (右抽屉宽度 / overlay / focus trap) |
| DESIGN_TOKENS.md | C9 | Heatmap 不借 chart-N 引擎色 (sequential / diverging 色带专属) |
| DESIGN_TOKENS.md | C10 | **Brand Mode FilterBar 唯一出口** — 6 个深度分析页顶部 mount `<BrandAnalysisFilterBar>`, URL state via `useBrandAnalysisFilters()` hook 读 `?from=&to=&engines=&profileGroup=&dimensions=&intents=`, 跨 sub-view 状态同步; 禁本地 `useState('7d')` 绕过 URL |
| DESIGN_TOKENS.md | C11 | mentionRate **小数 [0,1] 存储**, UI `(value * 100).toFixed(1)%` 渲染; 全局禁 `mentionRate ≥ 1` literal (修 1620% bug) |
| DESIGN_TOKENS.md | C12 | Sentiment Distribution 必须 `<DonutChart size={180}>`, 禁 3 个 text-3xl 文字百分比 |
| DESIGN_TOKENS.md | C13 | `CompetitorQuadrantChart` 必须暴露 `bubbleRadius={[rMin,rMax]}` (默认 `[8, 24]`) + `showLabels` prop, sqrt 面积正比映射, 禁 400px 霸屏 |
| DESIGN_TOKENS.md | C14 | V2 密度规范 (text-xl 页标题 / text-xs 副标题 / text-[13px] card header / p-3 card / space-y-3 根节奏) |
| DESIGN_TOKENS.md | C15 | `BrandProductDetailPage` brandId 走 query string 契约 — `useSearchParams()[0].get('brandId')`, 禁 `useParams()` 解构 |
| CLAUDE_CODE_SESSIONS.md | Session 4b (legacy TS) | IA reference (8 接入点 / AuthPromptModal / 速率限制 / export_log); Python rewrite **不照搬代码**, 只取交付项语义 |
| CLAUDE.md | 决策 #2 / #9 / #10 / #11 / #13 / #15 / #16 / #17 / #18 / #19 / #20 / #25 / #29 / #30 / #31 | IA v2.0 / Auth-Required / Onboarding 替代 Empty State / i18n / Engine-aware Prompt / non-brand 提及率 / 可伸缩筛选栏 / 测试自动化 A++ / Citation / V2 视觉统一 / Prompt 公约 / Python pivot / preview env / branch-per-session |

### 前置依赖 (Prerequisites, 决策 #25 规则 12 Type A4)

**任一前置 Session 未 GREEN, 立即 STOP Type A 等待, 不做 best-effort, 不 mock 前置 Session 的产出。** 头部 `Dependencies (硬前置)` 块列了 7 项, 此处按 GREEN 校验维度精炼为 4 个最小依赖锚点:

| 前置 Session | GREEN 条件 (CLAUDE.md 决策号 + Phase Gate) | 本 Session 依赖点 |
|---|---|---|
| **Session 3'** | CLAUDE.md 新增决策记录 Session 3' Phase Gate PASS; FastAPI `/api/v1/brands/*` `/api/v1/industries/*` `/api/v1/topics/*` `/api/v1/citations/*` `/api/v1/csv/export?type=*` 全部线上可调; OpenAPI schema 暴露在 `https://api.preview.genpano.dev/openapi.json` | 21 个 frontend 页面全部消费 3' 端点; `npm run gen:api-types` 拉 OpenAPI 生成 `src/lib/api-types.ts`; 5 KPI / Heatmap / Citation 5 Tab / CSV 8 接入点全 wire 真实 endpoint, 禁 mock |
| **Session A1'** | CLAUDE.md 新增决策记录 Session A1' Phase Gate PASS; Admin Citation Tier CRUD UI 已上 `admin.preview.genpano.dev`; `citation_domain_authority` 表至少 5 行 active Tier (1.0/0.7/0.4/0.15/0.0); `basePriceByTier` 参数表已 seed | `/brand/citations?tab=content-gap` Tier 2 覆盖矩阵 + Authority Radar 5 维数据来自 A1' 维护的 Tier 表; Citation Simulator 4b' **不实现编辑器** (推 A5'/Phase 2), 但只读展示需要 Tier active 数据 |
| **Session 4a'** | CLAUDE.md 新增决策记录 Session 4a' Phase Gate PASS; `/api/v1/auth/*` + `/api/v1/onboarding/*` + `DraftProject` 72h TTL + Route Guard `302 /onboarding?resumeStep=` 全线上 | `<RouteGuard>` + `<OnboardingGuard>` 配合 4a' 后端 302; AuthPage Email-first 2-step (PRD §4.1.1-form) lookup 调 4a' `/api/v1/auth/lookup`; OnboardingPage 4-step 调 4a' `/api/v1/onboarding/draft` |
| **Session 0'** | CLAUDE.md 决策 #30 + Vercel app subdomain DNS 已生效 + Render API service 已 up | 本 Session Phase Gate Layer 3 = Frank 在 `app.preview.genpano.dev` 浏览器跑完整 S1-S8 旅程; CI/CD pipeline (lint + typecheck + vitest + harness selftest + Playwright smoke 1 路径) 已建 |

**Verification (开工 Step 0 前必跑, 全 GREEN 才进入 §5 Step 1)**:

```bash
# 验证前置 Session 全部 PASS (CLAUDE.md 决策号已落)
rg -n "Session (3'|A1'|4a'|0').*Phase Gate.*PASS" CLAUDE.md docs/SESSION_PROGRESS.md 2>/dev/null
rg -n "决策 #(30|31|32|33|34|35|36|37|38|39)" CLAUDE.md | head -10

# 验证 Session 3' API 端点线上可调 (preview env smoke)
curl -fsSL https://api.preview.genpano.dev/openapi.json | jq '.paths | keys | length' 2>/dev/null  # 期望 ≥ 30 paths
curl -fsSL https://api.preview.genpano.dev/health 2>/dev/null  # 期望 {"status":"ok"}

# 验证 A1' Citation Tier 表 seed 完整 (admin 域 5 行 active)
rg -n "citation_domain_authority|basePriceByTier" backend/app/migrations/ 2>/dev/null | head -5

# 验证 4a' Onboarding 路由契约
rg -n "/onboarding\?resumeStep|DraftProject" backend/app/api/v1/ 2>/dev/null | head -10
```

**任一 verification 失败 → STOP Type A**: 写 alignment note 给 Frank, 列出未就绪的前置 Session 和缺失的 GREEN 条件; 不推进到 §5 Step 1, 不 mock 前置端点假装绿。

### 修改 (本 Session 写入或新建)

| 真相源 | 修改类型 | 落点 |
|---|---|---|
| `frontend/src/main.tsx` + `App.tsx` | 新建 | Vite + React 19 + React Router v6 entry; `<RouteGuard>` (auth-required) + `<OnboardingGuard>` (zero-Project 检查 → `/onboarding`) + `<AdminRouteGuard>` (admin 域 isolated, A0' 已有, 复用) |
| `frontend/src/pages/landing/LandingPage.tsx` | 新建 | Hero + 5 KPI 数据预览 (DESIGN_TOKENS 浅色 Stripe) + CTA 指 `/register` 带 UTM (`feedback_genpano_landing_v21.md`) |
| `frontend/src/pages/auth/AuthPage.tsx` | 新建 | Email-first 2-step 状态机 (PRD §4.1.1-form); `/login` + `/register` 都 mount; lookup ≥400ms anti-enum |
| `frontend/src/pages/onboarding/OnboardingPage.tsx` | 新建 | 4-step (industry → primary brand → competitors → preferences); `DraftProject` 72h resume; 事件 #70 onboarding_step_completed |
| `frontend/src/pages/brand/*.tsx` | 新建 | 9 子页 (BrandOverviewPage / VisibilityPage / TopicsPage / SentimentPage / CitationsPage / ProductsPage / ProductDetailPage / CompetitorsPage / DiagnosticsPage / ReportsPage) — 共 10 页 (含 product detail) |
| `frontend/src/pages/industry/*.tsx` | 新建 | 4 子页 (IndustryOverviewPage / RankingPage / TopicsPage / KnowledgeGraphPage); KnowledgeGraph 用 AntV G6 v5 (`feedback_genpano_g6_knowledge_graph.md` 8 坑点) |
| `frontend/src/pages/settings/SettingsPage.tsx` | 新建 | 账号 / Project / 偏好 / 通知 + L2 inline 登出 (PRD §4.1.1e) |
| `frontend/src/components/shell/*` | 新建 | Topbar (BrandPicker + Mode toggle pill + 🔍 搜索 ⌘K + 🔔 告警铃 + 👤 UserMenu) + Sidebar (Brand Mode 9 项 / Industry Mode 4 项 派生自 URL prefix) + AppLayout |
| `frontend/src/components/filterbar/BrandAnalysisFilterBar.tsx` + `useBrandAnalysisFilters.ts` | 新建 | DESIGN_TOKENS C10 唯一出口; URLSearchParams 读 `?from=&to=&engines=&profileGroup=&dimensions=&intents=`; 主筛选始终可见 + 扩展筛选折叠 |
| `frontend/src/components/charts/*.tsx` | 新建 | DonutChart / Sparkline / BrandTopicHeatmap (sequential 色带 mentionRate / diverging 色带 sentiment) / TopicIntentMatrix (跨 Brand+Industry 共享, v3.2 决策) / CompetitorQuadrantChart (C13 sqrt + showLabels) / AuthorityRadar (5 维) / Tier2CoverageMatrix (color-mix intensity) |
| `frontend/src/components/csv/ExportCsvButton.tsx` + `AuthPromptModal.tsx` | 新建 | 8 接入点共用; 未登录弹 AuthPromptModal 带 `?return_to=&hint=...`; 1k confirm / 10k 413 / 429 toast |
| `frontend/src/components/auth/*` | 新建 | UserMenu / SessionExpiredModal / `useAdminAuth` 已 admin 侧, app 侧 `useAuth` 新建; BroadcastChannel 跨 tab logout |
| `frontend/src/i18n/messages.json` (zh-CN + en-US) | 新建 | 双语全覆盖, formatBrand 单一入口 (`feedback_genpano_app_truth_source.md`); 不进 JSX literal CJK |
| `frontend/src/lib/api.ts` + `frontend/src/lib/queries/*.ts` | 新建 | TanStack Query v5 wrapper; per-route React Query factories; 401 → 重定向 `/login?redirect=` |
| `frontend/src/lib/mixpanel.ts` | 新建 | 事件 #50-#65 + #70; 登出 6 步契约 track 先于 reset (`project_genpano_logout_session_4_1_1e.md`) |
| `scripts/ci_check.py` | 扩展 | Group I 6 条新规则 (I1-I6, 见 §4 Layer 2) |
| `scripts/ci_harness_selftest.py` | 扩展 | EXPECTED_POSITIVES 32 → 38 (I1-I6 fixture self-seeded) |
| `frontend/playwright.config.ts` + `frontend/tests/e2e/*` | 新建 | 6 关键路径 E2E (smoke 1 路径 in-Session, 余 5 留给 Phase 4 Visual 决策 #18) |
| `vercel.json` | 扩展 | `app.preview.genpano.dev` 子域 + SPA fallback rewrite |
| `docs/CLAUDE_CODE_SESSIONS_PYTHON.md` | 更新 | 4b' 完成标志 + Phase Gate 验收记录 + MVP COMPLETE 状态 |

### 真相源版本警告 (规则 11)

1. **决策 #20 V2 6 深度分析页 FilterBar 唯一出口必读**: `Visibility / Topics / Sentiment / Citations / Products / Competitors` 顶部必须 mount `<BrandAnalysisFilterBar>`; 任何 sub-view 出现 `useState('7d')` / 本地时间筛选 = I4 Harness block; URL state 是 cross-sub-view 同步唯一机制。
2. **决策 #20 mentionRate 小数 [0,1] 契约**: 全 mock data + 全 API response + 全 UI 逻辑用小数; UI 渲染唯一句式 `(value * 100).toFixed(1)%`; 任何 `mentionRate >= 1` literal 数值 = I3 Harness block (修 1620% bug 决策)。
3. **决策 #20 BrandProductDetailPage brandId query string 契约**: `useSearchParams()[0].get('brandId')` 唯一; 禁 `const { brandId } = useParams()` (会 undefined 触发"暂无数据"空白页) — I5 Harness block; productId 走 path, brand 可为 null (降级而非空白)。
4. **决策 #19 Citation Tier 推 A5/Phase 2**: 4b' 不实现 Tier CRUD 编辑器 + Simulator 编辑器, 但 `/brand/citations` 5 Tab 含 `?tab=content-gap` 必须实现 (PRD §4.2.7.B); Authority Radar 5 维 + Tier 2 覆盖矩阵 必须渲染 (后端数据已 ready, 前端只读)。
5. **决策 #15 提及率 non-brand 口径**: 5 KPI 卡 mention rate 默认 dimension='品类' (CSV 列 `mention_rate_pct` non-brand + `mention_rate_all_pct` 全量双列); UI 文案不提技术细节, 只显示数字。
6. **决策 #11+#12 i18n China-first**: `messages.json` zh-CN + en-US 双 key 必须对偶完整; 任何只 zh 缺 en 的 key = A2 Harness block (沿用 Session 0' Group A 已建); JSX 内禁 CJK literal — 必须 `t('key')`。
7. **决策 #9 Auth-Required Route Guard**: `<RouteGuard>` 包裹除 `landing / auth (login+register) / forgot-password` 之外的所有路由; 未登录访问 `/brand/*` `/industry/*` `/settings` `/onboarding` → 重定向 `/register?redirect=<原 URL>` (Brand 直链额外带 `&brandHint=<name>`)。
8. **决策 #10 零 Project Route Guard → /onboarding**: 登录后 `<OnboardingGuard>` 检查 `User.projects.length === 0` → 强制重定向 `/onboarding`; 草稿 (`DraftProject` 72h) 重定向时附 `?resumeStep=N`。**E1/E2/E3/E4 Empty State 不实现** — 任何 DashboardEmptyState / ProjectRequiredBanner / LandingNavQuickCreateButton 出现 = I6 Harness block。
9. **决策 #18 测试自动化 A++**: 4b' 内只跑 1 路 Playwright smoke E2E (register → onboarding → /brand/overview), 视觉回归 `toHaveScreenshot` + 余 5 路 E2E 推 Phase 4; OpenAPI 契约自动生成是 Session 3' 已建, 4b' 只 consume 不重建。
10. **决策 #29 Python pivot**: API 全在 FastAPI, 前端通过 TanStack Query 消费; 不再有 Next.js API Routes; OpenAPI 自动从 FastAPI 生成 → `frontend/src/lib/api-types.ts` (openapi-typescript 命令 in `package.json`)。
11. **决策 #30 Frank Layer 3 验收**: 在 `app.preview.genpano.dev` 浏览器实操跑 S1-S8 完整新用户旅程, 不接受 mock 截图。
12. **决策 #31 branch-per-session**: `session-4bprime` 从 main HEAD fork, claude/* 分支 JSX 仅作视觉参考**只读**, 不 cherry-pick — 所有 TSX 从 PRD §4.6-IA-v2 + DESIGN_TOKENS C1-C15 重新写。

---

## §2 MVP Scope-Cut Declaration (决策 #25 Rule 10)

### ✅ 本 Session 做 (Y1-Y45)

**横切基础设施 (Y1-Y6)**

- **Y1** Vite + React 19 + TypeScript 5 strict + Tailwind + DESIGN_TOKENS CSS 变量 + React Router v6 入口; `npm run dev` 起 5173 端口
- **Y2** TanStack Query v5 client + 401 拦截器 (重定向 `/login?redirect=`); `frontend/src/lib/api.ts` axios+interceptor 包装; per-route query factories
- **Y3** OpenAPI typegen: `npm run gen:api-types` 跑 `openapi-typescript http://api.preview.genpano.dev/openapi.json -o src/lib/api-types.ts`; CI 检查 typegen drift (PR 必须重 gen 才合 main)
- **Y4** i18n: `frontend/src/i18n/messages.zh-CN.json` + `messages.en-US.json`; `useTranslation()` hook + `formatBrand(brand, locale)` 单一入口 (PRD §4.10.4a); JSX 零 CJK literal
- **Y5** Mixpanel client + 事件 #50-#65 + #70 全部 typed; 登出 6 步契约 helper (`logoutOrchestrator()`: track → invalidate session → broadcast → clear cookies → mixpanel.reset → 重定向)
- **Y6** msw (mock service worker) dev-only, 在后端不可达时让 UI 仍可渲染 (Phase Gate Layer 3 还是要求 Vercel preview 接真后端)

**App Shell + Route Guard (Y7-Y10)**

- **Y7** `<AppLayout>` + `<Topbar>` (BrandPicker + Mode toggle 🎯⇌🌍 + 🔍 ⌘K + 🔔 + 👤 UserMenu); Mode toggle 触发 URL prefix 切换 (`/brand/*` ↔ `/industry/*`), 不落 localStorage
- **Y8** `<Sidebar>` 派生自 URL prefix; Brand Mode 9 项 + Industry Mode 4 项; 侧栏底部 Project 一行小灰字 (MVP 隐身, 决策 #2)
- **Y9** `<RouteGuard>` (auth-required) + `<OnboardingGuard>` (zero-Project → `/onboarding`); 配合 4a' Route Guard 后端 `302 /onboarding?resumeStep=N`
- **Y10** `<SessionExpiredModal>` (token expired 唯一出口) + `<UserMenu>` 登出 (PRD §4.1.1e L1) + Settings inline 登出 (L2); BroadcastChannel 跨 tab 同步

**Auth + Onboarding (Y11-Y14)**

- **Y11** `LandingPage` (DESIGN_TOKENS 浅色 Stripe 风, Hero + 3 价值 + 数据示例 + CTA `/register?utm=landing`); 浅色单一视觉语言 (`feedback_genpano_landing_v21.md`)
- **Y12** `AuthPage` Email-first 2-step (PRD §4.1.1-form): Step 0 输入 email → lookup ≥400ms anti-enum → Step 1 (login: 输 password / register: 输 password + 阅读条款 / forgot: 发邮件); `/login` `/register` 都 mount; URL `?redirect=&brandHint=` 流转
- **Y13** `OnboardingPage` 4-step 状态机: Step 1 选行业 → Step 2 选主品牌 (从 KG 检索 brand) → Step 3 选 ≤5 竞品 → Step 4 偏好 (locale + email 通知频率); 进度条 + 上一步可回; 中途退出走 4a' `DraftProject` 72h; 每步成功调 `POST /api/v1/onboarding/draft` + 触发 Mixpanel #70
- **Y14** Settings 页: 账号信息 (邮箱只读 / locale 切换) / Project 列表 (主品牌 + 竞品 + 偏好) / 通知偏好 / "登出" L2 inline

**Brand Mode 9 子页 (Y15-Y29)**

- **Y15** `/brand/overview` — 5 KPI (提及率 / SoV / Sentiment / 引用份额 / 行业排名), Engine Compare Segmented Control (view transform 不切路由), Sparkline 时序; 接 `GET /api/v1/brands/:id/overview?profileGroup=&engines=&from=&to=`
- **Y16** `/brand/visibility` — `<BrandAnalysisFilterBar>` (C10 mount) + `<BrandTopicHeatmap>` (sequential 色带 mentionRate 0-1 真实比值); 接 `GET /api/v1/brands/:id/visibility/heatmap`
- **Y17** `/brand/topics` — FilterBar mount + `<TopicIntentMatrix>` (PRD §4.2.5, 共享 v3.2 决策) + ProfileGroupSampleWarning + 4-stat grid; 接 `GET /api/v1/brands/:id/topics`
- **Y18** `/brand/sentiment` — FilterBar mount + `<DonutChart size={180}>` (C12) Sentiment Distribution + `<BrandTopicHeatmap>` (diverging 色带 sentiment); 接 `GET /api/v1/brands/:id/sentiment`
- **Y19** `/brand/citations?tab=overview|content-gap|pr-targets|tier-coverage|domains` — 5 Tab (PRD §4.2.7.B)
- **Y20** Citation Tab `overview` — Authority Share 时序图 + `citation_attribution_mismatch` P2 alert + 5 级 Tier 分布
- **Y21** Citation Tab `content-gap` — `mentioned − attributed` 反向 + 页面类型对比 (PRD §4.2.7.B)
- **Y22** Citation Tab `pr-targets` — `pr_score` 排序表 + Tier 2 覆盖矩阵 + KOL Shannon entropy 多样性卡 + CSV #9 export 按钮
- **Y23** Citation Tab `tier-coverage` — `<Tier2CoverageMatrix>` 我 + Top 3 竞品 × 8 权威域 (color-mix intensity)
- **Y24** Citation Tab `domains` — Authority Radar 5 维 + Same-Group 共享域卡带 group 元信息 (M.6)
- **Y25** `/brand/products` — `<BCGQuadrant>` (C13 sqrt + showLabels + bubbleRadius) + Sparkline Grid + 表格 + 关系边 (Wave-4 4 区终版); 接 `GET /api/v1/brands/:id/products`
- **Y26** `/brand/products/:productId?brandId=:brandId` — **C15 契约**: `useSearchParams()[0].get('brandId')`; productId 走 path; brandId 缺失走 `PRODUCTS.find()` 反查; Legacy `/brands/:brandId/products/:productId` 301 → V2 路径 (vercel.json rewrite)
- **Y27** `/brand/competitors` — Top 3 威胁卡 → 选中 → Authority Radar + 胜负 Heatmap + 30d 趋势 + Tier 2 覆盖矩阵 + Same-Group 卡 (PRD §4.6-IA-v2.M.5/M.6); 接 `GET /api/v1/brands/:id/competitors`
- **Y28** `/brand/diagnostics` — Diagnostic 列表 (P1/P2/P3 优先级) + 单条详情 (`citation_source_loss` / `citation_attribution_mismatch` 互斥 + DOM change + 提及率骤降); Layer 3 anchor questions (PRD §4.7.0-a, 不给 playbook 保留咨询业务边界); 接 `GET /api/v1/brands/:id/diagnostics`
- **Y29** `/brand/reports` — 报告列表 + 单报告渲染 (体检 7 页 + Quick Wins / Strategic Bets / Branding Risks / Consulting Accelerators 四层); MVP 4b' **不生成 PDF**, 只渲染后端 JSON; 接 `GET /api/v1/brands/:id/reports`

**Industry Mode 4 子页 (Y30-Y33)**

- **Y30** `/industry/overview` — Hero 3 cards + 行业 KPI; 接 `GET /api/v1/industries/:slug/overview`
- **Y31** `/industry/ranking` — 排行榜 (panoScore DESC, C7 严格); 接 `GET /api/v1/industries/:slug/ranking`
- **Y32** `/industry/topics` — v3.2 5 段 (FilterBar / Hero 3 cards / Radar / `<TopicIntentMatrix>` 共享 / Drawer); 接 `GET /api/v1/industries/:slug/topics`
- **Y33** `/industry/knowledge-graph` — AntV G6 v5 radial 力导向图 (`feedback_genpano_g6_knowledge_graph.md` 8 坑点: radial / 不用 hover-activate / 放大胜利者 / shadowBlur / label 外置 / autoFit / 单一 composer / base style 显式 opacity); 接 `GET /api/v1/industries/:slug/kg`

**CSV Export 8 接入点 (Y34-Y41, PRD §4.6.4)**

- **Y34** `<ExportCsvButton>` 共享组件 + `<AuthPromptModal>` 未登录弹窗 (return_to allowlist); UTF-8 BOM + 1k confirm + 10k 413 + 429 toast
- **Y35** Brand Mode `/brand/overview` 角落接入 (exportType=`brand_overview`)
- **Y36** Brand Mode `/brand/visibility` 接入 (exportType=`brand_visibility_heatmap`)
- **Y37** Brand Mode `/brand/citations?tab=pr-targets` 接入 (exportType=`pr_targets`, CSV #9)
- **Y38** Brand Mode `/brand/products` 接入 (exportType=`brand_products`)
- **Y39** Brand Mode `/brand/diagnostics` 接入 (exportType=`brand_diagnostics`)
- **Y40** Industry Mode `/industry/ranking` 接入 (exportType=`industry_ranking`)
- **Y41** Industry Mode `/industry/topics` 接入 (exportType=`industry_topics`)

**Harness + 测试 + Deploy (Y42-Y45)**

- **Y42** Group I Harness 6 条 (I1-I6) + 6 self-seeded fixture (`frontend/src/__ci_fixtures__/I*.cifixture.tsx`); selftest 32 → 38
- **Y43** Vitest 单测 80% (跑 `frontend/src/lib/**` + `frontend/src/components/**`); 不测路由组件 (推 Playwright)
- **Y44** Playwright smoke E2E 1 路径: register → email-first lookup → password → onboarding 4 step → land on `/brand/overview` → 看到 5 KPI 渲染 (非 0 非 mock); 余 5 路 E2E 推 Phase 4
- **Y45** Vercel `app.preview.genpano.dev` 子域 + SPA fallback rewrite + Legacy 301 (11 条决策 #2); GitHub Actions `app-preview.yml` 自动部署; main merge 触发生产候选

### ❌ 本 Session 不做 (N1-N18)

- **N1** Citation Simulator (PRD §4.2.7.E) — 推 v1.1 / Phase 2; 4b' 不实现 Tier delta 滑杆 + basePriceByTier 编辑器
- **N2** Citation Tier CRUD 编辑器 (决策 #19) — 推 A5'/Phase 2; 但只读 Tier 表渲染 (Authority Radar 5 维) 必须做 (Y24)
- **N3** MCP Token 签发 + Bearer 用户面板 (PRD §4.5.2) — 推 A5'/Phase 2; 但 `/settings` 显示 MCP 文档 link + Token 状态 (active/none) 必须做
- **N4** 报告 PDF 生成 (PRD §4.7.0-a + §4.8.x) — 推 Phase 2; 4b' 只渲染后端 JSON 形式报告, 不调 puppeteer/weasyprint
- **N5** 体检 7 页 PDF / 行业线索 PDF / 行业报告 PDF — 推 Phase 2 (同 N4)
- **N6** Acquisition 事件流 (PRD §4.2.7.D v1.1) — 推 v1.1
- **N7** KOL Shannon entropy 多样性算法 — 后端推 Phase 2; 4b' 仅展示后端给的 entropy 数值 (Y22 单卡)
- **N8** Phase 4 视觉回归 `toHaveScreenshot` + 余 5 路 Playwright E2E (决策 #18) — 推 Phase 4
- **N9** Multi-turn dialogue Query (决策 #26.C2) — 推 Phase 2
- **N10** Mobile responsive 布局 — 推 Phase 2; 4b' 假设 desktop ≥1280px
- **N11** Custom Dashboard / drag-and-drop 自定义布局 — 推 Phase 2
- **N12** Phase 2 多 Project Picker 显式暴露 (决策 #2) — MVP Project 隐身
- **N13** E1-E4 Empty State (决策 #10 已废除) — Onboarding 替代; 任何 `DashboardEmptyState` / `ProjectRequiredBanner` / `LandingNavQuickCreateButton` 复活 = I6 Harness block
- **N14** Engine Compare 改回 Tab (决策 #2 已 deprecated) — 必须 Segmented Control
- **N15** 跨品牌 `/diagnostics` 顶层路由 (决策 #2 已废除) — 必须挂在 `/brand/diagnostics`
- **N16** Auth 第三方登录 (Google / GitHub OAuth) — 推 Phase 2; MVP 仅 email + password
- **N17** Admin 子域 (`admin.preview.genpano.dev`) — 由 A1' 独立交付, 4b' 不动 admin 路由代码
- **N18** Citation `?tab=simulator` Tab — 与 N1 一致, 4b' 5 Tab 不含 simulator

---

## §3 STOP-Trigger Template (决策 #25 Rule 12)

### Type A · 环境失败

- **A1**: `npm install` 拉 react@19 + typescript@5 + recharts + tldts + @tanstack/react-query + msw + @playwright/test 失败 → 停, 检查 npm registry 与 lockfile
- **A2**: `npm run gen:api-types` 拉 OpenAPI schema 失败 (后端 API 不可达 / openapi.json 404) → 停, 检查 Render API service 是否 healthy + Session 3' OpenAPI 端点是否暴露
- **A3**: Vercel preview build 红 (TypeScript strict / vite-plugin / SPA rewrite / 子域 DNS) → 停, Vercel dashboard 检查
- **A4**: Vite dev server 起不来 (5173 端口冲突 / Tailwind PostCSS 配置错) → 停
- **A5**: `app.preview.genpano.dev` DNS 未生效 → 停, alignment Frank check Cloudflare DNS record
- **A6**: msw 拦截配置在 production build 出现 (应只 dev) → 停, 是 vite.config.ts mode 检查 bug
- **A7**: Playwright `npm run e2e` 起不来 (浏览器二进制未装 / playwright install 失败) → 停
- **A8**: GitHub Actions `app-preview.yml` 红 (任一 lint / typecheck / vitest / playwright smoke / build) → 停, 修绿才推下一步
- **A9**: AntV G6 v5 引入冲突 (peer dep / 浏览器 ResizeObserver 警告) → 停, 按 8 坑点逐一对照

### Type B · 真相源冲突

- **B1**: §0 grep F1 输出 IA v2.0 sub-views 路径漂移 (`/brand/*` 9 项 ≠ overview/visibility/topics/sentiment/citations/products/competitors/diagnostics/reports 9 项) → 停, alignment Frank
- **B2**: §0 grep F2 输出 CSV exportType ≠ 8 (PRD §4.6.4 列表) → 停, 决策 N18 是否需要重排
- **B3**: §0 grep F3 输出 DESIGN_TOKENS 缺 C1-C15 任一 (Frank 删 / 重命名) → 停
- **B4**: §0 grep F5 输出 4a' Onboarding `?resumeStep` 契约不符 → 停, 走 Rule 4 双向同步
- **B5**: §0 grep F6 输出 Session 3' API 端点路径漂移 (FastAPI route 不在 `/api/v1/brands/:id/*`) → 停
- **B6**: §0 grep F7 输出 main 已有 `frontend/src/pages/` (决策 #31 期望空) → 停, 决议 cherry-pick 还是重写
- **B7**: §0 grep F9 输出 PRD §4.1.1-form AuthPage Email-first 被回退 → 停
- **B8**: PRD §4.6-IA-v2 子页数 ≠ 13 (9 brand + 4 industry; Frank 偷加 / 删) → 停
- **B9**: PRD §4.2.7 Citation 行动面 6 条结构变更 (Tab 数 ≠ 5) → 停
- **B10**: ADAPTER_CONTRACT 引擎枚举从 3 (chatgpt/doubao/deepseek-CN) 变更 → 停, BrandMode Engine Compare Segmented Control 选项要重画

### Type C · 范围溢出

- **C1**: 实施进入 Citation Simulator (N1) → 停
- **C2**: 实施进入 PDF 生成 (N4/N5) → 停
- **C3**: 实施进入 Acquisition / KOL entropy 算法 (N6/N7) → 停, 后端给数前端只展示
- **C4**: 实施进入 Phase 4 视觉回归 / 余 5 路 E2E (N8) → 停
- **C5**: 实施进入 Mobile responsive (N10) → 停
- **C6**: 实施进入 OAuth (N16) → 停
- **C7**: 实施进入 admin 路由代码 (N17) → 停, A1' 独立子域
- **C8**: 出现 E1-E4 Empty State 任一组件 (N13) → 停, I6 Harness violation
- **C9**: Engine Compare 出现 Tab 而非 Segmented Control (N14) → 停
- **C10**: 顶层 `/diagnostics` 出现 (N15) → 停
- **C11**: TSX 单文件 > 500 行 → 停, 拆分组件
- **C12**: TSX 页面数超过 18 (Brand 9 + 1 product detail + Industry 4 + 5 横切 = 19; product detail 算 Brand 9 中 Y26 不另计) → 停, 检查冗余
- **C13**: 任何 `useState('7d')` / 本地时间筛选状态绕过 URL — 停, I4 violation
- **C14**: 任何 `mentionRate >= 1` literal 数值 (含 mock) — 停, I3 violation
- **C15**: 任何 JSX 内 CJK literal — 停, A1 (Group A) violation; 必须 `t('key')`
- **C16**: 任何 sentiment `(value * 100).toFixed(2)` (而非 toFixed(0)) — 停, B4 (Group B) violation 决策 #18 + DESIGN_TOKENS C4
- **C17**: 任何 `.toFixed(2)` 给 mentionRate (用户层面) — 停 (用 `.toFixed(1)`)
- **C18**: cherry-pick claude/* 分支提交 — 停, 决策 #31 violation
- **C19**: Mixpanel 事件追加属性中含 PII (邮箱 / IP / 名字) — 停, 决策 #21 D2 violation
- **C20**: `/brand/citations` 出现第 6 个 Tab (`?tab=simulator` 等) — 停, N18 violation

---

## §4 Phase Gate 3-Layer (决策 #30)

### Layer 1 · `scripts/verify_4b.sh` 单脚本本地全绿

```bash
#!/usr/bin/env bash
# scripts/verify_4b.sh — 本地 + CI 共用 (preview 部署前必须 0 错误)
set -euo pipefail

cd frontend

# L1.1 ESLint 0 errors (含 react-hooks / a11y / formatBrand-required)
npm run lint

# L1.2 TypeScript strict 0 errors
npx tsc --noEmit

# L1.3 Vitest 单测 80% 覆盖率 (lib + components, 不含 pages)
npm run test:coverage -- --reporter=default
# 检查覆盖率 stmts/branches/funcs/lines 全部 ≥ 80%

# L1.4 vite build 成功 + 产物 size < 2MB gzipped
npm run build
test -d dist/ && du -sh dist/

# L1.5 OpenAPI typegen drift 检查 (预 commit 必须重 gen)
npm run gen:api-types
git diff --exit-code src/lib/api-types.ts || (echo "OPENAPI DRIFT" && exit 1)

# L1.6 i18n 双语对偶完整 (zh-CN 每个 key 在 en-US 必须有, vice versa)
node scripts/check-i18n-parity.mjs

# L1.7 ci_check.py Group I 6 条
cd ..
python scripts/ci_check.py --group I

# L1.8 harness selftest 32 → 38
python scripts/ci_harness_selftest.py | grep -q "selftest: PASS  (38 / 38"

# L1.9 Playwright smoke E2E (1 路径: register → onboarding → /brand/overview)
cd frontend
npx playwright install --with-deps chromium
npm run e2e:smoke

# L1.10 Lighthouse a11y (manual: 主要页面 score ≥ 90; CI 跑 4 页面 desktop)
npm run lighthouse:a11y

# L1.11 DESIGN_TOKENS 强制 lint (C1-C15 grep 无违规)
node scripts/check-design-tokens.mjs

# L1.12 Mixpanel 事件 schema 检查 (#50-#65 + #70 全部 typed, 0 PII attribute)
node scripts/check-mixpanel-events.mjs

echo "[verify_4b] ALL GREEN"
```

### Layer 2 · Harness Group I 6 条 + selftest 32 → 38

| Rule | 名称 | 扫描路径 | 拦截语义 |
|---|---|---|---|
| **I1** | `sparkline-must-default-to-100-percent-scale` | `frontend/src/components/charts/Sparkline*.tsx` + 所有调用点 | DESIGN_TOKENS C1; Sparkline 出现 `domain={[fixed, value]}` 或 `min/max` 写死 → block; 必须用 dataset min/max 自动 |
| **I2** | `sentiment-percentage-must-be-integer` | `frontend/src/**/*.tsx` | DESIGN_TOKENS C4; sentiment 数值给用户时 `.toFixed(1)` `.toFixed(2)` `.toFixed(3)` → block; 必须 `.toFixed(0)` 或 `Math.round()` |
| **I3** | `mention-rate-must-be-decimal-zero-to-one` | `frontend/src/**/*.{ts,tsx}` + `frontend/src/data/**` (mock) | DESIGN_TOKENS C11; literal `mentionRate: 1` `mentionRate: 100` `mentionRate: 1620` → block; UI 渲染必须 `(value * 100).toFixed(1)%` |
| **I4** | `brand-analysis-pages-must-mount-filter-bar` | `frontend/src/pages/brand/{Visibility,Topics,Sentiment,Citations,Products,Competitors}*.tsx` | DESIGN_TOKENS C10; 必须出现 `<BrandAnalysisFilterBar>` 组件; 任何 `useState('7d')` 或本地时间 state literal → block |
| **I5** | `product-detail-brandid-must-be-query-string` | `frontend/src/pages/brand/ProductDetailPage.tsx` | DESIGN_TOKENS C15; 出现 `useParams()` + 解构 `brandId` → block; 必须 `useSearchParams()[0].get('brandId')` |
| **I6** | `no-empty-state-components-allowed` | `frontend/src/**/*.tsx` | 决策 #10; 文件名 `DashboardEmptyState` `ProjectRequiredBanner` `LandingNavQuickCreateButton` 任一存在 → block; Onboarding 替代 |

6 个 self-seeded fixture 在 `frontend/src/__ci_fixtures__/I{1..6}_*.cifixture.tsx`, 每个故意触发对应规则 (memory `feedback_fixture_naming.md`: docstring **故意不 mention** 必要 token, 否则 `content.includes()` 自满足导致 selftest silently pass); `EXPECTED_POSITIVES` 32 → 38; selftest 必须打印 `selftest: PASS  (38 / 38 fixture expectations met)`。

### Layer 3 · Frank 浏览器实操验收 (preview env, 决策 #30)

Frank 在 `app.preview.genpano.dev` 子域执行下列 8 步, 全部成功后 4b' 关闭:

- **S1** 打开 `https://app.preview.genpano.dev/` → 看见 LandingPage Hero (DESIGN_TOKENS 浅色 Stripe) + 5 KPI 数据预览 (非占位 0); 点 "免费试用" CTA → URL 变 `/register?utm=landing`
- **S2** AuthPage 输入新邮箱 → 看到 lookup spinner ≥400ms → 进入 Step 1 注册表单 (输 password + 阅读条款) → 提交 → 1s 内重定向 `/onboarding?resumeStep=1`
- **S3** Onboarding Step 1 选 "美妆个护" → Next → Step 2 BrandPicker 输 "雅诗兰黛" 或 "Estée Lauder" → 看到 KG 检索结果 + 选中 → Next → Step 3 选 ≤5 竞品 (L'Oréal / SK-II 等) → Next → Step 4 偏好 (locale=zh-CN, 周报频率) → "完成" → 1s 内重定向 `/brand/overview`
- **S4** `/brand/overview` 看到 5 KPI 卡 (mention rate / SoV / sentiment / citation share / industry rank) 全部**真实数值** (非 0 / 非 NaN); Sparkline 30d 时序; Engine Compare Segmented Control 切换 `chatgpt | doubao | deepseek-CN` 数字变化
- **S5** 切到 `/brand/visibility` → 顶部 `<BrandAnalysisFilterBar>` 显示 + URL 变 `?from=&to=&engines=&profileGroup=` → BrandTopicHeatmap 渲染 sequential 色带 (mentionRate 0-1 真实比值, 不超过 100%)
- **S6** 切到 `/brand/products` → BCGQuadrant 渲染 4 象限 + 点某产品 → 跳到 `/brand/products/<productId>?brandId=<brandId>` → **不出现"暂无数据"空白页** (C15 契约); 详情页渲染产品 GEO 数据
- **S7** 任一 Brand Mode 页角落点 "导出 CSV" → 1s 内浏览器下载 utf-8 csv (UTF-8 BOM 头, 第一行字段名 zh-CN); 然后切到 Industry Mode `/industry/topics` → 同样导出 → 同样下载成功
- **S8** Frank 在终端 `curl https://app.preview.genpano.dev/api/v1/brands/<id>/overview -H "Cookie: app_session=..."` → 返回真实 JSON (非 503 非 401), 字段对应 PRD §4.6-IA-v2 5 KPI

只要任一 S 步红, 4b' Phase Gate 不绿, 回 §5 修后再来。**Frank 不接受截图替代浏览器实操** (`feedback_genpano_session_preview_env_2026_04_26.md`)。

---

## §5 12-Step Delivery Order (原子 commit)

每步独立 commit, 标题格式 `Session 4b' Step N: <topic>` (决策 #25 + commit rule):

| Step | 主题 | 关键交付物 |
|---|---|---|
| **0** | branch + Vite 脚手架 + 依赖 | `git checkout -b session-4bprime` (从 main, 在 A1' 合并之后); `frontend/` 起 Vite + React 19 TS strict + Tailwind + DESIGN_TOKENS CSS vars; `npm install` (Y1 依赖); 跑通 `npm run dev` |
| **1** | i18n + formatBrand + Mixpanel client + msw scaffold | Y4-Y6; `messages.zh-CN.json` + `messages.en-US.json` 双语对偶; `formatBrand()` 单一入口; Mixpanel 事件 typed; msw dev-only 配置 |
| **2** | API client + TanStack Query + OpenAPI typegen | Y2-Y3; `gen:api-types` 跑通 (后端 OpenAPI 已 ready by Session 3'); 401 拦截器; `useBrandOverview()` `useIndustryRanking()` 等 hooks |
| **3** | App Shell + Topbar + Sidebar + Mode Toggle + RouteGuard | Y7-Y10; URL prefix-derived sidebar; BroadcastChannel logout; SessionExpiredModal; 配合 4a' 后端 |
| **4** | LandingPage + AuthPage Email-first + Onboarding 4-step | Y11-Y13; PRD §4.1.1-form 状态机 + lookup ≥400ms; `DraftProject` 72h resume (4a' API); 事件 #57-#61 + #70 |
| **5** | SettingsPage + L1/L2 登出 + UserMenu | Y14; PRD §4.1.1e 6 步契约 helper; SettingsPage Project + 偏好 + 通知 + L2 inline 登出 |
| **6** | Charts 共享组件库 (DESIGN_TOKENS C1-C13 全部) | DonutChart (C12 size=180) / Sparkline (C1) / BrandTopicHeatmap (C9 sequential+diverging) / TopicIntentMatrix / CompetitorQuadrantChart (C13) / AuthorityRadar / Tier2CoverageMatrix; vitest 单测 80% |
| **7** | Brand Mode 9 子页 (含 product detail) | Y15-Y29; 接 Session 3' API; FilterBar mount (C10); product detail brandId query string (C15); Citation 5 Tab |
| **8** | Industry Mode 4 子页 + AntV G6 v5 KG 图 | Y30-Y33; G6 8 坑点对齐; TopicIntentMatrix 共享 (v3.2 决策) |
| **9** | CSV Export 8 接入点 + AuthPromptModal + 11 Legacy 301 | Y34-Y41 + vercel.json rewrite (`/dashboard` → `/brand/overview` 等 11 条) |
| **10** | Group I Harness 6 条 + 6 self-seeded fixture | `scripts/ci_check.py` Group I 段; 6 fixture 在 `__ci_fixtures__/`; `ci_harness_selftest.py` 32→38 |
| **11** | Playwright smoke E2E + verify_4b.sh + Vercel preview deploy | Y44-Y45 + scripts/verify_4b.sh + GitHub Actions `app-preview.yml`; preview push → Vercel 自动 deploy + Render API 接入 |
| **12** | Frank Layer 3 + CLAUDE.md 决策 #33 + .auto-memory + main merge → MVP COMPLETE | Frank S1-S8 全绿; CLAUDE.md 决策 #33 (Session 4b' 交付细节 + 偏差 C1/C2/...); `.auto-memory/project_genpano_mvp_completed.md`; PR `session-4bprime` → main fast-forward; **MVP COMPLETE 标志** |

每步收尾必须先跑 `scripts/verify_4b.sh` 全绿 → `git add -A && git commit -m "Session 4b' Step N: <topic>"` → 推送; 中间任一步 verify 红, **不推**, 修绿再推。

---

## §6 完成判定 + 收尾动作 (规则 7)

4b' Phase Gate 关闭条件 ≡ §4 三层全绿 (L1.1-L1.12 全 green + L2 selftest 38/38 + L3 Frank S1-S8 全过)。

收尾必做 4 件事 (规则 7 一致性回路):

1. **回跑 §0 Pre-flight grep F1-F12**: 真相源未漂移确认; 若漂移走 §3 Type B 流程
2. **CLAUDE.md 决策 #33 写入**: 含 A 段 (实施摘要 — 18 TSX 页 + 6 Harness + 8 CSV 接入点) / B 段 (偏差登记 C1/C2/... 按 Rule 3) / C 段 (与 §1 修改清单的 actual delta) / D 段 (**MVP COMPLETE 宣告** — 11 个 Python pivot Session 全部交付)
3. **`.auto-memory/project_genpano_mvp_completed.md` 写入**: 索引添加到 MEMORY.md, 记录 18 TSX 页 + 6 Group I Harness + 8 CSV 接入点 + Frank 实操 S1-S8 验收完成 + Phase 2 候选清单
4. **`docs/CLAUDE_CODE_SESSIONS_PYTHON.md` 状态更新**: 4b' 标 ✅; **Milestone 4 ✅ COMPLETE**; 在 master 索引顶部加 "**MVP COMPLETE 2026-04-XX**" 横幅; Phase 2 候选 Session (A2'/A5'/Citation Simulator/PDF 生成 等) 列出, 不属 MVP 关键路径

---

## §7 后续依赖 (无 — MVP 完成)

**4b' 完成 ≡ MVP 完成 ≡ 11 个 Python pivot Session 全部就位**:

```
0' (CI/CD) ✅ → A0' (Admin Auth) ✅ → 4a' (App Auth + Onboarding) ✅
            ↓
1' (Adapter framework) ✅ → 1.5' (KG Platform) ✅ → 1.2' (Adapter live) ✅
            ↓
2' (Planner Pipeline) ✅ → 2.1' (Planner LLM Refinement) ✅
            ↓
3' (Analysis + CSV + MCP API) ✅ → A1' (Admin UI 17 页) ✅
            ↓
4b' (App UI 18 页 + 真实集成) ✅ ← YOU ARE HERE
            ↓
        MVP COMPLETE
```

**Phase 2 候选 (不属 MVP, 不在本 Session)**:
- **A2'** — Multi-role RBAC (ops_admin / data_ops / support / bizdev)
- **A5'** — Citation Tier CRUD + MCP Token 签发 + 60s Redis blacklist
- **Citation Simulator v1.1** — Tier delta 滑杆 + basePriceByTier 编辑器
- **报告 PDF 生成** — 体检 7 页 / 行业线索 / 行业报告
- **Phase 4 视觉回归** — `toHaveScreenshot` 40 baseline + 余 5 路 E2E
- **Multi-turn dialogue Query** — followUpPromptId 拓展
- **Mobile responsive** — 全站 320-1280px
- **Module D Phase 2** — Alerts inbox / Schedule kill switch / Comms / Commercial leads / MCP-ops
- **Pipeline Analyzer** — Quality / QA 两子页 (ADMIN_PRD_B §3.1/§3.2)
- **KG Phase 2** — C7 Entity Merger / C8 KG Diff / C9 Quality Monitor (★ 三深化页)
- **OAuth 第三方登录** — Google / GitHub
- **Project 多视角** — ProjectPicker 显式暴露 + 多 Project 切换

---

## §8 Decision-Freshness Final Check (规则 11)

| Check | 状态 | 备注 |
|---|---|---|
| CLAUDE.md 最近 3 决策 (#29 Python pivot / #30 preview env / #31 branch-per-session) | ✅ 已 thread 入 §1 真相源 + §3 STOP A8/C18 + §4 Layer 3 |
| .auto-memory 近 7 天: `feedback_genpano_session_commit_rule.md` / `feedback_genpano_app_truth_source.md` / `feedback_genpano_no_api_scraping.md` / `feedback_genpano_branch_per_session.md` / `feedback_genpano_session_preview_env_2026_04_26.md` | ✅ commit 规则 / 真相源分立 / response_source labeling / branch / preview env 全部 thread 入 §3 + §4 + §5 Step 12 |
| .auto-memory 视觉契约: `feedback_production_deps.md` (recharts/AntV G6/TanStack 等成熟库) / `feedback_genpano_g6_knowledge_graph.md` (8 坑点) / `feedback_genpano_landing_v21.md` (浅色 Stripe) | ✅ Y6 Charts + Y33 KG + Y11 LandingPage 全部对齐 |
| .auto-memory 决策记录: `project_genpano_brand_industry_mode_ia.md` (IA v2.0 master) / `project_genpano_product_detail_brandid_contract.md` (C15) / `project_genpano_industry_overview_plan_s_v2.md` (v3.2 跨 Mode 共享) / `project_genpano_review_2026_04_21_closure.md` (38 harness 5 组) | ✅ §1 真相源 + §3 STOP B6/B8 + §4 Layer 2 全部 thread |
| PRD.md §4.6-IA-v2 supersession 完整 (废除 §4.6.1 / §4.6.1-0 / §4.6.1b / §4.6.1d / §4.6.1e 顶层结构 + E1-E4 Empty State) | ✅ 已 thread 入 §1 引用 + §3 STOP B1/C8 + §4 Layer 2 I6 |
| DESIGN_TOKENS C9-C15 (V2 6 深度页 + product detail) | ✅ 已 thread 入 §1 + §3 STOP C13/C14/C16/C17 + §4 Layer 2 I1-I5 |
| 决策 #19 Citation Tier 是否进 4b' | ❌ 已锁 N2 (Tier CRUD 编辑器), 但只读 Tier 渲染必做 (Y20-Y24 Citation 5 Tab); Tier 编辑 + Simulator 推 A5'/Phase 2 |
| 决策 #20 V2 视觉统一 + Heatmap + FilterBar + 数据口径 9 + 3 问 | ✅ 已 thread 入 §1 + §3 STOP C13-C17 + §4 Layer 2 I1-I5 全部覆盖 |
| Phase 2 候选清单完整 (A2' / A5' / Simulator / PDF / Phase 4 / Multi-turn / Mobile / Module D / Analyzer / KG ★ / OAuth / multi-Project) | ✅ §7 列出 12 项 |

**Frank**: 收到本 Prompt 后, 让 Claude Code 第一批动作必须是跑 §0 12 条 grep + 输出对照清单, 与 §1 一致才能进 §5; 不一致 stop alignment。**接受 §2 / §3 / §4 后再发 "go"**。

**这是 Python pivot 11/11 个 Session, 也是最后一个。完成 ≡ MVP COMPLETE。**

---

**END OF SESSION 4B PRIME PROMPT**
