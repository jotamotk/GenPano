# GENPANO

Agent-native 免费 GEO (Generative Engine Optimization) 监测平台。帮助 SEO 从业者和品牌团队追踪品牌在 AI 引擎回答中的可见度、排名和情感表现。

## 项目状态

- **阶段**: MVP 设计完成，准备进入 Claude Code 开发
- **MVP 引擎**: ChatGPT、豆包、DeepSeek
- **MVP 行业**: 4 个（美妆个护、奢侈品、食品饮料、服装时尚）
- **商业模式**: 工具免费，通过行业 GEO 数据报告和优化咨询服务盈利
- **开发方式**: Solo founder (Frank) + AI (Harness Engineering 方法论)

## 核心差异化

- **Data-First, User-Second**: 平台主动采集，用户注册即可看到完整数据
- **Agent-Native**: MCP Server + 结构化 API，AI Agent 可直接消费数据
- **智能大样本监测**: 四层 Pipeline (Topic→Prompt→Query→Response)，行业/品牌/产品三维度自动生成监测主题，每日全量采集

## 目录结构

```
GENPANO/
├── docs/                          # 产品文档
│   ├── PRD.md                     # 产品需求文档 (v1.3) - App 核心文档
│   ├── ADMIN_PRD.md               # Admin 后台 PRD (User / Auth / KG QA / Alerts / System Health)
│   ├── ADMIN_PRD_B_PIPELINE.md    # Admin Pipeline 监控 PRD 分卷
│   ├── ADMIN_PRD_C_KG.md          # Admin 知识图谱管理 PRD 分卷
│   ├── PRODUCT_PLAN.md            # 产品规划 & Milestone
│   ├── CLAUDE_CODE_SESSIONS.md    # App Session 规划 (App 侧开发实施指南)
│   ├── ADMIN_CLAUDE_CODE_SESSIONS.md  # Admin Session 规划 (A0-A5 开发实施指南; §0 固化 Prompt 编写 7 条公约)
│   ├── HARNESS_ENGINEERING.md     # Harness Engineering 方法论
│   ├── TEST_STRATEGY.md           # 4 层测试策略 + 异常场景矩阵 (v1.1)
│   ├── REVIEW_2026_04_21.md       # 4 维度 8 P0 gap 审查报告 (决策 #21 触发源)
│   ├── GROWTH_PLAN.md             # 增长计划（5000 MAU, 300万营收目标）
│   ├── DESIGNER_AGENT.md          # Designer Agent 设计方案（UI/UX Session 角色）
│   ├── DESIGNER_AGENT_CAPABILITIES.md  # Designer Agent 能力规划
│   ├── ADAPTER_CONTRACT.md        # 3 家引擎 Adapter 契约 (Session 1 真相源)
│   └── DATA_MODEL.md              # Prisma schema 语义 + CHECK 约束说明
├── design/                        # 设计稿 & 原型
│   ├── prototype.html / prototype-v2.html / prototype-design-system.html
│   ├── prototype-industry-redesign.html
│   └── architecture-diagram.html / architecture-executive.html
├── review/                        # 产品评审文档
├── scripts/                       # Repo-level scripts
│   ├── ci-check.mjs               # Harness L1 rule registry (A/B/C/D/E/F 共 46 条)
│   ├── ci-harness-selftest.mjs    # Self-seeded fixture 验证 (11 EXPECTED_POSITIVES)
│   └── check-data-contracts.mjs   # Node 运行时 C3/C7 等关系型约束校验
├── backend/                       # 后端代码 (Next.js 14 App Router + Prisma)
│   ├── prisma/
│   │   ├── schema.prisma          # Prisma schema 真相源 (引用 DATA_MODEL.md + ADMIN_PRD §5.6)
│   │   └── migrations/            # 原始 SQL migration (含 CHECK 约束, Prisma DSL 不支持)
│   ├── src/
│   │   ├── app/                   # Next.js App Router
│   │   │   └── admin/api/v1/auth/ # Session A0: login/refresh/logout/forgot-password/reset-password/change-password
│   │   ├── admin/auth/            # Session A0: JWT + cookies + rate-limiter + session + password + middleware 决策
│   │   ├── engines/               # Session 1: Adapter 框架 (doubao/deepseek/chatgpt)
│   │   ├── parsers/               # Session 1: brand-matcher / sentiment / citation / ranking / normalize
│   │   ├── scheduler/             # Session 1: retry / backoff / state / queue
│   │   ├── accounts/              # Session 1: state-machine / pool / prewarm / sms
│   │   ├── har/                   # Session 1: sanitize + recorder (Session 1.2)
│   │   ├── platform/              # Session 1.5: KG 冷启动 (llm / db / discovery / knowledge-graph / scheduler / planner / seed)
│   │   └── __ci_fixtures__/       # Self-seeded Harness violations (D8/D9/D10/F1)
│   ├── middleware.ts              # Edge runtime: /admin/* 路由守卫 (Session A0)
│   ├── scripts/
│   │   ├── admin-bootstrap.ts     # Session A0: 幂等 super_admin 种子脚本
│   │   └── seed-platform-data.ts  # Session 1.5: KG 冷启动端到端编排
│   ├── tests/
│   │   ├── unit/                  # Vitest 单测 (platform / admin/auth / parsers / scheduler / engines)
│   │   ├── integration/           # Session 1.2+: HAR replay
│   │   └── fixtures/              # queries.json + adapters/*.har
│   └── vitest.config.ts           # 80% 覆盖率阈值, coverage include 含 src/platform/** + src/admin/auth/**
├── frontend/                      # 前端代码 (React + Vite + Tailwind)
│   ├── src/
│   │   ├── App.jsx                # 路由总入口 + AdminAuthShell + AdminRouteGuard 嵌套
│   │   ├── components/ui/         # App 侧 UI token
│   │   ├── admin/                 # Session A0: Admin 前端
│   │   │   ├── pages/             # AdminLoginPage / AdminForgotPasswordPage / AdminChangePasswordPage / AdminDashboardPage
│   │   │   ├── context/           # AdminAuthContext (4 状态机 + silent refresh + BroadcastChannel)
│   │   │   ├── components/        # SessionExpiredModal + AdminAuthShell + AdminRouteGuard
│   │   │   └── lib/               # adminApi.js (adminFetch + adminAuthApi)
│   │   ├── __ci_fixtures__/       # Self-seeded Harness violations (A1/B1/C11/C14/D4)
│   │   └── data/mock.js
│   ├── vite.config.js             # /admin/api/* dev proxy → http://localhost:4000 (保 Path=/admin cookie 作用域)
│   └── postcss.config.js
└── CLAUDE.md                      # 本文件
```

## 技术架构要点

- **前端**: React + Vite + Tailwind CSS，Stripe 风格设计系统，Recharts 图表
- **后端**: Next.js API Routes + Prisma + PostgreSQL (Supabase)
- **LLM API**: 火山引擎 API 统一入口（支持 DeepSeek/豆包/GPT，国内直连无需代理）
- **爬取代理**: 海外通过 Ninja Clash 订阅链接获取代理节点（用于 ChatGPT/Gemini 爬取），国内直连用于豆包/DeepSeek（MVP 不用代理，量大后再加）
- **邮件**: Resend + React Email（验证、欢迎、密码重置等事务性邮件，每封邮件 zh-CN/en-US 双模板）
- **认证**: Email + Password，含找回密码流程（one-time token, 24h 有效）
- **国际化**: next-intl（UI 文案）+ 品牌名称多语言字段（nameZh/nameEn/aliases[]）+ Prompt 多语言（zh-CN/en-US）

## 行业知识图谱

平台核心数据基础设施，定义"监测什么"和"谁和谁竞争"：
- **节点**: Industry → Category (品类树, 3级) → Brand → Product
- **品牌关系边**: COMPETES_WITH (竞品), SAME_GROUP (同集团)
- **产品关系边**: COMPETES_WITH (直接竞品), SUBSTITUTES (替代), PAIRS_WITH (搭配), UPGRADES_TO (升级), BUDGET_ALT_OF (平替)
- **构建方式**: LLM 初始化 (冷启动) + Response 挖掘 (持续迭代, 置信度累积)
- **存储**: PostgreSQL 关系表 (kg_categories, kg_brands, kg_products, kg_brand_relations, kg_product_relations)

## 核心数据 Pipeline

```
Knowledge Graph → Planner (Bottom-Up) → Topics → ×Intent → Prompts → ×Profile → Queries → Browser → Responses
```

- **Topic** (监测主题): Planner 从知识图谱自动生成，品类树 + 关系边驱动多层次 Topic
- **Prompt** (提示语): Topic × Intent(informational/commercial/transactional/navigational) 生成自然语言问句
- **Query** (可执行查询): Prompt × Profile(用户画像采样) 组合后的最终执行单元
- **Response** (AI 回答): Browser 执行 Query 后返回的完整回答

## 关键设计决策

> **索引入口 (Plan J D4, 2026-04-26)**: 一行查找走 `docs/DECISION_LOG.md` (29 行表, 含 SUPERSEDED 状态列), 全文展开仍在本文件; CI 守护 `node scripts/decision-log-sync-check.mjs` 拦截两侧漂移。新增决策必须**同 PR**追加 DECISION_LOG.md 一行 + 本文件一节, 编号单调递增不复用 (详见 DECISION_LOG.md 头部编辑规则)。

1. **代理架构**: 只有爬取和通用访问需要代理，LLM API 通过火山引擎国内直连
2. **Brand Mode / Industry Mode 二 Mode IA (2026-04-20 反转, 取代原"三视角分工")**: 侧栏由顶栏 Stripe 风格 pill toggle `🎯 品牌 ⇌ 🌍 行业` 驱动, URL prefix 为 `/brand/*` 或 `/industry/*` (不落 localStorage)。**Brand Mode** 侧栏顶部 BrandPicker + 分析组 7 项 (总览 `/brand/overview` / 可见性 `/brand/visibility` / Topics `/brand/topics` / 情感 `/brand/sentiment` / 引用 `/brand/citations` / 产品 `/brand/products` / 竞品 `/brand/competitors`) + 运营组 2 项 (诊断 `/brand/diagnostics` / 报告 `/brand/reports`)。**Industry Mode** 侧栏顶部 IndustryPicker + 4 项 (总览 `/industry/overview` / 排行榜 `/industry/ranking` / Topics 热度 `/industry/topics` / 知识图谱 `/industry/knowledge-graph`)。**顶栏工具条**: 🔍 搜索 ⌘K / 🔔 告警铃 (跨品牌 Top 5) / 👤 UserMenu。**Engine 对比**从 Tab 改为 Brand Mode 全局筛选条 Segmented Control (view transform, 不是路由)。**Project 在 MVP 隐身**: 无 ProjectPicker, 侧栏底部一行小灰字 + 齿轮跳 Settings; Phase 2 多 Project 再显式暴露。**零 Project 态**: Route Guard 强制重定向 `/onboarding` (独立 4 步引导页, 无 App shell), 取代原 E1/E2/E3/E4 四面 Empty State。**已废除路由**: `/dashboard` → `/brand/overview`, `/brands/:id` → `/brand/overview?brandId=`, `/brands/:id/products/:pid` → `/brand/products/:pid`, `/topics` → `/brand/topics`, `/industries` → `/industry/overview`, `/knowledge-graph` → `/industry/knowledge-graph`, `/diagnostics` (跨品牌聚合) 废除, `/reports` → `/brand/reports`。面板 **5 KPI = 提及率/SoV/情感/引用份额/行业排名** 内容不变, 只是渲染锚点迁到 `/brand/overview`。详见 PRD §4.6-IA-v2 (新增, SUPERSEDES §4.6.1 / §4.6.1-0 / §4.6.1b / §4.6.1d / §4.6.1e 顶层结构)。
3. **数据采集**: 平台级每日全量采集，用户注册前数据已就绪
4. **免费策略**: MVP 全功能免费，Phase 2 自定义数据采集为付费功能
5. **四层 Pipeline**: Topic→Prompt→Query→Response 递进生成，每层有明确职责边界
6. **知识图谱**: Industry→Category→Brand→Product + 关系边，LLM 初始化 + Response 挖掘迭代
7. **Project = 视角过滤器**: 不存储监测数据，只引用平台数据（primaryBrandId + competitorBrandIds + preferences）
8. **用户共建**: 用户提交品牌 → 平台验证 → 纳入图谱成为公共资产，所有同行业用户受益
9. **Auth-Required 数据访问 (2026-04-20, 反转原 Data-Before-Auth)**: 所有数据页与数据 API 必须先登录。Landing + `/auth` + `/register` 是仅有的匿名入口。`/industries` / `/brands*` / `/topics` / `/reports` / CSV / MCP API 全部 Route Guard (RequireAuth HOC + Next.js middleware)。Brand 直链 `/brands/:id` 未登录 → 自动重定向 `/register?redirect=/brands/:id&brandHint=<name>`, 注册表单预填/高亮该品牌名以提升转化。MCP API 从 Day 1 要求 `Authorization: Bearer <apiToken>`, 不存在匿名调用。原 PRD §4.1.1c 路径 A/B/C 三入口架构 **已 SUPERSEDED**, 详见 PRD §4.1.1-gate。**为什么**: 数据稀缺是 GENPANO 的护城河, 免费注册即放开是最优 trade-off; 减少爬虫; MCP 单轨 auth; 转化漏斗更干净 (Landing → /register → 数据, 无探索→转化分叉); MVP 流量小 SEO 未起量, 全站 gate 损失有限。
10. **零 Project 态 Route Guard → /onboarding (2026-04-20, 同日再次简化, 取代 E1/E2 方案)**: §4.1.1d 的 E1/E2/E3/E4 四面 Empty State 模型被 §4.6-IA-v2.F **完全废除**。登录后 Route Guard 检查 `User.projects.length === 0` → 强制重定向 `/onboarding` 独立 4 步引导页 (选行业 → 选主品牌 → 选竞品 → 偏好), 用户根本看不到空 App shell。**没有 E1/E2/E3/E4**, 没有 DashboardEmptyState / ProjectRequiredBanner / LandingNavQuickCreateButton 组件 (若已实现则 Session T4' 删除)。草稿 Project (中途退出) 存 72h, 下次登录 Route Guard 检测到草稿再次重定向续上。**Auth-Required 仍成立** (决策 #9 未变), 只是"进来之后看什么"从空态 CTA 改为强制引导流。埋点 #44/#45/#46 弃用, #63/#64/#65 保留, 新增 #70 onboarding_step_completed。
11. **国际化 China-first, global-ready**: MVP 覆盖中文市场为主，但品牌名称多语言匹配 + Prompt 双语生成 + UI 中英界面从 Day 1 就支持，架构不留技术债（详见 PRD 4.10）
12. **品牌名称多语言匹配**: Brand/Product 模型含 nameZh/nameEn/aliases[]，Response 解析时用归一化匹配（去重音/小写/短别名消歧），保证提及率数据正确性
13. **Engine-aware Prompt 语言**: 豆包/DeepSeek 发中文 Prompt，ChatGPT 发中英双语 Prompt，Prompt 记录 language + appliesToEngines 字段
14. **UI i18n 用 next-intl**: Next.js App Router 原生集成，文案库按域划分命名空间，品牌名按 User.locale 显示对应语言版本
15. **Report 深化框架 (2026-04-16)**: 所有报告/诊断必须同时符合 **洞察 Stack** (L1 观察 / L2 解释含 causalChain+confidence / L3 方向仅含 focusArea + anchorQuestions + ifUntreated) 和 **三读者视角** (operator/manager/branding, 每 Section 声明 primaryReader + insightStackLayers)。**Layer 3 只给锚点问题不给执行剧本**——剧本属于付费咨询业务边界。详见 PRD §4.7.0-a / §4.8.2 / §4.8.2a / §4.8.6。体检 PDF 从 6 页扩为 7 页 (P1 上级导读 + P6 Branding Narrative + P5 三层 Stack 扩展); 线索报告采用 Quick Wins / Strategic Bets / Branding Risks / Consulting Accelerators 四层架构
16. **提及率 non-brand 口径 (2026-04-16)**: 面板 KPI 卡提及率默认只统计 `topic.dimension='品类'` 的 Query (non-brand), 不新增字段。品类 dimension 的 Topic 标题和 Prompt 文本禁止包含品牌名, Planner 配额品类 Topic ≥40%。CSV 导出 `mention_rate_pct` (non-brand) + `mention_rate_all_pct` (全量) 双列
17. **可伸缩筛选栏 (2026-04-16)**: 面板/品牌详情 Toolbar 分主筛选(时间+引擎+画像, 始终可见)和扩展筛选(维度 dimension + 意图 Intent, 折叠/展开); "更多筛选" 按钮 + 角标 + 活跃 tag; Topics 页面同规范
18. **测试高度自动化 A++ (2026-04-17)**: 4 层测试 (L1 Harness grep / L2 Vitest 单测 / L3 契约+HAR 回放 / L4 Playwright E2E+Visual) + 4 支柱 (视觉回归 `toHaveScreenshot` / HAR 录制回放 `routeFromHAR` / OpenAPI 契约自动生成 `openapi-typescript` / CI 自修复 Phase 4 延后). Frank 目标: 每次 PR `npm run ci` 全绿即可 merge, 零日常介入. CI 预算 < 12min, ~40 视觉 baseline, 30+ grep 规则, 80% 单测覆盖, 6 关键路径 E2E. 单一契约源 `openapi.yaml` + `DESIGN_TOKENS.md` C1-C7 + PRD §4.10.4a i18n 覆盖矩阵. 唯一真相源: `docs/TEST_STRATEGY.md`. 严禁手写 API 契约测试 (必须由 OpenAPI schema 生成); 严禁引入第二家视觉回归 (Percy/Chromatic) 替代 Playwright 内置
19. **Citation 全链路固化 + 6 条行动面 (2026-04-17)**: 
    - **§4.2.6 (A-H)** 原始层真相源 — Prisma 模型 `AiCitation` + `CitationDomainAuthority` / 5 级 Tier 表 (0 未知 / 1 官方 1.0 / 2 权威媒体 0.7 / 3 KOL 0.4 / 4 UGC 0.15) / 引擎抽取 (ChatGPT 脚注 + 豆包 `.reference-card` DOM + DeepSeek `.citation-tooltip` DOM) / 3 级归因 (official_domain > co_occurrence > text_match) / `citation_share` = brandsAttributed-based / PANO A = Σ(tier_weight × authorityConfidence) / Σ_industry × 100 / `citation_source_loss` T-14d diff (丢失 ≥3 AND remaining < 70% → P1)
    - **§4.2.7 (A-H)** 行动面 6 条 — (A) 归因诊断: `citation_attribution_mismatch` P2 Alert + Authority Share 时序图, 与 `citation_source_loss` **互斥触发 (grep 拦截)** / (B) 内容策略: `/brands/:id?tab=content-gap` 新子 Tab (品牌详情 4→5 Tab), 反向 `mentioned − attributed` + 页面类型对比 / (C) 外联 PR: `pr_score` 排序 (tier_weight × 竞品覆盖度^0.7 × trending 系数 × 已覆盖降权) + Tier 2 覆盖矩阵 + KOL Shannon entropy 多样性卡 + CSV #9 `pr_targets` / (D) 竞品解构: Authority Radar 5 维 + Same-Group 共享域 + Acquisition 事件流 (v1.1) / (E) Simulator 独立页 `/brands/:id/simulator`, Tier delta 滑杆 + `basePriceByTier` Admin 参数表 (v1.1) / (F) 3 个 MCP 工具 `genpano_get_citations` / `list_pr_targets` / `simulate_authority_boost` + CSV #10 `content_gap` (Phase 2)
    - **硬约束**: Tier 表 + `pr_score` 参数 + `basePriceByTier` 一律 DB/参数服务, 硬编码 = PR block; URL 归一化必须 `tldts`; 诊断 Alert 互斥 grep; UI 禁用开发者约束措辞 (§4.6.0a)
    - **埋点 (§4.11 S12, 事件 #50-#56)**: MVP 仅 #50 attribution_mismatch_viewed / #51 content_gap_tab_viewed / #52 pr_targets_viewed / #53 pr_targets_csv_exported; v1.1 追加 #54 simulator_opened / #55 simulator_run / #56 simulator_cta_click_consulting
    - **三层同步 (2026-04-17)**: PRD §4.2.6 + §4.2.7 + §4.5.2 MCP 工具 + §4.6.1b 5 Tab + §4.6.4 CSV #9/#10 + §4.8.1/§4.8.5 诊断类型 + §4.11.4 S12 / `CLAUDE_CODE_SESSIONS.md` Session 3 §1.7 + Session 4b content-gap/simulator 组件任务 / `mock.js` 新增 13 个 export: `AUTHORITY_SHARE_SERIES` + `ATTRIBUTION_MISMATCH_DIAGNOSTIC` + `CONTENT_GAP_TOPICS` + `CONTENT_GAP_PAGE_TYPE_DISTRIBUTION` + `PR_TARGETS` + `TIER2_COVERAGE_MATRIX` + `KOL_SCORECARDS` + `AUTHORITY_RADAR_DATA` + `SAME_GROUP_SHARED` + `ACQUISITION_EVENTS` + `SIMULATOR_BASELINE` + `SIMULATOR_PRESETS`
    - **任何 citation 功能开发前必须先读 §4.2.6 A-H + §4.2.7 A-H 全文**
20. **V2 分析页视觉统一 + Filter Bar + Heatmap + 数据口径 (2026-04-20, 追加 M.5/M.6 + C13/C14)**: Frank 反馈 9 问 + 傍晚追加 3 问固化为 T6' Session。Brand Mode 6 个深度分析页 (Visibility / Topics / Sentiment / Citations / Products / Competitors) 必须: (1) 顶部 mount `<BrandAnalysisFilterBar>` + 经 `useBrandAnalysisFilters()` hook 读 URL state (`?from=&to=&engines=&profileGroup=&dimensions=&intents=`), 跨 sub-view 状态同步; (2) Visibility/Sentiment 引入 `<BrandTopicHeatmap>` 替代原竞品矩阵表 + 象限图, sequential 色带(提及率) / diverging 色带(情感) 唯一; (3) Competitors 重构"我在哪些维度输给谁" 单一叙事 (Top 3 威胁卡 → 选中 → 雷达 + 胜负 heatmap + 30d 趋势) + **§4.6-IA-v2.M.5 Tier 2 引用域覆盖矩阵** (我 + Top 3 竞品 × 8 权威域, `color-mix` intensity) + **M.6 Same-Group 卡带 group 元信息 + 用户层面解释段** (讲清母集团叙事加强 vs 兄弟品牌 SoV 稀释); (4) mentionRate 全系统统一小数 0-1 存储, UI `(value * 100).toFixed(1)%` 渲染, 修复 1620% bug; (5) Sentiment Distribution 必须 `<DonutChart size={180}>`, 禁 3 个 text-3xl 文字百分比; (6) Products BCG primary 用 sort 替代 reduce, 避免字符串比较 bug; (7) **§4.6-IA-v2.M.5 / C13 `CompetitorQuadrantChart`** 必须暴露 `bubbleRadius={[rMin,rMax]}` (默认 `[8, 24]`) + `showLabels` prop, sqrt 面积正比映射 (修 400px 霸屏 bug); (8) **i18n interpolation API**: `t(key, { brand, count })` 传 values 对象, 禁 `t(key, 'fallback string')` 二路歧义 (修 `{brand} · 共 {count} 款产品` literal 泄漏); (9) **C14 密度规范**: text-xl 页标题 / text-xs 副标题 / text-[13px] card header / p-3 card / space-y-3 根节奏。新增 DESIGN_TOKENS C9-C14 + heatmap 色带 `--color-heatmap-seq-0..5 / --color-heatmap-div-neg-2..pos-2` + 13 条 Harness grep (见 §"V2 分析页统一契约 C9-C15 Harness"); 详见 PRD §4.6-IA-v2.K-N + M.5/M.6 + SESSIONS Session T6'。**Wave-4 (2026-04-20 傍晚, 初版已回滚 + 最终形态)**: 初版误读为"列表页扩 7 区 portfolio aggregate" (⓪ KPI 带状条 / ② Flagship Spotlight / ⑥ Portfolio Prompt Hits + "主推语境" 列), Frank 看到输出后校正: "不对, 我的意思是下钻到某个产品时需要这样的具体的页面", 并在后续澄清 "目前点击某一个详细的产品后, 应该是基于这些产品的 GEO 数据, 但是目前是空的"。**真正固化的是**: `/brand/products/:productId?brandId=:brandId` 详情页的 **brandId 从 query string 读取契约** — `BrandProductDetailPage.jsx` 必须 `useSearchParams()[0].get('brandId')`, 禁止 `const { brandId } = useParams()` (会得 undefined 触发"暂无数据"空白页)。同时: productId 走 path, brand 可为 null (降级而非空白: 品牌链接 disabled, 品牌名 fallback `product.brand`, industry/category 三元短路); 若 brandId 缺失由 `PRODUCTS.find(...)` 反查 `product.brand` 字段反向匹配 BRANDS; Legacy URL `/brands/:brandId/products/:productId` 保留 301 到 V2 路径。**回滚内容**: 列表页 `BrandProductsPage.jsx` 恢复 4 区 (① BCG / ③ Sparkline Grid / ④ 表格 / ⑤ 关系), 删除 ⓪/②/⑥ 三区 + "主推语境" 列 + `buildContexts` + Recharts imports。新增 DESIGN_TOKENS C15 + 3 条 Harness grep (C15-1/2/3) 锁定详情页路由契约; 详见 PRD §4.6-IA-v2.O (重写版) + DESIGN_TOKENS C15 (重写版) + SESSIONS Session T6' Wave-4 (重写为 §12.1-12.4)。**v3.2 Industry Topics 跨 Mode 复用 + 删重复矩阵 (2026-04-21)**: Frank 两问固化 — (A) "Brand × Topic 覆盖矩阵和 Visibility 里面的矩阵有什么区别" → 识别 Industry `<IndustryTopicCoverageHeatmap>` (`brandTopicHits` 0-100 合成 ordinal) 与 Brand Mode `<BrandTopicHeatmap>` (`mentionRate` 0-1 真实比值) 回答同一"brand × topic 覆盖强弱"问题, MVP mock 期后者语义更强 → **删除 Industry Coverage Heatmap 组件 + 段**; (B) "Topic × Intent 交叉矩阵这个挺好, 是不是也可以放到品牌这个地方" → 组件零 brand 依赖 (只用 `topic.topicName / topic.mentionCount / topicIntentBreakdown`) → **`git mv components/industry/IndustryTopicIntentMatrix.jsx → components/topics/TopicIntentMatrix.jsx`** 共享给 Brand Mode `/brand/topics` TopicsView (在 ProfileGroupSampleWarning 与 4-stat grid 之间挂载) + Industry Mode `/industry/topics` 段 ④。`/industry/topics` 从 v3.1 6 段缩到 **v3.2 5 段** (FilterBar / Hero 3 cards / Radar / Topic×Intent / Drawer); `brandTopicHits` helper **保留** 因 Radar + Drawer 仍用于 Top 3 品牌排序。**不引入新 harness** (C9/C14 仍覆盖共享组件); 新增两条 PRD §4.6.1g.D grep 阻止 `IndustryTopicCoverageHeatmap` / `components/industry/IndustryTopicIntentMatrix` 复活。详见 PRD §4.6.1g v3.2 + §4.2.5 (Brand Topics 第 1 层补充) + SESSIONS T2'.8 + T3' task 3 v3.2。
21. **2026-04-21 Review 修复闭环 (4 维度 8 P0 gap 全关)**: 基于 `docs/REVIEW_2026_04_21.md` (App/Admin × PRD/SESSIONS/Harness/DESIGN_TOKENS/frontend 4 维度审查), 对 8 个 P0 gap 一次性闭环, 落地到 **6 份文档同步**, 不修 `frontend/` 代码 (Frank: "目前 frontend 只是当作原型图, 只要通过 session 正式工程时可以做出来即可")。本决策是承接 #18 (测试自动化 A++) 的真正工程兑现, 下列每一条必须在相应 Session 开工前达成, 否则全链路无法兑付。

    **A. Session 0 测试地基强制前置 (非可选)**: `docs/CLAUDE_CODE_SESSIONS.md` Session 0 §5 扩写为 **38 条 Harness 规则, 5 组 A-E 分类**:
    - **A1-A6** i18n/文案边界: CJK 泄漏 / en-US 对偶完整 / `formatBrand` 唯一入口 / 开发者约束不进 i18n / 同不进 JSX / interpolation `t(key, {values})` API 强制
    - **B1-B7** 图表契约 C1-C7: Sparkline 100% 默认 / 引擎色不混用 chart-N / SoV "其他" 不大于任一真实片 / sentiment 不 `.toFixed(2)` 给用户 (C4-exempt 标注) / 禁 `i%N===0?±V:0` 锯齿波 / Donut `size={180}` 契约 / BRANDS.ranking 严格等于按 panoScore 降序 index+1
    - **C9-1..C15-3** V2 分析页契约: Heatmap 不借 chart-N / FilterBar 必挂载 / 无本地 `useState('7d')` 绕 URL / mentionRate literal 不 ≥1 / Sentiment 用 DonutChart / Quadrant sqrt+showLabels+半径 ≤40 / 密度 text-xl 页标题 p-3 card space-y-3 / **BrandProductDetailPage brandId 走 query string 禁 useParams 解构**
    - **D1-D7** 产品决策: Auth 门 (`/industries` 等路由必有 RequireAuth) / 登出 6 步契约 先 track 后 `mixpanel.reset` / Mixpanel 事件属性禁 PII / 11 条 Legacy 301 全覆盖 / MCP API 0 条匿名路径 / Onboarding 草稿 72h 过期 clean
    - **E1-E4** Citation + KG: Tier 权重禁硬编码 (DB seed + Admin CRUD) / URL 归一化必走 `tldts` / `citation_source_loss` 与 `attribution_mismatch` 诊断互斥 grep / `pr_score` + `basePriceByTier` 参数服务
    
    **B. 数据契约 Node 运行时断言 `scripts/check-data-contracts.mjs` (7 条)**: (1) C3 SoV "其他" 不得 > 任一真实品牌片 / (2) C7 BRANDS.ranking 严格等于按 panoScore DESC 后的 index+1 / (3) PRODUCTS.ranking 同上 / (4) mentionRate 全量 literal ∈ [0, 1] / (5) BCG 四象限至少 1 个产品覆盖 / (6) Citation Authority Radar 5 维齐备 / (7) Project.primaryBrandId ∈ competitorBrandIds 闭包检查。grep 不覆盖的关系型约束归此脚本。**Session 0 交付前 `npm run ci:data-contracts` 全绿**。
    
    **C. Harness 自验证 `frontend/src/__ci_fixtures__/` (5 条 self-seeded 故意违规)**: Harness 不是纸面规则, 必须能真的拦住真实违规; Session 0 交付一批故意违反的 fixture (A1 CJK 泄漏 / B1 Sparkline literal / C11-1 mentionRate > 1 / C14-1 `<h1 text-3xl>` / D4 缺 301), 配 `npm run ci:harness:selftest` 验证每条 grep "至少抓到 1 条自己的 fixture", 抓不到即 harness 本身坏掉。fixture 文件用 `__ci_fixtures__/` 前缀 + `.cifixture.jsx` 扩展, 主 harness 扫描必须把此目录反白为 expected-positive。
    
    **D. PRD/ADAPTER/DATA_MODEL/TEST_STRATEGY 文档补齐** (新增 / 扩写章节, 下列章节未就位前对应 Session 不得启动):
    - **PRD §4.10.3.A** · Intent × Engine × Locale 23 行决策矩阵 (informational/commercial/transactional/navigational × doubao/DeepSeek/ChatGPT × zh-CN/en-US, navigation 降频 30%), Planner 代码必须 lookup, 新增引擎必须 append + 同步 test
    - **PRD §4.1.1d.C** · Onboarding 草稿 `DraftProject` Prisma 模型全字段 (userId unique / step / industryId / primaryBrandId / competitorBrandIds[] / preferences Json / expiresAt) + 状态机 + Route Guard `302 /onboarding?resumeStep=` + pg_cron 小时级清理 + 3 个新事件 `onboarding_draft_created` / `_resumed` / `_expired`
    - **PRD §4.2.4.A** · Sentiment 0.5 tiebreak 规范: `[0, 0.45] negative / (0.45, 0.55) neutral / [0.55, 1.0] positive`, 单一入口 `classifySentiment()`, harness grep 封禁 `(sentiment|score)\s*>\s*0\.5`
    - **PRD §4.9.4** · 成本尖峰告警规则 4 源 + `cost_paused` 标志 + Planner 停止入队 (不 kill Worker) + 引用 DATA_MODEL §2.5 patch
    - **ADAPTER_CONTRACT §5.3a** · 账号 Pre-Warm 7 步流程 + 状态机 PENDING→PRE_WARMING→ACTIVE/QUARANTINED (COOLDOWN 变体) + 45s 预算 + `prewarm_last_run_at / _success_count / _failure_count / _last_failure_code` 字段
    - **ADAPTER_CONTRACT §7.4** · 0-Node 降级: Trigger A (≥5min 0 healthy overseas) / B (3× 订阅 fetch 失败 = 18h), 6 步降级 (overseas Worker idle 但 CN 继续), `AdminRuntimeFlags` 预定义 `overseas_proxy_pool_dead / cost_paused / kg_planner_paused`, 新 harness `admin-runtime-flag-cleanup` + `proxy-zero-fallback-must-pause-overseas-only`
    - **DATA_MODEL §2.5** · `ai_responses` 扩 5 字段 (`cost_usd DECIMAL(8,5) / cost_cny DECIMAL(8,4) / token_count JSONB / latency_breakdown JSONB / trigger_source CHECK IN ('scheduled','manual','retry','user_refresh','admin_replay')`) + 新索引 `idx_responses_trigger_source_date`; 迁移保留 `latency_ms`, backfill `trigger_source='scheduled'`
    - **DATA_MODEL §1.9** · `kg_mined_relations` 新表 (source/target × 8 种 relation_type + evidence_count + confidence_score DECIMAL(4,3) + promoted/admin_status 双轨) + 公式 `confidence_score = min(1.0, 1 - 0.85^evidence_count)` + 晋升规则 (≥0.70 AND ≥5 → auto / [0.50,0.70) AND ≥3 → manual_review)
    - **TEST_STRATEGY v1.1** · `docs/TEST_STRATEGY.md` 扩写 §9 (异常场景覆盖矩阵: Auth/Pipeline/Data 完整性/UI 空错加载/Cost/Admin) + §10 (Admin 测试矩阵 A0-A5 + 7 条 Admin-specific 异常) + §11 (P0 10 项 / P1 5 项 / P2 4 项优先级清单 + `coverage-gap-scan.mjs`) + §12 (fixture 命名 + F1-F3 harness) + §13 (38 规则血统表)

    **E. Admin 测试任务补丁 + Session A5 新增 (关 P0 #2 + #7)**:
    - `docs/ADMIN_CLAUDE_CODE_SESSIONS.md` 对 **A2.2 / A2.3 / A2.4 / A3** 追加完整 L1/L2/L3/L4 测试任务 (HAR 脱敏 + routeFromHAR 必用 / KG change_type 8 种枚举 / QA 5 层抽样 / Trust Score 11 边界)
    - 新增 **Session A5 · Citation Tier CRUD + MCP Token 签发** (半天): Tier 参数管理 UI + 回溯 recompute 幂等任务 + `mcp_api_tokens` 表 + 60s Redis pub-sub 吊销黑名单 + A-Gate 5 phase gate, 被 App Session 5 MCP server 依赖

    **F. 开工前强制读入**: 任何 App/Admin Session 开工第一批动作必须包含 `Read docs/REVIEW_2026_04_21.md + docs/TEST_STRATEGY.md v1.1 §9-§13`; 任何新 harness 规则必须同时在 `scripts/ci/harness-<group>.sh` 加规则 + `__ci_fixtures__/` 加违规 fixture + `npm run ci:harness:selftest` 证明能抓到。**这是 #18 的真正兑现条件: 每次 PR `npm run ci` 全绿即可 merge, 零 Frank 介入**。

22. **Session 1 · AI 引擎爬取框架交付 (2026-04-21)**: 按 `docs/CLAUDE_CODE_SESSIONS.md` Session 1 范围落地 Adapter 框架 / Result Parser / Scheduler / Account Pool / Humanize / Proxy / HAR 工具链 / Vitest 单测 + Group F Harness 三条规则 (F1/F2/F3)。实施策略: **"结构框架 + 可测试纯逻辑"** — Playwright 依赖的 execute() 路径暂留 TIMEOUT sentinel 到 Session 1.2 落 Camoufox, 但算法层 (parser / scheduler / state-machine / profile-sampler / humanize / proxy pool / HAR sanitize) 全部真实实现以满足 Vitest 80% 分支覆盖 (见 `backend/vitest.config.ts`)。

    **A. Adapter 契约对齐 `docs/ADAPTER_CONTRACT.md`**: `backend/src/engines/adapters/` 下 3 家引擎各有 `{selectors.ts, index.ts, api-fallback.ts, README.md}`: (i) DoubaoWebAdapter — `.reference-card[data-href]` 抽 citation / "请登录" 文案 → COOKIE_EXPIRED / 单 div captcha overlay; (ii) DeepSeekWebAdapter — localStorage.userToken 双轨鉴权 (缺失 → COOKIE_EXPIRED) / `.thinking-collapse` 剥离 / `.citation-tooltip` hover race; (iii) ChatGptWebAdapter — Cloudflare iframe (`iframe[src*="cloudflare.com/cdn-cgi/challenge-platform"]`) → CF_BLOCKED / `data-message-status` 仅查最后一条 assistant 消息 / `[data-testid^="cite-"]` 脚注抽取 / 强制走代理。API fallback 3 家统一走火山引擎 `/chat/completions` (Doubao `doubao-1-5-pro` / DeepSeek `deepseek-v3`) 或 OpenAI `/v1/chat/completions` (ChatGPT `gpt-4o`), API 模式 citations=[] 明确返回 (ADAPTER_CONTRACT §8)。9 种 AdapterError 错误码 + 每码重试策略矩阵锁定在 `backend/src/engines/adapters/errors.ts`, `retry_count` 只活在 `ExecutionContext.attempt`, 绝不做 DB 列 (ADAPTER_CONTRACT §6)。

    **B. Parser 纯逻辑模块 `backend/src/parsers/`**: (i) `normalize.ts` — `registrableDomain(url)` 包 `tldts.getDomain` 做 eTLD+1 (修复 news.loreal.com.cn → loreal.com.cn 归属) / `normalizeBrandName` 做 NFKD 去重音 + NFKC + lowercase / `splitSentences` 用 CJK + 西文标点 regex; (ii) `brand-matcher.ts` — 按句子级去重, ASCII 别名 < 3 字符走 whole-word 边界, 长别名优先排序防止 "LV" 误吃 "Louis Vuitton"; (iii) `sentiment-classifier.ts` — POS/NEG 中英词库 + 单一入口 `classifySentiment()` + `labelForScore` 是 [0, 0.45] / (0.45, 0.55) / [0.55, 1] 三档的唯一权威, 分数强制 clamp 到 [0.05, 0.95] (避免 0/1 边界崩); (iv) `ranking-extractor.ts` — 显式 "1." / "1、" / "1)" / "第 N 名" 1-50 只认这个范围, 无显式模式才降级为首次出现顺序; (v) `citation-extractor.ts` — 三级归因 official_domain (1.0) > co_occurrence (0.7) > text_match (0.4), 与 PRD §4.2.6 置信度档位一一对应。

    **C. Scheduler + Account Pool + Proxy + Humanize**: (i) `scheduler/retry.ts` — `executeWithRetry` 返回 `{response, finalError, attempts: AttemptRecord[]}`, 外部 throw 一律 coerce 成 PARSER_FAIL, `NO_ACCOUNT_AVAILABLE` 特判留 pending 不当失败; (ii) `scheduler/backoff.ts` — exp doubling ± 25% jitter, Math.random 可注入便于测试; (iii) `scheduler/state.ts` — QueryState 6 状态 + `LEGAL_TRANSITIONS` 表 + `IllegalStateTransitionError`; (iv) `scheduler/queue.ts` — 每引擎 concurrency 限流, task 失败仍释放 slot; (v) `accounts/state-machine.ts` — 6 状态 (ACTIVE/COOLDOWN/FROZEN/BANNED + PRE_WARMING/QUARANTINED), `COOLDOWN_DURATIONS_MS` 按 error code 差异化 (COOKIE_EXPIRED 12h / CAPTCHA_REQUIRED 4h / DEFAULT 1h), `autoPromoteExpiredCooldowns` 游标推进; (vi) `accounts/pool.ts` extends EventEmitter, pick() 优先 segmentGroup 匹配 → LRU fallback, activeCount < minActive 抛 `pool:low_watermark`; (vii) `accounts/prewarm.ts` 7 步流程 + STEP_BUDGET_MS (总 45s), `shouldQuarantine` 连续 3 次失败; (viii) `accounts/auto-register.ts` + `sms/luban.ts` stub — 只 doubao/deepseek 支持鲁班 SMS 自注册, ChatGPT 人工入池; (ix) `engines/proxy/pool.ts` — 黑名单 park 到下一个小时顶 (`setHours(+1, 0, 0, 0)`), 零健康触发 `proxy:zero-healthy` 事件; (x) `engines/behavior/humanize.ts` — PagePort interface (不强耦 Playwright) + Box-Muller normalSample + Bezier cubic mousePathPoints + `QUILL_ESCALATION_ORDER = ['keyboard', 'input-event', 'direct-assign']`; (xi) `engines/captcha/solve.ts` — CapSolver → 火山 vision → slider 三级兜底, 全失败抛 CAPTCHA_REQUIRED; (xii) `engines/profile-sampler.ts` — FNV-1a 确定性 hash 做 `profileGroupId:seed` 映射, 同 seed 必得同 preset, `backend/config/browser-profiles.ts` 8 个互洽 preset 覆盖 cn-consumer-desktop / overseas-consumer-us / overseas-consumer-sea 三组。

    **D. HAR 工具链**: `backend/src/har/sanitize.ts` 全量实现 — HEADERS_TO_STRIP_REQUEST (authorization / cookie / x-csrf-token / x-auth-token / x-api-key), HEADERS_TO_STRIP_RESPONSE (set-cookie / x-refresh-token), QUERY_PARAMS_TO_STRIP, BODY_FIELDS_TO_STRIP (password / token / refresh_token / access_token / code / otp / phone / email / mobile), 递归 `stripObjectFields` 深度扫描, 统一写 `__REDACTED__` 而非删除键 (保 schema). `scripts/record-har.ts` CLI shell + argparse + 写盘前 sanitize post-step, Session 1.2 接 Playwright launch 补录制。`backend/tests/fixtures/scraping/queries.json` 4 条规范查询 (skincare-recommendation-zh/en, luxury-watch-comparison-zh, beverage-market-leaders-zh), 所有 HAR replay 测试必须从这里读 prompt。

    **E. Vitest 13 套单测 + 覆盖率阈值**: `backend/vitest.config.ts` 锁 `include='tests/unit/**'` + environment='node' + coverage provider='v8' + 80% 全线阈值 (branches/lines/functions/statements)。13 个测试文件覆盖: parsers 4 件 (brand-matcher 8 例 / sentiment 多 band / citation 3 tier + 优先级 / ranking 5 例含 N>50 拒绝) + har/sanitize (Authorization/Cookie/query/JSON body/nested refresh_token/空 HAR 幂等) + accounts 2 件 (state-machine / pool LRU + watermark 事件) + scheduler 4 件 (retry / state transitions / backoff 随机夹持 / queue 并发 + 跨引擎独立) + engines 3 件 (profile-sampler 确定性 + 分组隔离 + listSegmentGroups 去重 / proxy-pool 黑名单 top-of-hour + zero-healthy / humanize jitter 钳制 + pausePonderingMs 范围 + Bezier endpoints)。

    **F. Group F Harness 三条新规则 + 自验证 fixture (决策 #21.C)**: `scripts/ci-check.mjs` 新 Group F 段 — **F1** `no-bare-playwright-import` 扫 `backend/src/**/*.ts`, whitelist `humanize.ts` / `camoufox-launch.ts` / `har/recorder.ts`, 其余 `from 'playwright(-extra|-core)?'` 或 `{chromium|firefox|webkit}` 一律 block; **F2** `har-fixture-secret-leak` 扫 `backend/tests/fixtures/adapters/**/*.har`, 9 种 leak pattern 同时覆盖 HAR 1.2 name/value 对形式 + `content.text` 嵌入的 **转义 JSON** 形式 (`\"refresh_token\":\"...\"`) + 兜底非转义形式, Session 1 首轮 F2 规则只写非转义 pattern 结果 selftest FAIL, 扩到"转义 + 非转义双轨"后 selftest 才 green; **F3** `no-inline-prompt-literal` 扫 `backend/tests/{unit,integration}/**`, 只对真正 exercise adapter 的测试 (引用 routeFromHAR / adapter.execute / AdapterBundle / 具体 Adapter 类) 生效, 已 import queries.json 的文件豁免, 拦住 > 20 字符的中英 prompt literal。**F1/F2/F3 各自对应一份故意违规 fixture**: `backend/src/__ci_fixtures__/F1_playwright_bare_import.cifixture.ts` / `backend/tests/fixtures/adapters/__ci_fixtures__/F2_har_bearer_leak.cifixture.har` (含未脱敏 Bearer + Set-Cookie + refresh_token 三连) / `backend/tests/unit/__ci_fixtures__/F3_inline_prompt.cifixture.test.ts` (routeFromHAR 引用 + 内联中文 prompt 不 import queries.json)。`scripts/ci-harness-selftest.mjs` EXPECTED_POSITIVES 从 5 扩到 8 (加 F1/F2/F3 三条), 最终 `node scripts/ci-harness-selftest.mjs` 必须打印 `● selftest: PASS  (8 / 8 fixture expectations met)` 才能 merge。

    **G. npm 脚本锚点**: `backend/package.json` 新加 devDep `vitest@^2.1.5` + `@vitest/coverage-v8@^2.1.5`, 新加 scripts `test` / `test:watch` / `test:coverage` / `ci:harness:selftest`。**下一步 (Session 1.2)**: 接入 Camoufox (playwright-extra 的隐身替代), 把 Adapter execute() 从 TIMEOUT sentinel 换成真实 page.goto + 稳定性自测; 接入鲁班 SMS 真实 client 替换 stub; 对 3 家引擎各录制 1 组 golden HAR 进 `backend/tests/fixtures/adapters/{doubao,deepseek,chatgpt}/` + 写 routeFromHAR 回放契约测试 (TEST_STRATEGY v1.1 L3 层)。本 Session 不写 Playwright 集成测试, E2E 延到 Session 1.2 或 Session 6 (TEST_STRATEGY Phase 4)。

23. **Session 1.5 · 行业知识图谱 Platform Layer 交付 (2026-04-21)**: 按 `docs/CLAUDE_CODE_SESSIONS.md` Session 1.5 范围落地知识图谱冷启动管线 — Industry → Category (3 级) → Brand → Product + 关系边 (COMPETES_WITH / SAME_GROUP / SUBSTITUTES / PAIRS_WITH / UPGRADES_TO / BUDGET_ALT_OF)。实施策略延续 #22 的 **"端口/适配器 + 可注入 transport"** 范式: 所有 orchestrator 通过 `KgRepositories` 接口 + `LlmTransport` 函数类型做依赖注入, 单测全部走 `InMemoryKgRepositories` + `vi.fn()` 桩化, 零网络零 DB 零 `@prisma/client` 解析。

    **A. 两层架构 · Platform Layer vs User View Layer**: 知识图谱是**平台层资产**, 由冷启动脚本 + 日常 Response 挖掘持续迭代, 所有用户共享同一份。User Project 只是**视角过滤器**, 存 `primaryBrandId + competitorBrandIds[] + preferences`, 不存任何监测数据。Session 1.5 的产出全部落在 `backend/src/platform/**`, 不触碰 `backend/src/app/**` (Next.js 用户态路由)。

    **B. 目录结构 (`backend/src/platform/`)**:
    - `llm/client.ts` — 火山引擎 OpenAI-compatible wrapper (POST `${baseUrl}/chat/completions`), `transport` 可注入, `callJson<T>()` 强制 JSON 输出 + 解析, `LlmCallBudgetExceededError` 超过 `maxCalls` 抛 (SESSIONS §1.5 硬约束: ≤ 50 LLM calls / industry), `makeFetchTransport` 默认产 fetch 实现, `estimateCostUsd` 内建 `doubao-1-5-pro` / `deepseek-v3` / `gpt-4o` 定价表
    - `db/ports.ts` — `KgRepositories` 接口 (industries / categories / brands / brandRelations / products / productRelations / minedRelations / discoveryLogs), 每表独立 Repository, 所有 upsert 返回行 id 供链式插入
    - `db/memory-repo.ts` — `InMemoryKgRepositories` 实测版, 每表一个 Map<string, Row>, key 按 Prisma `@@unique` 自然键组合 (`${industryId}::${primaryName}` 等)。**⚠️ 字段命名契约**: 内部 Map 必须与公共 Repository 字段同名则互冲 (public readonly 会覆盖 private readonly), 所以 Map 用 `categoriesByKey` / `brandRelationsByKey` / `minedRelationsByKey` / `discoveryLogEntries` 等后缀区分; 回归 harness 未单独写, 但命名冲突体现在字段名层, TS 不报但运行时 `this.xxx.get is not a function`
    - `db/prisma-repo.ts` — `makePrismaKgRepositories(prisma)` 生产版, 用 Prisma 编译时生成的 compound unique key 名 (`industryId_primaryName` / `brandId_primaryName` / `sourceType_sourceId_targetType_targetId_relationType` 等); 本文件在 vitest coverage **exclude** 列表, 因为 @prisma/client 可能未 generate, 单测不碰
    - `discovery/types.ts` — 纯类型 (BrandAlias / DiscoveredBrand / DiscoveredProduct / CategoryTreeNode / BrandRelationType / ProductRelationType)
    - `discovery/prompts.ts` — 中/英双语 prompt 模板 (category-tree / brand-discovery / product-discovery), LLM 输出 schema 强制 JSON
    - `discovery/category-tree.ts` — `generateCategoryTree` 调 LLM 生品类 3 级树 + 校验 (nameZh 必填, level ∈ {1,2,3} 越界降为 1, nameEn 缺失回填 nameZh), `persistCategoryTree` 递归写入 + `parent_id` 链, level-4+ 后代**丢弃而非报错** (LLM drift 容错)
    - `discovery/brand-discovery.ts` — `generateAndPersistBrands` 按 L1 category 逐一提问 LLM, 每 L1 一次调用, 跨 category 去重后批量 upsert + 写 COMPETES_WITH / SAME_GROUP 边; 捕获 `LlmCallBudgetExceededError` 返回 `budgetExhausted: true` + 部分结果不抛; 单 category LLM throw → skip 这条 category + 写 `discoveryLogs` + 继续下一条; 种子品牌 (`seedBrandsByCategory`) 触发 confidence floor 0.75
    - `discovery/product-discovery.ts` — `generateAndPersistProducts` 按品牌逐一提问, `resolveCategoryId` 三级回退 (精确 nameZh → nameZh/En 子串 → 首个 L1 兜底 + 累积 `unresolvedCategories` Set), 关系写入当前品牌的 `setProductRelation` (intra-brand, 跨品牌关系留给 Response 挖掘); 相同 budget/per-brand-error 容错语义
    - `discovery/dedupe.ts` — 纯函数 `mergeAliases` / `deduplicateBrands` / `deduplicateProducts` — alias 按 `(language, normalized value)` 合并, primaryName 归一化 (NFKD + lowercase) 后做相等判断, metadata 按 "winner confidence 高 + 缺字段从 loser 回填" 规则合并
    - `knowledge-graph/confidence.ts` — 置信度数学 `confidenceFromEvidence(n) = min(1, 1 - 0.85^n)` + `classifyPromotion` (auto ≥0.70 ∧ ≥5 / manual_review ≥0.50 ∧ ≥3 / hold)
    - `knowledge-graph/brand-relations.ts` / `product-relations.ts` — `setBrandRelation` / `setProductRelation` 对称边 (COMPETES_WITH / SAME_GROUP / SUBSTITUTES / PAIRS_WITH) 写两行, 有向边 (UPGRADES_TO / BUDGET_ALT_OF) 写一行, self-loop 跳过, 缺失端点记入 `missing[]` 不抛
    - `knowledge-graph/relation-extractor.ts` — Response 文本挖掘, 正则模式映射 (`比.*贵` → BUDGET_ALT_OF rightToLeft, `vs` → COMPETES_WITH, `搭配` → PAIRS_WITH), 命中后走 `minedRelations.bumpEvidence` 累积 evidence (非直接写 kg_*_relations, 避免低置信度污染真表)
    - `scheduler/platform-scheduler.ts` — 纯函数 `assignTiers` (按 popularityScore 分位, 默认 [0.2, 0.8] 分成 high/medium/low, manualTier 覆盖) + `buildEnqueuePlan(brands, config, now)` (cadence high=24h / medium=72h / low=168h, never_crawled priority 1.0, 超期度 × tierWeight 计算 0-0.99, 按 priority desc 取到 dailyBudgetUsd cutoff, 超预算入 `deferredByBudget`); `now` 参数注入便于测试零 Date mock
    - `planner/topic-pool.ts` — Session 2 stub, `generatePlatformTopics` 抛 `TopicPoolNotImplementedError`, 只导出接口形状供上层编排先落 import
    - `seed/mvp-industries.ts` — 4 行业静态种子数据 (beauty-personal-care / luxury / food-beverage / fashion-apparel), 每行业 4-5 L1 + 2-5 L2 children + `seedBrandsByCategory` 种子品牌提示

    **C. 端到端编排脚本 `backend/scripts/seed-platform-data.ts`**: 支持 flags `--dry-run` / `--industry=<slug>` / `--llm-tree` / `--max-llm-calls=N` (默认 50) / `--product-brands=N` (默认 10)。**Dry-run transport** 按 prompt 子串模式匹配 ("品类树" / "Top N 品牌" / "产品") 返回 canned JSON, 完全脱网可跑, 是 CI 的默认路径; **Live transport** 要求 `VOLC_API_KEY` (火山引擎), `VOLC_BASE_URL` 默认 `https://ark.cn-beijing.volces.com/api/v3`。每行业流程: upsert industry → persist 静态树 → (可选) LLM 扩树 → brand discovery 全 L1 → product discovery top N brands。**运行命令**:
    ```bash
    # 脱网 dry-run (CI 默认):
    npm run seed:platform:dry
    # 指定单行业 dry-run:
    npx tsx scripts/seed-platform-data.ts --dry-run --industry=beauty-personal-care
    # 生产 (需 VOLC_API_KEY):
    VOLC_API_KEY=sk-xxx npm run seed:platform
    ```

    **D. Vitest 覆盖率 · 10 套单测**: `tests/unit/platform/**/*.test.ts` 共 132 例, 覆盖 llm/client (20) / knowledge-graph/confidence + brand-relations + product-relations + relation-extractor (34) / discovery/dedupe + category-tree + brand-discovery + product-discovery (33) / db/memory-repo (21) / scheduler/platform-scheduler (18) + 其他已有 87 例, 合计 **219 tests / 25 files 全部 pass**。coverage v8 实测: **stmts 95.81% / branches 87.06% / funcs 90.6% / lines 95.81%** (`vitest.config.ts` 80% 阈值全线过)。`vitest.config.ts` 新增 exclusions 三条: `src/platform/db/prisma-repo.ts` (Prisma 客户端依赖) / `src/platform/planner/topic-pool.ts` (Session 2 stub) / `src/platform/seed/mvp-industries.ts` (纯常量)。

    **E. `backend/tsconfig.json` 新建**: Session 1.5 之前 backend 没有 tsconfig (npm run typecheck 打 help), 本 Session 首建: `target=ES2022 / module=NodeNext / moduleResolution=NodeNext / strict=true / noEmit=true / paths={"@/*": ["src/*"]}`, include 覆盖 `src/**`, `tests/**`, `prisma/seed.ts`, `scripts/**`, `vitest.config.ts`; exclude `node_modules / .next / dist / **/__ci_fixtures__/** / **/*.cifixture.*`。`npm run typecheck` 首次全绿。

    **F. 已交付 Session 1.5 acceptance 打勾**: (1) Industry Registry + 3 级 Category Tree (4 行业静态种子 + LLM 可选扩展) ✔ / (2) Brand Discovery Pipeline + 去重 + COMPETES_WITH/SAME_GROUP 关系 ✔ / (3) Product Discovery Pipeline + COMPETES_WITH/SUBSTITUTES/PAIRS_WITH/UPGRADES_TO/BUDGET_ALT_OF 关系 ✔ / (3a) Response-time 关系挖掘 ✔ / (4) Topic/Prompt interface stub ✔ (Session 2 填充) / (5) Platform Scheduler tier-based frequency + cost cap ✔ / (6) 端到端 seed script (steps 1-3 active, 4-5 deferred to Session 2+) ✔ / (8) 单测 ≥ 20 brands / ≥ 5 products / tier scheduler / Platform Layer 隔离 ✔。

    **G. 本 Session 不交付 (明确留给后续 Session)**: (7) Admin quality-review endpoint `GET /admin/platform/industries/:id/brands` — 依赖 Next.js Admin API 路由层, 本 Session 聚焦 Platform Layer 算法; 该端点应在 ADMIN Session A2 系列落地, 届时直接包 `makePrismaKgRepositories(prisma).brands.listByIndustry(id)` 即可, 无新增算法。Topic Pool 实现 (§4.0.1a Planner) 由 Session 2 填充 `src/platform/planner/topic-pool.ts`。

    **H. 硬约束 & 回归拦截**: (i) `LlmClient.maxCalls` 强制 ≤ 50/industry; 超过抛 `LlmCallBudgetExceededError`, orchestrator catch → 部分结果返回; (ii) `confidenceFromEvidence` 公式 (`EVIDENCE_DECAY=0.85`) **不得**随意调整, 动则发 DB migration note; (iii) mined-relation 任何 LLM bootstrap 写关系**必须**先进 `kg_mined_relations` (evidence_count=1, confidence≈0.15), 晋升到 `kg_brand_relations` / `kg_product_relations` 走 `classifyPromotion` 的双阈值; (iv) Platform Layer 绝不读取 `User` / `Project` 表, User View Layer 只读 KG 不写; (v) `InMemoryKgRepositories` 的字段名约定 (public `categories` 对内部 Map `categoriesByKey`) 不得倒退合并, 合则 `this.xxx.get is not a function` 立刻回归。

24. **Session A0 · Admin 认证脚手架交付 (2026-04-21)**: 按 `docs/ADMIN_CLAUDE_CODE_SESSIONS.md` Session A0 范围交付 Admin 模块第一块地基 — JWT 中间件 + `/admin/login` + 6 个 `/admin/api/v1/auth/**` 端点 + Rate Limit + Bootstrap Seed + Silent Refresh + Route Guard + 最小审计日志。所有后续 Admin Session (A1 用户管理 / A2 KG 质量审核 / A3 Alert / A4 系统健康 / A5 Citation Tier + MCP Token) 依赖本 Session 的 `requireAdminSession()` / `requireReauth()` helper。

    **A. Prisma schema 扩 + 3 新表**: `AdminUser` 扩字段 (`forcePasswordChangeAt DateTime?` / `lastPasswordAt DateTime?` / `lastLoginAt DateTime?`); 新增 `AdminSession` (refresh token 哈希 + userId + jti + userAgent + ipAddress + expiresAt + revokedAt) / `AdminPasswordReset` (userId + tokenHash + purpose CHECK IN ('reset','invitation') + expiresAt + consumedAt) / `AdminLoginAttempt` (email + ipAddress + success Boolean + failureCode enum + userAgent + createdAt). CHECK 约束走 raw SQL migration (Prisma 不支持 CHECK declaration, 见 §24.C.1 偏差)。真相源 `docs/ADMIN_PRD.md §5.6.8` 带 `2026-04-21` 唯一真相源标记, 任何字段变更先改 PRD 再改 schema。Rate limiter 走 `backend/src/admin/auth/rate-limiter.ts` 的 in-memory `Map<string, Bucket>` sliding-window (原 Prompt §5 方案), 不引入额外 schema 字段。

    **B. 后端 `backend/src/admin/auth/**` 12 文件**:
    - `jwt.ts` — `signAccessToken(payload)` + `verifyAccessToken(token)` HS256, `AdminJwtSecretMissingError` 在 `ADMIN_JWT_SECRET` 缺失或长度 < 32 字节时抛, `AdminJwtInvalidError(reason)` 失败码 4 枚 (expired / signature / malformed / claims), **Edge 兼容 (用 jose, 不用 node:crypto)**
    - `refresh-token.ts` — `generateRefreshToken()` 返回 `{token, hash}` (32 字节随机 + base64url + sha256), `constantTimeEqualHex()` 用 `timingSafeEqual` 带 length-mismatch short-circuit + malformed hex try/catch; **Node-only (import node:crypto), middleware.ts 禁引用**
    - `password.ts` — `hashPassword(pw)` 强制 `BCRYPT_COST=12` (单一入口, D9 harness 拦硬编码), `verifyPassword(pw, hash)` try/catch 包安全返回 false, `checkPasswordStrength(pw, userInputs)` 用 zxcvbn score ≥ 3 + length ≥ 12, 返回 `{ok:boolean, reason?: 'too_short'|'too_weak'}`
    - `cookies.ts` — `setAccessTokenCookie()` / `setRefreshTokenCookie()` 统一打 `HttpOnly + SameSite=Strict + Path=/admin + Secure (prod) + Max-Age` 选项; `clearAuthCookies()` 双 delete; `serializeCookieHeader()` RFC 6265 字符串形式供 `Set-Cookie` header 直接写 (API 路由用)
    - `middleware.ts` — `decideAdminAuth({pathname, accessTokenCookie, forcePasswordChangeAt})` 纯决策函数返回 `{action: 'allow'|'redirect'|'unauthorized', target?, reason?, payload?}`; 白名单 `AUTH_WHITELIST_PREFIXES` + `FORCE_CHANGE_WHITELIST_PREFIXES`; `isApiPath()` / `isWhitelisted()` 供 Edge middleware 和 React Router guard 共用
    - `reauth-gate.ts` — `evaluateReauth({lastPasswordAt, now?, maxAgeMs?})` 3 决策 (allowed / required:stale / required:never_authenticated), 支持时钟偏移 (future lastPasswordAt 视为 allowed), `requireRecentAuth()` helper bool alias
    - `rate-limiter.ts` — in-memory Map sliding-window, `checkEmailLimit(email)` 5 次/15min, `checkIpLimit(ip)` 20 次/15min; denied 尝试也计入窗口 (防止重复敲击绕过); 邮箱前 trim + toLowerCase 归一化; 空 IP 归一为 `'0.0.0.0'`
    - `session.ts` — Prisma-coupled (vitest coverage exclude), 读写 `admin_sessions` 表 + rotation 逻辑 (refresh 成功时旧 row.revokedAt = now() + 新 row 插入)
    - `audit.ts` — 写 `admin_login_attempts` 只含 email / ipAddress / success / failureCode 4 字段, 禁写密码/token
    - `email.ts` — Resend 调 React Email 模板 (`AdminPasswordResetEmail` / `AdminInvitationEmail`); `ADMIN_BASE_URL` 未配时 fallback `http://localhost:5173`
    - `constants.ts` — 所有 TTL / 长度 / algorithm / audience / issuer 单一真相源 (`ACCESS_TOKEN_TTL_SECONDS=900` / `REFRESH_TOKEN_TTL_SECONDS=604800` / `REAUTH_WINDOW_MS=30*60_000` / `BCRYPT_COST=12` / `MIN_PASSWORD_LENGTH=12` / `MIN_ZXCVBN_SCORE=3` / `JWT_ALGORITHM='HS256'` / `JWT_ISSUER='genpano-admin'` / `JWT_AUDIENCE_ACCESS='genpano-admin-access'` / `ACCESS_TOKEN_COOKIE='admin_access_token'` / `REFRESH_TOKEN_COOKIE='admin_refresh_token'` / `COOKIE_PATH='/admin'`)
    - `rate-limit-config.ts` — 给其他 handler 复用的 email/ip 限流常量

    **C. 与 ADMIN_PRD §5.6 schema / 工具链的偏差 (C1.1-C1.3 / C2 / C3 / C4, 必须记录, 未来 migration 须参考)**

    - **C1.1 (字段类型偏差 · Prisma DSL 限制)**: ADMIN_PRD §5.6.8 写 `uuid` / `varchar` / `text` 等 SQL 原生类型, Prisma schema 落地时统一变 `String @id @default(uuid())` / `String` / `String`。理由: Prisma DSL 不支持 SQL 原生 uuid/varchar 关键字, 运行时仍落 PostgreSQL `uuid` 列 (`@db.Uuid` 精修留给 Session A1 migration 合并扫)。
    - **C1.2 (字段命名 + 类型双偏差 · Q2 对齐结果)**: 原始 Prompt §3 指定 `mustChangePasswd Boolean`, 实施落地为 `forcePasswordChangeAt DateTime?`。理由: Boolean 只能表达"必须改"的静态状态, `DateTime?` 可同时表达"何时设为必须改"+"null=未触发"二义, 更适配 super_admin bootstrap 首登强制改密 + ops_admin 被管理员手动 reset 两种触发路径。Q2 alignment 已确认此偏差。ADMIN_PRD §5.6.8 `admin_users` 需同步改此字段语义 (见任务 2 执行结果)。
    - **C1.3 (实施路径偏差 · 就地扩写)**: Session 0-rev 已先行落地 `AdminUser` 基础模型 (id/email/passwordHash/role/status 等), Session A0 采取"就地扩写" 3 个新字段 (`forcePasswordChangeAt` / `lastPasswordAt` / `lastLoginAt`) 而非新建模型。理由: 避免 schema 分裂 + migration 冲突, 与 Session 0-rev 产物自然合流。Rate limiter 按原 Prompt §5 in-memory Map + TTL 落地, 不扩 schema (Step 11.5 一度误记"DB 持久化 + 2 字段"为偏差, Step 11.6 已回滚 — 见 `docs/SESSION_A0_STEP_11_6.md`)。
    - **C2 (super_admin 单值 · MVP 范围界定)**: ADMIN_PRD §5.6.1 列了 3 角色 (super_admin / ops_admin / viewer), Session A0 落地**只开 super_admin 单值 CHECK**, `ops_admin` / `viewer` 推到 Session A1 (Admin 用户管理)。理由: A0 只做 auth 地基, 多角色权限矩阵与审计面板一起落在 A1 更内聚。当 A1 扩 3 角色时必须: (a) 改 ADMIN_PRD §5.6.8 CHECK 约束行; (b) 写 migration `ALTER TABLE admin_users DROP CONSTRAINT admin_users_role_chk, ADD CONSTRAINT admin_users_role_chk CHECK (role IN ('super_admin','ops_admin','viewer'))`; (c) 在 A1 Session Prompt §1 真相源索引里引用本决策 #24.C2 说明历史。
    - **C3 (工具链配置偏差 · Next.js NodeNext 编译兜底)**: A0 实施过程在 `backend/next.config.mjs` 加 `webpack.resolve.extensionAlias` 7 行, 把 `.js` import 映射回 `.ts` source。理由: Next.js 14 + tsconfig moduleResolution=NodeNext 组合下, admin API 路由 (`src/app/admin/api/v1/auth/**`) 的相对 import 按 NodeNext 规范写 `.js` 后缀, 但 webpack 默认不 alias 回 `.ts` 源, 编译全失败。这是工具链约束下的永久配置, 语义层零变化. Phase 2 不需要收敛.
    - **C4 (schema gap · AdminPasswordReset.purpose 列缺失, scope-deferred)**: ADMIN_PRD §5.6.8 定义 AdminPasswordReset 应含 `purpose VARCHAR CHECK IN ('reset','invitation')`, 实际 Prisma schema (backend/prisma/schema.prisma:733-746) 只有 tokenHash / expiresAt / usedAt, `prisma db push` 跳过了 migration SQL 里的 purpose 语句. A0 scope 内 reset 流程正常 (默认单路径), invitation 流程本来就不在 A0 deliverable (属 A1 用户管理范围). **不是 regression**, 是提前落地的表未补齐未启用字段. Phase 2 (Session A1) · A1 实施用户管理时一并加 `purpose String @default("reset")` + backfill 存量行 + 启用 invitation 流程.

    **D. 前端 `frontend/src/admin/**` 4 目录**:
    - `pages/AdminLoginPage.jsx` / `AdminForgotPasswordPage.jsx` / `AdminChangePasswordPage.jsx` / `AdminDashboardPage.jsx` (A0 交付的 Phase Gate stub) — env-aware 色带顶条 (dev 绿 / staging 橙 / prod 红) 防生产误操作
    - `context/AdminAuthContext.jsx` — 4 状态机 (`initializing | authenticated | anonymous | expired`) + silent refresh 定时器 (14min 间隔, Access TTL=15min 内 lead=60s 提前续) + `BroadcastChannel('genpano-admin-auth')` 跨 tab 同步 (login / refresh / logout / expire 4 消息类型)
    - `components/SessionExpiredModal.jsx` — expired 态唯一出口, 无 X-close / 无 ESC / 无 backdrop-click, 唯一 CTA "重新登录" → `/admin/login?reason=session_expired&redirect=<current>`; `/admin/login` 页面本身不显示 modal 避免双 banner
    - `components/AdminRouteGuard.jsx` — 决策矩阵 (initializing→spinner / anonymous→navigate login+redirect / authenticated+forceChange+非 change-password 白名单→navigate change-password / authenticated+OK→render / expired→render children 让 modal 盖顶), 支持 `<AdminRouteGuard>{jsx}</AdminRouteGuard>` 与 `<Outlet />` 两种用法
    - `lib/adminApi.js` — `adminFetch()` wrapper + `adminAuthApi` 典型端点 (login/refresh/logout/forgotPassword/resetPassword/changePassword), `AdminApiError` class 携 `{status, body}`, `credentials: 'include'` 硬编码

    **E. Next.js 双 runtime 分割 (Edge vs Node)**: `backend/middleware.ts` 走 **Edge runtime** — 只 import `jose` + 常量; 禁止 touch Prisma / node:crypto / bcryptjs (Edge 不兼容)。6 个 `/admin/api/v1/auth/**` handler 走 **Node runtime** — 可自由 import Prisma / bcryptjs / node:crypto。`middleware.ts` 把 `forcePasswordChangeAt: null` 写死传给 `decideAdminAuth()`, 因为 Edge 查不了 DB; **forcePasswordChangeAt 真实 gating 在 `AdminRouteGuard.jsx` 第二层执行** (消费 refresh response 里带的 user.forcePasswordChangeAt 字段) — 这是两层守卫而非一层, 为了 Edge 兼容做的 trade-off。

    **F. Harness D8/D9/D10 三条新规则 + 自验证 fixture + selftest 8 → 11**:
    - **D8** `no-hardcoded-jwt-secret` — 扫 `backend/src/**/*.ts`, negative lookbehind 排除 `process.env.` 前缀, 抓 `ADMIN_JWT_SECRET = 'literal'` 型赋值 (fixture `D8_hardcoded_jwt_secret.cifixture.ts`)
    - **D9** `admin-password-bcrypt-cost-at-least-12` — 扫 admin/ + fixtures, 抓 `bcrypt.hash(x, <12)` 数字 literal, `password.ts` 白名单 (用 BCRYPT_COST 常量不会触发) (fixture `D9_bcrypt_cost_8.cifixture.ts`)
    - **D10** `admin-session-cookie-samesite-strict` — 抓 `sameSite: 'lax'|'none'` 任一, 额外守护 `cookies.ts` 必须 mention `sameSite: 'strict'` (fixture `D10_cookie_samesite_lax.cifixture.ts`)
    - `scripts/ci-harness-selftest.mjs` EXPECTED_POSITIVES 8 → 11, `node scripts/ci-harness-selftest.mjs` 打印 `● selftest: PASS  (11 / 11 fixture expectations met)` 才能 merge
    - Vitest 实测覆盖率 admin/auth 聚合: **stmts 97.71% / branches 93.06% / funcs 100% / lines 97.71%**, 全线过 80% 阈值; 7 个新测试文件合计 63 例 (password 8 / refresh-token 8 / rate-limiter 7 / reauth-gate 7 / cookies 11 / jwt 7 / middleware 15); 排除 Prisma / Resend / Next `next/server` 耦合的 5 个模块 (audit.ts / email.ts / session.ts / rate-limit-config.ts / constants.ts) — 留给 L3 endpoint replay 覆盖

    **G. Phase Gate 验收完成 (2026-04-21 Step 12, Frank 亲自确认)**

    - **9/9 PASS**: D1 (schema 4 张表 + 3 新列 CHECK 齐备) / D2 (bcrypt cost 12, hash 前缀 `$2a$12$`) / D3 (role + status CHECK constraint 到位) / S1 (登录 401/200 + 2 cookies HttpOnly+Strict+Path=/admin+Secure) / S2 (refresh 轮换 + revoke + replay 401) / S3 (5 次失败 → 6 次 429 + audit RATE_LIMITED) / S4 (JWT secret boot-time fast-fail, Step 11.6 复用证据) / C1 (harness selftest 11/11) / C2 (vitest 66 tests pass, coverage stmts 97.71% / branches 93.06% / funcs 100% / lines 97.71%)
    - **Smoke test 状态**: Frank 跳过 (Cowork Linux 沙箱 localhost:4001 对 Windows 主机不可达的架构限制, 非 bug), 接受 curl + Vitest 双层覆盖作为 API + 前端行为的充分证据
    - **执行环境留档**: Docker genpano-dev-pg on :5433 (可 `docker stop` 回收) + Next.js dev task b45zhdxjc on :4001 (可 TaskStop 回收) + backend/.env (gitignored) + seed super_admin frank@genpano.com (首登强改密)
    - **A0 officially green**: 后续 A1 启动前依赖项 (4 张 admin 表 + JWT 中间件 + /admin/login 页 + AdminRouteGuard) 全部就绪

25. **Session Prompt 编写公约固化 (2026-04-21)**: A0 实施过程中发现字段命名偏离 (早期 Prompt 草案把 `forcePasswordChangeAt` 写成 `mustChangePasswd`), 根因是 Session Prompt 独立重抄 PRD §5.6 schema 而非引用真相源段号, 导致两处描述漂移。本次将 7 条公约固化到 `docs/ADMIN_CLAUDE_CODE_SESSIONS.md §0 (line 55-160)`, **所有 Admin 和 App Session 新建或修改 Prompt 时必须遵守**。

    **7 条公约去向** (详见 ADMIN_CLAUDE_CODE_SESSIONS.md §0):
    - **规则 1 · 真相源 (Source of Truth) 锚定**: 同一信息只能有一处权威定义, Prompt 只能引用 (`见 PRD §X.Y`), 不能重抄。PRD §5.6.8 已加 `2026-04-21` 唯一真相源标记。
    - **规则 2 · 前置 Grep 契约 (Pre-Flight Grep Contract)**: Session Prompt §0 或 §1 必须先列 3-5 条 grep 命令, 让 Claude Code 开工第一批动作自证真相源的字段名 / CHECK 约束 / 路径常量与 Prompt 所引一致; 不一致则停下 alignment 不写代码。
    - **规则 3 · 偏离必记录 (Deviation-Record Contract)**: 实施中发现与真相源的不可调和冲突时 (如 Prisma 限制导致类型偏离), **Prompt 的最终进度报告**必须列出 C1/C2/... 偏离项, 同步落入 CLAUDE.md 对应决策的 **C 段**, 未来 migration 可追溯。本决策 #24.C 就是 A0 的偏离落点。
    - **规则 4 · 真相源双向同步 (Bidirectional Sync)**: 任何修改真相源 (PRD / DATA_MODEL / ADAPTER_CONTRACT) 的 PR 必须同步: (a) 触发 grep 扫描检查所有引用点是否漂移; (b) 更新引用 Session 的 Prompt 引用段号 (若段号重排); (c) 在本 CLAUDE.md 新增决策条目记录变更。
    - **规则 5 · Session Prompt 的 §1 必须声明"真相源索引"**: 每个 Session Prompt 头部 §1 用固定模板列清"本 Session 引用 / 修改的真相源", 例如 `PRD §4.6-IA-v2 [引用]` / `ADMIN_PRD §5.6.8 [修改]`, 让检阅者 (包括未来 Claude Code) 一眼看清影响面。
    - **规则 6 · 引用 PRD 段号必须锚定到最小单元**: 不写 `见 PRD §4`, 而写 `见 PRD §4.2.7.C (citation content gap)` — 段号漂移时精确定位, Grep 也更稳。**Plan J D4 微调 (2026-04-26)**: 引用 CLAUDE.md 决策时, **先查 `docs/DECISION_LOG.md` 一行索引**确认决策号 + 状态 (active / superseded by #N) + 标题, 再视需要打开 CLAUDE.md 决策体读全文; Prompt 引用形式 `见 CLAUDE.md #19 (Citation Tier 5 级权重)` 而不是 `见 CLAUDE.md (citation 段)` — 编号 + 一句标题让检阅者无需翻文件即可判断相关性。
    - **规则 7 · Session 完成时反查一致性**: Session 收尾前 Claude Code 必须运行规则 2 的 grep 命令 + 读 §1 列的每个真相源段号是否仍然成立 + 若发现新偏离回 §0 规则 3 登记 — 关闭回路。

    **适用范围**: 所有 Admin Session (A0-A5 及后续) 和 App Session (已存在和新建) 的 Prompt 新建或修改均须遵守。过去已写 Prompt 不做强制回溯, 但下次修改时需按 §0 补齐。

    **Phase 2 追加 (2026-04-23, Session 1.2 结构性缺陷关闭)**: Session 1.2 原 Prompt 在续推前暴露 3 结构性缺陷 — (i) **范围过大无 MVP 切分**: 原 §2 列了 8 大 deliverable (Camoufox / 鲁班 SMS / HAR 录制 / Adapter execute / L3 contract / CAPTCHA 升级 / 反检测指纹 / 账号池 prewarm live 化) 全部捆绑交付, 单 Session 注定超预算, 被迫分 "双修正原子批" + 续推两次; (ii) **决策漂移未反向同步**: Session 1.2 起草时 CLAUDE.md 仅到决策 #22, 写 Prompt 时未 grep 新增的 #26.C1 (attempts.browser_profile) / #27.G (rewrite_meta 同 JSONB) / Harness G3, 导致续推 Prompt 要额外加 "规则 8 反向同步" 条款弥补; (iii) **STOP 策略缺失**: 原 Prompt 没有显式 STOP trigger, 实施中遇到 VOLC_API_KEY 缺失 / Camoufox 首次启动 crash 类环境问题时, 无标准停机语义, 依赖 Frank 手动介入判断。为闭环, `docs/ADMIN_CLAUDE_CODE_SESSIONS.md §0` 追加 **规则 10 (MVP Scope-Cut Declaration)** — 要求每 Prompt §2 用 "本 Session 做 / 不做" 双列表 + §X.Y 锚点, 禁 "核心功能" 模糊措辞; **规则 11 (Pre-Send Decision-Freshness Check)** — 要求发 Prompt 前 30min 内跑 3 条 grep (F1 最近 3 条 CLAUDE.md 决策 / F2 近 7 天 .auto-memory 新增 / F3 近期 migration), 输出变化清单进 Prompt §1; **规则 12 (Explicit STOP-Trigger Template)** — Type A (环境失败) / B (真相源冲突) / C (范围溢出) 三类 STOP 作为地板, Session 专属 STOP 在此之上 append 而非替换。同时 `docs/CLAUDE_CODE_SESSIONS.md` Session 1.2 尾部追加 **"Prompt 续推 (2026-04-23)"** 作为规则 10/12 的标准样板 (§2 MVP scope cut + §4 STOP triggers + §5 12-step delivery order + §6 Phase Gate checklist)。**Phase 2 未来 (可选)**: 当 Session 数量累积到 10+ 且公约 1-12 手工执行成本变高时, 可追加 `scripts/check-doc-consistency.mjs` 做程序化校验 (扫描所有 Session Prompt 的"真相源索引"段 + 对比真相源文件是否存在 + 对比字段名是否还在真相源文件里出现 + 检查 §2 是否含"做/不做"双列表 + 检查 §4 是否含 Type A/B/C STOP) — 这是 Phase 2 可选增强, 不在 MVP 范围。

26. **Session 2 · 智能监测 Pipeline (Topic → Prompt → Query) 交付 (2026-04-22)**: 按 `docs/CLAUDE_CODE_SESSIONS.md` Session 2 范围落地 Planner 三层 — Topic Planner (Bottom-Up, 三维度 = 品类 / 品牌 / 产品) × Prompt Generator (Topic × Intent × Language) × Query Assembler (Prompt × Profile × Engine 扇出)。实施延续 #22/#23 的**"端口/适配器 + 可注入 repo"**范式, 所有 orchestrator 通过 `KgRepositories` 接口读 KG, 不直接 touch Prisma, 单测全走 `InMemoryKgRepositories` + 固定 seed, 零网络零 DB。

    **A. 目录与模块 (`backend/src/platform/planner/`)**:
    - `intent-engine-locale-matrix.ts` — PRD §4.10.3.A 23 行决策矩阵单一真相源, 导出 `EXPECTED_EXPLICIT_ROW_COUNT = 23` (Harness G1 锚点) + `lookupMatrix(intent, engine, locale): MatrixEntry` (单行返回, 不是数组)。navigational 全线 `reducedFactor = 0.3`, 其余 intent `reducedFactor = 1.0`。
    - `category-purity.ts` — `validateCategoryTopicPurity(topics, brandNames)` + `validateCategoryPromptPurity(prompts, brandNames)` 强制 "品类" 维度 Topic / Prompt 文本中不得夹带任何品牌名 (决策 #15 提及率 non-brand 口径护栏)。违规抛 `CategoryTopicBrandLeakError` / `CategoryPromptBrandLeakError`, Planner 必须 wire 进 hot path — Harness G2 锚点。
    - `topic-planner.ts` — 从 KG 按三维度自底向上生成 Topic: 品类 Topic ≥40% 配额 + 品牌 Topic 锚 primaryBrand + competitor 关系边 + 产品 Topic 锚 flagship SKU + 关系挖掘。生成后立即跑 `validateCategoryTopicPurity` (G2 执行点), 违规 throw 而非静默 drop。
    - `prompt-generator.ts` — Topic × 4 Intent 扇出, 按 `matrixRow.enabled === true` 过滤禁 cell, language 跟随 Intent × Engine × Locale 决策 (zh-CN 全线 + en-US 仅 ChatGPT)。Prompt 写入 `appliesToEngines[]` 字段, Query Assembler 消费。
    - `agent-profiles.ts` — AgentProfile 池: segmentGroup 按 `cn-consumer-desktop / overseas-consumer-us / overseas-consumer-sea` 8 preset 做 FNV-1a 确定性采样, 同 `(profileGroupId, seed)` 必得同 preset (Session 1 §C.xii 已实现, 本 Session 只是消费)。
    - `query-assembler.ts` — Prompt × Engine × Profile 扇出最终 Query, `baseSampleRange` 可配置 (默认 min=3/max=8), navigational intent 应用 `reducedFactor=0.3`, Query 写入 `personaSnapshot` 字段 (**注入到 attempts.browser_profile JSONB, 不建 query_executions 新列** — 决策 #21 Session 2 D1 + Harness G3 锚点)。
    - `sample-guard.ts` — 配额看门狗, `meetsCategoryQuota(topics, minShare=0.4)` 等 invariant。生产环境 assertion; 测试对最小 fixture 做 bounds check (不强制 ≥0.4), 避免把 "KG 太薄" 当成 planner bug。
    - `topic-pool.ts` — 上层编排 `generatePlatformPlan({industrySlug, repos, now?, intents?, baseSampleRange?})` → `{industrySlug, industryId, planner: {topics}, prompts: {prompts}, queries: {queries}}`, Session 1.5 的 stub 已替换为全实现。
    - `seed/profile-groups.ts` — 4 Profile Group 静态 seed (cn-consumer-desktop-default / cn-consumer-mobile-default / overseas-consumer-us-default / overseas-consumer-sea-default), 覆盖 MVP 3 家引擎的 locale 矩阵。

    **B. 新增 3 条 Admin 只读 API 端点 (`backend/src/app/admin/api/v1/platform/**`)**:
    - `GET /admin/api/v1/platform/industries/[slug]/topics` — 列出某行业当前所有 Topic (分 dimension 聚合 + 配额统计)
    - `GET /admin/api/v1/platform/topics/[topicId]/prompts` — 列出某 Topic 下的所有 Prompt (按 intent + language 聚合)
    - `POST /admin/api/v1/platform/industries/[slug]/plan/generate` — 幂等触发 `generatePlatformPlan` 做 dry-run 预览 (不写库, 只返回 topics/prompts/queries 三段计数 + 样本), 用于 Session 3 Admin UI 的"预生成"按钮。三条端点都要求 `requireAdminSession()` (Session A0 `requireRecentAuth` 门槛), 用户态读 API 留给 Session 4a / 3。

    **C. Prisma Migration `20260422000000_platform_baseline/migration.sql`**: 决策 #21 D 项要求的 baseline 迁移, 含 `platform_topics` / `platform_prompts` / `query_executions` / `agent_profile_snapshots` 四张表。**严格遵守 D1 Decision**: `query_executions` 表**不加** `persona_snapshot` / `persona_profile` / `agent_profile_snapshot` / `agent_profile_id` / `persona_id` 任一列; persona 快照一律注入到 `attempts` JSONB 子字段 `browser_profile` 里 (attempts 是 `query_executions.attempts JSONB`)。CHECK 约束走 raw SQL (Prisma DSL 不支持)。Harness G3 用 regex 锁定这组列名黑名单, fixture `G3_persona_column.cifixture.sql` 故意新增 `persona_snapshot` 列证明规则有效。

    **D. Vitest 9 套 Planner 单测 + Golden Case (`tests/unit/platform/planner/`)**:
    - `intent-engine-locale-matrix.test.ts` (9 例) — 23 行计数 / `lookupMatrix` 三元组穷举 / navigational reducedFactor=0.3 锁定 / 单一 ❌ 隐式 cell (overseas-sea × transactional × doubao) 处理
    - `category-purity.test.ts` (14 例) — 品牌名别名 / 大小写 / 长短 alias 消歧 / Topic & Prompt 双向 validator / 决策 #15 护栏回归
    - `topic-planner.test.ts` (9 例) — 3 维度齐备 / 配额 40% / 品牌锚 primaryBrand / 产品锚 flagship / purity guard 实际被调用
    - `prompt-generator.test.ts` (12 例) — 4 intent 覆盖 / 禁 cell 剔除 / zh-CN 全线 + en-US 仅 ChatGPT / navigational 降频
    - `agent-profiles.test.ts` (12 例) — FNV-1a 确定性 / segmentGroup 隔离 / 8 preset 覆盖
    - `query-assembler.test.ts` (13 例) — personaSnapshot 注入 / baseSampleRange / reducedFactor / 引擎扇出
    - `sample-guard.test.ts` (9 例) — meetsCategoryQuota / 边界 [0,1]
    - `topic-pool.test.ts` (7 例) — 端到端 `generatePlatformPlan` + determinism + 3 维度齐备 + `intents` 参数窄化
    - `golden-beauty.test.ts` (13 例) — **语义锚点** (决策 #21 Session 2 D4): Estée Lauder / L'Oréal + 小棕瓶 / 复颜真实 seed, 断言 (a) 3 维度覆盖 (b) 品类 Topic 零品牌泄漏 (用 `findBrandMentionsInText`) (c) Prompt fan-out 严格等于 matrix `enabled` cell 并集 (d) navigational reducedFactor=0.3 (e) en-US Query 只落 ChatGPT (f) BUDGET_ALT_OF 关系挖出 premium 替代 (g) determinism 相同 seed 两次跑完全一致。**不做快照对比**, 只做语义断言 — snapshot drift 不触发, matrix 偏离立即触发。
    - **总计**: 399/399 tests pass, coverage v8 实测 **stmts 96.87% / branches 89.06% / funcs 94.83% / lines 96.87%**, 全线过 80% 阈值。

    **E. Group G Harness 四条新规则 + 自验证 fixture (决策 #21.C)**: `scripts/ci-check.mjs` 新 Group G 段:
    - **G1** `planner-matrix-row-count-23` — regex `/EXPECTED_EXPLICIT_ROW_COUNT\s*=\s*(\d+)/` 扫 `backend/src/**/*.ts`, 捕获组 !== '23' 即 block。fixture `backend/src/__ci_fixtures__/G1_matrix_row_count_wrong.cifixture.ts` 写 `= 22` 证明拦截。
    - **G2** `planner-category-purity-guard-wired` — 扫 `backend/src/platform/planner/**`, basename 匹配 `topic-planner` 要求 token `validateCategoryTopicPurity`; `prompt-generator` 要求 `validateCategoryPromptPurity`。fixture `backend/src/platform/planner/__ci_fixtures__/G2_purity_guard_missing_topic-planner.cifixture.ts` 主动**不在 docstring 里 naming 该 token** (否则 `content.includes()` 会误匹配成 pass — 这是 fixture 编写的反直觉坑, 必须在注释里写 "the required identifier is NOT mentioned anywhere in this file by design")。
    - **G3** `query-execution-no-persona-column` — 扫 `backend/prisma/migrations/**/*.sql`, 只处理含 `query_executions` 的文件, 然后黑名单 regex `/\b(persona_snapshot|persona_profile|agent_profile_snapshot|agent_profile_id|persona_id)\b/`, 跳 `--` 注释行。fixture `backend/prisma/migrations/__ci_fixtures__/G3_persona_column.cifixture.sql` 同时添加 2 列证明抓双命中。
    - **G4** `planner-no-hardcoded-engine-list` — 扫 `platform/planner/**`, 白名单 `intent-engine-locale-matrix.ts` (唯一真相源), 黑名单 3 种排列的 `['doubao', 'deepseek', 'chatgpt']` 数组字面量, 跳 `//` + `*` 注释。fixture `G4_hardcoded_engines.cifixture.ts` 按 PRD §4.2.2a 引擎枚举写死数组证明拦截。
    - `scripts/ci-harness-selftest.mjs` EXPECTED_POSITIVES 从 11 扩到 15 (加 G1/G2/G3/G4), 最终 `node scripts/ci-harness-selftest.mjs` 必须打印 `● selftest: PASS  (15 / 15 fixture expectations met)` 才能 merge, 已验证通过。

    **F. 与真相源的偏差 (决策 #25 Rule 3, 必须落库)**

    - **C1 (Decision 1 · persona 存储路径偏离 DATA_MODEL §2.5 原表达)**: DATA_MODEL §2.5 早期草案把 persona/agent_profile 描述成 `query_executions` 的顶层列 (`persona_snapshot JSONB` / `agent_profile_id UUID`)。Session 2 实施时选择把 persona 快照**注入到 `query_executions.attempts` 这个 JSONB 列的 `browser_profile` 子字段**, 不建任何顶层列。理由: (a) query_executions 已有 `attempts` JSONB 容纳 retry trail, persona 是每次 attempt 的环境变量, 归在同一 envelope 下语义更自然; (b) 列膨胀成本高 (postgres 按行 toast), JSONB 单列存多维快照零扩列成本; (c) persona schema 仍在演化 (Session 3 可能追加 `timezone_drift` 等字段), JSONB flex 比 ALTER TABLE 低风险; (d) Harness G3 用 regex 长期锁定黑名单, 防止未来 Session 误加列导致双存储。**DATA_MODEL §2.5 需要在 Session 3 之前同步更新**: persona_snapshot 从"query_executions 列"改描述为"query_executions.attempts[].browser_profile 子字段", 并把 G3 rule 引为护栏。
    - **C2 (Decision 2 · 多轮对话 Query 延后)**: Session 2 Prompt §4 草案提到过 `Query.turns[]` 支持多轮对话采集 (Chat 场景), 实施时**明确延后到 Phase 2**。Query 当前是单轮 (`prompt → response`) 模型, `personaSnapshot` 是单次快照而非对话流。理由: (a) 3 家引擎 MVP 都用单轮 adapter 契约 (Session 1 ADAPTER_CONTRACT §5), 多轮需要 session state 延续, 对 account pool 冷却策略冲击大; (b) 多轮 prompt 生成需要"上轮 response → 下轮 prompt" 编排器, 超出 Planner 纯函数范畴; (c) PRD §4.2 MVP 口径只统计首轮 response 的提及率 / 情感, 多轮只是 nice-to-have。当 Session 6+ 要开多轮时应新增 `Query.followUpPromptId`, 不改 personaSnapshot 结构。
    - **C3 (Decision 3 · 用户态 API 延后到 Session 4a)**: 原 Session 2 草案列了 6 条端点 (3 admin + 3 user-facing `GET /api/v1/industries/[slug]/topics` 等)。实施时**只交付 3 条 admin 只读端点**, user-facing 端点推到 Session 4a (Onboarding + 用户系统) 一并落, 理由: (a) user 态需要 auth middleware + User/Project 表 ACL, Session 4a 才建这层; (b) MCP API 从 Day 1 要求 `Authorization: Bearer <apiToken>` (决策 #9 Auth-Required), Session 3 (MCP Server + Citation API) 自然承载; (c) Session 2 只负责 Pipeline 能跑通, 数据出口先给内部审查用 (Admin UI) 足够, 用户态出口跟 Onboarding 一起落更内聚。**SESSIONS Session 4a / 3 必须引用本 C3 说明历史**。

    **G. Phase Gate 验收 (2026-04-22 执行)**

    - **Typecheck**: `npx tsc --noEmit` 零错误
    - **Vitest**: 399/399 pass, coverage stmts 96.87% / branches 89.06% / funcs 94.83% / lines 96.87% (全线 >80% 阈值)
    - **Harness selftest**: 15/15 PASS (A1/B1/C11-1/C14-1/D4/D8/D9/D10/F1/F2/F3 旧 + G1/G2/G3/G4 新)
    - **ci-check Group G**: 4 pass / 0 fail (其他 Group A/B/C/D 失败均为 frontend 原型期 pre-existing 问题, 未触碰 mock.js 与 frontend/src/pages/brand/**, 按决策 #21 frontend 视为原型状态接受)
    - **data-contracts**: DC2/DC3/DC4/DC6/DC7 绿, DC1/DC5 红 — 同属 frontend mock 遗留, 非 Session 2 regression
    - **3 新 Admin 端点**: `/admin/api/v1/platform/industries/[slug]/topics` + `/admin/api/v1/platform/topics/[topicId]/prompts` + `/admin/api/v1/platform/industries/[slug]/plan/generate` (dry-run) 全部 requireAdminSession gate

    **H. 下一步依赖关系**: Session 3 (分析引擎 + API + MCP) 依赖本 Session 的 `query_executions` 表结构和 `generatePlatformPlan` 返回契约。Session 3 开工前必须先改 `docs/DATA_MODEL.md §2.5` 落地 C1 偏差, 然后 Session 3 实现 Response 采集 + 分析时 persona_snapshot 直接读 `attempts[].browser_profile`, 不要误建新列。Session 4a 交付 user-facing API 时复用本 Session 的 port/adapter 管线, 只是换 route + 加 user ACL middleware。

27. **Session 2.1 · Planner LLM Refinement 交付 (2026-04-22)**: 按 `docs/CLAUDE_CODE_SESSIONS.md` Session 2.1 范围落地 Planner 三层 LLM 增强 — Topic Refinement (LLM 给 realismScore + variant 扩展 + audit 三档) × Prompt Naturalization (LLM 把 skeleton prompt 改写成口语化 + naturalizeConfidence) × Query Profile-Aware Rewrite (LLM 按 persona 给 query 加场景化前缀 / 句式调整)。背景: Session 2 落地的是**纯规则模板** Pipeline (确定性 fan-out), Frank 验收时指出生成 query 像"机器人语料", 离真人提问差距大; 本 Session 在 Session 2 的同一管线上插入 3 层 LLM 后处理, **不改任何 schema 顶层结构**, 只在 envelope 里追加 audit 字段, 同时严格 honor #26.C1 (rewrite_meta 进 attempts JSONB, 禁加列)。

    **A. 三层 LLM 编排 (`backend/src/platform/planner/`)**:
    - `topic-planner.ts · refineTopicsWithLlm({topics, llm, brandsCatalog, now})` — 每个 skeleton topic 入 approvedTopics by reference (graceful degrade), 然后 LLM 调一次产生 N 个 variant + realismScore ∈ [0,1]; variant 进 approved (≥0.7) / auditQueue (∈[0.5,0.7) 标 `pending_review`) / dropped ({topic, reason}) 三档; 失败 catch 累 `llmFailureCount` 不抛, 返回 `{approvedTopics, auditQueueTopics, droppedTopics, llmCallsMade, llmFailureCount}`
    - `prompt-generator.ts · naturalizePromptsWithLlm({prompts, topics, brandsCatalog, llm})` — 每条 skeleton prompt 走 LLM 改写 + Gate 1 (intent drift) + Gate 2a (brand vocabulary 必带) + Gate 2b (品类维度 prompt 不夹品牌) + Gate 3 (low confidence < 0.5); 通过则 stamp `llmNaturalizedAt + naturalizeConfidence + rewriteMode='llm'`, 失败入 `fallbacks[]` 标 reason, prompt 仍保留 (skeleton 兜底)
    - `query-assembler.ts · rewriteQueriesForProfiles({queries, prompts, topics, brandsCatalog, llm})` — 每条 query (=Prompt × Profile) LLM 按 persona 加场景前缀 (zh-CN 用 "姐妹们, " / en-US 用 "Hey folks, "); fallback ladder: `llm` → `fallback_prefix` (persona 短前缀) → `skeleton_only` (原文); 注入 `attempts[].rewrite_meta = {originalText, rewrittenText, confidence, rewriteMode, rewriteFallbackReason, model, rewrittenAt}` (符合 #26.C1, 禁加 query_executions 顶层列, 由 Harness G3 锁定)

    **B. Canned LLM Transport (`llm-canned-responses.ts`)**: `createCannedLlmTransport()` 返回 `LlmTransport` 函数, 按 prompt 子串模式匹配 (品类/品牌/产品 × Topic-refine/Prompt-naturalize/Query-rewrite) 返回 deterministic JSON; 是 Session 2.1 在 `VOLC_API_KEY` 缺席时仍能 CI 全绿的核心机制。`generatePlatformPlan({llm: LlmClient | null})` 在 llm=null 时跳过 3 层 envelope (refine/naturalize/rewrite 全 null), 在 llm 存在时填充 envelope; canned transport 与 live transport 走同一代码路径, 只是 LLM 响应来源不同 — 即 **CI 跑 canned, 手工跑 live, 代码零分支**。

    **C. Prisma Migration `20260423000000_planner_llm_refinement/migration.sql`** (与 schema.prisma 同步):
    - `platform_topics` 加 3 列: `realism_score DECIMAL(3,2)` / `llm_refined_at TIMESTAMPTZ` / `audit_status VARCHAR(20)` + CHECK (`audit_status IN ('approved','pending_review','rejected')`) + 2 索引
    - `platform_prompts` 加 2 列: `llm_naturalized_at TIMESTAMPTZ` / `naturalize_confidence DECIMAL(3,2)` + 索引
    - `query_executions` **零顶层列变更**, 只加 `COMMENT ON COLUMN attempts` 文档化 `browser_profile` (Session 2) + `rewrite_meta` (Session 2.1) JSONB 子字段, 顶层列再加由 Harness G3 拦截

    **D. Group H Harness 三条新规则 + 自验证 fixture (决策 #21.C)** (`scripts/ci-check.mjs`):
    - **H1** `planner-must-invoke-llm` — 扫 `backend/src/platform/planner/**`, basename 匹配 `topic-pool` 时要求 token `refineTopicsWithLlm` + `naturalizePromptsWithLlm` + `rewriteQueriesForProfiles` 三者齐备 (任一缺失即 block 3 层 LLM 编排被静默删)
    - **H2** `query-rewrite-must-preserve-intent` — basename 匹配 `query-assembler` 时要求 token `classifyIntentHeuristic` 出现 (Gate 1 intent-drift 守卫被卸时拦截)
    - **H3** `query-rewrite-must-preserve-brand-vocab` — basename 匹配 `query-assembler` 时要求 `findBrandMentionsInText` + `anyKeywordPresent` 双 token (Gate 2a brand vocab + Gate 2b 品类 leak 双守卫被卸时拦截)
    - 3 个 self-seeded fixture: `__ci_fixtures__/H1_planner_no_llm_threading_topic-pool.cifixture.ts` / `H2_intent_drift_query-assembler.cifixture.ts` / `H3_brand_vocab_query-assembler.cifixture.ts`, basename 匹配 rule pattern, docstring **故意不 mention 必要 token** (memory `feedback_fixture_naming.md` — content.includes() 会自满足导致 selftest silently pass)
    - `scripts/ci-harness-selftest.mjs` EXPECTED_POSITIVES 15 → 18, 实测 `● selftest: PASS  (18 / 18 fixture expectations met)`

    **E. Vitest 399 → 464 (+65 新测试)**: `topic-pool.test.ts` 18 例覆盖 LLM threading (含 determinism / 桶 LLM 失败容错 / budget exhausted / 时间戳 stamping / 三层 envelope 联动 / refine 保 input by reference); `topic-planner.test.ts` / `prompt-generator.test.ts` / `query-assembler.test.ts` 各扩 LLM 分支 (skeleton-only baseline + LLM-on path 双轨); `llm-canned-responses.test.ts` 新文件覆盖 canned transport pattern matching。最终 42/42 文件 / 464/464 例全绿。

    **F. 端到端 Sample Dump (`backend/scripts/dump-planner-samples.ts`)**: Decision #27 / Task 8 — 跑 `generatePlatformPlan` 接 InMemory beauty industry (Estée Lauder + L'Oréal + Advanced Night Repair + Revitalift + 关系边) + canned LLM, 写 `planner-samples-20-20-20.json` (20 topic + 20 prompt + 20 query 完整 personaSnapshot + rewriteMeta), 是 Frank 视觉审查 query 真实度的入口。Live VOLC 跑法见 `docs/SESSION_2_1_LIVE_SMOKE_DEFERRED.md` (改 1 行 transport 即可)。**实测输出**: topics=17, prompts=400, queries=2614, llmCalls=3031, costUsd=0.7714, rewriteModes={llm:1578, fallback_prefix:1036, skeleton_only:0} — `llm` + `fallback_prefix` 两路都覆盖, `skeleton_only` 只在双失败时触发。

    **G. 偏差登记 (决策 #25 Rule 3)**

    - **C1 (Live VOLC smoke 延后)**: `backend/.env` 的 `VOLC_API_KEY=""` 为空, Phase Gate 接受 canned-transport dump 作为 LLM-threading 的等效证据。Live smoke 是手工后续任务 (类似 A0 Step 12 sandbox 限制), 不 block Session 3。文档化于 `docs/SESSION_2_1_LIVE_SMOKE_DEFERRED.md`: canned 与 live 走同一代码路径, 只换 transport, JSON 形状一致, cost 行不同。

28. **Session 1.2 · Camoufox + MVP 3 引擎 Adapter Live 化 (进行中, Phase A 规划 2026-04-23 / 双修正预先登陆 2026-04-22)**: Session 1 交付的是 "结构框架 + 可测试纯逻辑" (决策 #22), 所有 Adapter 的 `execute()` 仍是 TIMEOUT sentinel, Camoufox / 真实 HAR / routeFromHAR 契约测试 / CAPTCHA 真集成全部延到本 Session。**双修正预先登陆 (commit 5f05229, 27 files, +971/-186, 2026-04-22)**: 主体 §1-§8 未开工前, 先把两条横切关注点固化为不可回退的基线, 避免主体实施时漂移。**Phase A 规划 (2026-04-23)**: 开工前 Frank 追问 "账号 cookies 不是应该有自动注册流程来获取的吗" + "账号的管理，是否应该属于 admin 的模块？但是这个都是共享的 pipeline 的功能？", 触发两项 Phase A 决策 — (i) 拉回鲁班 SMS live 与 auto-register live 到本 Session (规则 12 Type C scope 扩张, 登记于 C2), (ii) 固化 Platform Layer 边界 (A 段) 避免 App / Admin 双轨代码。

    **A. Platform Layer 边界固化 (Phase A 规划, 2026-04-23)**

    Frank 提出的"账号管理归属"问题固化为三层架构: **账号管理的业务逻辑是 Platform Layer 资产 (App + Admin 共享), Admin UI 只做视图消费**。

    **三层架构**:
    - **Layer 1 · 契约层** (`docs/ADAPTER_CONTRACT.md §5.1 账号状态机 / §5.3a Pre-Warm 7 步 / §5.4 自动注册 (CN 引擎)`): 语义真相源, App 和 Admin 均不得偏离
    - **Layer 2 · Platform Layer** (`backend/src/accounts/**`): 业务逻辑实现, 共享给 App + Admin。包含 `sms/luban.ts` (鲁班 SMS live client) / `auto-register.ts` (自动注册编排器 live) / `pool.ts` (DB-backed 选择器 + LRU + watermark) / `state-machine.ts` / `prewarm.ts` / `crypto-noop.ts` (MVP 明文 identity, 未来 AES-GCM 替换入口) / `db-repo.ts` (Prisma 适配) / `cli/*.ts` (3 CLI 命令: `accounts:list` / `accounts:register` / `accounts:inject`)
    - **Layer 3 · Consumers**:
      - **App Session 1.2 (本 Session)** 交付 Platform Layer + CLI (供 Frank 手工入池 ChatGPT / 验证 doubao + deepseek-CN 自动注册)
      - **Admin Session A2 Tab 1 账号池** 交付 HTTP wrapper (`/admin/api/v1/pipeline/accounts/*`) + UI (引擎水位卡 + 账号列表 + JSON 批量导入 + "为引擎 X 新增账号" 按钮), API handler 一律 `import { ... } from '@/accounts/**'`, **严禁** 重写 Luban / auto-register / crypto

    **边界纪律**:
    - Admin API handler 只做 RBAC + audit 包装 + 调 Platform Layer, 零业务逻辑
    - Platform Layer 零依赖 Next.js / Admin 路由, 可脱 HTTP 层独立跑 (CLI + 单测 + 未来 worker 进程都复用)
    - 双轨代码检测 (未来 A2 开工前登陆为 harness): `no-luban-import-outside-accounts-dir` 扫 `backend/src/app/admin/api/**`, 不得直 import `sms/luban.ts` (必须走 `@/accounts/index.ts` re-export), 阻止 Admin 绕道实现
    - 四文档同步 (2026-04-23 完成): `docs/ADMIN_PRD.md §4.2.4` 架构边界块 + 明文契约 / `docs/ADMIN_CLAUDE_CODE_SESSIONS.md §A2` 前置依赖 + §A2 Tab 1 cookie 存储 + 自动注册按钮 / `CLAUDE.md #28.A` + `#28.C` / `docs/CLAUDE_CODE_SESSIONS.md` Session 1.2 Prompt 续推 §1/§2/§4/§5/§6

    **G. 双修正最终版 (2026-04-22 预先登陆)**

    - **C1 (双修正最终版)**: commit 5f05229 含 migration `20260424000000_session_1_2_adapter_hardening/migration.sql` + Harness F4 三子规则 + 21/21 selftest 全绿 + 464/464 vitest 全绿, 作为主体开工的稳定基线 (HEAD 必须在此或之后)
    - **C2 (Harness F4 三子规则)**: F4-1 adapter execute() 返回点必须 stamp `responseSource` / F4-2 api-fallback 返回点必须 stamp `responseSource: 'api_fallback'` / F4-3 `prisma.aiResponse.create` 插入必须带 `responseSource` — 三处 fixture self-seeded, 任一被卸 selftest 立挂
    - **C3 (6 枚举 response_source labeling)**: `ai_responses.response_source` 枚举 = `web_ui | api_fallback | mock_proxy | cached_replay | admin_har_replay | harness_fixture`, 所有写入必须显式 label, NO SCHEMA DEFAULT (backfill 后立即 DROP DEFAULT); 决策详情见 `.auto-memory/feedback_genpano_no_api_scraping.md`
    - **C4 (MVP 3 引擎口径)**: MVP 仅 `chatgpt | doubao | deepseek-CN`, Gemini/Claude/Bing 延后; `deepseek-CN` 是 EngineId literal (区分将来可能的 `deepseek-overseas`), 目录路径仍为 `backend/src/engines/adapters/deepseek/` 不改

    **C. 偏差登记 (决策 #25 Rule 3, 2026-04-23 Phase A 追加)**

    > 以下 C1 / C2 属于 Phase A 规划阶段的偏差登记, 与上方 G 段内部编号的 C1-C4 (双修正最终版) 是两组互不覆盖的清单 — G 是已登陆的横切基线, 此处是 Phase A 开工前的范围与方案调整.

    - **C1 (MVP 不加密 cookie, B1 路径)**: Frank 反馈 "应该不需要加密？后续很快就会有 UI, 而且账号也不值钱" → 撤回 AES-256-GCM + envelope encryption 方案, MVP 直接在 `accounts.encryptedCookies Bytes?` 字段存明文 UTF-8 JSON (`JSON.stringify({cookies, localStorage, userToken?})` 的 UTF-8 bytes). **字段名保留不改** (B1 路径, 不做 schema rename), Bytes 类型保留, 给日后加密升级当无感入口 — 未来切 AES-GCM 只改 `crypto-noop.ts` 这一个文件, 不需要跑 migration 改列名 / 迁移存量. 视图层 mask (UI 回显永远 `***` / 审计日志不记明文 cookie) 与底层加密解耦, 两条行为纪律独立生效. **风险可接受**: 账号本身由鲁班临时号注册 / 被 ban 周期性更换 / MVP 数据价值低 / cookies 失效窗口短. **真相源同步**: `docs/ADMIN_PRD.md §4.2.4` 存储要求段已改写 (原 "KMS 加密" → "MVP 明文 + 字段保留"), `docs/ADMIN_CLAUDE_CODE_SESSIONS.md §A2` Tab 1 Cookie 存储条目同步, Platform Layer 单一入口 `backend/src/accounts/crypto-noop.ts` 即 encode/decode 分界.
    - **C2 (Luban SMS live 拉回本 Session, 规则 12 Type C scope 扩张)**: Session 1.2 原 Prompt §2 "不做" 列把鲁班 SMS live 延到 Session 1.2.2, 但 Frank 在本 Session 开工前问 "账号 cookies 不是应该有自动注册流程来获取的吗" + "还是需要通过鲁班 SMS 完成账号注册, cookies/cookies+localstorage 的保存, 再注入 cookies", 显示延后方案会出现 "有注册框架但跑不起来 → Adapter execute() 无账号可用 → Phase Gate 假绿" 的链式空洞. 按决策 #25 规则 12 Type C (scope overflow 需显式登记), Phase A 规划把 Luban live 拉回本 Session, 同步 (a) `backend/src/accounts/sms/luban.ts` stub → live HTTPS client + `process.env.LUBAN_API_KEY` / (b) `backend/src/accounts/auto-register.ts` stub → live 编排器 / (c) doubao + deepseek-CN 两家引擎的 sign-up 页面导航 + 表单填写 + OTP 注入 + cookie 导出. **ChatGPT auto-register 仍延后**: ChatGPT 拒 datacenter IP 注册 + Cloudflare iframe 强拦 + MVP 海外手机号方案 Frank 尚未验证, 走手工 `accounts:inject` CLI 导入 (Frank 自备 cookie bundle). 拉回后 Session 1.2 交付步数从 12 步 → 16 步 (见 `docs/CLAUDE_CODE_SESSIONS.md` Session 1.2 续推 §5), Phase Gate 接受标准从 "execute 能跑" 扩为 "execute 能跑 + 每引擎 ≥2 active 账号 + `account_registration_logs` ≥2 success 行 + 3 个 CLI 命令 help 可跑".

    **A-F (主体 §1-§8 待本 Session 续推完成后回填)**: 续推 Prompt 见 `docs/CLAUDE_CODE_SESSIONS.md` Session 1.2 "Prompt 续推 (2026-04-23)" 段; 结构性缺陷 3 条修复已通过决策 #25 Phase 2 追加规则 10/11/12 关闭。**Session 收尾时**: header 改 "交付 (2026-04-XX)", A-F 按实施结果回填 (Camoufox launch / humanize 真实实例化 / 豆包 execute / DeepSeek-CN execute / CAPTCHA Level 1 / golden HAR + routeFromHAR 契约测试 + Luban live + auto-register live + CLI 3 命令各 1-3 段), A 段 (Platform Layer 边界) / C 段 (C1/C2 偏差) / G 段 C1-C4 不动。
    - **C2 (test 字段名修正回潮)**: 实施过程一度在 dump 脚本和 topic-pool.test.ts 写了 `t.id` / `p.topicId` / `'overseas-us'` 三处与真相源 (`PlannedTopic` 无 id / `PlannedPrompt` 用 topicIndex / `Region` 是 `'tier1'|'tier2-3'|'overseas'`) 不符的字段, vitest esbuild 不强检通过, `tsc --noEmit` 才暴露. 修复方式: dump 脚本改为 `topics.map((t, idx) => ({ topicIndex: idx, ... }))` + 测试改为 `prompts.filter(p => p.topicIndex === ...)` + Region 改 `'tier1' | 'tier2-3' | 'overseas'` 三档枚举. **教训**: vitest 默认 transpile-only, 类型偏差只能靠 `tsc --noEmit` 兜底, Phase Gate 必须 `npx tsc --noEmit` 全绿 + `npm run test` 全绿双绿才放行.

29. **Python pivot + 11 Session 重写 (2026-04-26)**: Frank 在 2026-04-26 决策架构反转 — TypeScript/Next.js 后端报废, 全栈切 FastAPI + SQLAlchemy 2.0 async + Alembic + Celery + Redis + Pydantic v2 + uv (package manager) + ruff + mypy strict; 前端保 Vite + React 18 + JSX (TSX 迁移延 Phase 2) + Tailwind + TanStack Query v5 + Recharts + AntV G6 v5. 工作仓从 `GENPANO_Claude_Lead/` 切到 `C:\Users\frank.wang\genpano` (jotamotk/GenPano.git, 32 份战略文档已迁入), `query_tool/` 排除. master Session 0 / A0 / 1 / 1.5 / 2 / 2.1 / 1.2 (决策 #21-#28) 后端代码全部报废, 但**决策本身仍是真相源** — 业务规则 / 测试纪律 / Harness 思想全部承继, 只是从 TypeScript 翻译到 Python (例: 决策 #28.G C3 的 6 枚举 response_source labeling, 在 Python 仍走 SQLAlchemy enum + 同名 Harness; 决策 #26.C1 attempts.browser_profile JSONB 子字段路径不变). 前端 IA v2.0 (决策 #2 Brand/Industry Mode) 已在 jotamotk 仓 21 页 JSX 落地 (含 brand/ 子目录 5 页), 不重写, 渐进式迁移.

    **A. 11 Session 重写计划真相源**: `docs/REPLAN_2026_04_26.md` (442 行 / 10 章) 是本次架构反转的**唯一真相源**, §4 列 11 Session 规格 (Session 0' / A0' / 4a' / 1' / 1.5' / 1.2' / 2' / 2.1' / 3' / A1' / 4b'). 注意 jotamotk 合并仓内的 `PRD.md` (29KB v1.2) 是**作废副本**, master `docs/PRD.md` (425KB v1.3) 仍权威. CLAUDE.md 决策 #1-#28 全部承继 (Python 翻译版), 此 #29 是承上启下的 anchor 决策, 后续所有 2026-04-26+ 工作都以 REPLAN_2026_04_26.md §X.Y 为真相源, **不再** 在 CLAUDE.md 内逐项展开 (避免 ~10K 行膨胀).

    **B. 11 Session Prompt 已交付**: `docs/SESSION_*_PRIME_PROMPT.md` (11 文件) 全部按决策 #25 12 公约编写 (真相源锚定 / Pre-Flight Grep / 偏差记录 / STOP-Trigger Type A/B/C / MVP scope-cut 等), 每份 Prompt 都引 REPLAN_2026_04_26.md 作主真相源 + 引 PRD §X.Y / ADMIN_PRD §X.Y / CLAUDE.md #X.Y 作子真相源. **Plan J D1 (2026-04-26)**: 旧 Session A5 (Citation Tier CRUD + MCP Token 签发 + Redis 60s 吊销黑名单) 整体并入 Session A1', 不再单独排期; SESSION_A1_PRIME_PROMPT.md §1 / §2 / §3 / §7 + REPLAN_2026_04_26.md §4 已同步更新, A1' 范围扩为 "用户/KG/Pipeline 监控 + Citation Tier CRUD + MCP Token 签发", 决策依据 = 决策 #19 Citation Tier 5 级权重锁定 + 决策 #21.E A5 规格 + DECISION_LOG.md 新建索引 (见 D 段).

    **C. 横切要求 (auto-memory `feedback_genpano_session_preview_env_2026_04_26.md`)**: 每个 Session 结束必须 (1) 代码经 Git CI/CD 上 preview env (Vercel / Render / Fly.io 任一); (2) 前后端联动可点击产物; (3) Frank 能在浏览器自验. Session 0' (CI/CD 基建) 必须先消化此横切要求.

    **D. 分支策略 (auto-memory `feedback_genpano_branch_per_session.md`)**: 每 1-几个 Session 一个 feature 分支从 main fork; Session 0' 起点 = main 当前 HEAD; `claude/*` 4 分支不再 merge 沉淀但不并入; 不 cherry-pick 历史代码, Python 重构按 PRD 重做架构.

    **E. 偏差登记**: 本决策本身是 anchor pointer 形式而非展开形式, 偏离决策 #25 Rule 1 "重抄禁止". **理由**: 11 Session × 各 ~300 行细节 = ~3300 行内容, 全展开会让 CLAUDE.md 从 ~420 行膨胀到 ~3700 行, 严重影响检索. **替代方案**: REPLAN_2026_04_26.md 单文件 442 行集中承载 11 Session 规格, CLAUDE.md #29 只做 anchor pointer + Python 翻译纪律 + 4 项关键 cross-cutting 决策 (A/B/C/D). 未来 Session 完成后, 各 Session 的偏差登记进对应 SESSION_*_PRIME_PROMPT.md 末尾 `## C. 偏差登记` 段, 不再写回 CLAUDE.md.