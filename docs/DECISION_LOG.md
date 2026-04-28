# GENPANO Decision Log (Master Index)

> Single-table index of all architectural / product decisions.
> Source of truth for one-line decision summaries; full body lives in `CLAUDE.md` (working copy at `C:\Users\frank.wang\genpano\CLAUDE.md`).
> Drift between this index and CLAUDE.md is a CI block (see `scripts/decision-log-sync-check.mjs`).
>
> **Editing rules (Plan J D4, 2026-04-26)**:
> 1. New decision in CLAUDE.md MUST add a row here in the same PR.
> 2. SUPERSEDED decisions stay in this table — strike text in summary column with `~~...~~` and add a "(see #N)" pointer to the replacement decision number.
> 3. Decision number column is monotonic; never renumber.
> 4. Anchor column points to the decision body in CLAUDE.md (working copy line numbers; advisory only — find by `^N\. \*\*` regex if line shifts).

| # | Date | Title (one-line summary) | Status | CLAUDE.md anchor |
|---|------|--------------------------|--------|------------------|
| 1 | early | 代理架构: 爬取通用访问走代理, LLM API 走火山引擎国内直连 | active | line ~120 |
| 2 | 2026-04-20 | Brand Mode / Industry Mode 二 Mode IA (Stripe pill toggle, URL `/brand/*` vs `/industry/*`, Project MVP 隐身, 零 Project 态 → /onboarding) | active (SUPERSEDES 三视角分工 + §4.6.1 老 IA) | line ~121 |
| 3 | early | 数据采集: 平台级每日全量, 用户注册前数据已就绪 | active | line ~122 |
| 4 | early | 免费策略: MVP 全功能免费, Phase 2 自定义采集付费 | active | line ~123 |
| 5 | early | 四层 Pipeline: Topic → Prompt → Query → Response 递进 | active | line ~124 |
| 6 | early | 知识图谱: Industry → Category → Brand → Product + 关系边, LLM 初始化 + Response 挖掘迭代 | active | line ~125 |
| 7 | early | Project = 视角过滤器: 不存监测数据, 只引用 primaryBrand + competitors + preferences | active | line ~126 |
| 8 | early | 用户共建: 用户提交品牌 → 平台验证 → 入图谱成公共资产 | active | line ~127 |
| 9 | 2026-04-20 | Auth-Required 数据访问: 反转原 Data-Before-Auth, 全站数据页/API 必须先登录, MCP API Day-1 Bearer token | active (SUPERSEDES 原 §4.1.1c 路径 A/B/C) | line ~128 |
| 10 | 2026-04-20 | 零 Project 态 Route Guard → /onboarding: 4 步引导页, 取代 E1/E2/E3/E4 四面 Empty State | active (SUPERSEDES E1/E2 方案) | line ~129 |
| 11 | early | 国际化 China-first global-ready: zh-CN 主 + en-US 双语 Day-1 架构 | active | line ~130 |
| 12 | early | 品牌名称多语言匹配: nameZh/nameEn/aliases[] + 归一化匹配 | active | line ~131 |
| 13 | early | Engine-aware Prompt 语言: 豆包/DeepSeek 中文, ChatGPT 双语, Prompt 记 language + appliesToEngines | active | line ~132 |
| 14 | early | UI i18n 用 next-intl (Python pivot 后改为 i18next, 见 #29) | partially superseded by #29 | line ~133 |
| 15 | 2026-04-16 | Report 深化框架: 洞察 Stack (L1/L2/L3) × 三读者视角 (operator/manager/branding); Layer 3 不给 playbook 保留咨询业务边界 | active | line ~134 |
| 16 | 2026-04-16 | 提及率 non-brand 口径: 默认 dimension='品类' 的 Query, 品类 Topic+Prompt 禁含品牌名, 配额 ≥40% | active | line ~135 |
| 17 | 2026-04-16 | 可伸缩筛选栏: 主筛选 (时间+引擎+画像) + 扩展筛选 (维度+意图) 折叠 | active | line ~136 |
| 18 | 2026-04-17 | 测试高度自动化 A++: L1 Harness grep + L2 Vitest + L3 契约+HAR + L4 Playwright; CI < 12min, 0 Frank 介入 | active | line ~137 |
| 19 | 2026-04-17 | Citation 全链路固化 + 6 条行动面: 5 级 Tier 表 (1.0/0.7/0.4/0.15) + Tier 表禁硬编码 + tldts URL 归一化 + 互斥诊断 grep | active | line ~138 |
| 20 | 2026-04-20 | V2 分析页视觉统一 + Filter Bar + Heatmap + 数据口径: BrandTopicHeatmap, mentionRate 0-1 存储, DonutChart size=180, BCG sort 替代 reduce, productDetail brandId 走 query string (Wave-4); v3.2 跨 Mode 复用 IntentMatrix | active | line ~145 |
| 21 | 2026-04-21 | 2026-04-21 Review 修复闭环: 4 维度 8 P0 gap, 38 Harness 5 组 A-E + 7 数据契约 + 5 self-seeded 违规 + Session A5 (Citation Tier CRUD + MCP Token) | active (A5 后于 #29.B 并入 A1') | line ~146 |
| 22 | 2026-04-21 | Session 1 · AI 引擎爬取框架交付 (TS, Adapter + Parser + Scheduler + Account Pool + HAR + Group F Harness F1/F2/F3) | superseded by #29 (TS 报废) — 业务规则承继 | line ~176 |
| 23 | 2026-04-21 | Session 1.5 · 行业知识图谱 Platform Layer 交付 (KG 冷启动管线, 端口/适配器范式, 219 tests) | superseded by #29 (TS 报废) — 业务规则承继 | line ~192 |
| 24 | 2026-04-21 | Session A0 · Admin 认证脚手架交付 (JWT + 6 auth endpoints + Rate Limit + Bootstrap Seed + Silent Refresh + Route Guard, D8/D9/D10 Harness) | superseded by Session A0' (Python 重写, 见 #29) — 业务规则承继 | line ~234 |
| 25 | 2026-04-21 | Session Prompt 编写公约固化: 7 公约 (rule 1-7) + Phase 2 追加 rule 10/11/12 (MVP scope-cut / Pre-Send Freshness / STOP-Trigger Type A/B/C) | active | line ~284 |
| 26 | 2026-04-22 | Session 2 · 智能监测 Pipeline (Topic/Prompt/Query) 交付; persona snapshot 注入 attempts.browser_profile JSONB (禁加 query_executions 顶层列, Harness G3 守护) | superseded by #29 (TS 报废) — 业务规则承继, JSONB 路径不变 | line ~299 |
| 27 | 2026-04-22 | Session 2.1 · Planner LLM Refinement (3 层 LLM: Topic Refine + Prompt Naturalize + Query Rewrite); rewrite_meta 进 attempts JSONB; Group H Harness H1/H2/H3 | superseded by #29 (TS 报废) — 业务规则承继 | line ~355 |
| 28 | 2026-04-23 | Session 1.2 · Camoufox + 3 引擎 Adapter Live 化 (含 Phase A: Platform Layer 边界 + MVP 不加密 cookie + Luban SMS live 拉回); 6 枚举 response_source labeling, Harness F4 三子规则 | superseded by Session 1.2' (Python, 见 #29) — 边界纪律 + response_source 枚举承继 | line ~384 |
| 29 | 2026-04-26 | Python pivot + 11 Session 重写: TS/Next.js 报废, 切 FastAPI + SQLAlchemy 2.0 async + Alembic + Celery + Redis + Pydantic v2 + uv + ruff + mypy strict; REPLAN_2026_04_26.md 真相源; 11 SESSION_*_PRIME_PROMPT.md 已交付; Plan J D1: 旧 Session A5 并入 Session A1' | active (anchor decision for all 2026-04-26+ work) | line ~420 |
| 30 | 2026-04-28 | Session A0' Phase Gate 接受标准 4 轮偏离 + Bug 4 logger gap: Round 1 Vercel 跳过 + Round 2 docker compose 跳过 + Round 3a 手工 L3 9 场景重跑跳过 + Round 3b 邮件实际发送跳过 (mock 模式 + Bug 4 logger 可观察性 gap, 修复方向 dictConfig + structlog + JSONRenderer); A1' 转交清单含 Bug 1-4 + Resend live + #24.C4 schema gap + preview env + docker-compose + 5 个 TS 时代 .mjs scripts 清理 | active (deviation registration for #29.C; transfer list to A1') | line ~432 |
| 31 | 2026-04-28 | MVP scope-cut: minimax 视频解析 / minimax 网页爬取 archaeology 空集; T1-T6 read-only 扫描确认 main 零代码 / 零 schema / 零真相源, MiniMax 仅在 PRD §4.2.2a future 候选行出现; MVP 3 引擎锁 `chatgpt|doubao|deepseek-CN` 不追加; claude/* archive 不删不 merge 不 cherry-pick; A1' Step 0 unblock | active | line ~445 |

## How to use this index

- **Adding a new decision**: append row, increment number, point anchor at the decision body line in CLAUDE.md, run `node scripts/decision-log-sync-check.mjs` before commit.
- **Looking up a referenced decision**: scan one-line summaries here first; only open CLAUDE.md if you need the body. This is the entry point that decision #25 rule 6 now points to.
- **Superseding a decision**: do NOT delete the row; update Status to `superseded by #N`, optionally strike the summary with `~~...~~`. CLAUDE.md body stays as-is for historical record.
- **Sync harness behavior**: `decision-log-sync-check.mjs` greps CLAUDE.md for `^N\. \*\*` lines, counts max N, compares to row count of this table; mismatch = exit 1 = PR block.
