# GENPANO - Claude Code Session 规划

> 每个 Milestone 对应一个独立的 Claude Code Session
> 每个 Session 包含: 完整 Prompt、预期产出、验收标准、依赖说明
> 完整方法论参见 [HARNESS_ENGINEERING.md](./HARNESS_ENGINEERING.md)

---

## 重大架构反转公告 (2026-04-26, 决策 #29)

> **本文档自 2026-04-26 起进入双轨态**: 顶部 "§0-§13 Python Backend Sessions" 是当前活跃 Session 计划; 中部 "Next.js 时代 Sessions" (Session 0-rev / 0 / 1 / 1.2 / 1.5 / 2 / 2.1 / 3 / 4a / 4b / 5) **整体降级为附录 A**, 保留作历史参考与决策溯源, 但**不得作为新代码的实施依据**.

**触发**: Frank 用 jotamotk/GenPano.git 实验代码合并 PRD + 32 份战略文档后, 决策最优架构 = **FastAPI 0.111+ + SQLAlchemy 2.0 async + Alembic + Celery 5.4 + Redis 7 + Pydantic v2 + Playwright + Camoufox + python-jose + slowapi + passlib bcrypt + httpx**. 原 Next.js + Prisma + TypeScript 后端代码 (Session 0-rev / A0 / 1 / 1.5 / 2 / 2.1) **代码本身报废**, 但所有决策 #21-#28 中的**契约 / 算法 / 错误码 / 状态机 / 测试 fixture 命名规范 / Harness 规则**全部 transpose 到 Python 等价物 (见 `docs/SESSION_PROGRESS.md` 报废范围 + transpose 资产表).

**前端**: `frontend/` 目录 (React 18 + Vite + JSX + Tailwind + recharts + d3 + framer-motion + @antv/g6 + Radix + mixpanel-browser + lucide-react) **完整保留**, 不切 TSX, T1'-T6' 五个 UI Prototype Session 全部 ✅ 已交付且作为视觉/IA 真相源继续使用. DESIGN_TOKENS.md C1-C15 + 38 条 Harness 规则 (Group A-E + F1-F4 + G1-G4 + H1-H3 + D8/D9/D10) 整体保留, 等价 Python pytest 实现见 `HARNESS_ENGINEERING.md` §10.6.

**MVP Milestone × Session 编号** (见 `docs/REPLAN_2026_04_26.md` + `docs/SESSION_PROGRESS.md`):

| Milestone | Sessions | 周期 | 后端栈 | Phase Gate |
|---|---|---|---|---|
| **M1 · Foundation** | 0' (脚手架 + CI/CD + Preview Env), A0' (Admin Auth Python 重写), 4a' (用户系统 + Onboarding) | 2-3 周 | FastAPI + SQLAlchemy + Alembic + python-jose | Gate 1 |
| **M2 · Pipeline** | 1' (Adapter 框架 + Parser + Scheduler), 1.5' (KG 冷启动 + LLM Discovery), 1.2' (Camoufox + Live Adapter + Luban SMS) | 3-4 周 | Playwright + Camoufox + httpx + Celery | Gate 2 + Gate 3 |
| **M3 · KG + Planner** | 2' (Topic/Prompt/Query 三层), 2.1' (LLM Refinement), 3' (分析引擎 + API + MCP) | 2-3 周 | Pydantic v2 + Celery beat + Redis | Gate 3 |
| **M4 · Analyzer + UI** | A1' (Admin 用户管理 + RBAC + KG 审核), 4b' (Dashboard 数据接入 + 报告生成 + 咨询转化) | 1-2 周 | + 前端集成 | Gate 4 + Gate 5 |

**总计 11 Sessions / 8-10 周**. Phase Gate 链见 `HARNESS_ENGINEERING.md` §10.6.

**横切要求 (决策 #30 + #31)**:
- 每 Session 结束必须 (a) 代码 push 触发 GitHub Actions CI 全绿 (b) Preview env 部署成功 (Vercel/Render/Fly.io 任一) (c) Frank 浏览器自验前后端联动可点击产物
- 每 1-几个 Session 一个 feature 分支从 main fork (branch-per-session); claude/* 历史分支不再 merge 也不并入
- 真相源仍是 `CLAUDE.md` + `PRD.md` + `DATA_MODEL.md` + `ADAPTER_CONTRACT.md`; 决策 #25 的 12 条 Prompt 编写公约对 Python Sessions 同样生效

**详细 Session Prompts**: 各 Session 的 Prompt 在开工前现场起草 (按决策 #25 公约 + 决策 #30 preview env + 决策 #31 branch-per-session 模板), 不预先批量灌入本文档以避免 PRD/CLAUDE.md 决策漂移导致 Prompt 过时. 真相源永远是 `docs/SESSION_PROGRESS.md` 的 Session 状态表.

**附录 A (本文档下方 Session 0-rev 起的全部内容)**: Next.js 时代 Sessions 的 Prompt + 任务清单 + 验收标准, 状态全部由 `SESSION_PROGRESS.md` 标记为 📜 已归档. **不得作为新代码实施依据**, 但 (a) 决策 #21-#28 提到的算法 / 错误码 / 状态机 / Harness 规则 / fixture 命名作为 transpose 起点必须读 (b) UI Prototype Sessions T1'-T6' (本文档 line 4729+) 状态保持 ✅, 不属于附录 A 范围.

---

## 前置阅读 (必读文件)

- **`ADMIN_CLAUDE_CODE_SESSIONS.md` §0 (line 55 到 §0 末尾)** — Session Prompt 编写 9 条公约 (2026-04-21 固化规则 1-8, 2026-04-22 追加规则 9 · commit closure), **全 App + Admin + UI Prototype Session 通用**, 本文档不复写, 以 ADMIN §0 为单一真相源
- `CLAUDE.md` — 项目决策链 + Session 产出边界 (#21 测试地基 / #22 Session 1 / #23 Session 1.5 / #24 Session A0 等)
- `PRD.md` — 产品需求与功能规格
- `PRODUCT_PLAN.md` — 产品路线图与优先级
- `DATA_MODEL.md` — DB schema / 表级真相源
- `openapi.yaml` — API 契约 / 前后端真相源
- `ADAPTER_CONTRACT.md` §2.3 API Data Shapes、§8b Citation Attribution Rules
- `DECISIONS.md` — 决策记录，解释为什么选了 PATCH/plural/30 天窗口等
- `TEST_STRATEGY.md` §9-§13 — 异常场景矩阵 / Admin 测试矩阵 / P0-P2 优先级 / fixture 规范 / 38 规则血统表
- `REVIEW_2026_04_21.md` — 4 维度 8 P0 gap 修复闭环 (Session 0 起均不得回退)

---

## 使用指南

### 每个 Session 的标准流程

```
PRE-FLIGHT ✈️ (人类, 10-15min)
  □ 前置 Session 验收标准全部 ✅
  □ 阅读 CLAUDE.md 确认上下文完整
  □ 审查本次 Prompt — 根据实际情况微调
  □ 环境就绪 (DB, deps, env vars)
  □ Git 状态干净
  → 复制 Prompt 粘贴给 Claude Code

EXECUTION 🏃 (AI 主导, 人类旁观)
  - 观察但不频繁打断
  - 只在方向性错误时介入 (技术路线选错、需求理解偏差)
  - 记录可疑点，等 Session 结束后统一 Review

REVIEW 🔍 (人类主导, 1-2h)
  □ 逐条检查验收标准
  □ 手动 Smoke Test 核心流程
  □ 代码审查重点: 架构/抽象/安全/幂等
  → 问题分级: 小修(同Session) / 中修(Fix Session) / 大修(回 Phase 0)

POST-FLIGHT 🛬 (人类, 15min)
  □ 确认 CLAUDE.md 已更新 (新增决策号含 A/B/C/D/E 段, 见 ADMIN §0 规则 3 + 规则 8)
  □ 执行 git commit — 按 ADMIN §0 规则 9 落地模板 (PowerShell here-string + git commit --file, 标题固定 "Session {号}: {主题} - Phase Gate X/X PASS", body 回引 CLAUDE.md 决策号, 禁 §/✅/— 等特殊 Unicode); commit 后跑 `git log --oneline -3` 作 closure 证据
  □ 回顾: Prompt 哪里不够清晰? AI 在哪里走了弯路?
  □ 如需调整后续 Session Prompt → 回到 Cowork 对话修改
```

### 关键原则
- **Phase 0 投入十倍回报**: 在 Cowork 对话中把 Prompt 打磨好，比 Session 执行中纠偏高效得多
- **CLAUDE.md 是共享大脑**: 每个 Session 结束时让 Claude Code 更新 CLAUDE.md，这是下个 Session 的唯一上下文入口
- **不要跳 Session**: 严格按顺序执行，每个 Session 有前置依赖
- **代码是 AI 写的，重写成本低**: 发现方向性问题不要硬撑，回到 Phase 0 纠偏后重新跑 Session
- **复杂 Session 可拆分**: 如果 context 不够，让 AI 总结进展 + 更新 CLAUDE.md，新 Session 继续

---

## 通用 Session Preamble (App Session 通用, 2026-04-22 固化)

> **为什么有这一段**: Session 2 启动时发现 bootstrap Prompt 里反复出现"任务之外的增量" (环境锚点 / 前置决策 / 第一批动作等), 口头约定无处体现 — 违反 ADMIN 第 0 节规则 1 (禁重抄真相源). 本段把 App Session 共用的"环境 + 真相源指针 + 公约引用 + 完工条件 + 第一批动作"固化一次, 每个 Session 的 "### Prompt" 围栏开头一行引用即可, bootstrap 不再复写.
>
> **适用范围**: App Session 1 / 1.2 / 1.5 / 2 / 3 / 4a / 4b / 5 全部通用. Admin Session 走 `docs/ADMIN_CLAUDE_CODE_SESSIONS.md` 第 0 节公约 + Admin 各 Session 特有锚点, 不走本段. UI Prototype Session (T1'-T6') 已全部完成, 不再追加.

### P.1 环境锚点

- OS: Windows; 工作目录: GENPANO 仓根目录
- Git remote: origin = https://github.com/jotamotk/GENPANO_Claude_Lead.git
- 第一动作永远是 `git status` 复核 working tree 干净; 有 untracked / modified 先报告人类, 不自行 commit / stash
- 本 Session 所依赖的前置 Session 是否全绿, 见 `docs/SESSION_PROGRESS.md` 的 "App Track Gate 链"; Gate 未过禁止启动

### P.2 真相源索引 (全 App Session 通用)

| 真相源 | 用途 |
|---|---|
| `CLAUDE.md` (仓根) | 项目决策链 + 关键设计决策 + 设计锚点 + 依赖规则 + Harness 契约 (C1-C15) |
| `docs/ADMIN_CLAUDE_CODE_SESSIONS.md` 第 0 节 (line 55 起) | Session Prompt 编写 9 条公约, 全 Session 通用, 本文档不复写 |
| `docs/CLAUDE_CODE_SESSIONS.md` 顶部 "前置阅读" (line 7-19) | 本文档自身的前置阅读清单, 与本段互补 |
| `docs/PRD.md` | 产品需求 + 功能规格, 本 Session 涉及的段号由 "### Prompt" 围栏自列 |
| `docs/DATA_MODEL.md` | DB schema / 表级真相源 |
| `docs/ADAPTER_CONTRACT.md` | 引擎契约 / 错误码 / 状态机 / 副作用边界 |
| `docs/DESIGN_TOKENS.md` C1-C15 | UI 视觉 / 结构 / 图表契约 |
| `docs/TEST_STRATEGY.md` 第 9-13 节 | 异常覆盖矩阵 / Admin 测试矩阵 / P0-P2 优先级 / fixture 规范 / 38 规则血统表 |
| `docs/REVIEW_2026_04_21.md` | 4 维度 8 P0 gap 修复闭环, Session 0 起不得回退 |
| `docs/SESSION_PROGRESS.md` | Session 状态索引 + Gate 链 + CLAUDE.md 决策号对照 |

本 Session 具体涉及哪些 PRD 段号 / schema 表 / 决策号, 由各 Session 的 "### Prompt" 围栏第 1 节 "真相源索引" 自列 (见 ADMIN 第 0 节规则 5). 本 Preamble 不预设.

### P.3 公约引用 (不复写)

开工前必读 `docs/ADMIN_CLAUDE_CODE_SESSIONS.md` 第 0 节 (line 55 到该节末尾) 的 Session Prompt 编写 9 条公约 (2026-04-21 固化规则 1-8, 2026-04-22 追加规则 9 commit closure). 本文档**不复写** 9 条规则内容, 9 条均对 App Session 生效.

### P.4 Pre-Flight Grep 契约

按 ADMIN 第 0 节规则 2 执行: 开工第一批动作必须自拟 3-6 条 grep, 覆盖本 Session 将动到的字段 / 表 / 函数 / stub / 常量, 报告人类后再写代码. 关键词由 "### Prompt" 围栏第 1 节真相源索引和本 Session 任务主体决定, 本 Preamble 不预设.

### P.5 完工条件 (缺一不可)

1. "### Prompt" 围栏内 "### 验收标准" 全部勾齐
2. Vitest coverage 四项 (branches / lines / funcs / stmts) ≥ 80% 不降
3. Harness (Group A-F + 本 Session 新增 Group G/H/…) selftest PASS; `scripts/ci-harness-selftest.mjs` EXPECTED_POSITIVES 同步上调
4. `CLAUDE.md` 新增决策号, 按 A0 决策 #24 的 A/B/C/D/E/F/G 段结构写齐 (含偏离说明 C1/C2, 见 ADMIN 第 0 节规则 3)
5. ADMIN 第 0 节规则 8 反向同步清单: grep 下游 Session 对本 Session 产出 (字段 / 表 / 函数 / 常量) 的引用, 清单报告人类, 已引用处反向 patch
6. ADMIN 第 0 节规则 9 commit closure: PowerShell here-string + `git commit --file commit-msg.txt`, 标题 `Session {号}: {主题} - Phase Gate X/X PASS`, body 回引 CLAUDE.md 决策号, 禁 `§/✅/—/🚫` 等特殊 Unicode; commit 后 `git log --oneline -3` 贴回"完成后报告"作 closure 证据
7. 更新 `docs/SESSION_PROGRESS.md` 本 Session 状态 ⬜/🟡 → ✅; CLAUDE.md 决策号对照表追加新行
8. 更新 `docs/MEMORY.md` 追加 1 行决策索引 (若本 Session 产出新决策); 仅当本 Session 产出 cross-Session 可复用 pattern 时才在 `docs/auto-memory/` 写 archive 文件 (对齐 A0' 实际落档机制 — A0' Step 12 commit 09014b0 仅写了 1 个 cross-Session pattern, 未写 per-session delivery archive)

### P.6 第一批动作模板

1. `git status` 复核 working tree 干净
2. Read `docs/SESSION_PROGRESS.md` 确认本 Session 可启动 + 前置 Session 状态
3. Read `docs/ADMIN_CLAUDE_CODE_SESSIONS.md` 第 0 节 9 条公约 (line 55 起)
4. Read 本文档 "### Prompt" 围栏任务主体
5. Read "### Prompt" 围栏第 1 节真相源索引列出的 PRD / schema / ADAPTER_CONTRACT / TEST_STRATEGY 段落
6. 按 P.4 拟 Pre-Flight Grep 跑, 报告人类后进入任务主体

---

## Preflight Session (Session -1): 研发前体检 ⭐ NEW (2026-04-21)

> **定位**: Session 0 之前执行一次。**只读盘点, 不写任何生产代码**。产出一份 `docs/PREFLIGHT_REPORT.md` 作为"从原型阶段切到生产级开发"这条分界线上的账面, 让后续 Session 0 (脚手架 / 测试骨架) 和 Session 1+ (业务功能) 的执行方案有客观依据, 而不是在 Cowork 里凭记忆猜。
>
> **为什么要有这一 Session**: 仓库当前实态 ≠ Session 0 当初假设的"空仓库冷启动"。`frontend/` 跑过 5+ 轮 UI 迭代 (Wave-4 / IA v2.0 / Plan S v3.1 v3.2 等), `backend/` 状态未知, `docs/` 已含 20+ 条关键设计决策 + C1-C15 Harness 契约, 但这些决策里哪些已落进代码、哪些只停留在文档、哪些出现了 SUPERSEDED 悬空引用——没盘清之前, 每个 Session Prompt 里的"全绿即 merge"都立不住脚。

### Prompt

```
你是 GENPANO 项目的体检官。本次 Session 的**唯一职责是盘点, 不是修复**——除了新建一份 docs/PREFLIGHT_REPORT.md, 严禁修改任何既有文件、严禁安装依赖、严禁执行迁移、严禁 commit 代码改动。发现问题记进报告, 由我 (Frank) 决定下一步。

## 前置阅读 (必须按顺序读完再动手)

1. CLAUDE.md (仓库根, 完整读) — 特别是"关键设计决策"(目前 20 条) / "设计锚点"(4 张子表) / "依赖规则" / "UI vs Prompt 指引边界" / "图表契约 Harness 拦截"(C1-C7) / "V2 分析页统一契约 C9-C15 Harness" / "依赖规则"
2. docs/PRD.md — 重点 §4.1.1-gate / §4.1.1-form / §4.2.6 / §4.2.7 / §4.6-IA-v2 / §4.6.0a / §4.6.1g (v3.2) / §4.10.4a / §4.11
3. docs/CLAUDE_CODE_SESSIONS.md — 本文件, 对照现有 Session 0-5 + T1'-T5' (若已写入) 看有没有引用的文件是 CLAUDE.md 锚点表里声称要建但尚未存在的
4. docs/DESIGN_TOKENS.md — 全文, 特别是 C1-C15 图表契约段
5. docs/TEST_STRATEGY.md — 4 层 4 支柱
6. docs/ADAPTER_CONTRACT.md — 至少扫目录, 章节标题
7. docs/DECISIONS.md — 历史决策记录

## 体检 6 轴 (每轴独立产一节报告)

### 轴 1 · 文档内一致性
扫描 PRD + SESSIONS + DESIGN_TOKENS + CLAUDE.md 之间的引用链:
- 列出所有 "SUPERSEDED by §X.Y" 标记, 对每条验证新章节 §X.Y 确实存在且语义完整
- 列出任何 PRD 章节号被引用但找不到目标章节的情况 (悬空引用)
- 列出 CLAUDE.md "关键设计决策" 20 条中, 每条的 PRD / SESSIONS 锚点章节是否都落地 (逐条打勾或标记缺失)
- 列出 CLAUDE.md "设计锚点" 表里声称存在的文件, 实际在 frontend/src/ 下是否真的存在 (grep/ls 验证, 不存在的标红)

### 轴 2 · Frontend 实态 vs CLAUDE.md 声明
- `ls frontend/src/pages/` 和 `ls frontend/src/pages/brand/` 和 `ls frontend/src/pages/industry/`, 对照 CLAUDE.md "设计锚点" 第 1 表 "结构锚点"
- 列出已存在的页面 vs 待建页面 (T1'-T5' 任务清单预估)
- 列出应该已被废弃但还残留的页面 (DashboardPage / BrandDetailPage / DiagnosticsPage 跨品牌聚合 / DashboardEmptyState / ProjectRequiredBanner / LandingNavQuickCreateButton / IndustryTopicCoverageHeatmap / components/industry/IndustryTopicIntentMatrix)
- 列出 frontend/ 根下可以清理的临时构建产物 (dist-v3/v31/v32/wave4/wave4rb 等), 是否该并入 .gitignore 或物理删除 — 仅列清单, 不动手

### 轴 3 · Harness C1-C15 基线
对 CLAUDE.md "图表契约 Harness 拦截" (C1-C7) 和 "V2 分析页统一契约 C9-C15 Harness" 里的**每一条 grep 命令**原样跑一遍, 记录:
- 命令原文
- 当前输出 (pass = 无输出 / fail = 输出行数 + 首 3 行示例)
- 对应代码位置 (文件:行号, 便于后续修复定位)
- 注: Wave-4 新加的 C15-1/2/3 (BrandProductDetailPage brandId query string 契约) 必须验证

同时标记:
- 哪些 grep 规则**只存在于 CLAUDE.md 文档**, 但没有进 .husky/pre-commit 或 scripts/ci-check.mjs (即"纸面 Harness"而非"可执行 Harness")
- C3/C7 的运行时断言 scripts/check-data-contracts.mjs 是否真的存在, 能否跑

### 轴 4 · 依赖清单核对
打开 frontend/package.json 和 (如存在) backend/package.json, 对照 CLAUDE.md "依赖规则" 的 14 行表:
- 每行: 已装 ✅ (版本号) / 未装 ❌ / 装了替代品 ⚠️ (列出实际装的)
- 特别检查: Recharts / AntV G6 v5 / D3 / TanStack Table / React Hook Form / Zod / Framer Motion / date-fns / SWR 或 TanStack Query / Sonner or react-hot-toast / Radix UI Dialog + Select / Lucide React / @react-pdf/renderer / @dnd-kit / mixpanel-browser + mixpanel / tldts / openapi-typescript
- 列出 package.json 里存在但 CLAUDE.md 表中没声明的额外依赖, 评估是否有存在必要

### 轴 5 · 测试基础设施就位度
对照 docs/TEST_STRATEGY.md 的 4 层 4 支柱 + Session 0 §5 的配置清单, 逐项勾选:
- vitest / @vitest/coverage-v8 / @testing-library/react / @testing-library/jest-dom / jsdom
- @playwright/test (含 toHaveScreenshot)
- husky + lint-staged + .husky/pre-commit 文件实际内容
- openapi-typescript + openapi.yaml 是否作为真相源被任何测试引用
- vitest.config.ts / playwright.config.ts 是否存在
- .github/workflows/ci.yml 是否存在, 若存在列出 job 清单
- scripts/ci-check.mjs 是否存在
- test-data/ 目录当前内容 (若用于 HAR 回放或 mock 基线)

报告应能告诉 Frank: "Session 0 §5 的测试骨架当前完成度是 X/N 项, 缺 Y/N 项"

### 轴 6 · Backend + 数据层实态
对 backend/ 做一次扫描:
- 是否有 package.json, 是什么框架 (Next.js / Fastify / Hono / 空)
- 是否有 Prisma schema.prisma, 若有列出当前 model 清单, 对照 PRD §5.3 + DATA_MODEL.md 的 Platform Layer + User Layer 14+ 表
- 是否有迁移文件
- 是否有 .env.example, 列出变量清单对照 Session 0 要求的 (DATABASE_URL / VOLC_API_KEY / RESEND_API_KEY / MIXPANEL_TOKEN / SENTRY_DSN)
- 是否有任何 API 路由实现 (api/ 或 app/api/ 目录)
- openapi.yaml 的 endpoint 清单 vs backend 实际实现的 endpoint, 差异列表

## 输出

在 docs/PREFLIGHT_REPORT.md 落一份报告, 结构:

```
# GENPANO 研发前体检报告 (生成日期)

## 摘要 (Executive Summary)
- 文档一致性: X 处悬空 / Y 处 SUPERSEDED 未收尾
- Frontend 实态: A 个页面已建 / B 个待建 / C 个应废弃但残留
- Harness 基线: D/13 条 grep pass, E 条 fail, F 条只在文档未进 pre-commit
- 依赖清单: G/14 行表已装, H 行缺失
- 测试基础设施: I/N 项就位
- Backend 实态: [一段话描述整体状态, 如 "仅脚手架" / "含 schema 未迁移" / "空"]

## 1. 文档内一致性详表
...

## 2. Frontend 实态详表
...

## 3. Harness C1-C15 基线详表
(按 Cx-y 逐条列: 规则 / grep 原文 / 结果 / 文件:行号)
...

## 4. 依赖清单核对详表
(14 行表 + 额外依赖评估)

## 5. 测试基础设施就位度详表
...

## 6. Backend + 数据层实态详表
...

## 建议下一步 (给 Frank)
- 优先级 P0 (阻塞 Session 0 执行): [...]
- 优先级 P1 (Session 0 内顺手处理): [...]
- 优先级 P2 (Session 1+ 再说): [...]
```

## 硬约束 (违反 = 本 Session 失败)

- ❌ 不得修改任何既有文件 (唯一允许的写操作: 新建 docs/PREFLIGHT_REPORT.md)
- ❌ 不得运行 npm install / pnpm install / yarn
- ❌ 不得运行 npm run dev / build / test 等触发写入的命令 (只读的 ls / grep / cat / find 允许)
- ❌ 不得运行 git commit / git add / git push
- ❌ 不得修改 CLAUDE.md (即便发现文档里有笔误/小漏, 也只记进报告, 不改)
- ✅ 允许运行 CLAUDE.md 里列出的 grep 命令 (只读)
- ✅ 允许 cd frontend && ls / cat package.json (只读)
- ✅ 允许 node scripts/check-data-contracts.mjs (若存在), 这是现存 Harness, 只读

完成后把报告路径和 6 轴摘要数字贴回来, 由我决定是直接进 Session 0 还是先补 PRD 漏洞。
```

### 预期产出

- `docs/PREFLIGHT_REPORT.md` (新建, 唯一的写操作)
- 报告 6 节 + 摘要 + 建议下一步
- 每一节都含"具体数字 + 具体文件:行号引用", 不含模糊描述

### 验收标准

- 摘要段 6 行数字 (X/Y/A-F/G/H/I 等) 全部填实, 没有 "TBD"
- Harness 基线至少覆盖 13 条 grep, 每条输出 pass/fail + 文件定位
- 依赖核对 14 行表逐行状态明确 (✅/❌/⚠️)
- 未发生任何代码改动 (git status 除新报告外无其他变更)
- 报告末尾 P0/P1/P2 建议至少各 1 条

### 依赖说明

- **前置**: 无 (这是最早的 Session)
- **后续**: 基于报告结论, Frank 决定是否需要先在 Cowork 里修 PRD / SESSIONS 再跑 Session 0; 或直接跑 Session 0 但按报告调整任务列表

### 重启准则

- 若 Claude Code 在执行过程中开始主动修代码/改文档, 立即 Ctrl-C, 重开新 Session, 强化硬约束段
- 若报告只有模糊判断 (如 "大部分 OK" 而没有具体数字 + 文件行号), 要求重跑相应轴
- 若报告超过 800 行, 要求精简到 ≤500 行 (摘要 + 详表 + 建议, 不要复述 PRD 内容)

---

# 附录 A · Next.js 时代 Sessions (2026-04-26 报废, 决策 #29)

> 以下全部内容 (Session 0-rev / Session 0 / Session 1 / Session 1.2 / Session 1.5 / Session 2 / Session 2.1 / Session 3 / Session 4a / Session 4b / Session 5 / Session A0-A5 / 等) 属于 **Next.js + Prisma + TypeScript** 时代的 Session 规划, 已于 2026-04-26 决策 #29 报废, **不得作为新代码实施依据**.
>
> **保留理由 (3 条)**:
> 1. **算法 transpose 源**: 部分纯逻辑模块 (parsers / sentiment classifier / KG confidence math / Planner intent matrix / topic purity guard / persona FNV-1a sampler 等) 算法本身有效, 新 Python Sessions 可作为 transpose 参考蓝本
> 2. **决策追溯**: CLAUDE.md 决策 #22-#28 引用本附录 Session 实施记录作为偏差登记锚点, 删除会导致追溯断链
> 3. **harness 规则源**: 38 master harness 规则 (Group A-E + F1-F4 + G1-G4 + H1-H3 + D8/D9/D10) 需 transpose 到 Python pytest grep, 本附录的 fixture / selftest 设计是直接参考
>
> **新代码实施请使用**:
> - 顶部"重大架构反转公告 (2026-04-26, 决策 #29)" 段
> - `docs/SESSION_PROGRESS.md` (11 个 ⬜ pending Sessions: 0' / A0' / 4a' / 1' / 1.5' / 1.2' / 2' / 2.1' / 3' / A1' / 4b')
> - `docs/REPLAN_2026_04_26.md` (M1-M4 Milestone × Session 详细规划)
> - 各 Session 开工前现场起草 Prompt (按决策 #25 公约 + 决策 #30 preview env + 决策 #31 branch-per-session 模板)

---

## Session 0-rev (Post-Preflight · Current-State-Aware): 测试地基 + Backend 脚手架 ⭐ NEW (2026-04-21)

> **定位**: 替代原 Session 0 作为真正的第一个执行 Session。基于 `docs/PREFLIGHT_REPORT.md` 六轴结论, 跳过原 Session 0 §1-§3 (技术栈 / 项目脚手架 / 建 CLAUDE.md — 这些在 frontend 迭代阶段已经事实上完成), 收敛到**可执行 Harness + 测试骨架 + backend Prisma 脚手架**三件事。
>
> **范围（最小版）**: 不触 frontend 业务代码 / 不做 git mv 物理迁移 / 不清理 dist-*/ / 不修 C14 违规 — 那些留给 T5'/T6' 或 Frank 手工处理。本 Session 结束后, 仓库进入"每条 Harness 规则都可执行, backend schema 可迁移, CI 有零号基线"状态, 后续 Session 1+ 才具备"全绿即 merge"的客观锚点。
>
> **原 Session 0 (line 214 起) 保留作历史参考**, 不执行。

### Prompt

````
你是 GENPANO 的测试基础设施架构师 + Backend 初始化工程师。本次 Session 唯一目标: 把当前仓库从"纸面 Harness / 空 backend / 零可执行测试"变成"38+ 条 harness 规则可在 pre-commit 和 CI 拦截 / backend 有可迁移的 Prisma schema / openapi.yaml 首次有代码消费者 / CI 有零号基线"。

## 前置阅读 (按顺序读完再动手)

1. docs/PREFLIGHT_REPORT.md — 六轴体检结论, 本 Session 的决策依据; 特别看"轴 3 Harness 基线"和"轴 5 测试基础设施就位度"和"轴 6 Backend 实态"
2. CLAUDE.md — 关键设计决策 #18 (测试自动化 A++) + #21 (2026-04-21 Review 闭环 5 子项 A-E)
3. docs/TEST_STRATEGY.md 全文, 特别 §9 异常场景矩阵 / §10 Admin 矩阵 / §11 优先级 / §12 fixture 命名 / §13 规则血统表
4. docs/CLAUDE_CODE_SESSIONS.md Session 0 §5.1-§5.8 (原 Session 0 里"测试自动化骨架"那一大段, 任务清单详细, 本 Session 直接消费)
5. docs/DATA_MODEL.md §1-§6 (backend schema 依据; 特别注意 §1.9 kg_mined_relations 新表 + §2.5 ai_responses 扩 5 字段)
6. CLAUDE.md 所有 harness grep 原文: "图表契约 Harness 拦截"(C1-C7) + "V2 分析页统一契约 C9-C15 Harness"(C9-C15) + "UI vs Prompt 指引边界"(UI1-UI2) — 这些原文即规则注册表

## 硬约束 (违反 = 本 Session 失败)

- ❌ 不修改 frontend/src/pages/**, frontend/src/components/**, frontend/src/i18n/** 任何业务代码
- ❌ 不增删 App.jsx 任何路由 / 301 redirect
- ❌ 不修复 C14 二十一处违规 (留给 T6')
- ❌ 不做 git mv 迁移 5 个 legacy 页到 V2 路径 (留给 T5'/T6')
- ❌ 不删 frontend/dist-*/ / snapshot-before-ia-v2-*/ / messages.js.broken-backup (由 Frank 手工或后续 Session 处理)
- ❌ 不删 DashboardEmptyState.jsx / ProjectRequiredBanner.jsx / LandingNavQuickCreateButton.jsx 三个废除组件 (留给 T4' 或 T6')
- ❌ 不执行 prisma migrate (没有 DATABASE_URL, 仅 prisma format + validate)
- ❌ 不装 Next.js App Router 到 frontend/ (frontend 继续保持 Vite SPA; Next.js 属 backend 范畴)
- ✅ 允许: 修 frontend/package.json (装依赖 + 加 scripts); 创建 frontend/vitest.config.ts / playwright.config.ts / src/__ci_fixtures__/; 创建 frontend/src/lib/analytics.ts (mixpanel 封装, 空骨架); 修 frontend/vite.config.js (若测试目录需排除构建)
- ✅ 允许: 创建全新目录 scripts/, .husky/, .github/workflows/
- ✅ 允许: 创建全新目录 backend/src/, backend/prisma/, backend/package.json, backend/.env.example

## 任务清单 (按序执行, 每项结束前自检)

### 任务 1 · 前端测试依赖 + config

按原 Session 0 §5.1 + §5.2 + §5.6 执行:

- **依赖**: vitest + @vitest/coverage-v8 + @testing-library/react + @testing-library/jest-dom + jsdom + @playwright/test + husky + lint-staged + openapi-typescript + js-yaml + mixpanel-browser + mixpanel
- **config 文件**:
  - frontend/vitest.config.ts — jsdom 环境 + setupFiles + @testing-library/jest-dom 扩展 + 排除 __ci_fixtures__/
  - frontend/playwright.config.ts — 3 projects (chromium-desktop / chromium-mobile / visual), baseURL http://localhost:5173, toHaveScreenshot({ maxDiffPixels: 100 })
  - .husky/pre-commit — `npm run ci:fast` (harness grep + changed-files 单测, < 60s)
  - .lintstagedrc.json — *.{js,jsx,ts,tsx}: ["eslint --fix"], *.md: ["prettier --write"]
- **npm scripts** (frontend/package.json 新增, 不删 dev/build/preview):
  - test:unit: vitest
  - test:integration: vitest --run --project integration
  - test:e2e: playwright test
  - test:visual: playwright test --project visual
  - check:harness: node ../scripts/ci-check.mjs
  - check:contracts: node ../scripts/check-data-contracts.mjs
  - check:selftest: node ../scripts/ci-harness-selftest.mjs
  - gen:api-types: openapi-typescript ../docs/openapi.yaml -o src/lib/api-types.d.ts
  - ci:fast: npm run check:harness -- --changed-only
  - ci: npm run check:harness && npm run check:contracts && npm run check:selftest && npm run test:unit && npm run test:e2e
- **frontend/src/lib/analytics.ts** — mixpanel-browser + mixpanel 统一封装骨架, 导出 `track(event, props)` / `identify(userId)` / `reset()` / `setUserProperties(props)`, 但**不写任何业务事件**(等 Session 4a 填)

### 任务 2 · Harness 执行层 (scripts/)

按 Session 0 §5.3 + §5.3a + CLAUDE.md 决策 #21.A 执行:

- **scripts/ci-check.mjs** — 38+ 规则聚合执行器, 每条规则结构:
  ```
  { id, group (A/B/C/D/E), description, command (grep 原文), expect (空输出), exitCode (1 on violation) }
  ```
  规则来源 (全部从 CLAUDE.md / PRD §4.6.0a 原文抄录, 不重新发明):
  - **A1-A6** i18n/文案边界 (PRD §4.6.0a + 决策 #21.A)
  - **B1-B7** 图表契约 C1-C7 (CLAUDE.md "图表契约 Harness 拦截")
  - **C9-1..C15-3** V2 分析页契约 (CLAUDE.md "V2 分析页统一契约 C9-C15 Harness"; 约 15 条)
  - **D1-D7** 产品决策 (Auth 门 / 登出 6 步 / Mixpanel PII / 11 条 Legacy 301 / MCP 0 匿名 / Onboarding 72h)
  - **E1-E4** Citation + KG (Tier 禁硬编码 / tldts / 诊断互斥 / pr_score 参数服务)
  
  输出格式: 结构化 JSON (CI 消费) + 彩色 summary (人类读)
  
- **scripts/check-data-contracts.mjs** — 决策 #21.B, 7 条运行时断言 (C3 SoV "其他" / C7 BRANDS ranking / PRODUCTS ranking / mentionRate 0-1 / BCG 四象限 ≥1 / Authority Radar 5 维齐 / Project.primaryBrandId ∈ competitorBrandIds); 读 frontend/src/data/mock.js, 失败 exit 1

- **scripts/ci-harness-selftest.mjs** — 决策 #21.C, 扫 frontend/src/__ci_fixtures__/ 目录, 对 ci-check.mjs 每条注册规则断言"至少抓到 1 个同 id 的 fixture"; 抓不到说明 grep 本身坏

- **scripts/coverage-gap-scan.mjs** — TEST_STRATEGY §11, 对比 openapi.yaml endpoint 清单 vs backend 实际实现 + PRD §11 P0 清单 vs 已写测试; 输出缺口报告, 不 fail 构建

- **scripts/gen-api-tests.ts** — 从 docs/openapi.yaml 生成 L3 契约测试骨架到 frontend/tests/contract/*.spec.ts (只生成骨架 + `it.skip`, 不写具体断言, 等 Session 3 实现)

### 任务 3 · Self-seeded 违规 fixture

按决策 #21.C 执行:

- 创建 frontend/src/__ci_fixtures__/ 目录
- 5 个 .cifixture.jsx 文件, 每个故意违反 1 条:
  - A1_cjk_leak.cifixture.jsx — i18n 键 value 含 "严禁 / 本页不做" 开发约束语 (测 A1)
  - B1_sparkline_literal.cifixture.jsx — `<MiniSparkline width={400} height={80} />` 像素锁死 (测 B1/C1)
  - C11_mentionrate_over1.cifixture.jsx — data export mentionRate: 35.7 (> 1, 测 C11-1)
  - C14_h1_text3xl.cifixture.jsx — `<h1 className="text-3xl">品牌总览</h1>` (测 C14-1)
  - D4_missing_301.cifixture.jsx — 故意注释掉一条 Legacy 301 redirect 的 App.jsx 片段 (测 D4)
- frontend/vite.config.js 的 build.rollupOptions.external 或 build.rollupOptions.input exclude 规则: 阻止 __ci_fixtures__/ 进生产 bundle
- frontend/tsconfig.json (若存在) 加 `exclude: ["src/__ci_fixtures__/**"]`
- scripts/ci-check.mjs 扫描时 allowlist __ci_fixtures__/ 目录, 不把违规计入真实业务违规
- scripts/ci-harness-selftest.mjs 反其道: 必须对 __ci_fixtures__/ 跑同样 grep, 每条规则对应 ≥1 fixture 才 PASS

### 任务 4 · CI Workflow

按 Session 0 §5.2 执行:

- **.github/workflows/ci.yml** — 4 job 并行, 总预算 < 12min:
  - **harness** (< 1min): scripts/ci-check.mjs + scripts/check-data-contracts.mjs + scripts/ci-harness-selftest.mjs
  - **unit** (< 3min): vitest run --coverage, 上传 coverage/ 到 Artifact
  - **integration** (< 3min): vitest --project integration (契约测试) + HAR replay 样例
  - **e2e-visual** (< 6min): playwright test, 上传 playwright-report/ HTML + 视觉 diff
- matrix node-version: 20.x
- trigger: pull_request + push to main
- 禁用 concurrent workflow 浪费 CI quota (concurrency: group)

### 任务 5 · Backend Prisma 脚手架

按 DATA_MODEL §1-§6 + CLAUDE.md 决策 #21.D 执行:

- **backend/package.json** — 技术栈: Next.js 14.x API Routes (App Router) + TypeScript 5.x + Prisma 5.x + Zod (与 frontend 对齐); scripts: `dev (next dev --port 3001) / build / start / prisma:format / prisma:validate / test`
- **backend/prisma/schema.prisma** — 覆盖全 32+ 张表:
  - §1.x KG 层 (9 张): users / projects / kg_industries / kg_categories / kg_brands / kg_products / kg_brand_aliases / kg_brand_domains / **kg_mined_relations (§1.9 新表: source/target × 8 种 relation_type + evidence_count + confidence_score DECIMAL(4,3) + promoted / admin_status 双轨, 公式: confidence = min(1.0, 1 - 0.85^evidence_count))**
  - §2.x Pipeline 层 (8 张): platform_topics / platform_prompts / query_executions / attempts / **ai_responses (§2.5 扩 5 字段: cost_usd DECIMAL(8,5) / cost_cny DECIMAL(8,4) / token_count JSONB / latency_breakdown JSONB / trigger_source CHECK IN ('scheduled','manual','retry','user_refresh','admin_replay') + 新索引 idx_responses_trigger_source_date)** / ai_response_citations / brand_mentions / product_mentions
  - §3.x Profile 层 (4 张): profile_groups / browser_profiles / accounts / account_states
  - §4.x Analytics 层 (4 张): metric_snapshots / mv_heatmap_mention_agg / mv_brand_rankings / brand_mention_daily_agg
  - §5.x Audit 层 (6 张): audit_logs / cost_events / brand_submissions / brand_discovery_logs / brand_bootstrap_jobs / parse_failures
  - §6.x Phase 2 (2 张, 标注 @@deprecated-or-phase-2): export_jobs / report_schedules
- **backend/.env.example** — 变量:
  - DATABASE_URL (Supabase Postgres URL 示例)
  - VOLC_API_KEY (火山引擎 LLM API)
  - RESEND_API_KEY
  - MIXPANEL_TOKEN (后端 SDK)
  - SENTRY_DSN
  - COST_ALERT_WEBHOOK (PRD §4.9.4 成本尖峰告警)
  - REDIS_URL (rate limit + queue, 可选)
- 执行 `cd backend && npx prisma format && npx prisma validate` 必须全绿
- **不执行** `prisma migrate dev` (没有 DATABASE_URL, Frank 本地手工跑时执行)

### 任务 6 · OpenAPI 客户端类型生成

- 用 openapi-typescript 一次性生成:
  - frontend/src/lib/api-types.d.ts (前端消费)
  - backend/src/lib/api-types.ts (后端自校验)
- 提交生成结果到 git; 后续修改 openapi.yaml 后跑 `npm run gen:api-types` 即可更新

### 任务 7 · 零号基线 (docs/CI_BASELINE_ZERO.md)

- 跑一次 `npm run ci`, 捕获完整输出
- 写入 docs/CI_BASELINE_ZERO.md, 结构:
  ```
  # GENPANO CI 零号基线 (生成于 Session 0-rev 结束)
  
  ## Harness 规则层
  总数: 38 (A组 6 / B组 7 / C组 15 / D组 7 / E组 4 或按实际)
  PASS: X | FAIL: Y | KNOWN_SKIP: Z
  
  ## 已知违规 (待后续 Session 修复, 本 Session 范围外)
  - C10-1 × 1 处: BrandTopicsPage.jsx 文件缺失 → 修复 Session: T2'/T5'
  - C14-1 × 2 处: BrandCitationsPage.jsx:58 / BrandSentimentPage.jsx:127 → 修复 Session: T6'
  - C14-2 × 15 处: 同上两文件 p-4 → 修复 Session: T6'
  
  ## 已知跳过
  - Unit tests: 无测试用例 (由 Session 1+ 逐步填充)
  - Integration tests: openapi.yaml 契约骨架已生成但 it.skip (Session 3 实现)
  - E2E tests: 无 spec (Session 4b + T5' 逐步填充)
  
  ## Self-test
  Harness grep 自验证: 5/5 fixture 全部被对应规则抓到, 证明 grep 可用
  
  ## 下一 Session 的前置
  本基线确认后, Session 1 + Session 1.5 + T5'/T6' 可并行启动
  ```

## 验收标准

- [ ] `npm run ci` 可执行到底, 产出结构化报告
- [ ] scripts/ci-check.mjs 至少注册 38 条规则, 每条有 id/group/description/command/expected
- [ ] scripts/ci-harness-selftest.mjs 绿 (5 个 fixture 全被对应规则抓到)
- [ ] scripts/check-data-contracts.mjs 跑一次, 断言结果 (对 mock.js 全绿是好的, 发现漏洞写进 CI_BASELINE_ZERO.md)
- [ ] `cd backend && npx prisma validate` 绿
- [ ] backend/prisma/schema.prisma 覆盖 32+ 张表, 与 DATA_MODEL §1-§6 字段清单一致 (特别 §1.9 / §2.5)
- [ ] .github/workflows/ci.yml 在 https://rhysd.github.io/actionlint/ 或 actionlint CLI 下校验通过
- [ ] docs/CI_BASELINE_ZERO.md 已产出
- [ ] `git status` 除上述新建文件外, frontend/src/** 无任何修改
- [ ] `git log --oneline -5` 显示本 Session 提交数 ≤ 5 个 (防止过度细碎 commit)

## 失败信号 (看到立即中止 Session 自查)

- 试图重写 CLAUDE.md 或 frontend/ 任一 .jsx 文件
- 试图 prisma migrate (没 DATABASE_URL)
- 试图改 App.jsx 路由表
- 试图装 Next.js app router 到 frontend/
- CI workflow 跑超 12min
- 试图自己清理 dist-*/ 或 snapshot-before-ia-v2-*/

## 完成汇报

末尾回 Frank 一段 5 行摘要:
- 装了 N 个依赖 (前端 M / 后端 K)
- 注册了 X 条 harness 规则 (A/B/C/D/E 各 x)
- 生成了 Y 张 Prisma model + Z 个新表字段 (§1.9 / §2.5)
- CI baseline: PASS X / FAIL Y (列 FAIL 的 id 和位置)
- 耗时 ~ H 小时, 本 Session 建议直接合并 or 有待 Frank 决策的悬挂项
````

### 预期产出

- frontend/package.json (updated scripts + 装 12 个依赖)
- frontend/vitest.config.ts / playwright.config.ts
- frontend/src/__ci_fixtures__/{A1,B1,C11,C14,D4}.cifixture.jsx (5 个)
- frontend/src/lib/analytics.ts (mixpanel 封装空骨架)
- frontend/src/lib/api-types.d.ts (openapi-typescript 生成)
- .husky/pre-commit + .lintstagedrc.json
- scripts/ci-check.mjs + check-data-contracts.mjs + ci-harness-selftest.mjs + coverage-gap-scan.mjs + gen-api-tests.ts
- .github/workflows/ci.yml
- backend/package.json + backend/prisma/schema.prisma + backend/.env.example + backend/src/lib/api-types.ts
- docs/CI_BASELINE_ZERO.md

### 验收标准

详见 Prompt 内 10 项 checklist。

### 依赖说明

- **前置**: Preflight Session 已执行, `docs/PREFLIGHT_REPORT.md` 已产出
- **后续**: 本 Session 完成后, 可**并行**启动以下三条支线:
  1. **基础设施打磨支线**: T5'/T6' 清理 (物理迁移 5 legacy 文件 / 删 3 废除组件 / 修 C14 二十一处)
  2. **Pipeline 支线**: Session 1.5 (知识图谱) → Session 1 (爬取) → Session 1.2 (Adapter 硬化) → Session 2 (Pipeline 链路)
  3. **业务支线**: Session 3 (Analytics + API + MCP) → Session 4a (Auth) → Session 4b (Dashboard)

### 重启准则

- 若 Claude Code 开始重写 frontend/src/pages/ 或 App.jsx, 立即 Ctrl-C 重开, 强化"硬约束"段
- 若 prisma validate 反复失败, 停下来让 Frank 决策 (schema.prisma 写错了 vs DATA_MODEL 规格有 bug)
- 若 harness rules 注册超过 50 条, 说明规则被误重复或误发明, 中止重看 CLAUDE.md

---

## Session 0 (DEPRECATED · 保留作历史参考): 项目初始化 & 技术选型

> **⚠️ 不要执行本 Session。** 本节写于 2026 年初仓库空白假设下, 描述的是"从零搭脚手架 / 决技术栈 / 建 CLAUDE.md"三件事, 现在已全部**事实上完成** (frontend/ 跑过 5+ 轮 UI 迭代, CLAUDE.md 含 21 条决策, 技术栈已定 React+Vite+Tailwind / Next.js+Prisma+PostgreSQL / 火山引擎 API)。
>
> **执行版本请用上方的 `Session 0-rev (Post-Preflight · Current-State-Aware)`** — 它基于 `docs/PREFLIGHT_REPORT.md` 收敛到"测试地基 + Backend 脚手架"两件事, 不会重建已经存在的东西。
>
> **本节保留的价值**: (1) 历史上技术选型 / 目录结构 / Prisma 迁移的详细决策过程可追溯; (2) **§5.1-§5.8 的测试骨架任务清单极度详细**, Session 0-rev 的任务 1 和任务 2 显式引用这几节作为实施细节, 所以不删; (3) §2.5 "接管已有原型作为 UI 基线" 是 UI 锚点契约的最初固化点, 后续 T1'-T6' 都基于它。
>
> **阅读顺序建议**: Session 0-rev Prompt 只提到"按原 Session 0 §5.1 + §5.2 + §5.6 执行", Claude Code 会来这里翻详细步骤; 你 (Frank) 平时不用读这一整节。

### Prompt (⚠️ 历史版本, 不要复制执行; 阅读 §5.1-§5.8 足够)

```
你是 GENPANO 项目的首席架构师。GENPANO 是一个 Agent-native 的免费 GEO (Generative Engine Optimization) 监测平台。

请阅读项目根目录下的 PRD.md 和 PRODUCT_PLAN.md，全面理解产品需求。

然后完成以下任务:

## 1. 技术选型 & 架构设计

基于以下原则选择技术栈:
- Solo + AI 团队，一个人能维护，减少 ops 负担
- MVP 4 周交付，开发效率优先
- 成本优先，尽量使用免费 tier (Cloudflare Pages, Supabase 等)
- Agent-native: API-first，所有功能可通过 API 访问
- 可扩展: 新增 AI 引擎只需添加 Adapter
- **部署分阶段**: 测试阶段用单台中国 VPS (全部服务 + 海外代理访问 ChatGPT)，正式上线迁移到双区域 (海外主节点 + 中国爬取节点)
- 架构必须确保: 测试→正式的迁移只需改部署配置和环境变量，**不需要改业务代码**
- 关键抽象: ScrapingWorker 通过 config (region/engines/proxy/resultEndpoint) 驱动，不硬编码部署拓扑
- 前端: 测试阶段 dev server / 本地构建，正式上线迁移到 Cloudflare Pages
- 需要支持: 定时任务、后台长任务、headless browser (Playwright)、LLM API 调用

请输出:
- 技术栈选择及理由 (前端、后端、数据库、队列、部署)
- 系统架构图 (ASCII)
- 目录结构设计

## 2. 项目脚手架

- 初始化 monorepo (如果适用) 或项目结构
- 安装核心依赖
- 配置 TypeScript / linting / formatting
- 设置环境变量模板 (.env.example)
- 配置数据库 schema 初始迁移 (基于 PRD 中的数据模型)
  - **重要**: 数据模型参考 PRD 5.3，分 Platform Layer (唯一数据源) 和 User Layer (视角过滤器)
  - Knowledge Graph 表: kg_categories (品类树), kg_brands, kg_products, kg_brand_relations, kg_product_relations
  - Pipeline 表: platform_topics, platform_prompts, query_executions, ai_responses, brand_mentions, product_mentions, sentiment_results
  - Analytics 表: metric_snapshots, geo_diagnostics
  - User 表: users, projects (视角过滤器: primary_brand_id + competitor_brand_ids + preferences), reports, report_schedules, api_keys, brand_submissions
- 基础 CI 配置 (GitHub Actions)

## 2.5 接管已有原型作为 UI 基线（⚠️ 必须）

`frontend/` 目录已存在一套打磨好的页面（Auth / Dashboard / Topics / Industry / Brands / Products / Layout），以及 `docs/DESIGN_TOKENS.md` + `frontend/src/index.css` 的 Design Tokens 系统。这是本项目 UI 的**唯一基线**，不是可替换的草稿。

- 验证 `cd frontend && npm install && npm run dev` 能启动
- 读完 `frontend/src/index.css` 中所有 `--color-*` / `--gradient-*` / `--shadow-*` / `--radius-*` / `.t-*` / `.text-themed-*` / `.bg-themed-*`
- 读完 `docs/DESIGN_TOKENS.md` 全文，理解 3 层结构（CSS vars → Tailwind theme → 组件类）
- 读完 CLAUDE.md "设计锚点" 一节，能口述 5 个要点（结构锚点 / 视觉锚点 / 样式契约 / 组件复用清单 / UI Session 3 步）

**约束（写进 CLAUDE.md 的"关键设计决策"）**：后续所有 UI Session 在 `frontend/` 上**演进**而不是**重建**。修改已有页面需保留结构锚点定义的分区；新增页面先找同类锚点参照。新增 token 必须先改 `DESIGN_TOKENS.md` 和 `index.css`，再在组件中引用。

## 3. 创建 CLAUDE.md

创建 CLAUDE.md 文件，包含:
- 项目概述
- 技术栈说明
- 目录结构说明
- 开发规范 (代码风格、命名约定、Git 规范)
- 常用命令 (启动、测试、部署)
- 架构决策记录
- **设计锚点章节（从现有 CLAUDE.md 的"设计锚点"一节继承，不得删减）**

## 4. 验证

- 确保项目能成功启动 (即使是空页面)
- 确保数据库连接正常
- 确保 lint/format 通过
- 运行一个简单的 health check endpoint

## 5. 测试自动化骨架 (TEST_STRATEGY.md Phase 0)

> **目标**: Session 0 结束时必须有能跑的 4 层测试骨架 (L1 Harness / L2 Unit / L3 Integration+Contract / L4 E2E+Visual), 哪怕每层只有 1-2 个样例. 详见 `docs/TEST_STRATEGY.md`.

### 5.1 测试依赖安装 (package.json)

- `vitest` + `@vitest/coverage-v8` + `@testing-library/react` + `@testing-library/jest-dom` + `jsdom`
- `@playwright/test` (含 `expect(page).toHaveScreenshot()` 内置 visual diff)
- `husky` + `lint-staged` (pre-commit hook)
- `openapi-typescript` + `js-yaml` (契约测试用)

### 5.2 配置文件

- `vitest.config.ts` — jsdom 环境 + setupFiles + `@testing-library/jest-dom` 扩展
- `playwright.config.ts` — 3 项目 (chromium-desktop / chromium-mobile / visual), baseURL `http://localhost:5173`, `toHaveScreenshot({ maxDiffPixels: 100 })` 阈值
- `.husky/pre-commit` — 只跑 `npm run ci:fast` (Harness grep + changed files 单测, < 60s)
- `.github/workflows/ci.yml` — 4 job (harness / unit / integration / e2e), 并行, 上传 Playwright HTML report + visual diff
- `.env.example` — 所有必需环境变量占位 (DATABASE_URL / VOLC_API_KEY / RESEND_API_KEY / MIXPANEL_TOKEN / SENTRY_DSN)

### 5.3 Harness 中枢脚本 `scripts/ci-check.mjs`

> **Session 0 必须交付全量 30+ 条规则**, 不是"首批 10-12 条"。规则分 5 组, 每组独立函数, 主函数顺序调用汇总 violation 数组, 末尾统一打印并 `process.exit(violations.length > 0 ? 1 : 0)`. 每条 violation 必须携带 `{ rule, file, line, message, fixHint }`, 方便 Claude Code 在 PR 评论里对着 fixHint 自动修.

**组 A — i18n / 文案边界 (§4.10.4a.D + §4.6.0a.D, 5 条)**

- A1 `i18n-cjk-leak` · JSX 文本节点禁 CJK (`frontend/src/**/*.{jsx,tsx}`), 白名单: 注释 / test / stories / `data-locale="zh"` 属性
- A2 `i18n-pair-coverage` · `frontend/src/i18n/messages.zh-CN.json` 与 `messages.en-US.json` 键集合必须对齐, 差集非空即报 (diff 每条列 key + 哪边缺)
- A3 `formatBrand-entry` · JSX 禁直接 `{brand.nameZh}` / `{brand.nameEn}` / `{item.productNameZh}` / `{item.productNameEn}`, 只能走 `formatBrand(brand, locale)` / `formatProduct(product, locale)`
- A4 `ui-developer-constraint-leak-i18n` · `frontend/src/i18n/*.json` 禁 `本页(只|不)做|只回答|不承担|详情请进入|请去.*查看|严禁|🚫|⚠️\s?(本页|本段)`
- A5 `ui-developer-constraint-leak-jsx` · JSX 文本节点同 A4 规则
- A6 `i18n-interpolation-api` · 禁 `t('key', 'fallback string')` 二路歧义, 只能 `t('key', { brand, count })` (2026-04-20 Wave-4 固化)

**组 B — 图表契约 C1-C7 (§4.1.1b / §4.6.1a / DESIGN_TOKENS, 7 条)**

- B1 `chart-c1-sparkline-default` · `MiniSparkline.jsx` 里 `width=`/`height=` 默认值必须是 `'100%'` 字符串, 禁数字像素
- B2 `chart-c2-engine-color-binding` · Recharts `<Line stroke=/>` 禁内联 hex, 必须 `var(--color-chart-*)`
- B3 `chart-c3-sov-others` · 走 `scripts/check-data-contracts.mjs` 运行时断言, 本脚本仅校验 mock.js 存在 `SOV_OTHERS` 字段与最大真实品牌字段
- B4 `chart-c4-sentiment-pct` · `sentiment.*\.toFixed\(2\)` 匹配除行尾 `// C4-exempt` 注释外一律拒
- B5 `chart-c5-sparkline-sawtooth` · `frontend/src/pages/**` 禁 `spark[A-Za-z]+\s*=.*i\s*%\s*[0-9]+\s*===\s*0\s*\?` 锯齿波合成
- B6 `chart-c6-donut-size-minimum` · `<DonutChart` 的 `size={n}` 禁 `n < 120`
- B7 `chart-c7-ranking-integrity` · 走 `scripts/check-data-contracts.mjs` 运行时断言 (BRANDS.ranking === 按 panoScore 降序 index+1)

**组 C — V2 分析页契约 C9-C15 (§4.6-IA-v2.K-N + M.5/M.6 + O Wave-4, 15 条)**

- C9-1 heatmap 色带唯一 · `BrandTopicHeatmap.jsx` 禁借用 `var(--color-chart-[0-9]|sentiment-(positive|negative|neutral))`
- C9-2 heatmap 禁内联 hex · 同文件 `(fill|background)[:=]\s*['"]?#[0-9a-fA-F]{3,8}` 拒
- C10-1 Brand Mode 6 分析页 mount FilterBar 或 hook · Visibility / Topics / Sentiment / Citations / Products / Competitors 必须 import `BrandAnalysisFilterBar` 或 `useBrandAnalysisFilters`
- C10-2 禁本地时间 state · `frontend/src/pages/brand/**` 禁 `useState\s*\(\s*['"]7d|useState.*dateRange|useState.*fromDate`
- C11-1 mentionRate literal 小数 · `frontend/src/data/mock.js` `mentionRate:\s*[1-9][0-9]*(\.[0-9]+)?[,\s}]` (整数 ≥1) 即报
- C12-1 BrandSentimentPage import DonutChart · 必须 `import.*DonutChart`
- C12-2 BrandSentimentPage 禁文字大百分比 · `text-(3xl|4xl|5xl).*(positive|negative|neutral)Pct`
- C13-1 CompetitorQuadrantChart 禁 radius > 40 · `radius\s*=\s*[4-9][0-9]|r=\{?\s*[4-9][0-9][^0-9]`
- C13-2 必须 `Math.sqrt` 面积正比 · 同文件 grep `Math\.sqrt` 缺失即报
- C13-3 必须 `showLabels` prop · 同文件 grep `showLabels` 缺失即报
- C14-1 分析页 h1/h2 禁 text-2xl+ · `<h[12][^>]*text-(2xl|3xl|4xl)`
- C14-2 分析页 Card 禁 p-4+ · `className=[\"'][^\"']*\bp-[4-9]\b`
- C14-3 分析页根 div 禁 space-y-4+ · `return\s*\(\s*<div\s+className=[\"'][^\"']*space-y-[4-9]`
- C15-1 BrandProductDetailPage 禁 `useParams().brandId` · `useParams\(\)[^{]*\{[^}]*\bbrandId\b` (brandId 走 query string)
- C15-2 必须 `import.*useSearchParams` · 缺失即报
- C15-3 空状态守卫禁 `!brand` 导致全页空白 · `if\s*\(\s*!brand[^)]*\)\s*\{?\s*return\b.*(Empty|暂无)`

**组 D — 产品决策契约 (§4.1.1-gate / §4.1.1e / §4.11.5 / §4.6-IA-v2, 7 条)**

- D1 `auth-gate-route-guard` · Next.js middleware.ts 或 RouteGuard HOC 必须覆盖 `/brand/*` / `/industry/*` / `/reports` / `/brands/*` (登录重定向 `/register?redirect=&brandHint=`)
- D2 `logout-6-step-order` · `useLogout` hook 里 `mixpanel.reset()` 必须晚于 `track('user_logged_out')` (awk 次序)
- D3 `mixpanel-pii-redline` · `track(` / `identify(` 的第 2 参对象字面量禁 `email|phone|token|password|company_name|ip_address` (允许 `email_domain` 单独一列, 即 `@` 之后部分)
- D4 `dashboard-301` · `next.config.js` / `middleware.ts` 必须有 `/dashboard → /brand/overview` redirect 301
- D5 `brand-detail-legacy-301` · `/brands/:id → /brand/overview?brandId=` + `/brands/:id/products/:pid → /brand/products/:pid?brandId=` 301
- D6 `auth-required-anonymous-data-api` · `app/api/**/route.ts` 除 `auth/login|register|lookup|forgot-password|health|og|sitemap` 白名单外, 必须有 `requireAuth(req)` 调用
- D7 `onboarding-draft-route-guard` · `middleware.ts` 检测到 session user 但 `projects.length === 0` 必须 302 跳 `/onboarding`

**组 E — Citation + KG 契约 (§4.2.6 / §4.2.7 / 决策 #19, 4 条)**

- E1 `citation-tier-not-hardcoded` · 业务代码禁 `const TIER_WEIGHTS = {` / `tierWeight\s*=\s*[0-9.]+` literal, 必须从 `parameter_service` / `citation_domain_authority` 表加载
- E2 `url-normalization-tldts` · `src/parser/**` / `src/services/citation/**` URL 解析必须 `import { parse } from 'tldts'`, 禁 `new URL(x).hostname` 裸用作 domain key
- E3 `citation-attribution-diagnostic-mutex` · `src/services/diagnostics/**` 同一 response 不得同时 emit `citation_attribution_mismatch` + `citation_source_loss` (互斥 grep: 同文件同函数内不得两个字符串都出现)
- E4 `pr-score-not-hardcoded` · 禁 `prScore\s*=\s*.*\*\s*[0-9.]+\s*\*\s*[0-9.]+` 硬编码 tier 权重+trending 系数, 必须从 `parameter_service` 拉

**合计 38 条 Harness 规则** (A6 + B7 + C15 + E4 均为本 Review 新增拦截)。脚本退出码: 0 全绿, 1 有违规 (单条打印 `rule | file:line | message | fixHint`).

### 5.3a 规则分组与编号约定

每条规则必须在 TEST_STRATEGY.md §2.1 留一条反向指针, 包含:
- 规则编号 (A1 / C15-1 etc.)
- 正向 & 负向样例代码片段
- 触发该规则的历史 Bug / PR / Session 链接 (没有就写 "preventive")

Session 0 产出 `scripts/ci-check.mjs` 时, 每条规则对应一个 `function ruleA1_i18nCjkLeak(projectRoot) { ... }` 的具名函数, 调用侧 `registerRule('A1', ruleA1_i18nCjkLeak)`. 禁止把 20 条规则塞进一个大 grep 调用——未来单条下线只需删一个函数 + 一条 register 调用。

### 5.4 契约源文件骨架

#### 5.4.1 `openapi.yaml`

- 至少 5 个端点骨架 (而非 3 个):
  - `GET /api/health` (Session 0 立即可跑)
  - `POST /api/auth/identifier-lookup` (§4.1.1-form Email-first 2-step)
  - `POST /api/auth/logout` (§4.1.1e I)
  - `POST /api/projects` (Onboarding 提交)
  - `GET /api/brands/:id/panorama` (Brand Mode 总览 API, 给 MCP / CSV 导出共用)
- `components.schemas` 至少定义: `Brand` / `Project` / `AuthIdentifierLookupResponse` / `PanoramaSnapshot` / `ErrorResponse` (统一错误码)
- `components.securitySchemes.bearerAuth` + `bearerFormat: JWT` 必须就位 (MCP Day-1 约束, 决策 #9)

#### 5.4.2 `scripts/check-data-contracts.mjs`

Node 脚本, 对 `frontend/src/data/mock.js` 做运行时断言 (import 其 named export). Session 0 必须落以下 7 条:

1. **C3 · SoV "其他" ≤ 最大真实品牌片**: 若 `SOV_PIE` 存在且含 `{ key: 'others', value }` 则断言 `value <= max(others_excluded_values)`
2. **C7 · BRANDS ranking**: `const sorted = [...BRANDS].sort((a,b)=>b.panoScore - a.panoScore); sorted.forEach((b,i) => assert(b.ranking === i + 1, ...))`. **Session 0 必须同步修正 mock.js BRANDS[]** (当前 `[1,2,3,5,7,8,4,6]` 违反, panoScore [85,82,79,77,75,73,71,68] 降序对应 ranking 应为 [1..8])
3. **C3-products · PRODUCTS ranking**: 同 C7 逻辑, 但同品牌下按 panoScore 降序+index
4. **mentionRate 小数域**: 所有 `mentionRate` 值必须 `0 <= v <= 1` (PRD §4.6-IA-v2.K C11 固化)
5. **BCG 象限覆盖**: `PRODUCTS` 至少每个象限 (Star / Question / Cash Cow / Dog) 有 1 条样本, 避免 UI 空态未覆盖
6. **Citation tier 分布**: `AUTHORITY_RADAR_DATA` 5 维每维至少 1 条样本, 避免 radar 出缺角
7. **Project primaryBrandId 闭环**: `PROJECTS[*].primaryBrandId` 必须能在 `BRANDS` 里找到

脚本签名: `node scripts/check-data-contracts.mjs` → stdout 汇总报告 + 退出码.

#### 5.4.3 自种违规样本 (Session 0 验证 Harness 能抓到)

Session 0 在 `frontend/src/__ci_fixtures__/` 下落 5 个故意违规文件, 并配 `scripts/ci-check.mjs --test-mode` 只跑这 5 条:

- `leak-cjk.jsx` (触 A1)
- `leak-dev-constraint.jsx` (触 A5)
- `bad-sparkline.jsx` (触 B1)
- `bad-competitor-quadrant.jsx` (触 C13-1)
- `bad-product-detail-useparams.jsx` (触 C15-1)

CI 里跑 `npm run ci:harness:selftest` 确认 5 条都红, 然后才跑真实 lint. 若任何一条漏网 → Session 0 不合格, 任务未完成.

### 5.5 目录脚手架

```
tests/
├── unit/            # Vitest 单测, 样例: utils/formatPct.test.ts
├── integration/     # Vitest + supertest API 契约测试 (Session 3 填充)
├── e2e/             # Playwright 6 关键路径 (Session 5 填充)
├── visual/          # Playwright 视觉回归 ~40 baseline (Session 4b 填充)
└── fixtures/
    ├── scraping/    # HAR 录制结果 (Session 1 填充)
    └── mock-data/   # 结构化 mock 数据
```

### 5.6 npm scripts

```
"test": "vitest run"
"test:watch": "vitest"
"test:e2e": "playwright test"
"test:visual": "playwright test --project=visual"
"test:visual:update": "playwright test --project=visual --update-snapshots"
"ci:harness": "node scripts/ci-check.mjs"
"ci:harness:selftest": "node scripts/ci-check.mjs --test-mode"
"ci:data": "node scripts/check-data-contracts.mjs"
"ci:fast": "npm run ci:harness && vitest run --changed"
"ci": "npm run ci:harness && npm run ci:harness:selftest && npm run ci:data && npm run test && npm run test:e2e"
```

### 5.7 Fixture 脚手架 (Session 1+ 填充, Session 0 仅落空骨架与命名约定)

> **目的**: `frontend/` 作为原型未来会被正式工程重写, 但**测试 fixture 永久存续**, 因为它们是"数据驱动分支覆盖"的最小证据。Session 0 必须落以下骨架 + 命名约定, Session 1-5 往里填真值.

#### 5.7.1 Empty/Error/Loading 状态 fixture (`frontend/src/data/fixtures/`)

- `EMPTY_STATE_FIXTURES.js` · 6 种空态:
  - `NO_PROJECT` (Onboarding 前)
  - `NO_RESPONSES_YET` (Project 刚建, 首批爬取未回)
  - `BRAND_ZERO_MENTIONS` (品牌提及率 = 0)
  - `NO_CITATIONS` (某品牌在时间窗内零引用)
  - `INDUSTRY_EMPTY` (行业 Topic 未 mine 完)
  - `PROFILE_GROUP_UNDER_SAMPLED` (< 最小样本阈值, 触发 ProfileGroupSampleWarning)
- `ERROR_STATE_FIXTURES.js` · 5 种错误:
  - `API_500` / `AUTH_EXPIRED` / `RATE_LIMITED_429` / `PARTIAL_FAIL_SOME_ENGINES_DOWN` / `NETWORK_OFFLINE`
- `LOADING_STATE_FIXTURES.js` · 3 种加载态:
  - `INITIAL_FETCH` / `REFRESH_POLLING` / `DRILLDOWN_LAZY` (skeleton UI 锚点)

#### 5.7.2 Adapter 错误码 fixture (`tests/fixtures/adapters/`)

按 ADAPTER_CONTRACT §6 的 8 个错误码各落 1 个 HAR + 1 个预期 ScrapingResult:

```
tests/fixtures/adapters/
├── doubao/
│   ├── success-cosmetic-query.har          → Response { status: 'success', ... }
│   ├── cf-blocked.har                      → ScrapingError { code: 'CF_BLOCKED' }
│   ├── cookie-expired.har                  → { code: 'COOKIE_EXPIRED' }
│   ├── captcha-required.har                → { code: 'CAPTCHA_REQUIRED' }
│   ├── page-crashed.har                    → { code: 'PAGE_CRASHED' }
│   ├── proxy-dead.har                      → { code: 'PROXY_DEAD' }
│   ├── no-account-available.fixture.json   → { code: 'NO_ACCOUNT_AVAILABLE' } (无 HAR, 调度器层)
│   ├── extract-empty.har                   → { code: 'EXTRACT_EMPTY' }
│   └── timeout.har                         → { code: 'TIMEOUT' }
├── deepseek/ (同上 9 份)
└── chatgpt/ (同上 9 份)
```

Session 1 的 HAR 录制脚本 `scripts/record-har.ts` 必须能生产这些文件名 (并脱敏). Session 0 落空目录 + README.md 说明命名约定即可.

#### 5.7.3 契约 & 回归 fixture (`tests/fixtures/contract/`)

- `mcp-get-panorama.request-response.json` · MCP `genpano_get_panorama` 一次正常请求+响应, Session 5 (MCP 层) 基于此打契约回归
- `mcp-get-citations.request-response.json` · 同理 (决策 #19 §4.2.7.F)
- `csv-export-golden-sample.csv` · CSV Tier 1 8 个 exportType 各一份 golden file, Session 3 填充. Column 顺序/BOM/编码变动 → diff 红

### 5.8 Session 0 与后续 Session 的锚点契约

> **⚠️ 给执行 Session 0 的 Claude Code**: 你在 Session 0 产出的测试地基是"未来 30+ Session 的契约基座"。以下 5 条锚点 Session 1-5 会反复依赖, 禁止 Session 1+ 为了"眼前方便"绕过本地基:

1. **Harness 规则不得被 Session 1+ 下线** — 只能新增, 不能删除现有规则. 若某规则真的失效, 必须在 `docs/TEST_STRATEGY.md` 对应位置写 "SUPERSEDED YYYY-MM-DD by 规则 X" + 删除日期
2. **mock.js 数据契约** — C3 / C7 / mentionRate 0-1 / BCG 4 象限覆盖这 4 条是 P0, Session 1+ 新增 mock 数据必须跑 `npm run ci:data` 绿
3. **自种违规验证** — Session 1+ 若修改 `scripts/ci-check.mjs`, 必须同步更新 `frontend/src/__ci_fixtures__/`, `npm run ci:harness:selftest` 必须红
4. **openapi.yaml 是单一契约源** — Session 3 / 5 写 API 时必须先改 `openapi.yaml`, 再跑 `openapi-typescript` 生成 `.d.ts`, 再写实现. 禁手写 response 类型
5. **HAR fixture 不得含明文 query / 真 cookie / 真 IP** — Session 1 录 HAR 脚本必须强制脱敏, `scripts/ci-check.mjs` 组 F (Session 1 追加) 会扫 `tests/fixtures/scraping/**.har` 里的 Authorization/Cookie/x-real-ip

请开始执行。每完成一个大步骤，简要汇报进展。
```

### 预期产出
- 完整的项目脚手架，可 `npm run dev` 启动
- 数据库 schema 初始化完成
- CLAUDE.md 项目规范文件
- .env.example 环境变量模板
- 基础 CI 配置
- **测试自动化骨架** (TEST_STRATEGY Phase 0): Vitest + Playwright + husky + `scripts/ci-check.mjs` (**≥38 规则**, 见 §5.3 A-E 五组) + `scripts/check-data-contracts.mjs` (**7 条 C3/C7/小数域/BCG 象限等**) + `openapi.yaml` 骨架 (**5 端点 + securitySchemes**) + `.github/workflows/ci.yml` 4 job + `frontend/src/__ci_fixtures__/` 自种违规样本 5 份 + `frontend/src/data/fixtures/` 三类状态 fixture 空骨架 + `tests/fixtures/adapters/` 27 份 HAR fixture 命名约定 README

### 验收标准
- [ ] `npm install` 无错误
- [ ] `npm run dev` 启动成功
- [ ] 数据库迁移执行成功
- [ ] `/api/health` 返回 200
- [ ] CLAUDE.md 内容完整
- [ ] **CLAUDE.md "设计锚点"一节存在，能口述 5 个要点**
- [ ] **`frontend/` 基线可启动，`docs/DESIGN_TOKENS.md` 已通读**
- [ ] **`npm run ci` 四层骨架全绿** (harness / unit / integration / e2e 至少各 1 样例通过)
- [ ] **`scripts/ci-check.mjs` 含 ≥ 38 条 Harness grep 规则** (A1-A6 + B1-B7 + C9-1..C15-3 + D1-D7 + E1-E4)
- [ ] **`scripts/check-data-contracts.mjs` 7 条断言全绿**, 包含 C7 修复后的 BRANDS.ranking ([1..8])
- [ ] **`npm run ci:harness:selftest` 能把 5 份 `__ci_fixtures__/` 全部检出红**, 一条漏网即不合格
- [ ] **`.husky/pre-commit` hook 能拦截 i18n CJK 泄漏 / UI 开发约束泄漏 / C1/C4/C5 违规样例**
- [ ] **Playwright `toHaveScreenshot()` 样例能生成 baseline 并在 diff > 100 像素时失败**
- [ ] **`openapi.yaml` 至少 5 端点骨架 + `bearerAuth` securityScheme**, `openapi-typescript` 能成功生成类型
- [ ] **`tests/fixtures/adapters/` 三引擎 × 9 错误码命名约定 README 就位** (真实 HAR 由 Session 1 填)
- [ ] **mock.js BRANDS[].ranking 修正为 [1,2,3,4,5,6,7,8]** (按 panoScore 降序, Wave-4 后遗留的 C7 违规)

> **⚠️ PHASE GATE 1: 架构确认 (人类 Review)**
> - □ 技术选型是否合理?
> - □ 目录结构是否清晰?
> - □ Platform/User 双层数据模型是否正确?
> - □ 阅读 review/ 中的 adversarial 报告
> - ⏱ ~30min

---

## Session 1: 核心监测引擎 - AI 爬取系统

### 前置依赖
- Session 0 完成，项目可启动
- **必读 (开工前)**: [`docs/ADAPTER_CONTRACT.md`](./ADAPTER_CONTRACT.md) **全文** — Adapter 接口形状、错误码、状态机、反检测、HAR 脱敏全部在这里固化。本 Session 的实施约束不在本文件重复定义, 以 ADAPTER_CONTRACT 为准。

### Prompt

```
继续 GENPANO 项目开发。

开工前必读 (按顺序):
1. CLAUDE.md (项目上下文)
2. docs/ADAPTER_CONTRACT.md 全文 (Adapter 实施真相源, §1-§12 全读, 不跳节)
3. docs/PRD.md §4.3 (产品层需求, 与契约互为交叉引用)

本 Session 目标：构建核心的 AI 引擎爬取系统（Web-First 方案，浏览器自动化）。

**契约锚点**: 本 Session 所有 Adapter 代码 (src/engines/adapters/**) 必须与 ADAPTER_CONTRACT §2
(接口) / §3 (Profile-Aware) / §6 (错误码) / §8 (DOM) / §10 (持久化) 一一对应。任何偏离必须先
在 ADAPTER_CONTRACT 更新再改代码, 禁止反向漂移。

**部署架构**: 爬取系统采用双区域部署:
- 海外 VPS: 运行 ChatGPT 的 Web Adapter (海外住宅代理)
- 中国 VPS: 运行 豆包/DeepSeek 的 Web Adapter (国内住宅代理)
- 两个 Worker 共享同一套 Adapter 代码，通过配置区分运行环境

## 任务

### 1. AI 引擎适配器框架

**重要**: 采用 Web-First 方案 (浏览器自动化爬取 Web 端)，API 仅作降级备选。参考 PRD 4.3 节。

实现 PRD 中定义的 Adapter 接口:
- 创建 `AIEngineAdapter` 基类/接口（包含 `type: 'web' | 'api'`）
- 实现 `DoubaoAdapter` (自研 Playwright + stealth plugin, 最高优先) [中国节点]
- 实现 `DeepSeekAdapter` (自研 Playwright + stealth plugin) [中国节点]
- 预留 `ChatGPTWebAdapter` 的骨架 (Web + API 降级) [海外节点]
- 为每个 Web Adapter 实现对应的 API 降级 Adapter
- Worker 启动配置: 通过环境变量 `WORKER_REGION=overseas|cn` 决定加载哪些 Adapter

每个 Web Adapter 需要:
- 使用自研 Playwright + playwright-extra stealth plugin 驱动本地浏览器实例
- 代理 IP 轮转 (住宅代理服务，如 IPIDEA/快代理)
- 账号池管理: 登录态保持、账号轮转、被封检测、自动补充
  - 账号生命周期自动化: 登录态定时刷新、健康探测、状态机流转
  - CN 引擎自动注册: 集成鲁班SMS接码平台 API (lubansms.com)，账号池水位低时自动触发注册补充
  - 海外引擎半自动注册: 临时邮箱 API + Playwright 注册脚本，CAPTCHA 失败告警人工介入
- 支持 AgentProfile (通过不同账号 + 对话上下文前缀模拟不同用户)
- 反检测: 随机请求间隔、模拟真实用户行为 (滚动、等待)
- 结果提取: 从页面 DOM 中提取 AI 回答全文 + 引用来源 + 产品卡片
- 可选: 页面截图保存 (用于调试和数据验证)
- 指数退避重试 (最多 3 次 attempt - 1 原始 + 2 次重试)
- 健康检查方法
- 降级策略: Web 爬取连续失败 N 次 → 自动切换到 API Adapter

### 2. 结果解析器

对爬取到的 AI 回答进行结构化解析:
- 从回答文本中提取品牌提及 (基于项目中配置的品牌列表)
- 从回答文本中提取产品提及
- 解析排名位置 (如果 AI 给出了推荐列表)
- 提取引用来源 URL
- 调用 LLM 进行情感分析 (可先用简单规则，标注 TODO 后续用 LLM)

### 3. 爬取调度器

- 基于项目配置的监测频率调度爬取任务
- 任务队列管理 (使用项目选定的队列方案)
- 并发控制 (每个引擎的速率限制)
- 爬取状态追踪 (pending, running, success, failed)
- 结果存储到数据库

### 4. 测试 (TEST_STRATEGY Phase 1 - HAR 录制回放)

> **目标**: 爬取路径的"第一次真实跑通"必须录制为 HAR fixture, 之后所有 CI 回归用 `page.routeFromHAR()` 回放, 不再依赖真实账号/代理/网络.

#### 4.1 单元测试 (L2)
- 为结果解析器 (`src/parser/`) 写单元测试, ≥ 80% branch coverage
- 品牌/产品归一化函数 (nameZh/nameEn/aliases) 多语言匹配用例
- 情感分析规则引擎的 positive/negative/neutral/mixed 四路径

#### 4.2 HAR 录制脚本 `scripts/record-har.ts`
- CLI: `npm run har:record -- --engine=doubao --query="..."` 
- 用真实账号跑一次, 保存完整网络流量到 `tests/fixtures/scraping/{engine}-{hash}.har`
- HAR 文件脱敏: 剔除 Authorization/Cookie/Set-Cookie/refresh_token 字段, 保留响应体 (用 HAR sanitizer 脚本, 见 TEST_STRATEGY §3.2)
- 文件名用 query 内容 SHA-1 前 8 位, 禁止含明文 query (避免敏感查询泄漏)

#### 4.3 HAR 回放集成测试 (L3)
- 每个 Adapter 至少 2 个 HAR fixture (一个成功路径 + 一个降级/失败路径)
- 测试用例通过 `page.routeFromHAR(path, { update: false })` 拦截所有出站请求
- 验证 Adapter 能正确解析回放响应, 产出结构化 Response
- CI 不连真实爬虫, 纯回放, 单测执行 < 30s

#### 4.4 调度器流程测试 (L3)
- 用 in-memory queue + 2 个 mock Adapter 验证: 调度 → 并发控制 → 状态机 (pending→running→success/failed) → 重试指数退避
- 不测真实代理, 只测调度逻辑

#### 4.5 账号池状态机测试
- 状态机转移矩阵 (healthy → rate_limited → banned → deprecated) 逐条单测
- 水位触发自动注册: mock 鲁班SMS + mock Playwright, 验证"水位低于 30% → 触发注册流程"

#### 4.6 本 Session 新增的 Harness 规则 (追加到 `scripts/ci-check.mjs`)
- 禁止业务代码直连 `playwright` 裸 API — 必须走 `src/engines/adapters/` 封装
- 禁止 HAR fixture 里出现 `Authorization:` / `Cookie:` 非空值 (sanitizer 未清理视为泄漏)
- 禁止爬取路径硬编码 query 字符串 — 必须从 `tests/fixtures/scraping/queries.json` 取

请确保代码结构清晰，便于后续添加新的 AI 引擎 Adapter。
执行完成后更新 CLAUDE.md。
```

### 预期产出
- `src/engines/` 目录下的 Adapter 实现
- `src/accounts/` 账号池管理 + 自动注册模块
- `src/parser/` 结果解析模块
- `src/scheduler/` 爬取调度模块
- 相关数据库迁移
- 测试用例

### 验收标准
- [ ] 豆包 Web Adapter 可通过自研 Playwright 执行单个 Query 并返回结构化 Response
- [ ] DeepSeek Web Adapter 可通过自研 Playwright 执行单个 Query 并返回结构化 Response
- [ ] 账号池管理: 至少 2 个测试账号可轮转使用
- [ ] 账号生命周期自动化: 登录态刷新、健康探测、状态机流转
- [ ] CN 引擎自动注册: 鲁班SMS接码 → Playwright 注册 → 入池 端到端可跑通
- [ ] 账号池水位监控: 可用账号低于阈值时自动触发补充
- [ ] Web 爬取失败时能自动降级到 API Adapter
- [ ] 结果解析器能从回答中提取品牌/产品提及
- [ ] 调度器能按计划执行批量爬取任务
- [ ] 测试通过率 > 80%
- [ ] **每个 Adapter ≥ 2 个 HAR fixture** (成功 + 失败/降级), 存 `tests/fixtures/scraping/`
- [ ] **HAR sanitizer 清理**: `grep -rE 'Authorization|Cookie|refresh_token' tests/fixtures/scraping/` 无非空命中
- [ ] **HAR 回放 CI < 30s**: 整个 Adapter 层测试不连真实爬虫也能全绿
- [ ] **`scripts/ci-check.mjs` 新增 3 条 Session 1 规则** (裸 playwright / HAR 凭据泄漏 / 硬编码 query)

---

## Session 1.2: Adapter Hardening — 反检测 / CAPTCHA / HAR 回归 ⭐ NEW (2026-04-22 真相源校准)

### 背景

Session 1 跑通了 "单 Query → 单 Response" 的快乐路径 (但 adapter.execute() 留 `TIMEOUT` sentinel, 纯逻辑模块 + 骨架交付)。Session 1.5 / 2 / 2.1 已在 Session 1 的产物上继续搭 KG + Planner + LLM Refinement, attempts 表和 `attempts.browser_profile` JSONB 契约已固化。Session 1.2 把 **真实生产对抗** 固化进来 — 这些经验全部来自 2025Q1-Q2 在 `github.com/jotamotk/GenPano` 测试床上对 9 引擎的实战，每条规则都对应一次 CF_BLOCKED / 账号被封 / DOM 变更 / CAPTCHA 升级 的真实 Bug。

### 前置依赖

- Session 1 ✅ + Session 1.5 ✅ + Session 2 ✅ + Session 2.1 ✅ 全部完成 (CLAUDE.md #22/#23/#26/#27 宣绿)
- **必读**: [`docs/ADAPTER_CONTRACT.md`](./ADAPTER_CONTRACT.md) 全文, **本 Session 任何改动偏离契约必须先改契约**
- **必读 (Cross-Session 契约)**: CLAUDE.md 决策 #26.C1 (persona_snapshot 走 `query_executions.attempts[].browser_profile` JSONB 子字段, 禁顶层列, Harness G3 锁定) + #27 G (rewrite_meta 走同一 JSONB envelope)

### Session 1 已交付基础 (本 Session 起点, 禁重做 ⚠️)

本 Session 开工前 CC 必须先跑下列 grep 确认"已交付模块"存在, **Prompt 任务条目里写明的同名条目等于"升级"而不是"新建"**:

```bash
# 必须已存在 (Session 1 已交付):
ls backend/src/engines/behavior/humanize.ts              # §1.2 humanize 行为库
ls backend/src/engines/errors.ts                         # §2.1 AdapterError 分类
ls backend/src/scheduler/retry.ts                        # §2.2 retry + POLICIES
ls backend/src/engines/captcha/solve.ts                  # §4 CAPTCHA 3 级 stub
ls backend/src/accounts/state-machine.ts                 # §5.1 状态机 (in-memory)
ls backend/src/accounts/pool.ts                          # §5 account pool (in-memory)
ls backend/src/accounts/sms/luban.ts                     # §7 SMS stub
ls backend/src/har/sanitize.ts                           # §6.1 HAR sanitize
grep -c "code: 'CF_BLOCKED'" backend/src/engines/types.ts  # 期望 1 (9 种错误码之一)

# 必须已存在 (Session 2 / 2.1 交付的契约):
grep -c "browserProfile" backend/prisma/schema.prisma    # 期望 ≥1 (Attempt.browserProfile)
grep -rn "rewrite_meta\|rewriteMeta" backend/src/platform/planner/query-assembler.ts
```

Session 1.2 对上述模块的 *升级口径* (不是重写):

| 已交付模块 | Session 1 交付状态 | Session 1.2 升级工作 |
|---|---|---|
| `engines/behavior/humanize.ts` | ✅ PagePort interface + Bezier + Quill + normalSample | 把 PagePort 接口实例化到真实 Playwright `Page`; adapter.execute() 接入 humanize API |
| `engines/errors.ts` + `types.ts AdapterError` | ✅ 9 种错误码 (CF_BLOCKED / COOKIE_EXPIRED / CAPTCHA_REQUIRED / PAGE_CRASHED / PROXY_DEAD / NO_ACCOUNT_AVAILABLE / EXTRACT_EMPTY / PARSER_FAIL / TIMEOUT) + POLICIES 策略表 | 在 3 家 adapter 的真实 execute() 路径里按 DOM 特征 throw 对应错误码 |
| `scheduler/retry.ts` | ✅ executeWithRetry + AttemptRecord[] append-only | 写 DB-backed attempts 持久化 (目前只 in-memory 结构) |
| `engines/captcha/solve.ts` | ✅ 3 级 stub (CapSolver → vision → slider) | Level 1/2 接真实 API client (目前 throw stub error) |
| `accounts/state-machine.ts` + `pool.ts` | ✅ 6 状态 + cooldown 差异化 + LRU pool (in-memory) | DB-backed pool (Prisma transaction) + SELECT FOR UPDATE SKIP LOCKED |
| `accounts/sms/luban.ts` | ✅ stub API shell | 接真实鲁班 SMS client |
| `har/sanitize.ts` | ✅ 全量 field strip | recorder.ts 接 Playwright launch + 录制后 auto-sanitize hook |

### 目标

把 Session 1 的"能跑"升级为"能存活"。覆盖 ADAPTER_CONTRACT §4 (反检测三层防御) / §6 (错误分类重试) / §8 (DOM quirks) / §9 (CAPTCHA 三级) / §10.2 (HAR 脱敏与回归)。

### Prompt

```
继续 GENPANO 项目开发。

开工前必读: 本文档顶部 "通用 Session Preamble (App Session 通用)" 段 (P.1-P.6) + `docs/ADMIN_CLAUDE_CODE_SESSIONS.md` 第 0 节 9 条公约 (line 55 起). 两者均为全 App Session 通用, 本 Prompt 不复写其内容, 以原文为准.

Session 特有前置阅读 (按顺序, 缺一不可):
1. CLAUDE.md (特别是决策 #22 Session 1 爬取框架 + #26.C1 persona_snapshot 契约 + #27 G rewrite_meta)
2. docs/ADAPTER_CONTRACT.md §4 (反检测) + §6 (错误码) + §8 (DOM) + §9 (CAPTCHA) + §10 (观测)
3. Session 1 已完成的 src/engines/adapters/** + tests/fixtures/scraping/**
4. Session 2/2.1 落地的 backend/src/platform/planner/query-assembler.ts (attempts.browser_profile 结构) + prisma/schema.prisma Attempt 模型
5. docs/TEST_STRATEGY.md Phase 1-2

本 Session 的 §Session 1 已交付基础 章节列出 7 个已就位模块的升级口径, 禁重做, 只升级. Prompt §1-§7 每条任务必须先 grep 检查"已交付状态", 存在即走升级分支.

## 0. Pre-Flight 环境依赖 + Cross-Session 契约 (开工第一批动作, 缺一不可)

### 0.1 环境依赖清单 (Frank 提供或走 stub 降级)

| 依赖 | 环境变量 | 状态检查 | stub 降级路径 |
|---|---|---|---|
| Camoufox / playwright-firefox | (无, 靠 npm install) | `node_modules/playwright-core/.local-browsers/firefox-*/` 存在 | 无降级 — 本 Session 硬需求 |
| Ninja Clash 订阅 URL | `NINJA_CLASH_SUBSCRIPTION_URL` | `.env` 存在且 fetch 返回 YAML | stub transport: 返回固定 3 个 mock 节点 |
| CapSolver API Key | `CAPSOLVER_API_KEY` | `.env` 存在 | Level 1 抛 CAPTCHA_REQUIRED, 走 Level 2 兜底 |
| 火山方舟 Vision endpoint + model | `VOLC_VISION_MODEL` (独立于 chat model) | `.env` 存在 | Level 2 抛 CAPTCHA_REQUIRED, 走 Level 3 兜底 |
| pg_cron 扩展 (DB 层 cron) | DB `CREATE EXTENSION pg_cron` | `SELECT * FROM pg_extension WHERE extname='pg_cron'` 返回 1 行 | 本 Session 延期 cron 注册, 只落定时任务 SQL 文件供后续手动注册 |

**CC 开工第一步**: 跑一遍上述 5 项的状态检查, 缺项记入"偏离登记", 不阻塞 Session 启动但各自走 stub 分支并在验收表打 ⚠️ 标记。**Camoufox 缺失视为本 Session blocker**, 其余缺失走降级不 block。

### 0.2 Cross-Session 契约 · attempts.browser_profile JSONB (决策 #26.C1 + #27 G)

- **硬约束**: 本 Session 的 adapter.execute() 真实 Playwright 路径**只能读**取 `attempts[].browser_profile.personaSnapshot` 字段 (由 Session 2.1 query-assembler 注入) 决定 Camoufox 启动参数 (userAgent / timezone / locale / viewport), **禁止自行生成 persona**, 也**禁止修改 browser_profile JSONB 结构**。
- **禁加列**: `query_executions` 表禁止任何 `persona_*` 或 `agent_profile_*` 顶层列新增 (Harness G3 `query-execution-no-persona-column` 锁定, 违反 → CI block)。若 Session 1.2 需要持久化新字段, 只能注入到 `attempts.browser_profile` JSONB 子字段 (例如加 `camoufoxLaunchArgs` 或 `proxyLeaseId`)。
- **rewrite_meta 同 envelope**: Session 2.1 在同一 JSONB 下写 `rewrite_meta` (LLM rewrite 审计), 本 Session 的写入不得冲掉或改写此字段, 只 append。

### 0.3 Schema 补丁 (本 Session 必须新建 migration `20260424000000_session_1_2_adapter_hardening/`)

Session 1/1.5/2/2.1 未覆盖, 本 Session 新增:

1. **`Account.lastProxyId VARCHAR(255)` 字段** — §1.3 账号-代理粘性需要, 记录上次成功使用的 ProxyNode id
2. **`AccountRegistrationLog` 表** — §7 auto-register 需要, 字段: id / engineId / phoneNumberMasked / success Boolean / errorCode / costUsd DECIMAL(8,4) / rawSmsProviderResponse JSONB / createdAt
3. **`engine_health_5min` materialized view** — §2.4 要求, SQL 按 ADAPTER_CONTRACT §10.4 实现, refresh cron `*/5 * * * *` (若 pg_cron 缺失, 落到 SQL 文件供后续注册)
4. **`ProxyNode` 表** — §1.3 Ninja Clash 节点缓存, 字段: id / subscriptionUrl / region / host / port / protocol / encryptedCredentials Bytes / lastHealthProbeAt / lastLatencyMs / status VARCHAR(30) / parkedUntil Timestamptz / createdAt
5. **`ProxyHealthLog` 表** — §1.3 健康探测日志, id / proxyNodeId / probeAt / ok Boolean / latencyMs / reason VARCHAR(100)

所有字段按现有 schema.prisma 约定 `@map` + `@db.Timestamptz(6)` + `@db.VarChar` + `@@map` snake_case 表名。CHECK 约束 (status 枚举、success Boolean 等) 走 raw SQL migration (Prisma DSL 不支持)。

## 任务

### 1. 反检测三层防御 (ADAPTER_CONTRACT §4)

#### 1.1 浏览器指纹层 (Camoufox 替换 playwright-extra)
- 评估 Camoufox 集成路径 (Python binding via child_process, 或直接用 playwright-firefox + stealth patch)
- 迁移现有 adapter 的 launch 参数到 ADAPTER_CONTRACT §4.1 清单:
  * --disable-blink-features=AutomationControlled
  * --disable-dev-shm-usage
  * --disable-software-rasterizer
  * --no-default-browser-check
  * --disable-features=IsolateOrigins,site-per-process
- 禁止 --headless=new 跑真实爬取 (CI 回放可以 headless)
- launch_persistent_context + 固定 user_data_dir (cookie/indexedDB 持久化)

#### 1.2 行为指纹层 (§4.2) — **[Session 1 已落骨架, 本 Session 接真实 Playwright]**
- `src/engines/behavior/humanize.ts` **已交付** PagePort interface + normalSample + Bezier mousePathPoints + `QUILL_ESCALATION_ORDER` + `pausePonderingMs`; 本 Session 工作:
  * 把 PagePort interface 实例化到真实 Playwright `Page` 类型 (原来接口是为了脱 Playwright 依赖便于单测)
  * 为 adapter 提供包装: `typeWithJitter(page, sel, text)` / `mouseMoveHumanlike(page, target)` / `scrollRandomly(page)` / `pausePondering(ms)` — 参数 range 按原 Session 1 常量
  * Quill 3 级降级 `injectQuill()` 实例化, 走 `QUILL_ESCALATION_ORDER = ['keyboard', 'input-event', 'direct-assign']`
- 所有 adapter.execute() 必须走上述函数, 禁止裸 page.fill / page.click + 立即 submit
- Harness 规则加入 scripts/ci-check.mjs: 禁止 page.fill 直接接 submit (grep 组合模式)

#### 1.3 网络指纹层 (§4.3) — **[Session 1 已落 proxy/pool.ts in-memory, 本 Session 接 Ninja Clash + DB 持久化]**
- `src/engines/proxy/pool.ts` **已交付** in-memory ProxyPool (黑名单 park 到下一小时顶 / 零健康 `proxy:zero-healthy` 事件)
- **本 Session 工作**:
  * `src/proxy/ninja-clash.ts` — fetchSubscription(url) → ClashNode[] / healthProbe(node, timeout=10s) → {ok, latency, reason} / sampleProxy(region, excludeRecentFail: Duration) → ProxySnapshot
  * 把 Session 1 的 in-memory ProxyPool 升级为 DB-backed: 读写 `ProxyNode` + `ProxyHealthLog` 表 (§0.3 新建)
  * 账号-代理粘性实现: `Account.lastProxyId` 字段 (§0.3 新建, Prisma model 名是 `Account` 不是 `LLMAccount`) + scheduler 优先复用
  * subscription_refresh cron (0 */6 * * *, §7.3) — pg_cron 若缺失则落 SQL 文件到 `backend/prisma/crons/` (§0.1 降级路径)

### 2. 错误分类 & 重试 (ADAPTER_CONTRACT §6)

#### 2.1 AdapterError 联合类型 — **[Session 1 已落 9 种错误码, 本 Session 升级分类函数]**
- `src/engines/errors.ts` + `types.ts` **已交付** 9 种错误码 (CF_BLOCKED / COOKIE_EXPIRED / CAPTCHA_REQUIRED / PAGE_CRASHED / PROXY_DEAD / NO_ACCOUNT_AVAILABLE / EXTRACT_EMPTY / PARSER_FAIL / TIMEOUT) + POLICIES 策略表 + `policyFor(code)`
- **本 Session 工作**: 补全 `toAdapterError(unknown, ctx): AdapterError` 分类函数 — 根据 DOM 特征 / response status / 异常消息归类: iframe src match `cloudflare.com/cdn-cgi/challenge-platform` → CF_BLOCKED; "请登录"出现 ≥ 2 次 → COOKIE_EXPIRED; 等等
- ❌ 禁止 catch 吞错返空 String; execute 必须抛 AdapterError

#### 2.2 重试副作用引擎 — **[Session 1 已落 executeWithRetry, 本 Session 补副作用 hook]**
- `src/scheduler/retry.ts` **已交付** executeWithRetry (纯逻辑 + AttemptRecord[] 返回); `POLICIES` 表在 errors.ts 也已就位
- **本 Session 工作**: 补 `applyErrorSideEffects(err, ctx)` 函数 (DB-backed), 按 §6.1 表更新 `Account.status` (走 `state-machine.transitionTo`) / `ProxyNode.status` / `ProxyNode.parkedUntil`; 在 executeWithRetry 外围挂 hook
- `shouldRetry(err, attempt)` 策略表 (Session 1 已有 `POLICIES[code].shouldRetry`, 本 Session 仅补 adapter 调用点)
- NO_ACCOUNT_AVAILABLE → markAsPending(query), 不计入失败分母

#### 2.3 Attempt 记录 — **[Session 1 已落 AttemptRecord in-memory, 本 Session 接 DB 持久化]**
- AiResponse.attempts: Attempt[] append-only — Prisma `Attempt` 表已由 Session 2 落地 (schema.prisma:397)
- **本 Session 工作**: `scheduler/retry.ts` 的 AttemptRecord[] 在每次 attempt 结束时 `prisma.attempt.create(...)`, `browserProfile` JSONB 字段写入 personaSnapshot (来自 query_executions.attempts[].browser_profile, 见 §0.2 Cross-Session 契约)
- 禁止 ExecutableQuery.retry_count 字段 (§6.3); 禁在 query_executions 加 persona_* 列 (Harness G3)
- 每次 attempt 独立 HAR / screenshot 文件名 traceId-attempt{n}-{engine}.har

#### 2.4 Metrics 分母口径 — **[本 Session 全新: Session 1 无此物化视图]**
- 成功率 = SUCCESS / (SUCCESS + 计入分母的 FAIL)
- 剔除: NO_ACCOUNT_AVAILABLE + COOKIE_EXPIRED (账号池/Cookie 问题)
- 物化视图 `engine_health_5min` 的 SQL 严格按 ADAPTER_CONTRACT §10.4 实现 (§0.3 Schema 补丁 3)
- refresh cron `*/5 * * * *` — pg_cron 若缺失, SQL 文件落到 `backend/prisma/crons/engine_health_5min.sql` 供后续手动注册 (§0.1 降级路径)

### 3. DOM 抽取稳定性 (ADAPTER_CONTRACT §8)

#### 3.1 Selector 集中管理 — **[Session 1 已落 selectors.ts 骨架, 本 Session 补 quirks README + Harness]**
- `src/engines/adapters/{chatgpt,doubao,deepseek}/selectors.ts` **已交付** — Session 1 每家都有统一 const 导出
- **本 Session 工作**:
  * 为每个引擎新建/扩写 `README.md` 的 quirks 小节 (按 ADAPTER_CONTRACT §8.3 三家 MVP 引擎的特异规则逐条落地)
  * 新增 Harness grep: 禁止 XPath 绝对路径 `/\/html\/body/` (§6.2)
  * 审查 adapter.execute() 真实路径都走 selectors.ts const, 禁止行内选择器 literal

#### 3.2 textContent 强制 — **[本 Session 全新: Session 1 execute() 留 TIMEOUT sentinel, 未写抽取]**
- `src/engines/dom/extract.ts` 新建 — `extractText(page, sel)` 实现 ADAPTER_CONTRACT §8.2 完整逻辑
- 多段落 textContent 手工 `\n\n` 拼接 (innerText 会受 CSS 影响, 不稳定)
- Harness grep: 禁止 `\.innerText` 在 `src/engines/**` 出现 (§6.2)

#### 3.3 引擎特异 quirks (MVP 3 引擎) — **[本 Session 全新: execute() 里实例化已定义的 selectors]**
- Session 1 的 `selectors.ts` 已定义选择器常量, 本 Session 在 adapter.runExecute() 里真实消费:
  * ChatGPT: streaming 完成判定 `data-message-status="in_progress"` 消失 + `[data-testid^="cite-"]` 脚注抽取 + Cloudflare iframe → `CF_BLOCKED`
  * 豆包: `.reference-card[data-href]` (不是 `<a>`) + "请登录" 关键词 ≥ 2 次才判 COOKIE_EXPIRED
  * DeepSeek: `.citation-tooltip` 必须 hover 触发 + `.thinking-collapse` 跳过 + `localStorage.userToken` 必传 (缺失 → COOKIE_EXPIRED)

### 4. CAPTCHA 三级处置 (ADAPTER_CONTRACT §9) — **[Session 1 已落 engines/captcha/solve.ts 三级 stub, 本 Session 接真实 API]**

- Session 1 **已交付** `src/engines/captcha/solve.ts` 三级兜底链 (CapSolver → 火山 vision → slider), 全失败抛 `CAPTCHA_REQUIRED`; 当前 Level 1/2 返回 stub error
- **本 Session 工作** (新建独立模块, 便于 mock 测试):
  * `src/captcha/capsolver.ts` Level 1 (Turnstile/hCaptcha/reCAPTCHA) — 接 `CAPSOLVER_API_KEY` (§0.1 可降级)
  * `src/captcha/vision.ts` Level 2 — 接 `VOLC_VISION_MODEL` (独立于 chat model, 默认 `doubao-seed-2.0-pro`)
  * `src/captcha/slider.ts` Level 3 — 贝塞尔人类轨迹 (复用 `humanize.ts` 的 `mousePathPoints`)
  * 把 `engines/captcha/solve.ts` 的三级调用点从 stub 改为引用上述真实模块
- 三级全败 → 抛 `CAPTCHA_REQUIRED`, P1 告警 (走 Admin §4.2.6 `CAPTCHA_UNSOLVED` 分组)
- **禁止自动人工环节**: 人工只在 P1 告警侧响应, 不阻塞调度器

### 5. 账号 & Cookie 生命周期 (ADAPTER_CONTRACT §5)

#### 5.1 状态机实现 — **[Session 1 已落 6 状态 in-memory + Cooldown 差异化, 本 Session 接 Prisma 事务]**
- `src/accounts/state-machine.ts` **已交付** 6 状态 (ACTIVE/COOLDOWN/FROZEN/BANNED + PRE_WARMING/QUARANTINED) + `COOLDOWN_DURATIONS_MS` 按 error code 差异化 (COOKIE_EXPIRED 12h / CAPTCHA_REQUIRED 4h / DEFAULT 1h) + `autoPromoteExpiredCooldowns` 游标推进
- Prisma model 名是 `Account` 不是 `LLMAccount` (真相源 `prisma/schema.prisma:577`)
- **本 Session 工作**: 把 `state-machine.transitionTo()` 的 in-memory Map 写入替换为 `prisma.$transaction([...])` 原子更新, 保证并发状态转移不丢失

#### 5.2 Cookie 保活 — **[本 Session 全新: Session 1 无保活 cron]**
- `cookie_keep_alive` cron `*/2 * * * *` (ADAPTER_CONTRACT §5.2, 测试床 6h 有风控所以调到 2h)
- 只读取 `home` + `/api/user/me`, 禁止保活时发 Query (保活 ≠ 监测, 分离 traffic)
- pg_cron 若缺失 (§0.1 降级), 落 SQL 文件到 `backend/prisma/crons/cookie_keep_alive.sql`

#### 5.3 Cookie 粘贴格式支持 — **[本 Session 全新: Session 1 无 cookie 解析入口]**
- `parseCookieInput(raw: string)` 自动判断 EditThisCookie JSON / HAR `request.cookies` 两种粘贴格式
- 转成 `BrowserContext.addCookies()` 格式
- DeepSeek 额外字段 `userToken` → `localStorage.setItem` 注入 (Session 1 selectors.ts 已识别)
- KMS 加密 `Account.encryptedCookies Bytes` 字段 (schema.prisma 已有)

#### 5.4 并发安全 — **[本 Session 全新: Session 1 pool 是纯 in-memory LRU]**
- 账号选择 SQL: `SELECT ... FOR UPDATE SKIP LOCKED` (ADAPTER_CONTRACT §7.2 完整 SQL)
- 替换 Session 1 `accounts/pool.ts` 的 `pick()` LRU → DB-backed 查询 (保留 EventEmitter + `pool:low_watermark` 事件对外契约)
- 测试: 双 worker 并发 100 次选账号, 验证无重复命中

### 6. HAR 脱敏 & CI 回归 (ADAPTER_CONTRACT §10.2)

#### 6.1 Sanitizer — **[Session 1 已落 har/sanitize.ts 全量实现, 本 Session 接 recorder + CLI]**
- `backend/src/har/sanitize.ts` **已交付** — HEADERS_TO_STRIP_REQUEST/RESPONSE + QUERY_PARAMS_TO_STRIP + BODY_FIELDS_TO_STRIP (password/token/refresh_token/access_token/code/otp/phone/email/mobile) + 递归 `stripObjectFields` 深度扫描 + 统一写 `__REDACTED__`
- **本 Session 工作**:
  * `scripts/record-har.ts` CLI shell (Session 1 已落骨架) 接 Playwright launch, 录制后 auto-sanitize hook
  * `scripts/har-sanitize.mjs` 独立 CLI 入口 (便于 CI 批量跑 + 人工 ad-hoc 清洗)

#### 6.2 CI Harness 规则 (追加到 scripts/ci-check.mjs) — **[Session 1 已有 F1/F2/F3 三条, 本 Session 只补真正新增的 3 条]**
- Session 1 **已交付 F1** `no-bare-playwright-import` + **F2** `har-fixture-secret-leak` + **F3** `no-inline-prompt-literal` (决策 #22.F)
- **本 Session 新增** (归入 Group F 或新 Group I, 命名由 CC 决定, 不要重复 F1/F2/F3):
  * `no-inner-text-in-engines`: grep `\.innerText` 在 `src/engines/**` 非空即失败 (强制 textContent, §3.2)
  * `no-xpath-absolute-in-engines`: grep `/\/html\/body/` 在 `src/engines/**` 非空即失败 (§3.1)
  * `no-bare-page-fill-submit`: 组合 grep `page.fill\(.*\).*page.click\('button\[type="submit"\]'\)` (同文件) 非空即失败 (§1.2 humanize 强制, 禁止裸 fill → submit)
- **禁止重新实现 F1 / F2** (F1 已覆盖 "chromium 禁止裸 import", F2 已覆盖 HAR fixture leak)
- 每条新规则必须伴随 `backend/src/__ci_fixtures__/` 或 `backend/tests/fixtures/adapters/__ci_fixtures__/` 下的自验证违规样本, 并把 `scripts/ci-harness-selftest.mjs` 的 `EXPECTED_POSITIVES` 从 18 扩到 21

#### 6.3 HAR 回放测试 (L3) — **[本 Session 全新: Session 1 只落 queries.json 骨架]**
- `backend/tests/fixtures/scraping/queries.json` **已交付** 4 条规范查询 (Session 1 §D)
- **本 Session 新增**: 每个 MVP Adapter 录制真实 HAR 至少 2 个 fixture (success + 降级/失败)
- `page.routeFromHAR({ update: false, notFound: 'abort' })` 拦截 (TEST_STRATEGY v1.1 L3 层)
- 整个 adapter 层测试 < 30s, 不连真实网络

### 7. 账号自动注册 (ADAPTER_CONTRACT §5.4) — **[Session 1 已落 luban stub + auto-register 骨架, 本 Session 接真实 client]**

- `src/accounts/sms/luban.ts` **已交付** stub 入口 (requestNumber / getSmsCode / releaseNumber), `src/accounts/auto-register.ts` **已交付** 骨架
- **本 Session 工作**:
  * `src/accounts/sms/luban.ts` 接真实鲁班 SMS client (保持 Session 1 的 API shape 不变, 便于测试 mock)
  * `src/accounts/auto-register.ts` 豆包 + DeepSeek 注册 Worker 实现 (ChatGPT 人工入池, 不自动注册)
  * `AccountRegistrationLog` 表记录 success/fail + cost (§0.3 Schema 补丁 2)
  * `account_pool_watermark_check` cron `*/10 * * * *`, 低水位自动触发 (pg_cron 若缺失落 `backend/prisma/crons/` SQL, §0.1 降级)
- 测试: mock LubanSMS + mock Playwright, 验证"水位 < 3 → 触发注册" 流程 (Session 1 已有 `pool:low_watermark` 事件, 只是接收端改为 auto-register worker)

### 8. 回归测试矩阵

- L1 Harness: 上面 §6.2 三条新 grep (inner-text / xpath-absolute / bare page.fill→submit) 全绿 + Session 1 的 F1/F2/F3 保持绿 + harness selftest 18 → 21
- L2 单测: `retry.ts` + `applyErrorSideEffects` 决策表逐行覆盖 (9 错误码 × 3 attempt × 账号/代理副作用); Vitest 覆盖率维持 >80% 全线阈值
- L3 集成: 4 条关键路径 HAR 回放
  * 快乐路径 (2 个 fixture: success 文本 + success 含 citation)
  * CF_BLOCKED → 换代理 → 成功
  * COOKIE_EXPIRED → 换账号 → 成功
  * CAPTCHA Level 1→2→3 全败 → P1 告警 + PENDING
- L4 E2E: 至少 1 条 staging 环境真实跑通 + 产线 smoke (P-Gate 1.2 Frank 手动验证)

### 验收

**升级口径**: Session 1 已交付的模块此处只勾"升级完成", 新增项勾"新建完成"。

- [ ] (升级) ADAPTER_CONTRACT §4 反检测三层: 指纹层 Camoufox / 行为层 humanize 实例化到真实 Page / 网络层 Ninja Clash + ProxyNode DB-backed
- [ ] (升级) 9 种 AdapterError 代码 (Session 1 已定义), `toAdapterError()` 分类函数补齐; 上游调度器 `applyErrorSideEffects` 按 §6.1 表正确处置
- [ ] (硬约束) `retry_count` 字段不落库, attempts[] append-only; `query_executions` 表无顶层 `persona_*` 列 (Harness G3 持续绿)
- [ ] (升级) 账号状态机 in-memory → Prisma transaction; `SELECT FOR UPDATE SKIP LOCKED` 并发 100 worker 测试通过无重复命中
- [ ] (升级) `har/sanitize.ts` 已交付; 本 Session 接 recorder + CLI + 批量清洗脚本, F2 harness 持续绿
- [ ] (新建) 每个 MVP 引擎 ≥ 2 HAR fixture (真实录制 + sanitized), 整套 L3 回放 < 30s
- [ ] (升级) 自动注册: luban stub → 真实 client, auto-register 骨架 → 豆包/DeepSeek 真实流程; `AccountRegistrationLog` 有数据
- [ ] (升级) CAPTCHA: `engines/captcha/solve.ts` 三级 stub → 真实 API (Level 1 CapSolver / Level 2 Volc vision / Level 3 slider 复用 humanize); 三级全败 → P1 告警通路打通
- [ ] (新建) MVP 3 引擎 quirks README.md 落地, adapter.runExecute() 的 TIMEOUT sentinel 全部替换为真实 Playwright 实现
- [ ] (新建) `scripts/ci-check.mjs` 3 条新规则 + `ci-harness-selftest.mjs` EXPECTED_POSITIVES 18 → 21, selftest PASS
- [ ] (新建) Migration `20260424000000_session_1_2_adapter_hardening/` 落地 §0.3 五项 Schema 补丁 (Account.lastProxyId / AccountRegistrationLog / engine_health_5min / ProxyNode / ProxyHealthLog)
- [ ] (环境) §0.1 五项依赖 (Camoufox / Ninja Clash / CapSolver / Volc Vision / pg_cron) 状态检查通过或按降级路径落文件
- [ ] CI 运行时 < 12 min (TEST_STRATEGY 预算)

执行完毕后更新 CLAUDE.md (新增 "Adapter Hardening 完成" 章节, 预留决策号 #28)
并在 ADAPTER_CONTRACT.md 末尾追加一条 "2026-XX-XX: Session 1.2 完成, Camoufox/HAR sanitizer/错误码链路固化"

---

## 环境依赖真实状态声明 (Frank 提供, 替代 §0.1 CC 自测 — 按此推进)

- **Camoufox / playwright-firefox**: 未装, 开工时用 `playwright-firefox + stealth patch` 路线, `npm install playwright @playwright/test` + `npx playwright install firefox` 搞定. **本 Session 硬需求**, 装不上立刻停下来报错.
- **NINJA_CLASH_SUBSCRIPTION_URL**: 空值 (backend/.env), 走 stub 降级 (固定 3 mock 节点). 验收表打 ⚠️.
- **CAPSOLVER_API_KEY**: 已填真实 key (backend/.env), 走真实 Level 1 API.
- **VOLC_VISION_MODEL**: 空值 (backend/.env), 走 Level 2 降级兜底. 验收表打 ⚠️.
- **pg_cron**: 未开 (本地 Docker `genpano-dev-pg` 未挂 shared_preload_libraries). 所有 cron 任务落 SQL 到 `backend/prisma/crons/<cron_name>.sql` 供后续 Supabase/手动注册, **本 Session 不启动任何 cron**.

## 开工第一批动作 (严格按顺序, 任何异常立刻停下来问 Frank)

1. 跑 §Session 1 已交付基础 的 `ls` + `grep` 清单, 报告 7/7 模块就位 (不就位立停)
2. 跑 §0.1 五项依赖真实状态检查, 对比上方"环境依赖真实状态声明", 任何不一致立停
3. 按 §0.3 起 migration `20260424000000_session_1_2_adapter_hardening/` 的 schema 草稿 — **先不跑 `prisma migrate dev`, 让 Frank review SQL 草稿**
4. Schema 草稿绿了再进 §1.1 Camoufox 集成路径评估 + §1.2 humanize 实例化

## Commit / 宣绿约束

- Commit 规则遵循 CLAUDE.md 决策 #25 (Session Prompt 公约) + `memory/feedback_genpano_session_commit_rule.md`
- Session 宣绿后立即 git commit, 标题 `Session 1.2: Adapter Hardening - Phase Gate X/X PASS`
- 标题禁 §/✅/— 等特殊 Unicode (PowerShell here-string 坑)
- Commit body 回引 CLAUDE.md #28 (预留) + 引用 #22 (Session 1) + #26.C1 / #27 G (cross-session 契约)
```

### 预期产出

**(U) = 升级 Session 1 已交付模块; (N) = 本 Session 新建**

- (U) `src/engines/behavior/humanize.ts` — PagePort 实例化到真实 Playwright `Page` + adapter 包装 API
- (U) `src/engines/errors.ts` + `types.ts` — 补 `toAdapterError(unknown, ctx)` 分类函数 (9 错误码表已定义)
- (N) `src/engines/dom/extract.ts` — textContent 强制抽取
- (U) `src/engines/adapters/{chatgpt,doubao,deepseek}/` — execute() 从 TIMEOUT sentinel 替换为真实 Playwright 实现; 新建/扩写 `README.md` quirks 小节
- (N) `src/captcha/{capsolver,vision,slider}.ts` 三级处置真实模块 (替换 `engines/captcha/solve.ts` 的 stub 调用点)
- (U) `src/accounts/sms/luban.ts` stub → 真实鲁班 client
- (U) `src/accounts/auto-register.ts` 骨架 → 豆包/DeepSeek 真实注册 Worker
- (U) `src/accounts/state-machine.ts` + `pool.ts` — in-memory → Prisma transaction + SELECT FOR UPDATE SKIP LOCKED
- (N) `src/proxy/ninja-clash.ts` — 订阅客户端 + 健康探测 + sampleProxy
- (U) `src/engines/proxy/pool.ts` — in-memory → 读写 ProxyNode + ProxyHealthLog 表
- (N) `scripts/har-sanitize.mjs` CLI + `record-har.ts` 接 Playwright launch
- (U) `scripts/ci-check.mjs` 3 条新 harness 规则 + `scripts/ci-harness-selftest.mjs` EXPECTED_POSITIVES 18 → 21
- (N) Migration `20260424000000_session_1_2_adapter_hardening/` — 5 项 Schema 补丁 (§0.3)
- (N) `backend/prisma/crons/` SQL 文件 (若 pg_cron 缺失, 降级路径)
- (N) HAR fixture 每引擎 ≥ 2 份 (真实录制 + sanitize 过)

### Phase Gate

- **P-Gate 1.2**: Frank 在 staging 模拟"豆包 CF 风控收紧 + Cookie 失效" 组合故障, 观察 Adapter 自动切代理/账号 + 告警触达 Admin 是否 < 15 min 恢复

---

### Prompt 续推 (2026-04-23, 双修正已落 commit 5f05229 后的 MVP 主体推进 · Phase A 规划已回填)

**背景**: 原 Prompt 实施时因范围过大 + 决策漂移 + 环境 STOP 策略缺失三条结构性缺陷 (诊断见本节末), 触发了 2026-04-22 落地的 "MVP 3 引擎口径" 与 "6 枚举 fallback labeling" 双修正预先登记 (commit 5f05229, 27 files, +971/-186), 主体 §1-§8 未开始。本续推 Prompt 把原 Prompt 按 MVP 重新剪裁一次, 配合 §0 公约新增规则 10/11/12 (见 `ADMIN_CLAUDE_CODE_SESSIONS.md §0`, 2026-04-23 固化) 一并关闭结构性缺陷。**Phase A 规划 2026-04-23 追加两项范围调整** (见 `CLAUDE.md #28.A` + `#28.C`): (a) 固化 Platform Layer 边界 (Admin API 只做 HTTP wrapper, 业务归 `backend/src/accounts/**`); (b) 按规则 12 Type C 登记, 把鲁班 SMS live + auto-register live 从 "不做" 拉回本 Session, 同时 MVP 不加密 cookie (#28.C1, B1 路径, 字段名保留).

```
继续 Session 1.2 主体实施。双修正最终版已在 commit 5f05229 登陆 (27 files, +971/-186), 现在从 §0.3 Schema patch 之后的暂停点续推。

## §0 · 当前基线确认 (开工第一批动作)

在任何代码改动前先做 4 步确认, 任一不符立即 STOP 向 Frank 报告:

1. `git log --oneline -5` 确认 HEAD = `5f05229 Session 1.2 双修正最终版` (或在其之后)
2. `cd backend && npm run test -- --run` 确认 464/464 green
3. `cd .. && node scripts/ci-harness-selftest.mjs` 确认 `PASS (21 / 21 fixture expectations met)`
4. `grep -n "进行中" CLAUDE.md | head -5` 确认决策 #28 header 仍是 "进行中, Phase A 规划 2026-04-23 / 双修正预先登陆 2026-04-22" — 本 Session 收尾时会改成 "交付 (2026-04-XX)" 并回填 A-F 实施段 (A 段 Platform Layer 边界 / C 段 C1/C2 偏差 / G 段 C1-C4 双修正 不动)
5. `grep -n "#28.A" docs/ADMIN_PRD.md docs/ADMIN_CLAUDE_CODE_SESSIONS.md` 确认 Phase A 规划四文档同步已落 (ADMIN_PRD §4.2.4 + ADMIN SESSIONS §A2 + CLAUDE.md #28.A + 本续推 Prompt)

5 步绿后才能进入 §1。

## §1 · 真相源索引 (规则 5, 只引用不重抄)

- **修改**:
  - **Adapter 核心**: `backend/src/engines/adapters/{doubao,deepseek}/index.ts` (真实 execute), `backend/src/engines/browser/camoufox-launch.ts` (新建), `backend/src/engines/behavior/humanize.ts` (真实实例化), `backend/src/har/recorder.ts` (Playwright 接入)
  - **Platform Layer (Phase A 拉回, #28.A)**: `backend/src/accounts/sms/luban.ts` (stub → live HTTPS client + `process.env.LUBAN_API_KEY`), `backend/src/accounts/auto-register.ts` (stub → live 编排器: 租号 → 注册 → OTP → cookie 存库 → 释放租约), `backend/src/accounts/crypto-noop.ts` (**新建**, MVP identity encode/decode, #28.C1 唯一入口), `backend/src/accounts/db-repo.ts` (**新建**, Prisma 适配 `accounts` + `account_states` + `account_registration_logs` 读写), `backend/src/accounts/pool.ts` (扩 DB-backed 选择器, 从 in-memory 升级到 Prisma `SELECT ... ORDER BY last_used_at LIMIT 1`; SELECT FOR UPDATE SKIP LOCKED 仍延后到 Session 1.2.2), `backend/src/accounts/index.ts` (re-export 统一入口, 供 Admin `@/accounts` 消费), `backend/src/accounts/cli/{list,register,inject}.ts` (**新建**, 3 CLI 命令)
  - **测试 fixture**: `backend/tests/fixtures/adapters/{doubao,deepseek}/` (1 条 golden HAR 各), `backend/tests/integration/adapters/*.test.ts` (routeFromHAR 契约测试), `backend/tests/unit/accounts/{luban-live,auto-register-live,db-repo}.test.ts` (**新建**, 覆盖 live client + 编排器幸福路径 + 失败释放路径)
  - **Migration**: `backend/prisma/migrations/20260424000000_session_1_2_adapter_hardening/migration.sql` (**续写已存在目录, 禁新建 migration**, 双修正已登陆此目录; 主体若需加列/索引 append 同文件, 不创建 20260425xxx; `account_registration_logs` 表已在该 migration 含 engine_id CHECK 约束)
  - **npm scripts (`backend/package.json`)**: 加 `accounts:list` / `accounts:register` / `accounts:inject` 三条, 指向 `tsx src/accounts/cli/{list,register,inject}.ts`
- **引用 (不改)**:
  - `docs/CLAUDE_CODE_SESSIONS.md` Session 1.2 原 Prompt §1.1 / §1.2 / §3.2 / §3.3 / §4 / §6.1 / §6.2 / §6.3
  - `docs/ADAPTER_CONTRACT.md` §5 (Profile-Aware 启动序列) / **§5.1 (账号状态机)** / **§5.3a (Pre-Warm 7 步)** / **§5.4 (自动注册流程, Phase A 真相源)** / §7 (代理调度) / §8 (DOM 抽取) / §10.5 (responseSource 六枚举)
  - `docs/ADMIN_PRD.md` §4.2.4 (账号池架构边界块, 2026-04-23 新增)
  - `docs/ADMIN_CLAUDE_CODE_SESSIONS.md` §A2 前置依赖 + §A2 Tab 1 账号池 (HTTP wrapper 契约, 本 Session 不实施 Admin UI, 仅确认边界)
  - `docs/TEST_STRATEGY.md` v1.1 L3 (routeFromHAR 契约层)
  - `CLAUDE.md` 决策 #22 (Session 1 框架) / #26.C1 (attempts.browser_profile 禁顶列) / #27.G (rewrite_meta 同 envelope) / **#28.A (Platform Layer 边界)** / **#28.C1 (MVP 不加密 cookie B1 路径)** / **#28.C2 (Luban live 拉回本 Session, 规则 12 Type C)** / #28.G (双修正已登陆)
- **真相源双向同步**: 本 Session 结束前回写 `CLAUDE.md` 决策 #28 B/D/E/F 主体实施段 + 把 header 从 "进行中" 改 "交付 (2026-04-XX)", A 段 (Platform Layer 边界) / C 段 (C1/C2 偏差) / G 段 (C1-C4 双修正) 已固化不动

## §2 · MVP 范围剪裁 (严格遵守, 不自作主张扩 — 公约规则 10)

**本 Session 做**:
- **§1.1** Camoufox 真实接入 (playwright-firefox + playwright-extra + stealth plugin)
- **§1.2** humanize 真实实例化 (PagePort 接入 Playwright Page, Bezier mouse + Box-Muller 停顿)
- **§1.3** Ninja Clash 订阅真实拉节点 (Frank 已确认 `NINJA_CLASH_SUB_URL` 是真实值, 不是占位)
- **§3.2** **豆包** `DoubaoWebAdapter.execute()` 真实落地, 替换 TIMEOUT sentinel, 产出含 responseSource='web_ui' 的 AIResponse
- **§3.3** **DeepSeek-CN** `DeepSeekWebAdapter.execute()` 同上
- **§4** CAPTCHA Level 1 (CapSolver 真实集成) 落地, Level 2 (火山 vision) / Level 3 (slider) 保 stub + TODO 注释
- **§5a (Phase A 拉回, #28.C2)** **鲁班 SMS live client** 落地: `backend/src/accounts/sms/luban.ts` stub → live, `process.env.LUBAN_API_KEY`, 3 方法 (`leasePhone` / `pollOtp` / `releasePhone`) 真实调鲁班 HTTPS API; F2 harness 拦住日志里的完整手机号与 SMS 全文 (只允许 `masked phone (last 4)` + `OTP length` 两种 meta)
- **§5b (Phase A 拉回, #28.C2)** **auto-register live 编排器**: `backend/src/accounts/auto-register.ts` stub → live, doubao + deepseek-CN 两家 sign-up 页面导航 + 手机号提交 + OTP 拉取 + 验证码填写 + cookie/localStorage 导出 → `accounts` 行 (state=PRE_WARMING, encryptedCookies 明文 UTF-8 JSON, #28.C1) + `account_registration_logs` 行 (success=true); 失败路径**必须先 `releasePhone` 再 rethrow** (鲁班租费按时扣), Vitest 覆盖这条失败释放路径
- **§5c (Phase A 拉回, #28.A)** **Platform Layer DB 适配 + CLI**: `backend/src/accounts/db-repo.ts` 新建 (Prisma 读写 accounts / account_states / account_registration_logs), `pool.ts` pick() 从 in-memory 扩 DB-backed (`ORDER BY last_used_at ASC NULLS FIRST LIMIT 1`; FOR UPDATE SKIP LOCKED 延后 Session 1.2.2), `accounts/index.ts` 统一 re-export (供 Admin `@/accounts` 单一入口消费), `cli/list.ts` / `cli/register.ts` / `cli/inject.ts` 3 命令 + npm scripts 入口
- **§5d (Phase A, #28.C1)** **crypto-noop.ts 新建**: identity `encode(Buffer) → Buffer` + `decode(Buffer) → Buffer`, 全量代码走这个唯一入口, 未来换 AES-GCM 只改此文件 (不改调用方). auto-register / inject CLI / 读取路径全部必须 `import { encode, decode } from '@/accounts/crypto-noop'`, 禁直操作 `accounts.encryptedCookies` 字段
- **§6.1** `backend/scripts/record-har.ts` Playwright launch 补上 (Session 1 留的 CLI shell 接入真实 browser)
- **§6.2** 豆包 + DeepSeek-CN 各录 **1 条 golden HAR** 进 `backend/tests/fixtures/adapters/{doubao,deepseek}/happy-path.har`, 过 F2 sanitizer harness
- **§6.3** 每条 HAR 写 1 条 `routeFromHAR` 契约测试进 `backend/tests/integration/adapters/`, 断言 adapter.execute() 回放 HAR 得稳定 AIResponse (rawText 非空 + citations ≥0 + responseSource='web_ui' + parsed.mentions 至少 1 个命中)

**本 Session 不做 (明确延后)**:
- **ChatGPT 真实 execute()** → Fix Session 1.2.1 (Cloudflare iframe + 海外代理 + 账号冷却三重复杂度, 单独 Session 更干净)
- **ChatGPT auto-register** → Fix Session 1.2.1+ (ChatGPT 拒 datacenter IP 注册 + Cloudflare iframe 强拦 + 海外手机号方案 Frank 未验证 — MVP 走手工 `accounts:inject` CLI 导入 Frank 自备 cookie bundle, 见 §5 delivery order Step 14)
- **每引擎第 2 条 HAR** (error path / cookie-expired / captcha) → Fix Session 1.2.1
- **Account Pool SELECT FOR UPDATE SKIP LOCKED 并发事务** → Fix Session 1.2.2 (本 Session 交付 DB-backed pick 但不做并发锁, MVP 并发度 1-2 够用)
- **Luban 账号复用 / 预付费余额面板 / 号码黑名单** → Fix Session 1.2.2+
- **L4 staging smoke** → Frank 手动 headed 跑 2 引擎各 1 query + 跑 `npm run accounts:register -- --engine=doubao` 各 1 次, 不是 CC 任务
- **Admin UI 账号池页** → Session A2 Tab 1 实施, 本 Session 只交付 Platform Layer + CLI, 严禁在本 Session 碰 `backend/src/app/admin/**` 路由 (CLAUDE.md #28.A 边界)

## §3 · 硬约束 (任何一条违反 = PR block)

1. **F4-1/F4-2/F4-3 必须持续 green**: 新写的真实 execute() 里**每一个**返回 AIResponse 的路径都必须显式 stamp `responseSource: 'web_ui'`; routeFromHAR 回放路径也算 web_ui (因为是 HAR 来自真实 web UI 采集后脱敏); 若新增 "cached_replay" 路径, 必须同时在 F4-1 rule 里 append 白名单 — 但本 Session 不新增枚举值
2. **G3 (no persona_* top columns) 持续 green**: persona 快照按 #26.C1 只进 `query_executions.attempts[].browser_profile` JSONB; rewrite_meta 按 #27.G 只进 `attempts[].rewrite_meta` JSONB; 新 migration 如果要加列, 不得碰 persona_/agent_profile_/rewrite_ 前缀的顶层列
3. **F2 HAR sanitizer 必须抓得住**: 录完 HAR 立即跑 `node scripts/ci-check.mjs` 确认 F2 green; 若 HAR 里有 Bearer / Cookie / refresh_token 字面量就是 recorder.ts 的 sanitize 没钩到, 停下来修 recorder 不是删 HAR 里的字段
4. **F1 (no bare playwright import) 白名单扩张合法**: `camoufox-launch.ts` / `har/recorder.ts` 已在白名单; 如果 humanize 真实实例化需要 import playwright 类型, 走 `import type { Page } from 'playwright'` 只 import 类型 (TS 编译期消除), 不触发 F1
5. **`tsc --noEmit` 零错误**: AIResponse.responseSource 已是 required, 所有新返回点必须显式写; 测试 fixture 同样
6. **Vitest 阈值 80% 不降**: 新代码必须带单测; routeFromHAR 契约测试算 L3 集成测试, 进 `tests/integration/`, coverage 配置已 include
7. **Harness selftest 本轮不新增规则**: EXPECTED_POSITIVES 保持 21; 若实施过程中发现需要新 harness (例如 Camoufox 检测规避失败模式), 写进 commit body 的 Follow-up 节, 不在本 Session 加
8. **CLAUDE.md #28 header 本 Session 改 "交付"**: G 段 C1-C4 不动; A-F 主体按实施结果回填 (引擎架构 / Camoufox / humanize / CAPTCHA / HAR / routeFromHAR 各 1-3 段 + 决策根因)

## §4 · STOP 触发条件 (公约规则 12, 满足任一立即停下不自作主张降级)

**类型 A · 环境依赖失败**:
- Camoufox / playwright-firefox npm install 超时 or stealth plugin 与 playwright-extra 版本不兼容 → STOP 报告 (a) 失败 log; (b) 判断是环境问题还是代码问题; (c) 提议方案 (升版本 / 延后该子项); **禁切 playwright-chromium 兜底** (Session 1 锁定 Camoufox 作为反检测真相源, 降级会穿透决策)
- Ninja Clash 订阅拉节点 0 返回 → STOP 报告订阅响应内容 + 建议方案 (换订阅 / 走 §0.1 降级 stub)
- CapSolver API 真实调不通 (401 / 429 / 5xx) → STOP 报告 HTTP 状态 + 建议 (换 key / 换服务商 / Level 1 保 stub 延后)
- **鲁班 SMS API 401 / 429 / 5xx 持续返回** (Phase A 拉回条目, #28.C2) → STOP 报告 HTTP 状态 + 完整 response body (脱敏后) + 建议 (换 key / 联系鲁班客服 / 降级 doubao+deepseek-CN 自注册到 Fix Session 1.2.2, 但不降级整个 Session, 豆包 execute + HAR 流程仍可完成)
- **鲁班号码池空** (leasePhone 持续返回 "no_available_phones" ≥ 3 次) → STOP 报告, 不循环重试爆预算; 建议 (换地区代码 / 充值 / 延后本子项)
- **OTP 60s 超时连续 3 次** (pollOtp 同一引擎 × 同一运营商 × 同一时段连续 3 次空返) → STOP 报告受影响引擎 + 已花费手机号 + 建议 (换时段重试 / 临时延后该引擎的 live 注册 + Frank 用 `accounts:inject` 手工兜底)

**类型 B · 真相源与 Prompt 冲突**:
- §1 真相源索引引用的 `CLAUDE.md #26.C1` / `#27.G` / `#28.G` 段落, grep 时发现已被后续决策改写 → STOP 报告当前真相源状态 + 建议改 Prompt / 改真相源 / 撤回本次改动三选一
- `attempts.browser_profile` JSONB 结构与 Session 2.1 query-assembler 输出不一致 (persona 字段名 drift) → STOP, 不自行 "修复"

**类型 C · 范围溢出 §2 "做" 列表**:
- 实施 §3.2 豆包 execute() 时发现必须动 §5 Account Pool Prisma 事务才能继续 (例如登录态并发冲突) → STOP 报告 (a) 为什么必须动; (b) 是否可以 in-memory pool 兜底; (c) 拆 Fix Session 1.2.2 接手的提议
- 录 golden HAR 时发现 recorder.ts 不够 sanitize 某字段 → STOP 报告字段名, 不自行删 HAR 行 (规则 3 F2 必须抓得住 = 改 recorder 不改 fixture)

**偏差登记义务** (规则 3): 若某条 golden HAR 录出来 Content-Length 过大 (>500KB) 或含无法脱敏的 session-specific token, 写进 commit body 的 Known Issues 节, 用 `attempt_01` 而非 `golden` 命名占位, Fix Session 再重录。

## §5 · 交付顺序 (依赖正确, Phase A 拉回后扩为 16 步)

1. **环境准备**: `cd backend && npm install playwright-firefox playwright-extra puppeteer-extra-plugin-stealth && npx playwright install firefox` — 失败走 §4 类型 A
2. **Camoufox launch module**: `src/engines/browser/camoufox-launch.ts` 新建, export `launchCamoufox({proxy, profile, hAR?})` 返回 `{browser, context, page}`
3. **humanize 真实实例化**: `src/engines/behavior/humanize.ts` 的 PagePort 实现接 Playwright Page (mouse.move + keyboard.type + wait)
4. **crypto-noop 新建 (Phase A, #28.C1)**: `src/accounts/crypto-noop.ts` export `encode(b: Buffer): Buffer` + `decode(b: Buffer): Buffer` (MVP identity), 单测覆盖 round-trip + Unicode 边界
5. **db-repo 新建 (Phase A, #28.A)**: `src/accounts/db-repo.ts` 包 Prisma, 提供 `createAccount` / `listActiveByEngine` / `markUsed` / `upsertState` / `appendRegistrationLog` / `bulkImport` 等接口; auto-register + pool + CLI 都走这里, 禁在其他文件直 `prisma.account.*`
6. **accounts/index.ts 统一 re-export (Phase A, #28.A)**: 把 `luban` / `autoRegister` / `AccountPool` / `encode/decode` / `db-repo` 方法通过 `index.ts` 统一导出, Admin Session A2 将来 `import { ... } from '@/accounts'` 的单一入口在此 (严禁跨文件 deep import 绕过边界)
7. **Luban live client (Phase A, #28.C2)**: `src/accounts/sms/luban.ts` stub → live HTTPS 客户端, `process.env.LUBAN_API_KEY`, 3 方法全实现 + 日志脱敏 (只 log `last 4 digits` + `OTP length`, F2 harness 拦全量); 单测用 `vi.fn()` stub fetch transport, 覆盖 401/429/号码池空/OTP 超时 4 条失败路径
8. **auto-register live 编排 (Phase A, #28.C2)**: `src/accounts/auto-register.ts` stub → live, 豆包 + deepseek-CN 两家 sign-up 流程. 必须接 `launchCamoufox` + `humanize` + `luban.leasePhone/pollOtp/releasePhone` + `db-repo.createAccount` + `db-repo.appendRegistrationLog` + `crypto-noop.encode` (**唯一** cookie 写入入口). **失败路径必须先 `releasePhone` 再 rethrow** (Vitest 覆盖)
9. **AccountPool DB-backed (Phase A, #28.A)**: `src/accounts/pool.ts` 的 `pick()` 扩 DB 读取 (`db-repo.listActiveByEngine`), 保留 in-memory EventEmitter 的 `pool:low_watermark` 事件; 仍不做 `SELECT FOR UPDATE SKIP LOCKED` (延后 1.2.2)
10. **豆包 execute()**: `src/engines/adapters/doubao/index.ts` 的 execute() 从 TIMEOUT sentinel 换成 `await launchCamoufox()` → page.goto(`https://www.doubao.com/chat`) → `AccountPool.pick({engineId:'doubao', preferredSegmentGroup})` 取账号 → `decode(account.encryptedCookies)` 回填 cookies/localStorage → humanize 注入 prompt → wait for `.reference-card` → parse + 返回 AIResponse (responseSource='web_ui')
11. **DeepSeek-CN execute()** 同上, 站点 `https://chat.deepseek.com/`, DOM 参考 selectors.ts; 注意 localStorage.userToken 双轨鉴权, inject 时必须同时恢复 cookies + localStorage
12. **CLI 3 命令 (Phase A, #28.A)**: `src/accounts/cli/{list,register,inject}.ts` + `package.json` scripts `accounts:list` / `accounts:register` / `accounts:inject`. (a) `list` 读 db-repo + 格式化表格; (b) `register` 调 `autoRegister({engineId, countryCode})` 做 1 次注册 + 打印结果; (c) `inject` 接受 `--engine` + `--cookie-file` (JSON), 通过 `encode()` 写入 `accounts` 行, 供 ChatGPT 手工入池
13. **HAR recorder 接 Playwright**: `scripts/record-har.ts` CLI 从 shell 换成真跑 launchCamoufox + context.routeFromHAR (record mode)
14. **录 golden HAR + ChatGPT 手工 inject**: (a) `npm run record-har -- --engine=doubao --prompt="小红书推荐的精华液"` / `--engine=deepseek --prompt="推荐几款高端护肤品"` 产出 2 条 HAR 进 fixtures; (b) Frank 在本地跑 `npm run accounts:register -- --engine=doubao` 和 `--engine=deepseek-CN` 各 ≥1 次真实注册入池; (c) ChatGPT 由 Frank 用 `npm run accounts:inject -- --engine=chatgpt --cookie-file=./chatgpt-cookies.json` 手工导入 ≥1 个账号 (CC 不自己跑, 只确认 CLI help 可用 + inject 路径单测绿)
15. **routeFromHAR 契约测试 + CAPTCHA Level 1**: `tests/integration/adapters/doubao-happy-path.test.ts` + `deepseek-happy-path.test.ts` 各 1 条, 用 `context.routeFromHAR(path, {update: false})` 回放, 断言 execute() 得稳定结果; `src/engines/captcha/solve.ts` 的 `capSolverSolve()` 真实调 CapSolver API (key 从 env), Level 2/3 继续抛 NotImplemented
16. **验证四件套 + 回填 + commit**:
    - `npx prisma validate` → `npx tsc --noEmit` → `npm run test` (应 ≥ 464 + ≥ 6 新 accounts 单测 green) → `node scripts/ci-harness-selftest.mjs` (21/21) → `node scripts/ci-check.mjs` (F1-F4/G1-G4 全绿; F1 白名单确认只有 `camoufox-launch.ts` / `har/recorder.ts` / `humanize.ts`, **accounts/** 不入白名单**)
    - 回填 CLAUDE.md #28: header 从 "进行中, Phase A 规划 ..." 改 "交付 (2026-04-XX)", 回填 B/D/E/F 段 (Camoufox 实施 / 两引擎 execute / CAPTCHA / HAR + routeFromHAR / Luban live + auto-register live + CLI 的实施注记); A/C/G 不动
    - **commit**: title 严格 `Session 1.2: Camoufox + doubao/deepseek-CN real scrape + Luban/auto-register live + CLI - Phase Gate X/X PASS`, body 引用决策 #28 + 回引 #22/#26.C1/#27.G/#28.A/#28.C1/#28.C2, Phase Gate 清单 + Known Issues + Follow-up (ChatGPT execute / 第 2 HAR / FOR UPDATE SKIP LOCKED / L4 smoke)

## §6 · Phase Gate 验收 (X/X 全绿才 commit, Phase A 拉回后共 16 项)

- [ ] Camoufox 成功 launch + stealth 通过 bot-detector 自测 (打开 `https://bot.sannysoft.com/` 截图 4/4 绿)
- [ ] 豆包 adapter.execute() 真跑 1 次 (不走 HAR), 返回 rawText 非空 + citations ≥1 + responseSource='web_ui'
- [ ] DeepSeek-CN adapter.execute() 同上
- [ ] 2 条 golden HAR 过 F2 sanitizer (零 secret 泄漏)
- [ ] routeFromHAR 2 条契约测试 pass, 单条 <30s
- [ ] **Luban live client 跑通 ≥1 次真实 leasePhone + pollOtp + releasePhone 闭环** (Phase A, #28.C2); F2 harness 扫单测 + adapter 日志零手机号 / SMS 全文泄漏
- [ ] **`accounts:register` CLI 真跑成功 ≥2 次**: doubao ≥1 + deepseek-CN ≥1, `account_registration_logs` 表含 ≥2 条 `success=true` 行 (Phase A, #28.C2)
- [ ] **每引擎 ≥2 个 state='ACTIVE' 账号可选**: `SELECT engine_id, COUNT(*) FROM accounts WHERE status='ACTIVE' GROUP BY engine_id` 三家 (doubao/deepseek-CN/chatgpt) 各 ≥2 — 其中 chatgpt 由 Frank 用 `accounts:inject` CLI 手工导入 (Phase A, #28.A)
- [ ] **`accounts:list` / `:register` / `:inject` 三个 CLI 命令 `--help` 可跑且文档化参数** (Phase A, #28.A)
- [ ] **Platform Layer 边界无破口 (Phase A, #28.A)**: `grep -rn "import.*sms/luban" backend/src/app/` 返回空 (Admin API 路由未直 import Luban); F1 harness 白名单 grep `whitelistOf(F1)` 仅含 `camoufox-launch.ts` / `har/recorder.ts` / `humanize.ts` 三个文件, **`src/accounts/**` 不在 F1 白名单**
- [ ] **crypto-noop 单测绿**: identity round-trip + Unicode 边界 2 条测试 pass (Phase A, #28.C1)
- [ ] `npx tsc --noEmit` 0 errors
- [ ] `npm run test` 全绿, coverage ≥80% (应含 ≥6 条新 accounts 单测: luban-live 401/429/空池/OTP 超时 + auto-register 幸福路径 + 失败释放路径 + crypto-noop round-trip + db-repo 读写)
- [ ] `node scripts/ci-harness-selftest.mjs` PASS (21/21; 本 Session 不新增 harness 规则)
- [ ] `node scripts/ci-check.mjs` F1/F2/F3/F4-1/F4-2/F4-3/G1/G2/G3/G4 全 pass
- [ ] CAPTCHA Level 1 真实 CapSolver API 跑通 1 次 (可用 CapSolver 自带的 test challenge)
- [ ] CLAUDE.md 决策 #28 header 改 "交付 (2026-04-XX)", B/D/E/F 实施段已回填 (Luban live + auto-register live + CLI + 边界实证 各 1 段), A 段 (Platform Layer 边界) / C 段 (C1/C2 偏差) / G 段 C1-C4 不动

## §7 · 回报格式

执行完每个交付步骤 (§5 的 1-12) 汇报 1 次: `[Step N/12] PASS/FAIL 简述`。全部跑完后给一份 Phase Gate X/X 勾选单 + commit hash + Known Issues 列表。若中途任一 Phase Gate 项卡住, STOP 报告, 不自作主张降要求通过。
```

### 结构性缺陷诊断 (2026-04-23, 修复动作已闭环)

原 Session 1.2 Prompt 实施不到位不是 CC 执行缺陷, 是**结构性缺陷**。三条可识别问题 + 对应修复:

1. **范围过大, 无 MVP 剪裁** (§1-§8 覆盖 2-3 个 Session 的量, 没说"做 / 不做") → 修复: 续推 Prompt §2 强制二分段; `ADMIN_CLAUDE_CODE_SESSIONS.md §0` 新增 **规则 10 (MVP Scope-Cut Declaration)**, 要求所有 Session Prompt §2 必须有该段
2. **决策漂移未反向同步** (2026-04-22 的 MVP 3 引擎口径 + 6 枚举 fallback labeling 晚于原 Prompt, 发送前未回查) → 修复: `§0` 新增 **规则 11 (Pre-Send Decision-Freshness Check)**, 要求 Prompt 发送前 30 分钟内跑 3 条 freshness grep
3. **STOP 策略缺失** (环境依赖失败 / 真相源冲突 / 范围溢出三类情况无显式 STOP) → 修复: 续推 Prompt §4 使用 STOP 模板; `§0` 新增 **规则 12 (Explicit STOP-Trigger Template)**, 把类型 A/B/C STOP 触发条件模板化

规则 10/11/12 三条同步在 `CLAUDE.md 决策 #25` 的 Phase 2 段登记, 适用范围与规则 1-9 一致 (全 Admin + App + UI Prototype Session)。

---

## Session 1.5: 平台数据基础设施 - 行业知识图谱 ⭐ NEW

### 前置依赖
- Session 1 完成，爬取系统可运行
- Session 0 的数据库迁移包含 Knowledge Graph 表结构

### Prompt

````
继续 GENPANO 项目开发。请先阅读 CLAUDE.md 了解项目上下文，再阅读 PRD.md 的 4.0 节 (平台数据基础设施)，重点阅读 4.0.1a (行业知识图谱) 和 4.1.2 (Project 设计)。

本 Session 目标：构建行业知识图谱——包含行业→品类→品牌→产品的节点和关系网络，作为 Pipeline 和用户 Project 的数据基础。

## 背景

GENPANO 的核心策略是 "Data-First, User-Second":
- 竞品 (Profound) 模式: 用户注册 → 填入品牌 → 等待爬取 → 数小时后看到数据
- GENPANO 模式: 平台预采集 → 用户注册 → 选行业/品牌 → 立即看到完整数据

知识图谱是一切的基础:
1. 它定义了"监测什么" — Pipeline 从图谱生成 Topic
2. 它理解"谁和谁竞争" — 诊断引擎用关系边判断竞争格局
3. 它帮用户找到竞品 — Project 创建时从图谱推荐竞品
4. 它通过 Response 挖掘持续自我进化

## 任务

### 1. 行业 Registry + 品类树

创建行业种子数据 + 品类树 (MVP 覆盖联蔚集团 4 个核心客户行业):

```typescript
const MVP_INDUSTRIES = [
  { id: 'beauty', name: '美妆个护', nameEn: 'Beauty & Personal Care',
    seedBrands: ['雅诗兰黛', '兰蔻', 'SK-II'] },
  { id: 'luxury', name: '奢侈品', nameEn: 'Luxury',
    seedBrands: ['LV', 'Gucci', 'Hermès'] },
  { id: 'food-beverage', name: '食品饮料', nameEn: 'Food & Beverage',
    seedBrands: ['蒙牛', '农夫山泉', '元气森林'] },
  { id: 'fashion', name: '服装时尚', nameEn: 'Fashion & Apparel',
    seedBrands: ['Nike', 'UNIQLO', 'lululemon'] }
];
```

**品类树生成** (PRD 4.0.1a):
- 每个行业由 LLM 生成 3 级品类树，人工审核后入库
- 示例: 美妆个护 → 护肤(L1) → 精华(L2) → 抗衰精华(L3)
- 数据库表: `kg_categories` (id, name, level, parent_id, industry_id)

**数据库表**:
- `kg_categories` (id, name, nameEn, level, parentId, industryId, status)
- `platform_industries` (id, name, nameEn, status)
- Seed 脚本: 初始化 4 个行业 + LLM 生成品类树
- Admin API: CRUD 行业和品类

### 2. 品牌发现 + 关系建立 Pipeline

实现自动化品牌发现，同时建立品牌间竞争关系 (参考 PRD 4.0.1a + 4.0.2):

```
输入: Industry (含种子品牌) + kg_categories (品类树)
  ↓
Step 1: LLM 品牌发现 (按品类)
  - Prompt: "你是行业分析师。列出 {industry} 中 {category} 的 Top 30 品牌。
    对每个品牌输出 JSON: {
      primaryName, nameZh, nameEn,
      aliases: [{value, language: 'zh'|'en'|..., type: 'abbr'|'variant'|'legal'|'informal'}],
      positioning, priceRange, parentCompany, origin
    }
    别名必须包含: 常见中英文缩写 (如 YSL/EL)、无重音变体 (Estee Lauder)、
    法律实体名 (如"雅诗兰黛公司")、俗称昵称。
    同时标注品牌间的竞争关系和集团归属。
    已知品牌: {seedBrands} (确保包含这些)"
  - 对每个 L1/L2 品类分别调用
  ↓
Step 2: 去重 & 合并
  - 跨品类去重 (同品牌可能出现在多个品类)
  - 合并品牌别名
  ↓
Step 3: 存储品牌节点 + 关系边
  - 写入 kg_brands 表 (品牌节点)
  - 写入 kg_brand_relations 表 (COMPETES_WITH / SAME_GROUP 边)
  - 关系置信度初始值: confidence = 0.6 (LLM 来源)
  ↓
输出: 每行业 20-50 个品牌 + 品牌间竞争关系图
```

实现:
- `src/platform/discovery/brand-discovery.ts` — 品牌发现核心逻辑
- `src/platform/knowledge-graph/brand-relations.ts` — 品牌关系管理
- LLM 调用封装 (火山引擎 API，支持 DeepSeek/豆包模型)
- 品牌去重逻辑 (名称相似度 + 别名匹配)
- 数据库表:
  - `kg_brands` (id, industryId, primary_name, name_zh, name_en, aliases JSONB [{value,language,type}], positioning, priceRange, parentCompany, origin, source, confidence, status)
  - `kg_brand_relations` (brandAId, brandBId, type, confidence, source)
- 发现日志: `discovery_logs` (记录每次发现的原始 LLM 输出，用于审计)

### 3. 产品发现 + 关系建立 Pipeline

类似品牌发现，同时建立产品间关系 (参考 PRD 4.0.1a):

```
输入: Brand (含品牌名 + 行业) + kg_categories (品类树)
  ↓
Step 1: LLM 产品发现
  - Prompt: "列出 {brand} 最知名的 10 个产品/产品线。
    对每个产品输出 JSON: {
      primaryName, nameZh, nameEn,
      aliases: [{value, language, type}],
      categoryName, priceRange, keyFeatures[], status
    }
    别名需包含中文昵称 (如'小棕瓶')、英文简称 (如 'ANR')、无重音变体。
    同时标注: 与哪些竞品产品竞争、是否有平替/升级关系"
  ↓
Step 2: 存储产品节点 + 关系边
  - 写入 kg_products 表 (产品节点)
  - 关联品类: Product → IN_CATEGORY → Category (匹配 kg_categories)
  - 写入 kg_product_relations 表:
    - COMPETES_WITH: 直接竞品 (小棕瓶 ↔ 小黑瓶)
    - SUBSTITUTES: 替代关系 (精华 ↔ 精华面霜)
    - UPGRADES_TO: 升级关系 (小棕瓶 → 海蓝之谜精华)
    - BUDGET_ALT_OF: 平替关系 (国货精华 → 小棕瓶)
    - PAIRS_WITH: 搭配推荐 (精华 + 眼霜)
  ↓
输出: 每品牌 5-15 个核心产品 + 产品间关系网络
```

- `src/platform/discovery/product-discovery.ts`
- `src/platform/knowledge-graph/product-relations.ts` — 产品关系管理
- 数据库表:
  - `kg_products` (id, brandId, categoryId, primary_name, name_zh, name_en, aliases JSONB [{value,language,type}], priceRange, keyFeatures JSON, source, confidence, status)
  - `kg_product_relations` (productAId, productBId, type, confidence, source)

### 3a. Response 关系挖掘 (持续迭代)

在 Response 解析环节 (Session 3 分析引擎) 增加关系提取:

```
每条 AIResponse 解析时:
  ├── 已有逻辑: 提取 BrandMention / ProductMention / Sentiment
  └── 新增逻辑: 提取产品关系信号
      ├── "A 的平替是 B" → BUDGET_ALT_OF
      ├── "A 搭配 B 使用" → PAIRS_WITH
      ├── "A 和 B 哪个好" → COMPETES_WITH (如不存在)
      ├── "升级可选 B" → UPGRADES_TO
      └── 更新 kg_product_relations 置信度 (confidence += 0.1)
```

- `src/platform/knowledge-graph/relation-extractor.ts` — 从 Response 提取关系
- 与分析引擎集成，在 Response 解析 pipeline 中增加一步

### 4. 平台级 Topic/Prompt 生成

**复用 Session 2 的 Topic → Prompt Pipeline**，但在平台级运行:

- `src/platform/topic-pool.ts` — 对所有平台品牌/产品批量生成 Topic + Prompt
- 存储: `platform_topics` / `platform_prompts` 表 (区别于用户自定义)
- 生成策略: 每个品牌 10-15 个 Topic，每 Topic 2-4 个 Prompt
- 去重: 跨品牌/产品的 Topic 去重

**注意**: Topic/Prompt 生成的核心 pipeline 代码在 Session 2 实现。本 Session 只需:
1. 调用 pipeline 的批量入口
2. 存储到 query_executions (而非 user_queries)
3. 调度逻辑

### 5. 平台级采集调度器 (Platform Scheduler)

扩展 Session 1 的调度器，增加平台级调度:

```typescript
// 平台级调度配置
interface PlatformScheduleConfig {
  dailyStartHour: number;          // 每日采集开始时间 (如 02:00)
  tierConfig: {
    high: { interval: '1d', brands: 'top_20_percent' },   // 高活跃品牌每日
    medium: { interval: '3d', brands: 'mid_60_percent' },  // 中等品牌每3日
    low: { interval: '7d', brands: 'bottom_20_percent' }   // 长尾品牌每周
  };
  maxDailyExecutions: number;       // 每日最大爬取次数 (成本控制)
  profileSamplingRate: number;      // 每 Prompt 采样 Profile 数 (1-5)
}
```

- `src/platform/scheduler/platform-scheduler.ts`
- 分层采集频率实现
- 与 Session 1 的 Worker 队列集成
- 采集进度监控 (完成率、失败率、耗时)
- 成本控制: 每日爬取量 ≤ 账号池容量 × 日限额

### 6. 首批数据灌入脚本

一次性运行的初始化脚本:

```bash
# scripts/seed-platform-data.ts
# 1. 初始化 4 个行业
# 2. 对每个行业运行品牌发现
# 3. 对每个品牌运行产品发现
# 4. 对所有品牌/产品生成 Topic + Prompt (依赖 Session 2 的 pipeline)
# 5. 触发首次全量采集
```

**注意**: 步骤 4 和 5 需要 Session 2 完成后才能完整运行。本 Session 先实现 1-3，并为 4-5 预留调用接口。

### 7. 数据质量审查

- 简单的管理端点: GET /admin/platform/industries/:id/brands (品牌列表审核)
- 品牌/产品的 approve/reject 状态管理
- 发现日志查看

### 8. 测试

- 品牌发现 Pipeline: 以"美妆个护"行业为输入，验证发现 20+ 品牌
- 产品发现 Pipeline: 以"雅诗兰黛"为输入，验证发现 5+ 产品
- 平台调度器: 验证分层调度逻辑
- 数据库: 验证 Platform Layer 数据隔离

执行完成后更新 CLAUDE.md，特别说明 Platform Layer 的数据结构和发现 Pipeline。
````

### 预期产出
- `src/platform/discovery/` — 品牌/产品发现 Pipeline
- `src/platform/knowledge-graph/` — 知识图谱管理 (关系边 CRUD、置信度维护、关系提取)
- `src/platform/scheduler/` — 平台级采集调度器
- `src/platform/topic-pool.ts` — 平台级 Topic/Prompt 批量生成
- `scripts/seed-platform-data.ts` — 首批数据灌入脚本
- 数据库迁移: kg_categories, kg_brands, kg_products, kg_brand_relations, kg_product_relations, discovery_logs
- Admin API 端点
- 测试用例

### 验收标准
- [ ] 4 个行业种子数据 + 品类树已入库 (每行业至少 2 级品类)
- [ ] 品牌发现 Pipeline: "美妆个护" → 发现 20+ 品牌 (含元数据)
- [ ] 品牌关系: 发现的品牌之间存在 COMPETES_WITH 边 (至少 10 条关系)
- [ ] 产品发现 Pipeline: "雅诗兰黛" → 发现 5+ 产品 (含别名)
- [ ] 产品关系: 产品之间存在 COMPETES_WITH / BUDGET_ALT_OF 等边
- [ ] 产品品类关联: 每个产品关联到正确的 kg_categories 节点
- [ ] 发现日志: 每次 LLM 调用的原始输出有记录
- [ ] 平台调度器: 分层采集频率逻辑可运行
- [ ] 成本控制: 每日爬取量有上限保护
- [ ] Admin API: 可查看/审核品牌列表
- [ ] 首批数据灌入脚本 (步骤 1-3) 可端到端运行
- [ ] Platform 数据与 User 数据表结构隔离
- [ ] **LLM API 成本控制: 品牌/产品发现 Pipeline 单次运行 LLM 调用次数有上限 (每行业 ≤ 50 次调用)，异常截断有保护**

> **⚠️ PHASE GATE 2: 平台数据 + 爬取确认 (人类 Review)**
> - □ 爬取引擎核心流程是否通顺?
> - □ 品牌/产品发现 pipeline 结果抽检 (品牌名正确? 别名合理?)
> - □ 4 个行业数据图谱质量审核
> - □ 亲手触发一次爬取看结果
> - □ 阅读 review/ 中的 compliance 报告
> - ⏱ ~1h

---

## Session 2: 智能监测 Pipeline (Topic → Prompt → Query)

### 前置依赖
- Session 1 完成，爬取系统可运行
- Session 1.5 完成，平台品牌/产品图谱已入库

### Prompt

```
继续 GENPANO 项目开发。

开工前必读: 本文档顶部 "通用 Session Preamble (App Session 通用)" 段 (P.1-P.6) + `docs/ADMIN_CLAUDE_CODE_SESSIONS.md` 第 0 节 9 条公约 (line 55 起). 两者均为全 App Session 通用, 本 Prompt 不复写其内容, 以原文为准.

然后阅读 `CLAUDE.md` 了解项目上下文 (特别是决策 #16 / #21 / #22 / #23) + `PRD.md` 的 4.2 节 (智能监测 Pipeline: Topic → Prompt → Query → Response) + `PRD.md` 的 4.10.3 节 + 4.10.3.A 节 (多语言 + Intent × Engine × Locale 23 行决策矩阵, CLAUDE.md 决策 #21 要求 Planner strict lookup, 新增引擎须 append 矩阵行).

本 Session 目标：构建四层监测 Pipeline 和 Agent Profile 系统——这是 GENPANO 的核心差异化模块。

## 核心概念 (术语定义)

GENPANO 数据采集使用四层递进 Pipeline:
- **Topic** (监测主题): 需要监测的品牌/产品/品类维度主题，由 Planner 从品牌图谱 Bottom-Up 生成
- **Prompt** (提示语): Topic × Intent(意图) 矩阵生成的自然语言问句
- **Query** (可执行查询): Prompt × Profile(用户画像) 组合后的最终执行单元
- **Response** (AI 回答): Browser/API 执行 Query 后返回的完整回答

扇出关系: 1 Brand → N Topics → N×M Prompts → N×M×K Queries → N×M×K Responses

## 背景

竞品的监测来源问题:
- Semrush: 依赖小样本 opt-in 用户的真实查询数据，样本量小且有偏
- Profound: 需要用户手动填入 topic，费时且覆盖面窄
- 两者都没有 Profile 维度——只用一种"用户身份"爬取，数据有偏

GENPANO 的策略: Bottom-Up Topic 生成 + Intent 矩阵 + Profile 采样，在 Topic/Prompt/Profile 三个维度上实现大样本覆盖。

## 任务

### 1. Topic 生成 (Planner, Bottom-Up)

实现完整的 Topic 生成流程。**严格按 Bottom-Up 顺序**:

输入: { industry: "美妆", brands: [{name: "雅诗兰黛", tags: ["高端", "抗衰"]}], products: [{name: "小棕瓶", tags: ["精华液", "抗衰", "500价位"]}] }

Planner 步骤 (顺序不可变):
1. **产品级 Topic (最先)**: 从具体产品出发，生成最接近真实用户关注的主题
2. **品牌级 Topic**: 从产品列表推导品牌维度主题 (去掉产品名保留品牌)
3. **行业级 Topic**: 从品牌/产品属性中提炼品类词+场景词 (去掉品牌名保留品类) + 竞品发现类主题
4. **变体扩展**: 口语化、场景化、地域化、长尾化变体 (对所有层级)
5. **去重 & 质量评分**: 合并相似 Topic，评估"真实度" (像真人会关注的吗？过滤掉SEO味道的主题)

### 1.5 Prompt 生成 (Topic × Intent × Language)

对每个 Topic 生成多个 Prompt:
- 每个 Topic 至少覆盖 2 种 Intent (informational + commercial 为必选)
- Prompt 必须是自然语言完整句子，像真人在对话框里打的问题
- 支持多轮 Prompt 链: [主问题 → 追问1 → 追问2]
- 避免关键词堆砌 ("推荐 精华液 抗衰 2026 排行") ← 搜索引擎思维，不是 AI 对话思维
- **多语言生成** (PRD 4.10.3):
  - 每个 Prompt 带 `language` 字段 (`zh-CN` / `en-US`) 和 `appliesToEngines[]`
  - 中文 Prompt: 发给豆包/DeepSeek/ChatGPT 三个引擎
  - 英文 Prompt: 只发给 ChatGPT；为每个 Topic 额外生成英文版本
  - 中文 Prompt 使用品牌 nameZh，英文 Prompt 使用 nameEn，禁止混合
- **品类 Topic 纯净度约束** (PRD §4.2.1 Step 5 + §4.2.2 生成规则, 2026-04-16 新增):
  - `dimension='品类'` 的 Topic 标题和 Prompt 文本**禁止包含任何已知品牌名** (KG Brand.{nameZh, nameEn, aliases[]})
  - **提及率默认口径仅统计 `topic.dimension='品类'` 的 Query** (non-brand) — brand Topic 下 LLM 几乎必然提到该品牌, 提及率虚高无诊断价值
  - Planner 配额约束: 品类 dimension Topic 占比 ≥40%, 保证 non-brand Query 样本量充足

### 2. Agent Profile 系统 & Query 组装

参考 PRD 4.2.3 节 + 4.2.3a (Profile Group)，实现 Profile 池和 Query 组装:
- 定义 Profile 数据结构 (人口统计 + 行为 + 引擎设置维度, 含 `groupIds: string[]`)
- 创建默认 Profile 池 (覆盖主要人口统计组合)
- 实现采样策略: 每个 Prompt 随机采样 3-5 个 Profile
- **Query 组装**: Prompt + Profile 上下文 → ExecutableQuery (含 persona 前缀, locale, context, `profileGroupIds[]` 冗余存储)
- Profile 转换为 API 调用参数 (system prompt persona, 对话上下文前缀)
- 支持用户自定义 Profile (Phase 2 标注 TODO)

**Profile Group seed (PRD §4.2.3a)**:
- 新建 `src/seed/profile-groups.ts` 落地 6-10 个 MVP 预置 Group: `all` / `young_female_tier1` / `mid_age_female_tier23` / `male_tier1` / `price_sensitive` / `zh_chatgpt` / `en_chatgpt` (+ 行业特化组, 见 PRD §4.2.3a)
- 每个 Profile 插入时按 `ProfileGroup.filterRules` 计算 `groupIds`, 冗余存到 Query 的 `profileGroupIds`
- 存表: `profile_groups` (id, nameZh, nameEn, description, filterRulesJson, industryScope, isDefault)
- 提供 `matchProfileGroups(profile: AgentProfile): string[]` 工具函数, 在 Profile / Query 落库时同步调用

### 3. LLM Prompt 工程 (用于生成 Topic 和 Prompt 的模板)

设计高质量的 LLM prompt 模板:
- Topic 生成模板: 确保生成的 Topic 像真实用户会关注的主题
- Prompt 生成模板: 确保生成的 Prompt 像真实用户会问的问题
- 支持中英双语生成
- 包含 few-shot examples
- 支持不同行业的特化模板

### 4. Topic & Prompt 管理 API

- POST /api/v1/projects/:id/topics/generate - 触发 Topic 生成 (含 Prompt)
- GET /api/v1/projects/:id/topics - 获取 Topic 列表 (含 Prompt 展开, 支持过滤、分页)
- POST /api/v1/projects/:id/topics/custom - 用户添加自定义 Topic (系统自动生成 Prompt)
- PATCH /api/v1/projects/:id/topics/:tid - 标记 Topic (关键/忽略)
  - PATCH 语义：字段级 merge（只传被修改字段），与 PRD.md §4.5.1 对齐。
- DELETE /api/v1/projects/:id/topics/:tid - 删除 Topic (级联删除 Prompt)
- GET /api/v1/projects/:id/topics/:tid/prompts - 获取 Topic 下的 Prompt 列表
- POST /api/v1/projects/:id/topics/:tid/prompts/custom - 用户添加自定义 Prompt

### 5. 与爬取系统 & 平台数据集成

- 新生成的 Topic → Prompt → Query 自动进入爬取队列
- 支持增量更新 (新增 Topic 不影响已有 Topic 的历史数据)
- **平台级批量生成**: 完善 Session 1.5 预留的 `platform/topic-pool.ts` 接口
  - 对知识图谱中所有 kg_brands / kg_products 批量运行 Planner
  - Planner 利用品类树和关系边 (COMPETES_WITH, SUBSTITUTES 等) 生成更精准的 Topic
  - 输出写入 platform_topics → platform_prompts 表
  - 与 Platform Scheduler 集成 (Topic 生成 → Prompt 生成 → Query 组装 → 入队)

### 6. 测试

- 测试不同行业输入的 Topic/Prompt 生成质量
- 测试去重逻辑
- 测试 API 端点
- 生成一个实际案例: 以"美妆/雅诗兰黛/小棕瓶"为输入，展示完整的 Topic → Prompt → Query 生成结果
- **平台级批量测试**: 对 Session 1.5 灌入的品牌/产品数据运行批量 Topic 生成

### 7. 完成 Session 1.5 的 seed 脚本

运行 `scripts/seed-platform-data.ts` 的步骤 4-5:
- 对 4 个行业的所有品牌/产品生成 Topic + Prompt
- 触发首次全量 Query 组装 + 采集 (可设置小批量验证)

执行完成后更新 CLAUDE.md。
```

### 预期产出
- `src/topic-planner/` Topic 生成模块 (Planner)
- `src/prompt-generator/` Prompt 生成模块 (Topic × Intent)
- `src/query-assembler/` Query 组装模块 (Prompt × Profile)
- LLM prompt 模板文件 (用于 Topic/Prompt 生成)
- Topic & Prompt 管理 API 端点
- 与爬取调度器的集成
- **平台级批量 Topic/Prompt 生成逻辑**
- 测试用例 + 一个实际案例输出

### 验收标准
- [ ] 输入"美妆/雅诗兰黛/小棕瓶"能生成 20+ Topic，每 Topic 2-4 个 Prompt，合计 50+ Prompt
- [ ] Topic 按 Bottom-Up 层级标注 (产品/品牌/行业)
- [ ] Prompt 覆盖 4 种 Intent 类型 (informational/commercial/transactional/navigational)
- [ ] 生成的 Prompt 读起来像真实用户会问的问题（不像SEO关键词堆砌）
- [ ] Agent Profile 池包含至少 10 个预设 Profile
- [ ] 每个 Prompt 能关联 3-5 个采样 Profile 组装为 Query
- [ ] **Profile Group seed (PRD §4.2.3a)**: `profile_groups` 表有 ≥6 条 MVP 预置分组 (all/young_female_tier1/mid_age_female_tier23/male_tier1/price_sensitive/zh_chatgpt/en_chatgpt); `profile_groups.nameZh` / `nameEn` 双语齐备
- [ ] **Profile Group 计算**: `matchProfileGroups()` 对每个 Profile 产出 ≥2 个 groupIds (至少 `all` + 1 个特化组); Query 表 `profileGroupIds[]` 冗余存储, 便于按 group 聚合
- [ ] **最小样本保护**: 实现 `hasEnoughSamplesInGroup(groupId, dateRange, engineFilter)` 返回 bool + count, 阈值 50 Queries / 30 天, 供 Dashboard / API 调用
- [ ] Topic & Prompt 管理 API 全部可用
- [ ] 新增 Topic 能自动触发 Prompt 生成 → Query 组装 → 进入爬取队列
- [ ] **平台级批量生成: 4 行业全部品牌/产品的 Topic + Prompt 已生成并入库**
- [ ] **seed 脚本完整运行: 发现+生成+首次采集 端到端可跑**

---

## Session 2.1: Planner LLM Refinement (Topic / Prompt / Query-Rewrite)

> **Session 起源 (2026-04-22)**: Session 2 交付后 Frank 校对 "Session 2 是否已经成功从 LLMs 处获取了 response" — 发现 Session 2 的 Planner 是纯规则模板填充, 零 LLM 调用, Topic/Prompt 读起来像 SEO 关键词堆砌, 不是真人会问的句子。Frank 进一步强化目标: "最终 query 要和真实用户的 query 无限接近, 他们有相似的 browser profile、user profile"。Session 2.1 把 Planner 三层 (Topic / Prompt / Query Assembler) 全部接入 LLM, 把 Session 1.5 已经落地的 LlmClient + LlmTransport 拉进来, 让 Query 从"机器拼接"升级到"真人问法", 同时保留降级路径确保 LLM 故障时 Pipeline 不阻塞。

### 前置依赖
- Session 1.5 完成 (LlmClient / LlmTransport / 火山引擎统一入口 / dry-run transport / canned fixture 范式)
- Session 2 完成 (Topic/Prompt/Query skeleton 生成 + baseline migration `20260422000000_platform_baseline` + 3 admin 只读端点 + 399/399 Vitest + Harness 15/15)

### Prompt

```
继续 GENPANO 项目开发。

开工前必读: 本文档顶部 "通用 Session Preamble (App Session 通用)" 段 (P.1-P.6) + `docs/ADMIN_CLAUDE_CODE_SESSIONS.md` 第 0 节 9 条公约 (line 55 起). 两者均为全 App Session 通用, 本 Prompt 不复写其内容, 以原文为准.

然后阅读 `CLAUDE.md` 了解项目上下文 (特别是决策 #22 / #23 / #25 / #26 / #26.C1) + `PRD.md` 的 §4.2.1 Step 4 / Step 5 + §4.2.2 "Prompt naturalization 实现手段" + §4.2.3b "Profile-Aware Prompt Rewrite (LLM)" + §4.10.3 / §4.10.3.A 决策矩阵.

本 Session 目标: 把 Planner 三层 (Topic Planner / Prompt Generator / Query Assembler) 全部接入 Session 1.5 已经落地的 LlmClient + LlmTransport, 让生成的 Query 从"机器拼接"升级到"真人问法"; 同时保留 LLM 故障时的降级路径, Pipeline 必须在 VOLC_API_KEY 缺失时 CI 仍然全绿.

## 真相源索引 (ADMIN §0 Rule 5)

本 Session 引用 / 修改的真相源. 开工第一批动作必须 Grep 验证段号与字段名是否漂移, 漂移即停下 alignment 不写代码 (ADMIN §0 Rule 2 硬约束):

- `docs/PRD.md` §4.2.1 Step 4 / Step 5: 引用 (本 Session 前已同步). LLM naturalization + realismScore 硬阈值 0.5 / 0.7
- `docs/PRD.md` §4.2.2 "Prompt naturalization 实现手段": 引用. Intent-aware LLM naturalization + 4 条保留契约 (Intent 语义锚点 / Topic 关键词不稀释 / language 按 §4.10.3 矩阵 / CI canned fixture)
- `docs/PRD.md` §4.2.3b "Profile-Aware Prompt Rewrite (LLM)": 引用. rewrite 契约 + 降级路径 + rewriteMode/rewriteConfidence/rewriteFallbackReason 字段
- `docs/PRD.md` §4.10.3 Intent × Engine × Locale 决策矩阵: 引用. 23 行显式矩阵, naturalize / rewrite 的 language 必须 lookup 此表
- `docs/CLAUDE.md` 决策 #26.C1: 引用 + 执行. persona_snapshot 注入 `query_executions.attempts[].browser_profile` JSONB 既定路径, rewrite_meta 遵守同一规范 (不建顶层列)
- `docs/ADMIN_CLAUDE_CODE_SESSIONS.md` §0 公约 7 条: 引用 + 执行. Rule 1/2/3/5/6/7 全链路遵守
- `backend/src/platform/llm/client.ts`: 引用 / 复用. Session 1.5 落地的 LlmClient, Session 2.1 不新建 LLM 入口
- `backend/src/platform/planner/**`: 修改. topic-planner.ts / prompt-generator.ts / query-assembler.ts 内嵌 LLM 调用
- `backend/prisma/schema.prisma` PlatformTopic / PlatformPrompt / QueryExecution: 修改 (新增列). realismScore / llmRefinedAt / auditStatus / llmNaturalizedAt / naturalizeConfidence 等字段
- `backend/prisma/migrations/20260423000000_planner_llm_refinement/`: 新建. 不动 baseline, 新增一条迁移
- `scripts/ci-check.mjs`: 修改. 新增 Group H (H1/H2/H3), EXPECTED_POSITIVES 15 → 18

## Pre-Flight Grep Contract (决策 #25 Rule 2)

开工第一批动作, 写代码前必跑, 结果与本文描述不一致立即停下 alignment:

- `grep -n "本步骤由 LLM" docs/PRD.md` 应命中 §4.2.1 Step 4 与 §4.2.2 "Prompt naturalization 实现手段" 至少两处
- `grep -n "4.2.3b" docs/PRD.md` 应至少命中 1 次 (章节头存在)
- `grep -rn "export class LlmClient" backend/src/platform/llm/` 应命中 client.ts 导出
- `grep -rn "export .* LlmTransport" backend/src/platform/llm/` 应命中 LlmTransport interface/type 导出
- `ls backend/prisma/migrations/` 应含目录 `20260422000000_platform_baseline` (Session 2 产物, Session 2.1 迁移在其后)
- `node scripts/ci-harness-selftest.mjs` 最后一行应为 `selftest: PASS  (15 / 15 fixture expectations met)`

## 本 Session 范围 (10 Tasks)

### Task 1. Topic LLM Refinement (topic-planner.ts)

复用 Session 1.5 LlmClient, 在 `topic-planner.ts` 的 Step 4 (变体扩展) + Step 5 (真实度评分) 内嵌 LLM 调用. 新导出函数 `generateTopicsForIndustry(industry, repos, opts)`, opts 签名为 `{ llm?: LlmClient; minRealismScore?: number }`, 返回 `{ topics, auditQueue }`.

行为合约:
- `opts.llm` 未传时: 直接返回 Session 2 的 skeleton 结果, auditQueue 为空数组 (backward-compat 必须)
- `opts.llm` 已传时: 对每条骨架 Topic 调 `refineTopicWithLlm(skeleton, llm)` 生成 2-3 个变体, 再对每个变体调 `scoreTopicRealismWithLlm(variant, llm)` 获得 realismScore
- realismScore 分档 (硬阈值): ≥ 0.7 写入 topics (附 llmRefinedAt 时间戳), ∈ [0.5, 0.7) 写入 auditQueue (附 realismScore 供人工复核), < 0.5 直接 drop
- minRealismScore opts 参数覆盖 0.5 审核下限, 不覆盖 0.7 approved 线
- 返回前再跑一次 Session 2 的 `validateCategoryTopicPurity([...topics, ...auditQueue], brandNamesFrom(industry))`, 纯净度违规 throw 而非静默放行 (决策 #15 口径护栏)

Prompt 模板存 `backend/src/platform/planner/prompts.ts`, 命名 `TOPIC_REFINE_VARIANT_PROMPT` 与 `TOPIC_REALISM_SCORE_PROMPT` 做单一真相源; 模板内含 Intent 语义锚点示例与行业占位符, 禁在生成端重复拼接.

### Task 2. Prompt LLM Naturalization (prompt-generator.ts)

`generatePromptsForTopic` 新增 `llm?: LlmClient` 参数, 对每条骨架 Prompt 调 `naturalizePromptWithLlm({ skeleton, intent, language, topic, brandVocab })`.

必须传入 LLM 的 context:
- `topic.topicName` + `topic.dimension` (LLM 据此判定品类 Topic 下禁夹品牌名)
- `intent` + intent 语义锚点示例 (防漂移)
- `language` (zh-CN / en-US, 按 §4.10.3.A 矩阵 `lookupMatrix(intent, engine, locale)` 结果)
- `brandVocab`: KG 中该行业已知品牌的 nameZh / nameEn / aliases[] 组合. LLM 必须从此 vocab 里选, 禁自创新别名

naturalize 后必须跑三层校验:
- `validateCategoryPromptPurity` 扫品类 Topic 的 Prompt 是否夹带品牌名 (Session 2 已落地)
- `intentClassifier.classify(naturalized)` 必须严格等于 originalIntent
- `brandMatcher.findMissingKeywords(naturalized, topic.keywords)` 必须返回空数组

任一校验失败 → 丢弃 LLM 输出, 回退到 skeleton 版本, 并把该 Topic × Intent 的失败次数 +1; 连续 3 次失败在同一 Topic × Intent 对上 → 记 warning 日志供 Admin 审核.

### Task 3. Profile-Aware Prompt Rewrite (query-assembler.ts, 本 Session 核心新增)

这是 Session 2.1 相对 Session 2 最大的新增面. Query Assembler 在扇出 Prompt × Profile × Engine 时, 对每个 (prompt, profile) 对调用 `rewritePromptForProfile(prompt, profile, opts)`.

函数签名: opts = `{ llm?: LlmClient; minConfidence?: number }` (minConfidence 默认 0.6).
返回 RewriteResult 的字段集合: promptText (rewrite 后的最终问句) / rewriteMode (字面量 union: 'llm' | 'fallback_prefix' | 'skeleton_only') / rewriteConfidence (LLM 自评 [0, 1], fallback 模式省略) / rewriteFallbackReason (fallback_reason 字面量 union: 'llm_unavailable' | 'intent_drift' | 'brand_miss' | 'low_confidence').

行为合约:
- `opts.llm` 未传时: 返回 Session 2 原行为 `buildPersonaPrefix(profile) + prompt.promptText`, rewriteMode='fallback_prefix', rewriteFallbackReason='llm_unavailable'
- `opts.llm` 已传时: 调 `callLlmRewrite(llm, prompt, profile)` 取 `{ rewritten, confidence }`, 随后三层校验:
  1. intent 校验: `classifyIntent(rewritten) === prompt.intent`, 失败 → fallbackPrefix with reason='intent_drift'
  2. 品牌词校验: `brandMatcher.missingKeywords(rewritten, prompt.topicKeywords)` 必须为空, 有缺 → fallbackPrefix with reason='brand_miss'
  3. 置信度校验: `confidence >= minConfidence`, 不足 → fallbackPrefix with reason='low_confidence'
- 三层全过 → 返回 `{ promptText: rewritten, rewriteMode: 'llm', rewriteConfidence: confidence }`

rewrite 结果写入 `query_executions.attempts[].rewrite_meta` JSONB 子字段, 严格遵守决策 #26.C1 既定路径, 禁建顶层列. 子字段集合: mode / confidence / fallback_reason / original_prompt (Session 2 skeleton 原文, 供对比) / rewritten_prompt (Session 2.1 LLM 输出) / profile_signals 对象 (LLM 用到的 profile 信号, 字段含 age_band / gender / region / conversation_mode / style, 审计回溯用).

### Task 4. Canned LLM Responses Fixture (llm-canned-responses.ts)

`backend/src/platform/planner/llm-canned-responses.ts` 新建, 保证 CI 在 VOLC_API_KEY 缺失时 Planner 三层测试仍然全绿:
- 覆盖度: 4 行业 × 至少 10 骨架样本 × 3 LLM 任务 (refine / naturalize / rewrite) = 至少 120 条 canned pair
- 模式: `Map<promptHash, cannedResponse>` 结构, 以 SHA-256 hash 骨架 prompt 做 key
- dry-run transport (LlmTransport fetch stub) 根据 prompt hash 查 Map 返回对应 canned response; 未命中 key 时抛明确错误 (便于测试发现覆盖盲点)
- Live mode 需设 VOLC_API_KEY; 无 key 时 CI 必须自动 fallback 到 canned 模式且所有 vitest 测试 green

### Task 5. Vitest Dual-Branch (每层两套)

每个 refined 模块 (topic-planner / prompt-generator / query-assembler) 必须有两套 Vitest describe 块:
- skeleton-only mode (opts.llm undefined): Session 2 已有测试不退化, backward-compat 验证
- with LLM refinement (dry-run transport): 本 Session 新增. 必须覆盖 realismScore 分档 (< 0.5 drop / [0.5, 0.7) auditQueue / ≥ 0.7 refined) / LLM 生成 2-3 个 variants 都被收录 / 品类 Topic 纯净度仍被 validateCategoryTopicPurity 拦截 (即使 LLM 改写过) / LlmCallBudgetExceededError 抛出时部分结果正确返回

query-assembler 两套额外必须覆盖: 三种 fallback_reason (intent_drift / brand_miss / low_confidence) 各一例 + rewrite_meta 确实写到 attempts[i] 而非顶层列 (配合 Harness H, 双保险).

- 最低覆盖率阈值: 继续 80% 全线 (vitest.config.ts 不改)
- 新增测试数预期: 至少 60 例 (20 topic + 20 prompt + 20 query-rewrite), 总数从 399 升至约 460

### Task 6. Prisma Migration 20260423000000_planner_llm_refinement

新增迁移一条, 不动 Session 2 baseline. 迁移内容 (原始 SQL, CHECK 约束走 raw SQL 因为 Prisma DSL 不支持):
- `ALTER TABLE platform_topics ADD COLUMN realism_score DECIMAL(3,2)` 存 [0, 1] 浮点
- `ALTER TABLE platform_topics ADD COLUMN llm_refined_at TIMESTAMPTZ`
- `ALTER TABLE platform_topics ADD COLUMN audit_status VARCHAR(20) DEFAULT 'approved'` 加 CHECK 约束 `audit_status IN ('approved', 'pending_review', 'rejected')`
- `ALTER TABLE platform_prompts ADD COLUMN llm_naturalized_at TIMESTAMPTZ`
- `ALTER TABLE platform_prompts ADD COLUMN naturalize_confidence DECIMAL(3,2)`
- `query_executions` 零新列, 仅 COMMENT 该表 attempts 列为 "JSONB array of attempt records. Session 2.1+ each entry may include rewrite_meta subfield (see PRD 4.2.3b)"
- 部分索引: `CREATE INDEX idx_topics_audit_status ON platform_topics(audit_status) WHERE audit_status = 'pending_review'` + `CREATE INDEX idx_topics_realism_score ON platform_topics(realism_score) WHERE realism_score IS NOT NULL`

Prisma schema.prisma 同步三个字段映射 (realismScore / llmRefinedAt / auditStatus for PlatformTopic, llmNaturalizedAt / naturalizeConfidence for PlatformPrompt), 不新增 QueryExecution 列.

### Task 7. Group H Harness (3 条新规则 + 自验证 fixture)

`scripts/ci-check.mjs` 新增 Group H 段, 3 条规则:

- H1 `planner-must-invoke-llm`: 扫 topic-planner.ts / prompt-generator.ts / query-assembler.ts 三个文件, 每个文件必须出现 `import.*LlmClient` 或 `import.*LlmTransport` (正则 anchor 到 `from '.*llm.*client'` 或等价路径). 找不到即 block. Session 2 的纯规则实现在此规则启用后立即违规, 强制 Session 2.1 接入.
- H2 `query-rewrite-must-preserve-intent`: 扫 query-assembler.ts, `rewritePromptForProfile` 函数体内必须出现 `classifyIntent` 或 `intentClassifier.classify` 调用 token. 缺失 → block (rewrite 后不做 intent 校验就返回是硬伤).
- H3 `query-rewrite-must-preserve-brand-vocab`: 扫 query-assembler.ts, `rewritePromptForProfile` 函数体内必须出现 `brandMatcher` 或 `findMissingKeywords` 调用 token. 缺失 → block.

三条 self-seeded 违规 fixture (决策 #21.C 的 harness 自验证要求):
- `backend/src/platform/planner/__ci_fixtures__/H1_planner_no_llm_import.cifixture.ts`: 写一个 topic-planner 变体不 import LlmClient, 证明 H1 抓到
- `backend/src/platform/planner/__ci_fixtures__/H2_rewrite_skip_intent_check.cifixture.ts`: 写 rewritePromptForProfile 变体跳过 classifyIntent 调用, 证明 H2 抓到
- `backend/src/platform/planner/__ci_fixtures__/H3_rewrite_skip_brand_check.cifixture.ts`: 写 rewritePromptForProfile 变体跳过 brandMatcher 调用, 证明 H3 抓到

写 fixture 时注意 G2 的反直觉坑: 注释里不能出现被扫的 identifier, 否则 `content.includes()` 会误判为 pass. 在每个 fixture 顶部加一行说明 "the required identifier is intentionally NOT mentioned anywhere in this file".

`scripts/ci-harness-selftest.mjs` EXPECTED_POSITIVES 数组从 15 扩到 18, 新增 'H1' / 'H2' / 'H3' 三项. 数组最终应覆盖: A1 / B1 / C11-1 / C14-1 / D4 (App 5) + D8 / D9 / D10 (Admin A0 3) + F1 / F2 / F3 (Session 1 adapter 3) + G1 / G2 / G3 / G4 (Session 2 planner 4) + H1 / H2 / H3 (本 Session 3), total 18. selftest 通过标志为打印 `selftest: PASS  (18 / 18 fixture expectations met)`.

### Task 8. Live Smoke Test (VOLC_API_KEY)

在 Phase Gate 最后一步, 用 VOLC_API_KEY 真调火山引擎跑一次 end-to-end, 命令形如 `VOLC_API_KEY=sk-xxx npm run seed:platform -- --industry=beauty-personal-care --product-brands=3 --max-llm-calls=30`.

抽样要求 (贴到本 Session 收尾报告, Frank 验收):
- 20 个 Topic 样本 (含 realismScore 值, 预期全部 ≥ 0.7 才算本轮 LLM 质量合格)
- 20 个 Prompt 样本 (含 naturalize_confidence + Intent 标注)
- 20 个 Query 样本 (含 rewrite_mode='llm' + rewriteConfidence, 至少覆盖 3 种不同 Profile 做对比展示)
- 成本验证: 单行业 LLM 调用总额 ≤ $2 (按火山引擎 doubao-1-5-pro 定价 + token_count 累加, 超额即 block 合并)

如果 Frank 目测某些样本"还是像机器问的", Task 1 / 2 / 3 的 Prompt 模板需迭代直到样本过关, 再重跑 Phase Gate.

### Task 9. Phase Gate 验收 (5/5 一票否决)

- G1 typecheck: `npx tsc --noEmit` 零错误 (backend 工作目录)
- G2 单测 + 覆盖率: `npm run test:coverage` 全绿 + 80% 全线阈值不退化
- G3 harness selftest: `node scripts/ci-harness-selftest.mjs` 最后一行必须打印 `selftest: PASS  (18 / 18 fixture expectations met)`
- G4 ci-check Group H: `node scripts/ci-check.mjs` Group H 三条全绿 (其他 Group 失败若是 frontend 原型期遗留仍按决策 #21 可接受, 但 Group H 必须 0 fail)
- G5 Live smoke 抽样目测: Task 8 的 20+20+20 样本贴到收尾报告, Frank 目测"像真人问的"才过

任一 FAIL → 修 → 重跑 G1-G5, 不允许跳过或以 "pre-existing failure" 为由绕开 Group H / G3.

### Task 10. 收尾 (CLAUDE.md 决策 #27 + SESSION_PROGRESS + Commit)

Phase Gate 5/5 全绿后才做收尾, 禁先宣胜利再写 CLAUDE.md:

1. 更新 `CLAUDE.md` 追加决策 #27 "Session 2.1 · Planner LLM Refinement 交付", 子段必含: (A) 三层 LLM 入口 (Topic refine / Prompt naturalize / Query rewrite) 各自的 API 签名; (B) Canned fixture 机制与 Live mode 切换策略; (C) 降级路径三种 fallback_reason 的精确定义; (D) rewrite_meta 存 attempts[] JSONB (遵守 #26.C1) 的理由与禁建顶层列的 harness 护栏; (E) Group H H1/H2/H3 的规则文本与 selftest 数据点; (F) 与 PRD §4.2.1 / §4.2.2 / §4.2.3b 的精确对齐点位; (G) 偏离登记 (C1, C2, ... 如有); (H) Phase Gate 实测数字 (test 通过数 / coverage 百分比 / selftest 18/18 / Live smoke 成本实测)
2. 更新 `docs/SESSION_PROGRESS.md` Session 2.1 行状态从 PENDING 改为 DONE
3. 反查真相源索引 (ADMIN §0 Rule 7): PRD §4.2.1 Step 4/5 / §4.2.2 naturalization 段 / §4.2.3b 全段是否仍与本 Session 交付对齐. 有漂移按 ADMIN §0 Rule 3 登记为 C-deviation 回到 CLAUDE.md #27.G 段
4. Git commit (决策 #27 / 记忆 feedback_genpano_session_commit_rule): 标题格式 `Session 2.1: Planner LLM Refinement - Phase Gate 5/5 PASS`, body 引用 CLAUDE.md #27, 禁特殊 Unicode (section sign / check mark / em-dash 等), PowerShell 用 here-string + `git commit --file`

## 偏离登记模板 (决策 #25 Rule 3, Session 收尾前填)

Session 收尾前若发现真相源与实施的不可调和冲突, 按 C1 / C2 / ... 编号追加到 CLAUDE.md #27.G 段. 每条至少记录: 真相源 vs 实施的差异 / 原因 / 后续动作 (补齐 migration / 回到真相源改描述 / 推到后续 Session). 过度保守的缺省: 宁可记空 deviation 登记段也不省, 后续 Session 可追溯.

## 不在本 Session 范围 (明确边界)

- 多轮 Prompt 链 (follow-up 对话态): Session 2 偏离 C2 已延后到 Phase 2, 本 Session 仍不做, Query 保持单轮模型
- User-facing API 端点 (`/api/v1/projects/:id/topics/...` 系列): Session 2 偏离 C3 已延后到 Session 4a, 本 Session 仍只交付 3 条 admin 只读端点, 用户态 ACL + auth middleware 留给 Session 4a
- Admin Topic/Prompt 人工审核 UI: auditQueue 的 Admin CRUD 界面属于 Session A2 (KG 质量审核) 的范围, 本 Session 只落数据模型 + audit_status 字段 + auditQueue 返回结构, UI 交付 A2
- Response 采集端的 LLM 分析 (情感 / citation 提取的 LLM 化): 属于 Session 3 分析引擎范围, 本 Session 严格只管 Planner 三层 (Topic / Prompt / Query-Rewrite)

执行完 Task 10 并 Phase Gate 全绿后, 告知 Frank 继续 Session 3.
```

### 预期产出
- `backend/src/platform/planner/topic-planner.ts` · Step 4/5 接 LlmClient, 新导出 `generateTopicsForIndustry(industry, repos, opts)` 返回 `{ topics, auditQueue }`
- `backend/src/platform/planner/prompt-generator.ts` · `generatePromptsForTopic` 新增 llm 参数, naturalize 三层校验
- `backend/src/platform/planner/query-assembler.ts` · 新导出 `rewritePromptForProfile(prompt, profile, opts)` + RewriteResult 类型, rewrite_meta 写 attempts[] JSONB
- `backend/src/platform/planner/prompts.ts` · Topic / Prompt / Rewrite 三套 LLM 模板集中管理
- `backend/src/platform/planner/llm-canned-responses.ts` · 至少 120 条 canned pair, CI 脱网运行
- `backend/prisma/migrations/20260423000000_planner_llm_refinement/migration.sql` · 新增列 + 部分索引 + 注释
- `backend/prisma/schema.prisma` · PlatformTopic / PlatformPrompt 新字段映射
- `scripts/ci-check.mjs` · Group H 段 (H1/H2/H3) 三条 grep
- `scripts/ci-harness-selftest.mjs` · EXPECTED_POSITIVES 15 → 18
- `backend/src/platform/planner/__ci_fixtures__/H1/H2/H3_*.cifixture.ts` · 三份 self-seeded 违规 fixture
- `backend/tests/unit/platform/planner/*.test.ts` · dual-branch 约 60 例新增, 覆盖 skeleton-only + LLM refinement 两路径
- Session 收尾报告: Live smoke 20 Topic / 20 Prompt / 20 Query 样本 + 成本账单 + Phase Gate 实测截图
- CLAUDE.md 决策 #27 + SESSION_PROGRESS Session 2.1 状态 DONE + git commit

### 验收标准
- [ ] Pre-Flight Grep 六条全部命中预期, 否则停下 alignment 不写代码
- [ ] Task 1 Topic refine 接 LLM, realismScore 三档 drop/pending/approved 硬阈值落地 (< 0.5 / [0.5, 0.7) / ≥ 0.7)
- [ ] Task 2 Prompt naturalize 接 LLM, intent / purity / brand_vocab 三层校验全覆盖, 校验失败自动回退 skeleton
- [ ] Task 3 rewritePromptForProfile 接 LLM, 三种 fallback_reason (intent_drift / brand_miss / low_confidence) 各自有对应单测, rewrite_meta 走 attempts[] JSONB 不建顶层列
- [ ] Task 4 canned-responses.ts 至少 120 条, CI 在 VOLC_API_KEY 缺失时所有单测仍绿
- [ ] Task 5 vitest 新增 ≥ 60 例, 总数达到约 460, coverage ≥ 80% 全线不退化
- [ ] Task 6 migration `20260423000000_planner_llm_refinement` 通过 `prisma migrate dev --create-only` 生成且 apply 不报错, baseline 保留不改
- [ ] Task 7 Group H 三条 + 三份 cifixture 落地, selftest 18/18 通过
- [ ] Task 8 Live smoke 20+20+20 样本抽到位, 成本 ≤ $2/行业, Frank 目测通过
- [ ] Task 9 Phase Gate G1-G5 全绿
- [ ] Task 10 CLAUDE.md #27 追加完成, SESSION_PROGRESS 更新, git commit 推送

---

## Session 3: 分析引擎 & API & MCP Server

### 前置依赖
- Session 1 (爬取系统) + Session 2 (Topic/Prompt/Query Pipeline) 完成

### Prompt

```
继续 GENPANO 项目开发。

开工前必读: 本文档顶部 "通用 Session Preamble (App Session 通用)" 段 (P.1-P.6) + `docs/ADMIN_CLAUDE_CODE_SESSIONS.md` 第 0 节 9 条公约 (line 55 起). 两者均为全 App Session 通用, 本 Prompt 不复写其内容, 以原文为准.

然后阅读 CLAUDE.md (特别是决策 #19 Citation 模块 A-H + #21 Review 闭环 + #22 爬取框架 + #23 KG Platform Layer), 再阅读 PRD.md 的 4.4 节 (分析引擎) + 4.5 节 (API & MCP Server) + 4.2.6 节 (Citation 原始层 A-H) + 4.2.7 节 (Citation 行动面 A-H) + 4.8 节 (GEO 优化诊断建议).

本 Session 目标：构建分析引擎 (含 PANO Score + 优化诊断)、完整的 RESTful API、以及 MCP Server。

## 任务

### 1. 分析引擎

基于爬取的原始数据，计算以下核心指标:

**提及率 (Mention Rate)** (2026-04-16 口径精化)
- **默认口径 (面板 KPI)**: 品牌被提及的 Response 数 / `topic.dimension='品类'` 的 Query 总数 — 排除 brand Topic, 测真实穿透率
- **完整口径 (品牌详情 / 导出)**: 品牌被提及的 Response 数 / 全量相关 Query 总数
- 支持按引擎、时间、Intent 类型、Topic.dimension 维度聚合

**排名位置 (Position Score)**
- 品牌在推荐列表中的平均位置
- 处理未被提及的情况 (null)

**情感分数 (Sentiment Score)**
- Sentiment 字段（`ai_responses.sentiment`）在 MVP 阶段使用规则+词典实现：中文用 SnowNLP、英文用 VADER；字段 `sentiment_source = 'rule'`。LLM 增强延到 Phase 2。
- 范围 -1 到 +1，支持总体/产品质量/服务/价格 子维度

**Share of Voice**
- 同一 Topic 下各品牌被提及比例
- 按行业、品类聚合

**推荐语境分析**
- 提取 AI 推荐品牌时的条件和语境

**引用来源追踪 & 品牌归属 (§4.2.6 新增 2026-04-17)**

- **新增 Prisma 模型**: `AiCitation` + `CitationDomainAuthority` (见 PRD §4.2.6.A)
- **适配器扩展**: 每个 Engine Adapter 实现 `extractCitations(rawResponse, html): SourceCitation[]`
  - ChatGPT: 正则 `[N]` + 文末 "参考资料:" / "Sources:" 段落 + DOM `.citation-link`
  - 豆包: DOM `.reference-card` / `.source-link` + 文末段落 fallback
  - DeepSeek: DOM `.citation-tooltip` / `sup.footnote-ref` + networkIdle 等待
  - URL 归一化必须使用 `tldts` 包 (CLAUDE.md 依赖规则, 禁止手写正则)
- **Brand → Citation 归属** (pipeline 后处理): 三级优先级 official_domain > co_occurrence > text_match
  - 冲突处理: >3 个品牌归属 → 仅保留 Tier 1 命中
  - attributionReason 落 Audit Log, 不落主表
- **Authority Tier 打标**:
  - 命中 `brand.officialDomains[]` → Tier 1 自动
  - 其他 domain → 查 `CitationDomainAuthority` 缓存表, 未知 domain 默认 Tier 0 (confidence 0.3, 标 `tierSource='heuristic'` 待人工复核)
  - Admin 管理后台需支持 CitationDomainAuthority CRUD (复用 ADMIN_PRD)
- **citation_share KPI 公式 (修正)**:
  - 分子: `brandsAttributed` 包含 brandId 的 citation 数
  - 分母: 品牌相关 Response 的全部 citation 数
  - 当 Response 数 = 0 → 返回 `null` (不返回 0, 避免误导)
- **L2 单测必测场景** (详见 PRD §4.2.6.H):
  - 三引擎格式 fixture 回放 + 归属优先级 + URL 归一化 + Response 为 0 的 null 返回 + 首次入库品牌不触发 source_loss Alert

**时间序列**
- 所有指标支持日/周/月粒度
- 实现 MetricSnapshot 的定期快照机制

### 1.5 PANO Score 综合评分体系

参考 PRD 4.4 中的 PANO Score 定义，实现三级评分:

**Brand PANO Score** (品牌综合评分, 0-100):
- 加权聚合: 可见度 + 排名 + 情感 + 推荐语境 + 引用来源质量 (A 维)
- **A 维度公式 (2026-04-17, PRD §4.2.6.F)**: `A_score = Σ tier_weight(c.authorityTier) × c.authorityConfidence / Σ_industry tier_weight` 归一化到 [0,100]
  - Tier 权重表: 1=1.0 / 2=0.7 / 3=0.4 / 4=0.15 / 0=0 (PRD §4.2.6.B)
  - 权重表作为 `CitationDomainAuthority` 种子配置, **严禁硬编码到业务逻辑**
- 各子维度权重可配置
- 支持跨引擎和单引擎两种视角

**Product PANO Score** (产品评分, 0-100):
- 继承品牌评分维度 + 信息准确度 + 竞品推荐频率对比

**Industry PANO Score** (行业评分, 0-100):
- 品牌在行业中的 Share of Voice 排名 + 行业整体 AI 成熟度

PANO Score 需要支持时间序列趋势 (Score 的变化可直观反映 GEO 表现)

### 1.6 GEO 优化诊断引擎

参考 PRD 4.8 节，实现诊断模块:

**规则引擎检测**:
- 提及率环比下降 > 20% → 可见度下降诊断
- 情感分数跌破阈值 → 负面情感异常
- 竞品排名反超 → 竞品超越告警
- 产品信息与配置不匹配 → 信息失真
- PANO Score 大幅下降 → 综合表现恶化告警
- **`citation_source_loss` (2026-04-17, PRD §4.2.6.F)**: Tier 1+2 authority domain 集合 T-14d vs T-0 做 set diff, 丢失 ≥ 3 且剩余 < 70% → 触发 P1 Alert; evidence 使用 `CitationSourceLossEvidence` schema; 首次入库 (无 W1 窗口) 的品牌不触发
- **`citation_attribution_mismatch` (2026-04-17, PRD §4.2.7.A)**: 品牌 T-14d 窗口 `co_occurrence` + `text_match` 归因占比 ≥ 60% **AND** PANO A 落在行业后 30% → 触发 P2 Alert; evidence schema `CitationAttributionMismatchEvidence` (`byMethod.{official_domain,co_occurrence,text_match}` + `possibleCauses` 三选一: `missing_official_domain_config` / `domain_not_indexed_by_ai` / `alias_mismatch_in_text`); **硬约束: 与 `citation_source_loss` 对同一 Response 不得合并触发**, 规则引擎必须互斥检查 (详见 PRD §4.2.7.A Harness grep)

**§1.7 Citation 行动面 4 条 (MVP 口径, PRD §4.2.7)** — 2026-04-17 新增

> **实施原则**: §4.2.6 交付原始 citation 数据, §4.2.7 把它转化成 6 条用户行动面. MVP 内仅 A / B / C 上线 (D/E/F 延 v1.1 或 Phase 2), SESSIONS Session 3/4 按下列任务分拆.

**Session 3 (分析 + API 层) 新任务**:
1. **§4.2.7.A 归因诊断后端 (MVP)**: 规则引擎增加 `citation_attribution_mismatch` 检测 (见上一条 bullet); `AuthorityShareSeries` 聚合 API `GET /api/v1/brands/:id/authority-share?range=...` 返回 `[{ date, official_domain_pct, co_occurrence_pct, text_match_pct }]` (样本不足返回 `{ insufficient: true, minSamplesRequired: 20, currentSamples: N }`)
2. **§4.2.7.B 内容缺口后端 (MVP)**: `GET /api/v1/brands/:id/content-gap?range=...` 执行反向 query `mentioned - attributed` → 返回 Top 20 Topic (fields 对齐 CSV #10); 页面类型聚类用 URL path pattern regex 分 6 类 (product/review/ranking/kol/knowledge/other), regex 表独立 `content_gap_page_patterns` DB 种子
3. **§4.2.7.C PR 候选后端 (MVP)**: `GET /api/v1/brands/:id/pr-targets?top=50&excludeCovered=true` 按 `pr_score` 算式 (PRD §4.2.7.C) 返回 Top 50; `pr_score` 里的 tier_weight / trending 基数必须从 `CitationDomainAuthority` + 参数服务读, 禁硬编码; CSV #9 exportType=`pr_targets` 由此 API 流式导出
4. **§4.2.7.E Simulator 后端 (v1.1)**: `POST /api/v1/brands/:id/simulate-authority` 接 `{ deltaByTier, confidenceOverride? }`, 复用 §4.2.6.F A 公式, 返回 `{ currentPanoA, simulatedPanoA, delta, basePriceEquivalent }`; `basePriceByTier` 走 Admin 参数表 (§ADMIN_PRD 新增一个 CRUD 入口)
5. **§4.2.7.F MCP 工具 (Phase 2)**: `genpano_get_citations` / `genpano_list_pr_targets` / `genpano_simulate_authority_boost` — 入参/返回见 PRD §4.5.2, 单元测试覆盖鉴权/越权 (401/403); 事件注入 Mixpanel `mcp_api_call_made` 之前先 `distinct_id=api_key.userId` 映射

**Session 4b (前端) 新任务**:
1. 品牌详情 `?tab=content-gap` 新子 Tab, 组件 `BrandContentGapTab.jsx` (结构锚点: 参考 `BrandProductsTab.jsx` 同 Tab 布局); 子区块 ①-⑥ 按 PRD §4.2.7.B + C
2. 品牌详情概览 Tab 插入 `AuthorityShareTimeSeries.jsx` (Recharts AreaChart 堆叠, 3 层); v1.1 追加 `AuthorityRadarChart.jsx` + `SameGroupSharedCard.jsx` + `AcquisitionEventTimeline.jsx`
3. 独立 Simulator 页 `frontend/src/pages/BrandSimulatorPage.jsx` (v1.1), 滑杆用 Radix UI `<Slider>` (依赖规则), 禁止手写
4. Mixpanel 事件 #50-#56 封装进 `frontend/src/lib/analytics.ts` 唯一出口, 不得业务代码直接 import `mixpanel-browser`
5. i18n: `messages/{zh-CN,en-US}/citation.json` 新命名空间承载 §4.2.7 UI 文案; 列头 `pr_score / authority_tier / gap_ratio` 等经 `export.csv.column.*` 接入 (不新建 column 命名空间)
6. Visual regression: 新增 baseline `content-gap.png` / `authority-share.png` / `simulator.png` (v1.1) 到 Playwright `test-results/visual/`

**硬约束 (PR block)**:
- Tier 权重 / pr_score 算式参数 / basePriceByTier 一律从 DB/参数表读, 硬编码进业务代码 = PR block (复用 §4.2.6 同款 grep 拦截)
- UI 禁用开发者约束措辞 (§4.6.0a); citation.json 的 key 只能承载用户价值语 (例: "查看内容缺口" / "生成 PR 候选清单"), 禁写 "本页只做 / 请去 XX 查看"
- MCP 工具不得开放未鉴权的 citation 明细 (防爬导出)

**LLM 辅助归因**:
- 将检测到的异常 + 上下文 (Topic/Prompt、AI 回答原文、趋势) 送入 LLM
- 生成 possibleCauses 和 direction (方向性建议，不含具体执行步骤)
- **direction 颗粒度规范 (关键，详见 PRD 4.8.5)**:
  - 目标颗粒度: Level 3 — 问题诊断 + 数据对标 + 优化方向，不给具体渠道/动作
  - 撰写公式: [问题陈述] + [数据证据] + [标杆对比] + [优化方向] + [不干预后果]
  - LLM Prompt 必须约束:
    1. 包含: 具体数据指标 + 环比变化 + 行业对标数据 + 优化方向 + 不干预后果
    2. 优化方向用「动词 + 抽象对象」: ✅"提升权威来源覆盖密度" ❌"在小红书发内容"
    3. 包含行业 Top 品牌对标数值 (至少 1 个维度)
    4. 包含"若不干预"后果预估 (PANO Score 或排名变化)
    5. 禁止指出具体平台/KOL/内容类型 (这是咨询服务的价值)
    6. 允许定位问题边界 (哪类场景/内容/时段出了问题)

**输出**: GEODiagnostic 结构体数组 (参考 PRD 4.8.2 的 TypeScript interface, 2026-04-16 升级版含 causalChain / industryBenchmark 结构化 / priorityScore / timeSeries / relatedDiagnostics / anchorQuestions / readerHints / focusArea / ifUntreated)
- 每条含 severity (P0-P3)、evidence、possibleCauses、direction
- 分品牌/产品/行业三个维度
- **新增**: 
  - `quantifiedImpact` (量化预期影响): 诊断项的潜在业务影响量化估算 (如"提及率可恢复 15-20%")
  - `industryBenchmark` (同行业 Top 品牌特征参考): 行业 Top 3 品牌在该诊断维度的表现特征，用于对标

**重要边界**: 诊断只告诉用户"问题是什么、为什么、严重程度、大致方向、潜在影响、行业对标"，不输出具体优化执行步骤。这是咨询服务的入口钩子。详细颗粒度示例见 PRD 4.8.5。

### 2. RESTful API

实现 PRD 中定义的全部 API 端点:
- 项目管理 CRUD
- 品牌监测指标查询 (支持时间范围、引擎、**Profile Group** 过滤)
- 产品监测指标查询 (同上)
- 行业概览和趋势
- Topic & Prompt 管理
- Queries 列表 (支持 engine / **profileGroup** / status / profileId 过滤, 承接 PRD §4.6.1e 的 Queries drilldown)
- 报告生成

**Profile Group 维度 (PRD §4.2.3a)**:
- 所有指标聚合类 API (例如 `GET /api/v1/projects/:id/brands/:brandId/metrics`) 统一支持 `?profileGroups=group1,group2` 多值参数
- 后端聚合时: 只统计 `Query.profileGroupIds ⊇ requestedGroups` 的 Response
- 当样本数 < 50 Queries 时返回 `{ sufficient: false, sampleCount: N, fallback: 'use_all' }` 或直接拒绝, 由前端决定展示; **严禁**静默用全量数据替代
- `GET /api/v1/profile-groups` 新端点: 列出所有预置 Profile Group (id, nameZh, nameEn, description, isDefault, industryScope), 供前端下拉渲染

要求:
- OpenAPI (Swagger) 文档自动生成
- API Key 认证中间件
- 速率限制中间件
- 统一错误处理和响应格式
- 分页支持

### 3. MCP Server

实现 GENPANO MCP Server，让 AI Agent 可以直接查询 GEO 数据:

MCP Tools (参考 PRD 4.5.2):
- genpano_get_brand_visibility
- genpano_compare_brands
- genpano_get_industry_trends
- genpano_get_product_ranking
- genpano_generate_report

MCP Resources:
- genpano://projects/{id}/dashboard
- genpano://brands/{id}/report
- genpano://industry/{name}/benchmark

要求:
- 使用 @modelcontextprotocol/sdk
- 每个 tool 有清晰的 description 和 parameter schema
- 返回结构化的 JSON 数据，Agent 可直接消费
- 可独立运行，也可嵌入主应用

### 4. 测试 (TEST_STRATEGY Phase 2 - OpenAPI 契约驱动)

> **目标**: API 契约测试 100% 自动生成, 不再手写. 修改 `openapi.yaml` → `npm run test` 自动生成 / 运行契约测试, 契约与实现任一侧变动都立即失败.

#### 4.1 `openapi.yaml` 完整化
- Session 0 的 3 端点骨架扩到本 Session 实现的**全部**端点 (覆盖 §4.5 所有 API)
- 每个端点必须有: request body schema / response 200 schema / 错误响应 4xx/5xx schema / example
- components.schemas 定义复用类型 (Project / Brand / GEODiagnostic / PanoScore / ProfileGroup 等)
- 为所有 `profileGroups` 查询参数定义, 保证 §4.2.3a 样本不足响应 schema (`{sufficient:false, sampleCount, fallback}`) 明确

#### 4.2 契约测试自动生成 `scripts/gen-api-tests.ts`
- 读 `openapi.yaml` → 对每个端点生成 Vitest + supertest 测试骨架
- 生成内容: happy path (200 schema 校验) + 4xx 错误路径 + 请求 schema 反向校验 (发不符合 schema 的 body 必须被拒)
- 用 `ajv` 或 `zod-openapi` 做 runtime schema 断言
- 输出到 `tests/integration/api/__generated__/*.test.ts` (gitignore, CI 里重新生成)
- `npm run test:contract` = gen + run

#### 4.3 分析引擎准确性测试 (L2)
- PANO Score: 固定输入数据, 断言输出分数, 覆盖 subScore 权重 4 种配置
- 诊断规则引擎: P0/P1/P2/P3 各级至少 1 个 fixture 触发用例
- **诊断 direction 纯度 Harness grep** (追加到 `ci-check.mjs`): 
  - 正则检测 direction 文本禁含 "在小红书 / 发内容 / 投放 / KOL" 等具体渠道/动作 (黑名单见 PRD §4.8.5)
  - 有命中 CI 失败, 提示"direction 颗粒度越界"

#### 4.4 MCP Server 契约测试
- 每个 MCP tool 的 parameter schema 和 return schema 单测
- 用 `@modelcontextprotocol/sdk` test client 发起真实调用, 不走 HTTP mock
- 验证 tool description 文本含必需关键词 (方便 Agent LLM 正确选用)

#### 4.5 本 Session 新增的 Harness 规则 (追加到 `scripts/ci-check.mjs`)
- API 实现与 `openapi.yaml` drift 拦截: 自动扫 `src/api/` 路由表, 任何未在 yaml 声明的端点拒合并
- `profileGroups` 参数契约: 每个接收此参数的端点必须返回 `{sufficient, sampleCount}` 字段, grep schema 强制
- 诊断 direction 颗粒度: 上述 4.3 的黑名单正则

执行完成后更新 CLAUDE.md。
```

### 预期产出
- `src/analytics/` 分析引擎模块
- `src/analytics/pano-score/` PANO Score 计算模块
- `src/analytics/diagnostics/` GEO 诊断引擎 (规则引擎 + LLM 归因)
- 完整的 RESTful API 实现 + OpenAPI 文档
- `src/mcp-server/` MCP Server 实现
- API 认证 & 速率限制中间件
- 测试用例

### 验收标准
- [ ] 所有 API 端点可用，Swagger 文档可访问
- [ ] 输入品牌名 + 时间范围，能返回完整的指标数据
- [ ] PANO Score: 品牌/产品/行业三级评分可计算，支持时间序列趋势
- [ ] PANO Score 子维度权重可配置
- [ ] 诊断引擎: 模拟数据触发 P0-P3 各级诊断，输出结构体完整
- [ ] 诊断 direction 字段仅包含方向性建议，不含具体执行步骤
- [ ] **诊断增强**: 每条诊断包含 quantifiedImpact (量化影响估算) 和 industryBenchmark (行业对标数据)
- [ ] MCP Server 可独立启动并响应 tool 调用
- [ ] 使用 Claude Desktop 连接 MCP Server 能成功查询数据
- [ ] 分析计算结果与手动计算一致
- [ ] **`openapi.yaml` 覆盖全部实现端点**, `npm run test:contract` 自动生成 + 通过 ≥ 80%
- [ ] **API/yaml drift Harness 拦截**: 故意在 `src/api/` 新增未声明端点, `scripts/ci-check.mjs` 能识别并失败
- [ ] **诊断 direction 颗粒度 Harness**: 在 direction 字段写入 "在小红书投放", CI 失败并提示黑名单命中
- [ ] **`profileGroups` 样本不足响应契约**: 构造 < 50 Query 场景, 响应 `{sufficient:false, sampleCount, fallback}` 契约测试通过

> **⚠️ PHASE GATE 3: 核心引擎 + API 确认 (人类 Review)**
> - □ Query 生成 + 分析引擎 + API 全链路通顺?
> - □ MCP Server 可用? (用 Claude Desktop 实际连接测试)
> - □ PANO Score 计算合理? (抽查几个品牌)
> - □ 诊断 direction 是否严格不含执行步骤?
> - ⏱ ~45min

---

## Session 4a: 用户系统 & Onboarding ⭐ (原 Session 4 上半)

### 前置依赖
- Session 3 完成，API 全部可用

### Prompt

```
继续 GENPANO 项目开发。

开工前必读: 本文档顶部 "通用 Session Preamble (App Session 通用)" 段 (P.1-P.6) + `docs/ADMIN_CLAUDE_CODE_SESSIONS.md` 第 0 节 9 条公约 (line 55 起). 两者均为全 App Session 通用, 本 Prompt 不复写其内容, 以原文为准.

然后阅读 CLAUDE.md (尤其是 "设计锚点" 一节 + 决策 #9 Auth-Required 数据访问 + 决策 #10 零 Project 态 Route Guard → /onboarding), 再阅读 PRD.md 的 4.1 节 (用户系统) + 4.1.1-gate (Auth-Required 数据访问) + 4.1.1-form (AuthPage Email-first 2-step 状态机) + 4.1.1a (事务性邮件) + 4.1.1b (Onboarding) + 4.1.1d.C (Onboarding 草稿 DraftProject Prisma 模型) + 4.1.1e (登出 & 会话管理) + 4.1.2 (Project 设计) + 4.10 (国际化).

本 Session 目标：构建用户认证系统、事务性邮件、单路径 Onboarding 流程，UI 与邮件从 Day 1 支持中英双语。

## 结构参照（⚠️ 开始写任何 UI 前必读）

本 Session 不重建 UI。对应锚点已在 `frontend/`：

- **AuthPage** ⚠️ 2026-04-19 更新: 原 3 mode 骨架 (login / register / forgot) **已由 §1b 任务重构为 Email-first 2-step 状态机** (PRD §4.1.1-form, 锚点 `design/prototype-auth-v4.html` + `prototype-auth-v5.html`)。`/login` 和 `/register` 两条 URL **仍然保留**, 但进入后第一屏统一为 Step 0 邮箱输入 → lookup → Step 1 分叉 (新邮箱创建账号 / 已注册输密码 / 忘记密码)。本 Session 在 §1b 落地 state machine + `/api/auth/lookup` stub (含 ≥400ms anti-enum 定时), 在 §1 完成真实 lookup/register/login/oauth API 对接 + React Hook Form + Zod + 路由保护。视觉走 Stripe Light tokens (`--color-bg-page` / `t-input` / `t-btn-primary`), **禁止**保留旧版 LeftPanel 深色渐变 + 硬编码中文 + 装饰 blob。
- **Onboarding / 探索视图**: 骨架参考 `frontend/src/pages/IndustryPage.jsx`（同密度、同 card 模式、同 tokens）。D3 力导向图谱按 PRD 4.1.1b 新增，节点 / label / 详情面板的色值与字体走 tokens。
- **DashboardLayout**: 已就位于 `frontend/src/layouts/DashboardLayout.jsx`。Session 4a 只需保证受保护路由重定向到登录页、登录后进入 Layout，**不改侧栏结构**。
- **开工第一步**: `ls frontend/src/components/` 核对 `t-input`、`t-btn-primary`、`Badge`、`Card` 等是否已存在，能用的一律复用。

## 样式契约

- 禁止内联 hex / rgba / 字号绝对值（品牌 logo SVG 除外）
- 所有 UI 使用 `.t-input` / `.t-input-error` / `.t-btn-primary` / `.t-btn-secondary` / `.text-themed-*` / `var(--color-*)`
- 邮件模板（React Email）的色值同样来自 tokens：`--color-accent` / `--color-text-primary` / `--color-border-subtle`，通过 inline style 注入 HTML（邮件客户端不支持 CSS 变量，需要在模板里把 tokens 值拷成 hex 静态常量并**集中导出**到 `src/emails/tokens.ts`，源头仍是 DESIGN_TOKENS）

## 工程契约（⚠️ 不遵守会编译失败或导致样式失效）

- **文件扩展名即语法契约**：本项目前端是 **JSX + JSDoc**，不是 TypeScript。`.jsx` 文件内**禁止** `type Xxx = ...` / 泛型 `useForm<Foo>()` / 参数注解 `(data: FormData) =>`。需要类型提示时用 JSDoc 注释。新增 TypeScript 文件（`.ts` / `.tsx`）前先确认 `tsconfig.json` 和 Vite TS 插件已就位，否则直接写 `.jsx`。
- **新依赖 = 同一个 commit 里三件事**：(1) `npm install --save <pkg>` 让 package.json / package-lock.json 落盘 (2) import 到源码 (3) 如引入新生态（如 Radix / Framer Motion）在 `CLAUDE.md` 依赖规则小节里确认映射已存在。**不允许**只 import 不装包。
- **class 名必须可溯源**：写 `className="xxx"` 前，先 `grep -rn "xxx" frontend/src/index.css frontend/tailwind.config.js`。如果该 class 既不是 Tailwind 内置工具类，也不在 `index.css` / `tailwind.config.js` 里定义，说明是**幻觉 class**。此时改用 `style={{ accentColor: 'var(--color-accent)' }}` 这类 inline + CSS 变量写法，不要臆造 `accent-themed-xxx` / `t-yyy` 这类看起来像的类名。

## 任务

### 0. UI 国际化基础设施 (PRD 4.10.4 / 4.10.4a) ⭐

- 安装并配置 `next-intl` (Next.js App Router 原生支持)
- 目录结构 (⚠️ 必须覆盖 §4.10.4a 列出的全部命名空间):
  ```
  messages/
    ├── zh-CN/
    │   ├── common.json     # 导航/按钮/通用文案 (含 lang.switch_to_*, nav.*)
    │   ├── auth.json       # 注册/登录/找回密码
    │   ├── onboarding.json # 行业选择/探索视图
    │   ├── dashboard.json  # Dashboard 文案 (含 dashboard.alerts.*, dashboard.kpi.*)
    │   ├── settings.json   # settings.{account,api_keys,mcp,notifications}.* (PRD 4.10.4a.B)
    │   ├── project.json    # project_settings.*, project_selector.* (PRD 4.10.4a.B)
    │   ├── brand_meta.json # brand_meta.{positioning,price_range,primary_badge,competitor_badge} (PRD 4.10.4a.C)
    │   ├── alerts.json     # 模板型告警 titleKey 对应文案 (PRD 4.10.4a.A)
    │   ├── user.json       # 用户 profile 兜底文案 (PRD 4.10.4a.B)
    │   └── email.json      # 邮件正文文案 (与模板共用)
    └── en-US/
        └── (同结构)
  ```
- 路由策略: `/[locale]/...` 结构，middleware 识别 locale
- 语言推断: 首次访问根据浏览器 `Accept-Language` 推断，写入 cookie
- 登录后从 `User.locale` 读取偏好，覆盖 cookie
- 用户设置页提供语言切换 (中文 / English)

**🔒 Settings 页 (PRD §4.6.3 / §4.10.4a.B) 必须覆盖项**:
- `SettingsPage`: 所有文案 (Account / API Keys / MCP / Notifications 四个 Card 的标题、字段标签、toggle 描述、按钮文字、占位符) 必须走 `t('settings.*')`
- 注册时间 / API key created_at 必须走 `formatDate()`, 禁止 `toLocaleDateString('zh-CN', ...)` 硬编码 locale
- 用户名/邮箱在接入真实 auth 前读取 `t('user.profile_default_*')` 兜底
- 验收 grep: `grep -rnE '[\u4e00-\u9fff]' frontend/src/pages/SettingsPage.jsx` 期望无匹配

### 0.5 分析基础设施 (PRD §4.11) ⭐ NEW 2026-04-17

**本子任务**在 1/1a/2/2a 之前落地, 因为后续所有任务都会向 Mixpanel 上报事件, 必须先有封装. **不要**把 Mixpanel 直接 import 到页面组件.

**0.5.1 依赖 & 环境变量**

- 安装 `mixpanel-browser` (前端) + `mixpanel` (后端 Node SDK). 按 CLAUDE.md "新依赖 = 同一个 commit 里三件事": package.json 落盘 / 源码 import / CLAUDE.md 依赖规则行.
- 环境变量:
  - `VITE_MIXPANEL_TOKEN` (前端, Vite 暴露): 按 `NODE_ENV` 从 3 个项目 token 选一 (`genpano-dev` / `-staging` / `-prod`)
  - `MIXPANEL_TOKEN_SERVER` (后端): Mixpanel 的 Service Account token, 不等同于前端 token
  - `.env.example` 同步追加

**0.5.2 封装层 `frontend/src/lib/analytics.ts` (或 `.js` + JSDoc, 按 CLAUDE.md 工程契约选)**

- 导出 4 个函数: `track()` / `identify()` / `alias()` / `resetSession()` (签名见 PRD §4.11.1)
- 内部自动注入公共属性 (PRD §4.11.3 的 User/Session/Device/Page 4 类)
- `NODE_ENV=test` 时 `track` 为 no-op
- 每次 `track` 自动拼 `$insert_id = {event_name}|{session_id}|{fingerprint}` 做去重

**0.5.3 事件枚举 `frontend/src/lib/analytics-events.ts`**

- 从 PRD §4.11.4 清单生成 42 个 event name 的 union type / enum
- `EventProps` 按事件名映射各自必填属性, 漏传字段 TypeScript 报错
- 事件名永远 **append-only**; 删除 = breaking, 拒绝合并

**0.5.4 后端 SDK 封装 `backend/src/lib/analytics.ts`**

- 导出 `trackServer(eventName, { distinctId, properties })`
- 仅 3 个事件使用: `user_created` / `report_generation_succeeded` / `alert_email_sent`

**0.5.5 Harness (抄 PRD §4.11.7 4 条 grep)**

- 加到 pre-commit hook + CI
- 4 条均必须通过才能合并

**0.5.6 Mixpanel 项目初始化**

- 登录 Mixpanel, 创建 3 个 project (`genpano-dev/staging/prod`)
- 把 3 个 token 存到 1Password 或 GitHub Secrets (不入库)
- Dev 项目里按 §4.11.6 的 4 条漏斗建板, 作为 "可跑通" 验收

### 1. 用户认证

- 实现邮箱注册 + 登录
- OAuth 登录 (Google) — 如果时间允许，否则标注 TODO
- **找回密码流程**: 输入邮箱 → 发送重置链接 (一次性 token, 24h 有效) → 设置新密码
  - 频率限制: 同一邮箱 60s 内限 1 次
  - 仅邮箱注册用户展示入口，OAuth 用户隐藏
- JWT / Session 管理
- 保护 Dashboard 路由
- **User 模型新增 `locale` 字段** (`zh-CN` | `en-US`)，注册时自动推断，用户可修改

### 1b. AuthPage Email-first 2-step 迁移 (PRD §4.1.1-form) ⭐ NEW 2026-04-19

> **⚠️ 开发者约束 (不作为 UI 文案)**: 本节包含"本页做/不做"式的实现指引, 仅用于指导编码, 严禁被 copy-paste 到 `messages.*.json` 或 JSX 文本节点, 参见 PRD §4.6.0a。

**1b.1 背景**

Frank 从 Landing 进应用时发现原 AuthPage 不是"最新设计": 原实现单表单同时显示邮箱+密码+确认密码, 登录时要求用户预判自己有没有账号。2026-04-19 对齐 Stripe / Linear / Vercel / Claude.ai 的 identifier-first 范式, **邮箱优先 2 步**:

- Step 0: 只输邮箱 + "用邮箱继续" 按钮
- Lookup 中: loading 条 (≥400ms fixed delay anti-enum)
- Step 1 New: "正在为你创建账号" chip + 密码 + 确认密码 + "创建账号"
- Step 1 Existing: "欢迎回来" chip + 密码 + "忘记密码?" link + "登录"
- Step 1 Forgot: 邮箱输入 (已从 Step 0 预填) + "发送重置链接"
- Step 1 Forgot.sent: 已发送提示 + "返回登录" link

**1b.2 URL 路由契约**

- `/login` 和 `/register` **两条路由都保留**, 均 mount `<AuthPage />` (不再按 type prop 分叉)
- 进入 AuthPage 后 Step 切换**不改 URL** (状态内部化), 避免用户 refresh 丢 progress
- Deep link: `/login?email=foo@bar.com` / `/register?email=foo@bar.com` → 进页时 email state 预填, 自动触发 Step 0 → Step 1 过渡
- `returnTo` / `action` / `entry_source` query param 原样透传到 Step 1 登录/注册完成后的重定向

**1b.3 API 契约 (stub 形式先落地)**

`POST /api/auth/lookup`

- Request: `{ email: string }`
- Response (200 fixed): `{ next: 'register' | 'login', hasPassword: boolean }`
  - `next: 'register'` → Step 1 New 分支
  - `next: 'login'` → Step 1 Existing 分支
- Response timing: **固定 ≥ 400ms** (通过 `await sleep(Math.max(400 - elapsed, 0))` 实现); 返回结构两分支**字节数一致** (anti-enum)
- 后端真实实现放 §1. 本 Session 1b 先在前端 mock 一个 hardcoded 列表 (`['demo@genpano.com', 'frank@genpano.com']` 视为已注册), 其他邮箱一律 `next: 'register'`

**1b.4 状态机 (前端实现锚点)**

```
step ∈ { 0_email, 1_new, 1_existing, 1_forgot, 1_forgot_sent, 1_looking_up }
nextAction ∈ { null, 'register', 'login' }
email: string
password: string
passwordConfirm: string
error: string | null
```

转换:
- `0_email` → submit email → `1_looking_up` (fetch POST /api/auth/lookup, timer 400ms)
- `1_looking_up` → lookup done with `next: 'register'` → `1_new`
- `1_looking_up` → lookup done with `next: 'login'` → `1_existing`
- `1_new` / `1_existing` → "换个邮箱" link → `0_email` (email 保留, password 清空)
- `1_existing` → "忘记密码?" link → `1_forgot`
- `1_forgot` → submit → `1_forgot_sent`
- `1_forgot_sent` → "返回登录" link → `1_existing`

**1b.5 i18n keys 必须覆盖 (双语全)**

`frontend/src/i18n/messages/{zh-CN,en-US}/auth.json` 新增 namespace:

- `auth.step0.title` — "用邮箱继续 / Continue with your email"
- `auth.step0.subtitle` — "1 秒识别账号状态, 新用户 / 老用户同入口 / One entry for new and returning users"
- `auth.step0.email_label` / `auth.step0.email_placeholder` / `auth.step0.submit`
- `auth.step0.oauth_google` — "用 Google 账号继续"
- `auth.step0.divider` — "或"
- `auth.step0.looking_up` — "识别中…"
- `auth.step1.new.chip` — "新邮箱 · 正在为你创建账号"
- `auth.step1.new.title` / `auth.step1.new.password_label` / `auth.step1.new.password_confirm_label`
- `auth.step1.new.password_hint` — "至少 8 位, 包含字母和数字"
- `auth.step1.new.submit` — "创建账号"
- `auth.step1.new.switch_email` — "换个邮箱"
- `auth.step1.new.terms_notice` — 继续即同意…  (含 Terms / Privacy 链接)
- `auth.step1.existing.chip` — "欢迎回来"
- `auth.step1.existing.title` / `auth.step1.existing.password_label` / `auth.step1.existing.submit`
- `auth.step1.existing.forgot_link` — "忘记密码?"
- `auth.step1.existing.switch_email` — "换个邮箱"
- `auth.step1.forgot.title` — "重置你的密码"
- `auth.step1.forgot.subtitle` — "我们会把重置链接发到你的邮箱, 24 小时内有效"
- `auth.step1.forgot.submit` — "发送重置链接"
- `auth.step1.forgot.back` — "返回登录"
- `auth.step1.forgot.sent_title` — "已发送"
- `auth.step1.forgot.sent_body` — 已发送…的提示文案 (不暴露账号是否存在, anti-enum)
- `auth.errors.email_invalid` / `auth.errors.password_too_short` / `auth.errors.password_mismatch` / `auth.errors.lookup_failed` / `auth.errors.rate_limited`

**1b.6 Harness grep 规则 (加到 pre-commit + CI, 对应 PRD §4.1.1-form H1-H5)**

```bash
# H1: /api/auth/lookup 必须存在 ≥400ms anti-enum delay
grep -rnE "auth/lookup" backend/src --include='*.ts' \
  | xargs grep -L "sleep\s*\(\s*Math\.max\s*\(\s*400" \
  && echo "❌ H1 fail: lookup handler missing 400ms anti-enum guard" && exit 1

# H2: AuthPage 禁止硬编码中文或英文正文 (必须走 t())
grep -nE '>[^<>{}]*[\u4e00-\u9fff][^<>{}]*<' \
  frontend/src/pages/AuthPage.jsx \
  && echo "❌ H2 fail: hardcoded CJK in AuthPage" && exit 1

# H3: i18n 双语键覆盖, zh-CN 与 en-US 下 auth.step0/step1 键集合必须一致
node scripts/check-i18n-coverage.mjs auth.step0 auth.step1

# H4: AuthPage 禁止直接走 window.location / history.pushState 切 step
# (step 切换不应改 URL)
grep -nE "window\.location|history\.pushState|navigate\(['\"]/(register|login)" \
  frontend/src/pages/AuthPage.jsx \
  | grep -v "navigate(.*returnTo\|entry_source" \
  && echo "❌ H4 fail: AuthPage step transitions must not rewrite URL" && exit 1

# H5: reset password token 必须 24h + 一次性, 消费后立即 DELETE
grep -rnE "password_reset_token|PasswordResetToken" backend/src --include='*.ts' \
  | xargs grep -L "prisma\.passwordResetToken\.delete\|TTL.*86400\|expiresAt.*24" \
  && echo "❌ H5 fail: reset token 24h+one-time invariant missing" && exit 1
```

**1b.7 Analytics 事件 (PRD §4.11.4 S13 新增 #57-#61)**

5 个事件 (按 PRD §4.11 唯一真相源追加, 不在页面里直接 `mixpanel.track`, 一律经 `lib/analytics.ts` 封装):

- `#57 auth_step0_viewed` — `{ entry_source: 'landing' | 'pricing' | 'watch_brand' | 'auth_prompt_modal' | 'quick_create' | 'pdf_upsell', prefilled_email: boolean }`
- `#58 auth_email_submitted` — `{ entry_source, email_domain }` (⚠️ PRD §4.11.5 红线: **只记 domain 不记完整 email**)
- `#59 auth_lookup_resolved` — `{ next: 'register' | 'login', latency_ms }` (latency 分布监控 anti-enum 是否稳定)
- `#60 auth_step1_submitted` — `{ next, entry_source, has_oauth: false }`
- `#61 auth_forgot_requested` — `{ email_domain }`

**1b.8 验收**

- Step 0 → lookup → Step 1 分叉 2 个路径均可走通 (mock lookup)
- lookup 即使瞬间返回, UI 观察到的"识别中…" loading 也 ≥ 400ms
- 已注册 / 未注册两条路径前端过渡动画一致 (DOM diff 不暴露 `next` 值)
- Landing nav 快速入口 / WatchBrandButton / AuthPromptModal / PDF upsell 4 个已知 caller 点击后**均**先进 Step 0, 不绕过
- `grep -rnE '[\u4e00-\u9fff]' frontend/src/pages/AuthPage.jsx` 期望无匹配
- H1-H5 五条 Harness 全绿
- Visual regression: `npm run test:visual -- auth-step0.spec` / `auth-step1-new.spec` / `auth-step1-existing.spec` / `auth-step1-forgot.spec` 4 个快照初始化

### 1a. 事务性邮件系统

参考 PRD 4.1.1a，实现认证流程全部事务性邮件:

**邮件服务搭建**:
- 集成 Resend (npm: resend) 作为邮件发送服务
- 使用 React Email (npm: @react-email/components) 构建邮件模板
- 统一品牌模板: Logo + 品牌色 header → 正文 + CTA 按钮 → footer (联系方式 + 安全提示)

**需实现的邮件** (共 5 封 × 2 语言 = 10 份模板):

| 邮件 | 触发 API | 关键逻辑 |
|------|---------|---------|
| E1 邮箱验证 | POST /api/auth/register | 生成 token → 存 DB (hashed) → 发送验证链接 → 用户点击 → GET /api/auth/verify-email?token=xxx → 激活账户 |
| E2 欢迎邮件 | 邮箱验证通过 / OAuth 首次登录 | 异步发送，含快速开始引导 (选行业→看数据) |
| E3 找回密码 | POST /api/auth/forgot-password | 查邮箱存在 → 生成一次性 token → 发重置链接 → 用户点击 → 前端重置密码页 → POST /api/auth/reset-password |
| E4 密码重置成功 | POST /api/auth/reset-password 成功后 | 确认通知 + "如非本人操作请立即联系" |
| E5 异常登录提醒 | 登录成功但检测到新设备/IP | 记录 user-agent + IP → 与历史比对 → 不匹配则发送提醒 |

**多语言要求** (PRD 4.10.4 / 4.10.5):
- 每封邮件同时维护 `zh-CN` 和 `en-US` 两套文案
- 发送时按 `User.locale` 选模板；注册邮件 (E1) 未登录状态按浏览器 `Accept-Language` 推断
- 邮件正文文案与 UI 共用 `messages/{locale}/email.json`，React Email 模板通过 `next-intl` 或简易 t() 函数读取
- Subject 行同样双语 (例: "验证你的邮箱 / Verify your email")

**安全要点**:
- Token: crypto.randomBytes(32) → SHA-256 hash 后存 DB，原文仅出现在邮件链接中
- 过期: token 24h 过期，使用后立即从 DB 删除
- 频率限制: 用 Redis (或内存 Map) 按 email + type 限流，60s 内同类型限 1 次
- 无论邮箱是否存在，找回密码 API 都返回相同成功响应 (防枚举)

**文件结构**:
```
src/emails/
  ├── components/           # 共享邮件组件 (Header, Footer, Button)
  ├── verify-email.tsx      # E1 (接收 locale prop)
  ├── welcome.tsx           # E2
  ├── reset-password.tsx    # E3
  ├── password-changed.tsx  # E4
  └── login-alert.tsx       # E5
src/lib/
  ├── email.ts              # Resend 客户端 + sendEmail(user, type, data) 按 locale 渲染模板
  └── i18n-email.ts         # 邮件专用翻译加载器
messages/{zh-CN,en-US}/email.json  # 邮件文案
```

### 1c. Auth 端点汇总 (ADAPTER_CONTRACT.md §2.3 + openapi.yaml)

**Auth 端点汇总**：
| Method | Path | 响应 | 说明 |
|---|---|---|---|
| POST | /api/v1/auth/login | 200 + `{ token, user }` | email+password |
| POST | /api/v1/auth/register | 201 + `{ token, user }` | 新建 |
| POST | /api/v1/auth/logout | 204 | 吊销当前 session |
| GET | /api/v1/users/me | 200 + User | 当前用户 |
| DELETE | /api/v1/users/me | 204 | 30 天延迟硬删 + 立即登出 |
| POST | /api/v1/auth/forgot-password | 202 | 邮件链接 |
| POST | /api/v1/auth/reset-password | 204 | 使用 reset token |

### 2. Onboarding 流程 — Data-Before-Auth (PRD 4.1.1b + 4.1.1c + 4.1.2) ⭐

**设计原则 (2026-04-17 重订)**: Data-First 升级为 **Data-Before-Auth**——未登录也能看数据, 注册**不是**入口, 是触发高价值动作时的"解锁". 行业选择**不再是**注册后的必选步骤, 而是通过 URL (`/industries/:id` / `/brands/:id` 直链) 自然体现用户意图. Onboarding 的 3 条入口路径 (Landing 首屏 / 品牌直链 / `/auth` 直达) 与对应行为见 PRD §4.1.1b.

**路径 A (主力, 预期 ≥ 80% 新用户)**:
```
访问 / (landing, 未登录)
  → 首屏展示"今日 AI 热度 Top 4 行业"卡片 (数据预览: 品牌数 + PanoScore Top 3)
  → 点击行业 → /industries/:id (公开, 无拦截)
    - Graph View (D3 力导向图) / List View 切换
    - 用户浏览品类、品牌、产品节点和关系
    - 点击品牌节点 / 行 → /brands/:brandId?from=industry (公开只读, §4.6.1b 状态 C)
  → Brand Detail 未登录状态 (§4.6.1b 状态 C)
    - 顶部浅蓝公共 Banner + 完整数据展示 (平台全量采集)
    - 竞品对比降级为"vs 行业 Top 5"
    - 用户触发 T1 "+ 加入竞品监控" / T2 CSV 导出 / T4 "创建监测项目" / T5 "订阅告警" / T6 "保存筛选"
  → 触发 T1/T2/T4/T5/T6/T8 → <AuthPromptModal> (Radix UI Dialog, 见 PRD §4.1.1c B 段)
    - Modal 带 hookKey + returnTo + action
    - 主 CTA "免费注册 →", 次 CTA "已有账号, 登录"
    - Modal 下方固定 3 条价值点 (auth.prompt.why.*)
  → 注册/登录完成
    - 后端 redirect 到 returnTo (经 allowlist 校验)
    - 前端监听 action query 自动重放动作 (如 action=watch → 自动调加入监控 API)
    - 埋点: user_created + first_binding_action (触发 TTV P50 计算)

**路径 B (品牌直链, SEO/PDF 二维码/分享链接)**:
- 用户从 /brands/:id 直接进入 (未登录) → 同上从 "Brand Detail 未登录状态" 起走

**路径 C (直达 /auth, 老用户 / SEO / magic link)**:
- /auth → 仅收集 邮箱 + 密码 (不再问行业)
- 注册完成 → "你想先看哪个行业?" 引导卡 (可跳过)
  - 选中 → 写 User.defaultIndustryId, 进 /industries/:id
  - 跳过 → 进 /dashboard 空 Project 态, 展示 "先逛逛" CTA 引导到 /industries
```

**行业选择卡片**: 每张卡片展示品牌数量 + PanoScore Top 3，让用户选择前就看到数据价值。**Landing 首屏**和**路径 C 登录后引导卡**复用同一组件, 不要 fork 出两份。

**国际化 (PRD 4.10.4 / 4.10.5)**:
- 行业名、品类名、UI 文案从 `messages/{locale}/onboarding.json` 读取
- 品牌/产品节点名按 `User.locale` 优先显示 `nameZh` 或 `nameEn`，缺失时回退到 `primaryName`
- D3 图谱节点 label、详情面板字段标签、CTA 文字全部走 i18n
- 竞品推荐理由 ("经常一起被提及" / "mentioned together frequently") 双语

**Project 是视角过滤器** (PRD 4.1.2):
- Project 不存储监测数据，只存 primaryBrandId + competitorBrandIds + preferences
- Dashboard 展示 = 平台数据 × Project 过滤
- **一个用户最多可创建 3 个 Project (MVP 限制)**，超出时提示"MVP 限 3 个项目"

**品牌提交流程**:
- 从侧边栏"新建项目"入口创建时，需搜索品牌；若未知品牌 → LLM 自动验证 → 纳入知识图谱
- 品牌入图谱后 → 自动生成 Topic → Pipeline 首次采集 (2-6h)
- 采集完成 → 邮件通知用户 "数据已就绪"
- 该品牌对所有同行业用户可见 (共建效应)

**竞品推荐**:
- 基于知识图谱的 COMPETES_WITH 边推荐品牌竞品，每个推荐带理由标签 ("经常一起被提及"/"同价位竞品"/"行业热门")
- API: GET /api/v1/knowledge-graph/brands/:id/competitors

### 2a. 延迟注册墙触发点矩阵 & TTV 埋点 (PRD §4.1.1c) ⭐ NEW 2026-04-17

**本任务目的**: 把 PRD §4.1.1c 表格里的 8 个触发点 (T1-T8) 实装, 并埋好 4 类 TTV 事件使 §4.1.1 KPI 能从 D+1 起稳定测量.

**2a.1 `<AuthPromptModal>` 组件**

- 位置: `frontend/src/components/AuthPromptModal.jsx` (新建)
- 依赖: **必须**用 Radix UI Dialog (`@radix-ui/react-dialog`) — 见 CLAUDE.md "依赖规则"中 Modal/Dialog 行; 禁止手写 modal / 焦点陷阱 / ESC 处理
- Props (JSDoc):
  ```
  /**
   * @param {object} props
   * @param {'watch_brand'|'export_csv'|'create_project'|'subscribe_alerts'|'save_preferences'|'mcp_apikey'} props.hookKey
   * @param {string} props.returnTo   - 必须为 genpano.com 内部绝对路径 (经 isInternalPath() 校验)
   * @param {string} props.action      - 用于前端注册成功后自动重放动作
   * @param {() => void} props.onClose
   */
  ```
- 结构参照 PRD §4.1.1c B 段 ASCII 图; 文案全部走 i18n key, 不硬编码
- 次 CTA "已有账号, 登录" → 切换到 `<AuthPage mode="login">` 并透传 returnTo/action

**2a.2 i18n 新增 key (messages/{zh-CN,en-US}/auth.json)**

每个触发点追加 `title` + `body` 两条:
```json
{
  "hook": {
    "watch_brand":     { "title": "免费注册后可持续监控 {brandName}", "body": "..." },
    "export_csv":      { "title": "免费注册即可导出 CSV",            "body": "..." },
    "create_project":  { "title": "免费注册开始建立你的监测项目",     "body": "..." },
    "subscribe_alerts":{ "title": "免费注册订阅此品牌告警邮件",       "body": "..." },
    "save_preferences":{ "title": "免费注册保存你的筛选偏好",         "body": "..." },
    "mcp_apikey":      { "title": "免费注册获取 MCP API Key",        "body": "..." }
  },
  "prompt": {
    "why_register": "注册后你将获得:",
    "why": {
      "daily_update":  "每日自动追踪, 数据即时更新",
      "free_mvp":      "MVP 阶段全功能免费",
      "agent_ready":   "支持 MCP, Agent 可直接消费你的数据"
    }
  }
}
```
en-US 同结构, 翻译文案见 PRD §4.1.1c B 段. `{brandName}` 经 `formatBrand()` 按 locale 渲染.

**2a.3 触发点接入 (按 PRD §4.1.1c A 段表格顺序)**

| ID | 接入位置 (文件) | 替换原有逻辑 |
|----|---------------|-------------|
| T1 | `WatchBrandButton.jsx` (已存在, §4.1.2a 状态 #6) | 状态 #6 "未登录" 的 onClick 从跳 `/auth` 改为弹 `<AuthPromptModal hookKey="watch_brand">` |
| T2 | `ExportCsvButton.jsx` (§4.6.4 已有引用) | 未登录分支改为弹 Modal (不变行为, 只是替换组件) |
| T3 | `ShareReportButton.jsx` | **不拦截**; 公开分享页 `/reports/public/:token` 不登记触发点, 仅页脚注册 CTA 条 |
| T4 | 品牌详情 & Industry 的 "创建监测项目" CTA | 同上 Modal |
| T5 | 品牌详情诊断 Tab "订阅此品牌告警邮件" 按钮 | 同上 Modal |
| T6 | Toolbar 的 "保存当前筛选为默认" 按钮 | 同上 Modal |
| T7 | 行业探索视图筛选器 | **不拦截**; 实现 `useGuestPreferences()` hook, 写 `localStorage.genpanoGuest.*`, 注册时后端同步 |
| T8 | "在 MCP 中查询此品牌" 按钮 | 同上 Modal |

**2a.4 return_to allowlist 工具**

- 新建 `frontend/src/lib/safeReturnTo.js`:
  ```
  // 只允许 genpano.com 内部绝对路径 (/... 开头, 不含协议, 不含 //)
  export function isInternalPath(path) { ... }
  export function sanitizeReturnTo(raw) { ... } // 失败返回 '/'
  ```
- 后端 `/api/v1/auth/login` / `/register` / OAuth 回调 3 个端点在 302 redirect 前必须过 `sanitizeReturnTo`
- 测试: `' javascript:alert(1)'` / `//evil.com` / `https://evil.com/a` 三条 case 必须返回 `/`

**2a.5 action 重放器**

- 新建 `frontend/src/lib/replayAuthAction.js`:
  ```
  // 登录成功后在 Dashboard 首次渲染时调用, 读 URL ?action=... 并派发对应 API
  export async function replayAuthAction(search) {
    const params = new URLSearchParams(search);
    const action = params.get('action');
    switch (action) {
      case 'watch':           await api.watchBrand({ brandId: params.get('brandId') }); break;
      case 'export_csv':      await triggerExport({ exportType: params.get('exportType'), ... }); break;
      case 'create_project':  router.push(`/projects/new?primaryBrandId=${params.get('primaryBrandId')}`); break;
      case 'subscribe':       await api.subscribeAlerts({ brandId: params.get('brandId') }); break;
      case 'save_filter':     await api.saveFilter({ ... }); break;
      default:                /* no-op */
    }
  }
  ```

**2a.6 TTV 事件埋点 (Mixpanel, 见 PRD §4.11)**

本子任务**依赖**任务 0.5 (见下方新增) 先把 Mixpanel 基础设施搭好; 本步只落 4 个 TTV 相关事件:

| 事件 | PRD §4.11 编号 | 上报位置 |
|------|----------------|---------|
| `session_first_event` | #1 | `frontend/src/App.jsx` mount 时, 判断 `gpSessionId` cookie 是否刚生成 |
| `auth_prompt_shown` | #2 | `<AuthPromptModal>` mount effect, 属性 `{ hook_key, return_to, action }` |
| `user_created` | #4 | **后端** `/api/v1/auth/register` / OAuth callback 成功分支, Node SDK 上报 |
| `first_binding_action` | #41 | 一个 `useFirstBindingOnce()` hook 监听 T1/T2/T4/T5 的 success mutation, session 内只发一次; 属性 `{ binding_action, minutes_since_first_event }` |

**严禁**:
- 在业务代码里 `import mixpanel from 'mixpanel-browser'` — 必须走 `frontend/src/lib/analytics.ts` 封装
- 在事件属性里写邮箱/手机号/token/公司名等 PII (PRD §4.11.5 红线)
- 手动传 `session_id` / `user_id` / `page_path` 等公共属性 (封装自动注入, 见 PRD §4.11.3)

**2a.7 Harness 拦截 (pre-commit + CI, 抄 PRD §4.1.1c E 段 3 条 grep)**

- 三条 grep 加到 `.claude/hooks/pre-commit-guard.sh` (若已存在) 或 `package.json` lint 脚本
- GitHub Actions 对应加 step, fail build on any match

### 2b. 零 Project 态引导 & 专家快路径 (PRD §4.1.1d) ⭐ NEW 2026-04-17

> **动机**: 现 frontend 硬编码 `PROJECTS[0]` (`DashboardLayout.jsx:112` / `BrandsPage.jsx:28` / `ProjectContext.jsx:48`), 零项目路径未走通, 用户注册后无"下一步"引导. 本任务落地 PRD §4.1.1d 的四个引导位 E1-E4 + T9 触发点, 解决 Frank 2026-04-17 反馈的三类痛点:
> - Pain A (新手不知能建项目) → E1 + E2
> - Pain B (专家想快建) → E3 + T9 
> - Pain C (登录后没归宿) → E1

**2b.1 `<DashboardEmptyState>` 组件 (E1)**

- 位置: `frontend/src/components/empty/DashboardEmptyState.jsx` (新建)
- 结构严格按 PRD §4.1.1d B 段 ASCII 实现: title / subtitle / 主次 CTA / 分隔线 / preview.title / 3 灰色预览卡
- 预览卡用 `<div className="bg-gray-100 rounded-lg h-32 flex items-center justify-center">` + 标签 label, **禁止** import Recharts / 任何 mock 数据生成器 (避免"已有数据只是空"的误导)
- 主 CTA onClick: `navigate('/projects/new?source=empty_state_dashboard')` + track `project_creation_entry_clicked` (`entry_source=empty_state_dashboard`) + track `dashboard_empty_state_cta_clicked` (`cta=primary`)
- 次 CTA onClick: `navigate('/industries')` + track `dashboard_empty_state_cta_clicked` (`cta=secondary`)
- Mount effect 触发 `dashboard_empty_state_shown` (`surface=dashboard_empty`, `has_explored_industry`, `default_industry_id`)

**2b.2 DashboardPage.jsx 早退逻辑 + 硬编码清理**

- `DashboardPage.jsx` 顶部加:
  ```jsx
  const { projects } = useProject();
  if (projects.length === 0) return <DashboardEmptyState />;
  ```
- 位置: 所有 `useXxx()` hook 调用后、JSX 渲染前 (遵循 rules-of-hooks)
- 同步清理:
  - `DashboardLayout.jsx:112` `useState(PROJECTS[0]?.id)` → `useState(null)` 由 `projects[0]?.id` 派生当 `projects.length > 0`
  - `BrandsPage.jsx:28` `const activeProject = PROJECTS[0]` → `const { activeProject } = useProject()` (走 Context)
  - `ProjectContext.jsx:48` `useState(() => SEED_PROJECTS[0]?.id)` → `useState(() => SEED_PROJECTS.length > 0 ? SEED_PROJECTS[0].id : null)`
- **验证**: PRD §4.1.1d.E Harness grep #5 对 `PROJECTS[0]` / `projects[0]` 在这三处应 exit 0

**2b.3 ProjectSelector 零 Project 态变形 (E2)**

- 修改 `frontend/src/components/ProjectSelector.jsx` (已存在, **不新建 V2**, 记忆: "GENPANO UI Sessions anchored, never rebuilt")
- 顶部加分支:
  ```jsx
  if (projects.length === 0) {
    return (
      <button
        onClick={() => {
          track('project_creation_entry_clicked', { entry_source: 'empty_state_sidebar', is_authenticated: true });
          navigate('/projects/new?source=empty_state_sidebar');
        }}
        className="w-full flex flex-col items-start gap-1 px-3 py-3 rounded-lg"
        style={{ backgroundColor: 'var(--color-accent)', color: 'var(--color-text-on-accent)' }}
      >
        <span className="font-medium text-sm">{t('sidebar.empty.cta')}</span>
        <span className="text-xs opacity-80">{t('sidebar.empty.hint')}</span>
      </button>
    );
  }
  ```
- **严禁**: 零 Project 态沿用 Active 态的 "Select Industry" / "Select Brand" label (line 74 / 85). 必须由 `projects.length === 0` 分支完整替代
- Mount 时若零 Project 额外发 `dashboard_empty_state_shown` (`surface=sidebar_empty`)
- **验证**: PRD §4.1.1d.E Harness grep #1 对 `"Select (Industry|Brand|Project)"` 在 ProjectSelector.jsx 应 exit 0

**2b.4 `<LandingNavQuickCreateButton>` 组件 (E3, Pain B 主解法)**

- 位置: `frontend/src/components/nav/LandingNavQuickCreateButton.jsx` (新建)
- 三态切换逻辑:
  ```jsx
  const { isAuthenticated } = useAuth();
  const { projects } = useProject();
  const labelKey = !isAuthenticated ? 'nav.quickCreate.label.unauth'
                 : projects.length === 0 ? 'nav.quickCreate.label.zero_project'
                 : 'nav.quickCreate.label.has_project';
  const onClick = () => {
    track('project_creation_entry_clicked', { entry_source: 'landing_nav_quick', is_authenticated: isAuthenticated });
    if (!isAuthenticated) {
      openAuthPromptModal({ hookKey: 'auth.hook.quick_create_project', returnTo: '/projects/new?source=landing_nav_quick', action: 'create_project' });
    } else if (projects.length === 0) {
      navigate('/projects/new?source=landing_nav_quick');
    } else {
      navigate('/brand/overview');
    }
  };
  ```
- 挂载到 Landing page 顶部 nav: `frontend/src/pages/LandingPage.jsx` (若已存在) 或 `<PublicLayout>` 共享 header
- 视觉: 主色填充, 圆角 8px, 高度 36px, 右对齐

**2b.5 `<ProjectRequiredBanner>` 组件 (E4, Gated Page Banner)**

- 位置: `frontend/src/components/project/ProjectRequiredBanner.jsx` (新建)
- 条件渲染: `isAuthenticated && projects.length === 0 && !sessionStorage.getItem('genpano.projectRequiredBannerDismissed')`
- 挂载到需 Project 的子页顶部: `BrandDetailPage.jsx` (诊断 Tab) / `TopicsPage.jsx`
- 主 CTA `+ 创建项目解锁` onClick: `navigate('/projects/new?primaryBrandId=${brandId}&source=gated_banner')` + track `project_creation_entry_clicked` (`entry_source=gated_banner`)
- `关闭` onClick: `sessionStorage.setItem('genpano.projectRequiredBannerDismissed', '1')` + 隐藏
- 与 §4.6.1b 状态 #5 upsell banner 并存但语义分离 (E4 针对零 Project, #5 针对有 Project 但品牌不在池)

**2b.6 i18n 新 key 清单 (§4.1.1d.E Harness #3 校验)**

- `frontend/src/i18n/messages/{zh-CN,en-US}/dashboard.json` 追加 `empty.*`:
  ```
  "empty": {
    "title": "...",
    "subtitle": "...",
    "cta": { "primary": "...", "secondary": "..." },
    "preview": { "title": "...", "panoScore": "...", "sov": "...", "quadrant": "..." }
  }
  ```
- `.../project.json` 追加 `sidebar.empty.*` + `gatedBanner.*`:
  ```
  "sidebar": { "empty": { "cta": "...", "hint": "..." } },
  "gatedBanner": { "body": "...", "cta": "...", "dismiss": "..." }
  ```
- `.../common.json` 追加 `nav.quickCreate.*`:
  ```
  "nav": {
    "quickCreate": {
      "label": { "unauth": "...", "zero_project": "...", "has_project": "..." }
    }
  }
  ```
- `.../auth.json` 追加 `hook.quick_create_project.*` (T9 的 AuthPromptModal 文案):
  ```
  "hook": {
    "quick_create_project": {
      "title": "...",
      "body": "..."
    }
  }
  ```
- **UI 边界**: 所有文案遵守 PRD §4.6.0a, 严禁 "本页/请去/详情请进入" 开发者约束措辞

**2b.7 埋点接入 (§4.11.4 #44, #45, #46)**

- 3 个新事件加到 `frontend/src/lib/analytics-events.ts` enum
- `entry_source` 6 个枚举值必须在源码里全部出现过 (PRD §4.1.1d.E Harness #4):
  - `empty_state_dashboard` ← DashboardEmptyState 主 CTA
  - `empty_state_sidebar` ← ProjectSelector 零态 CTA
  - `landing_nav_quick` ← LandingNavQuickCreateButton
  - `gated_banner` ← ProjectRequiredBanner
  - `industry_row_cta` ← IndustryPage 行内 "+ 创建监测项目" 按钮 (已存在, 补 track 调用)
  - `brand_detail_cta` ← §4.6.1b 状态 #5 upsell banner (已存在, 补 track 调用)
- `project_created` (事件 #42) 属性追加 `entry_source` 做归因 (后端从前端传入的 source query 继承)

**2b.8 Harness 拦截 (抄 PRD §4.1.1d.E 5 条 grep)**

- 加到 `.claude/hooks/pre-commit-guard.sh` 和 CI step
- 重点验收: grep #5 `PROJECTS[0]` 修完 2b.2 后 exit 0; grep #1 `"Select (Industry|Brand|Project)"` 修完 2b.3 后 exit 0

### 2c. 登出 & 会话管理落地 (PRD §4.1.1e, 2026-04-17 新增)

> **Task 2c 的核心目标**: 补齐 §4.1.1 注册/登录的镜像一侧. 当前 frontend 的 `DashboardLayout.jsx:285-300` 用户头像按钮只跳 `/settings`, SettingsPage Account 卡片里也没有登出按钮——用户一旦登录就出不去. Task 2c 实施 PRD §4.1.1e 全部 A-J 段, 包括 UserMenu / SessionExpiredModal / silent refresh / BroadcastChannel 跨标签同步 / 后端 logout endpoint / i18n / Harness.
>
> **前置**: Task 2a (认证系统 / useAuth hook 基础) + Task 2b (UserMenu 挂载点仍在 DashboardLayout 底部)
>
> **不覆盖范围**: Settings Danger Zone "注销账户" (PIPL 删除权) 单独排到 Phase 2 Session, 本 Task 只占事件号 #48/#49, 不实施.

**2c.1 新增依赖**

- `npm install --save @radix-ui/react-popover` — UserMenu 依赖 Popover (Dialog 已在 Task 2b 装过)
- 确认 Axios (或项目已用的 HTTP 库) 已在 `package.json`; Task 2c 需要加 response interceptor 做 silent refresh
- 检查 `package.json` 里 `@radix-ui/react-dialog` 已存在 (Task 2b 落地时装过), 不重复装

**2c.2 `<UserMenu>` 组件 (L1 主入口, PRD §4.1.1e A/B)**

- 新建 `frontend/src/components/user/UserMenu.jsx` (目录若不存在先建)
- 基于 `@radix-ui/react-popover`, 禁止手写 dropdown
- **挂载点**: 替换 `DashboardLayout.jsx:285-300` 当前整块跳 `/settings` 的头像按钮; 按钮本身保留 (作为 PopoverTrigger), 展开内容按 PRD §4.1.1e B 段 ASCII 结构:
  ```
  [F] Frank (只读行)
      frankwangfj@gmail.com
  ────────────────────────
  ⚙ 个人设置        → /settings
  🌐 EN / 中文      → setLocale()
  ────────────────────────
  ↩ 登出 (危险色)  → logout('manual')
  ```
- **危险色样式**: `color: var(--color-danger)` (若 token 不存在, 先在 `DESIGN_TOKENS.md` / `index.css` 里补 `--color-danger: #DC2626` / dark mode 下对应映射)
- **Props**:
  ```jsx
  <UserMenu
    user={{ name, email, avatarChar }}
    onBeforeLogout={() => hasUnsavedChanges}  // 可选, 返回 true 时 inline 提示
  />
  ```
- **ESC / 点外部关闭**: Radix Popover 默认行为, 不额外写
- **i18n 键位**: 所有文案走 `t('common.userMenu.*')`, 禁止 JSX 硬编码中文

**2c.3 `useAuth()` hook 扩展 + `logout()` 方法 (PRD §4.1.1e C)**

- 位置: `frontend/src/contexts/AuthContext.jsx` (Task 2a 已建); 在 Provider 内 `value` 对象新增 `logout: (trigger) => Promise<void>`
- **实现严格按 PRD §4.1.1e C 段 TypeScript 伪代码**, 顺序不可颠倒:
  1. 先 `analytics.track('user_logged_out', { trigger, session_duration_sec, had_project, locale })`
  2. `await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' })`
  3. `projectCtx.reset()` + `localStorage.removeItem('genpanoUser')` (保留 `genpanoGuest.*`)
  4. `mixpanel.reset()` (⚠️ 必须在 track 之后, 否则 distinct_id 已清)
  5. `logoutChannel.postMessage({ type: 'logout', at: Date.now() })` (跨标签, 见 2c.5)
  6. 跳转:
     - `trigger === 'session_expired'` → `/auth?return_to=${encodeURIComponent(currentPath)}&reason=session_expired`
     - 其他 trigger → `/` (Landing, 非 `/auth`, 对齐 Data-Before-Auth)
- `session_duration_sec` 计算: `AuthContext` 登录成功时记 `session.startedAt = Date.now()`, logout 时取差

**2c.4 `<SessionExpiredModal>` (L3, PRD §4.1.1e A/E)**

- 新建 `frontend/src/components/auth/SessionExpiredModal.jsx`
- 基于 `@radix-ui/react-dialog` (复用 Task 2b `<AuthPromptModal>` 同款)
- **触发**: `AuthContext` 收到 silent refresh 失败信号后, 设 `isSessionExpired = true`, Modal 订阅此状态自动弹
- **结构**:
  - 标题: `t('auth.session.expired.title')` = "会话已过期" / "Your session has expired"
  - 正文: `t('auth.session.expired.body')`
  - 主 CTA: `t('auth.session.expired.cta_primary')` = "重新登录 →" → `logout('session_expired')` (会用 return_to 带回当前 URL)
  - 次 CTA: `t('auth.session.expired.cta_secondary')` = "继续浏览公开数据" → 清本地 auth state 后判断当前 URL 是否是 §4.1.1c C 段的公开路由: 是则留原地, 否则跳 `/`
- **不可关闭**: 该 Modal 没有 × 按钮 (Radix Dialog 的 `onInteractOutside` 和 ESC 都拦截); 会话过期状态下用户必须在"重登"或"离开工作台"之间做选择

**2c.5 跨标签同步 `BroadcastChannel` (PRD §4.1.1e D)**

- 位置: `frontend/src/App.jsx` 顶层建 channel, 或做成 `useLogoutChannel()` hook
- 主方案:
  ```jsx
  const logoutChannel = new BroadcastChannel('genpano-auth');
  // logout() 内部 postMessage
  logoutChannel.postMessage({ type: 'logout', at: Date.now() });
  // 所有标签订阅
  logoutChannel.onmessage = (e) => {
    if (e.data.type === 'logout' && authCtx.isAuthenticated) {
      authCtx.setSessionStale(true);  // 标记, 不立即跳转 (避免打断当前输入)
    }
  };
  ```
- **下一次路由切换时检测**: `App.jsx` 里加 `useEffect` 监听 `location.pathname` 变化; 如 `sessionStale === true` 且新路由属于 §4.1.1c C 段"强制登录"页, 自动跳 `/`
- **fallback (BroadcastChannel 不支持的浏览器)**: 降级用 `window.addEventListener('storage', ...)`; logout 时写 `localStorage.setItem('genpanoSessionRevokedAt', Date.now())`, 其他标签监听此 key 变化做同样处理
- **⚠️ 已登录且零 Project 态**: sessionStale = true 时 §4.1.1d E1 Empty State 不渲染, 优先渲染"会话已过期"Modal (L3 优先级高)

**2c.6 Axios interceptor — silent refresh (PRD §4.1.1e E)**

- 位置: `frontend/src/lib/http.ts` (若不存在新建) — 集中的 Axios instance
- Response interceptor:
  ```typescript
  instance.interceptors.response.use(
    (res) => res,
    async (err) => {
      const original = err.config;
      if (err.response?.status === 401 && err.response.headers['www-authenticate']?.includes('token_expired') && !original._retry) {
        original._retry = true;
        try {
          await instance.post('/api/auth/refresh', {}, { withCredentials: true });
          return instance(original);  // 重试原请求
        } catch (refreshErr) {
          authCtx.setSessionExpired(true);  // 触发 L3
          throw refreshErr;
        }
      }
      throw err;
    }
  );
  ```
- **Token 策略**: access 15min / refresh 30d rotation — 后端侧落地在 2c.9
- **并发保护**: 多个 401 同时触发时只调一次 refresh, 用模块级 `Promise` 缓存 (防"refresh storm")

**2c.7 后端 `POST /api/auth/logout` + `POST /api/auth/refresh` endpoints (PRD §4.1.1e C/E)**

- 位置: `backend/src/routes/auth.ts` (Task 2a 已建 /register /login /forgot-password, 延续同一 router)
- `POST /api/auth/logout`:
  - 吊销当前 refresh token: 写 `refresh_tokens.revoked_at = now()` (Prisma)
  - 清 Set-Cookie 三个 token cookie (HttpOnly, Secure, SameSite=Lax): `access_token` / `refresh_token` / `session_id`
  - 返回 `204 No Content`, **无 body**, **幂等** (token 已过期或 session 不存在也返回 204)
  - 使用 **POST 非 GET** 防 CSRF 预取; 需 Origin 校验
- `POST /api/auth/refresh`:
  - 读 refresh_token cookie → 查 DB → 校验未 revoked 且未过期
  - 校验通过: 生成新 access_token (15min) + 新 refresh_token (30d rotation, 旧 refresh 立即 revoke), 写 Set-Cookie, 返回 204
  - 校验失败: 清所有 auth cookie, 返回 401 `{ error: 'refresh_expired' }` → 前端拦截器走 session_expired 分支
- **数据模型**:
  ```prisma
  model RefreshToken {
    id          String   @id @default(cuid())
    userId      String
    tokenHash   String   @unique  // 不存明文, 存 hash
    issuedAt    DateTime @default(now())
    expiresAt   DateTime
    revokedAt   DateTime?
    replacedBy  String?            // rotation 链
    user        User     @relation(fields: [userId], references: [id])
    @@index([userId, revokedAt])
  }
  ```

**2c.8 `<SettingsPage>` L2 inline 登出链接 (PRD §4.1.1e A)**

- 修改 `frontend/src/pages/SettingsPage.jsx` Account Card 最底部
- 在 "注册时间" 行下方新增分隔线 + inline 链接 (非 Button):
  ```jsx
  <div className="pt-4 border-t border-themed">
    <button
      onClick={() => logout('manual')}
      className="text-sm text-themed-muted hover:text-[var(--color-danger)] transition-colors"
    >
      {t('settings.account.logout.link_text')}
    </button>
    <p className="text-xs text-themed-muted mt-1">
      {t('settings.account.logout.description')}
    </p>
  </div>
  ```
- **禁止**: 用 Radix AlertDialog 做二次确认——登出本身无数据损失, 二次确认是过度防御; 唯一例外是当 `hasUnsavedChanges` 时 inline 提示

**2c.9 i18n 3 新命名空间 (PRD §4.1.1e H)**

- `frontend/src/i18n/messages.js` (或 `messages/{zh-CN,en-US}/*.json` 结构, 沿用 §4.1.1d 落地方式)
- **新增键位**:
  - `common.userMenu.settings`: "个人设置" / "Settings"
  - `common.userMenu.logout`: "登出" / "Log out"
  - `common.userMenu.logout_confirm_unsaved`: "有未保存的修改, 确认登出?" / "You have unsaved changes. Log out anyway?"
  - `auth.session.expired.title`: "会话已过期" / "Your session has expired"
  - `auth.session.expired.body`: "为了保护你的账户安全, 请重新登录后继续" / "For your security, please log in again to continue."
  - `auth.session.expired.cta_primary`: "重新登录 →" / "Log in again →"
  - `auth.session.expired.cta_secondary`: "继续浏览公开数据" / "Continue browsing"
  - `settings.account.logout.link_text`: "登出当前设备" / "Log out of this device"
  - `settings.account.logout.description`: "登出后你可以随时用相同邮箱登录回来" / "You can log back in anytime with the same email"
- **Phase 2 预留 (本 Task 不实施, 但注释标记)**: `settings.dangerZone.*` — 账户注销, 留给 Phase 2 Session

**2c.10 埋点 `user_logged_out` 事件 #47 (PRD §4.1.1e G + §4.11.4 S11)**

- 扩展 `frontend/src/lib/analytics.ts` (或 Task 2b 已建的 `analytics-events.ts` enum)
- 新增 event 常量:
  ```typescript
  export const EV_USER_LOGGED_OUT = 'user_logged_out';
  ```
- 上报位置**唯一**: `useAuth().logout()` 内第 1 步 (mixpanel.reset 之前)
- 属性结构严格按 PRD §4.11.4 S11 行 47: `trigger` / `session_duration_sec` / `had_project` / `locale`
- Mixpanel event catalog 部署 (S4a Task 7 批次) 一并上 #47

**2c.11 Harness 拦截 (抄 PRD §4.1.1e I 的 4 条 + Phase 2 预留第 5 条)**

- 加到 `.claude/hooks/pre-commit-guard.sh` 和 CI
- **#1 禁止硬跳 `/auth` 丢失 return_to**:
  ```bash
  grep -rnE "(window\.location|location\.href|navigate)\s*=?\(?\s*['\"]/auth['\"]" frontend/src \
    --include='*.jsx' --include='*.tsx' | \
    grep -vE 'return_to|source=|reason=session_expired'
  ```
- **#2 `mixpanel.reset()` 前必须有 `user_logged_out` track**: 按 PRD §4.1.1e I 的 awk 逻辑
- **#3 BroadcastChannel / storage event 二选一必须存在**: `grep -rnE "new BroadcastChannel\(['\"]genpano-auth['\"]\)|genpanoSessionRevokedAt" frontend/src | wc -l` ≥ 1
- **#4 登出文案走 i18n 不硬编码**: `grep -rnE '>[^<]*(登出|Log out|Logout|Sign out)[^<]*<' frontend/src` 排除 `t(['"]common\.userMenu\.logout|t(['"]auth\.session` 后应无输出
- **#5 typed-confirm (Phase 2 占位)**: 源码注释说明"Phase 2 Settings Danger Zone Session 实施时启用", MVP 阶段本 grep 不执行

**2c.12 Phase Gate 4a 人类 Review 追加 (PRD §4.1.1e + Phase Gate 既有)**

在 Phase Gate 4a 的 "人类 Review 检查点" 追加三条:
- □ 点击侧栏用户头像 → Popover 展开, 显示三项 (个人设置 / 语言切换 / 登出), 登出是危险色
- □ 登出后跳 `/` (Landing) 不是 `/auth`; 跳回后公开数据仍可浏览
- □ 开两个标签, 一个登出, 另一个切换路由时自动跳回 `/`

---

### 3. 测试

- 认证全流程: 注册 → 邮箱验证 → 登录 → 找回密码 → 重置密码
- 邮件发送: mock Resend 验证 5 封邮件 × 2 语言 = 10 份模板渲染正确 (zh-CN / en-US)
- Onboarding: 选行业→探索视图→创建项目 全流程
- Project CRUD + 数量限制
- 品牌提交流程
- **国际化**:
  - 未登录访问 `/zh-CN/...` 与 `/en-US/...` 渲染对应语言
  - 登录后切换 `User.locale`，所有页面重定向到对应 locale 路径
  - 品牌节点根据 locale 切换 `nameZh` / `nameEn` 显示
  - 注册邮件 (E1) 按浏览器 `Accept-Language` 发送对应语言

执行完成后更新 CLAUDE.md。
```

### 预期产出
- 用户认证系统 (注册/登录/找回密码/JWT，User 模型含 `locale` 字段)
- 事务性邮件系统 (5 封邮件 × 2 语言 = 10 份模板 + Resend 集成，按 `User.locale` 自动选模板)
- 单路径 Onboarding 流程 (选行业→探索视图，含 D3 知识图谱)
- Project CRUD (含数量限制)
- 品牌提交流程
- **next-intl i18n 基础设施** (`/[locale]/` 路由、`messages/{zh-CN,en-US}/*.json` 文案库、语言切换器)
- 测试用例 (含 i18n 场景)

### 验收标准
- [ ] 用户可以注册 → 收到验证邮件 → 验证 → 登录
- [ ] 找回密码: 输入邮箱 → 收到重置链接 → 设置新密码 → 可用新密码登录
- [ ] 事务性邮件: E1 邮箱验证 / E2 欢迎邮件 / E3 找回密码 / E4 重置成功 / E5 异常登录 均可正常发送
- [ ] 邮件安全: token 一次性使用后失效，过期 token 无法重置密码，频率限制生效
- [ ] Onboarding 单路径: 选行业 (带数据预览卡片) → 直接进入行业探索视图 (D3 图谱 + 列表)
- [ ] 行业选择卡片: 展示品牌数量 + PanoScore Top 3，点击后零延迟进入探索视图
- [ ] 品牌详情面板: 点击品牌节点/行弹出详情 (PanoScore/趋势/竞品)，底部 CTA "创建监测项目" 告知用户能得到什么
- [ ] Project 创建 1 步完成: 从品牌详情进入 → 确认竞品 (带推荐理由) → 完成，报告偏好用默认值
- [ ] Dashboard 首屏呼应: 创建 Project 后首屏展示品牌 vs 竞品对比 + 数据快照
- [ ] 品牌提交: 输入未知品牌 → 自动验证 → 纳入知识图谱 → Project 标记"数据准备中"
- [ ] **Project 数量限制: 用户创建第 4 个 Project 时被拒绝并提示"MVP 限 3 个项目"**
- [ ] 未登录用户访问 Dashboard 路由被重定向到登录页
- [ ] **延迟注册墙 - 未登录公开页 (PRD §4.1.1c C 段)**: `/`, `/industries/:id`, `/brands/:id`, `/brands/:id/products/:productId`, `/reports/public/:shareToken` 5 条路由未登录可访问, 不被 redirect
- [ ] **延迟注册墙 - 注册表单瘦身 (PRD §4.1.1)**: Register mode 只收集 邮箱 + 密码 两个字段; 不再出现"选行业"步骤 (行业引导改由登录后首屏卡承载, 且**可跳过**)
- [ ] **延迟注册墙 - 触发点矩阵 (PRD §4.1.1c A 段)**: T1/T2/T4/T5/T6/T8 未登录点击弹 `<AuthPromptModal>` (Radix UI Dialog); T3/T7 不拦截
- [ ] **延迟注册墙 - return_to 安全**: `sanitizeReturnTo('javascript:...')`、`'//evil.com'`、`'https://evil.com'` 三条 case 均回退 `/`; 正常 `/brands/xyz?a=b` 路径原样返回
- [ ] **延迟注册墙 - action 重放**: 在 Modal 里走完注册, 登录成功后自动执行原动作 (如 action=watch → 自动加入监控, 无需用户再点一次)
- [ ] **延迟注册墙 - T7 localStorage**: 未登录切换行业/画像/时间写入 `localStorage.genpanoGuest.*`; 注册成功后后端合并到 `User.preferences` (以用户侧新值优先, 避免覆盖老用户偏好)
- [ ] **TTV 埋点 (PRD §4.1.1c D 段)**: 4 类事件均落 `events` 表; 可用示例 SQL 查出 P50 数值 (即使 D1 样本少, 查询本身必须 run 通)
- [ ] **Harness 拦截 (PRD §4.1.1c E 段)**: 3 条 grep 在 CI 上均 exit 0 (无泄漏)
- [ ] **零 Project 引导 - E1 Dashboard Empty (PRD §4.1.1d A/B)**: 已登录 + `projects.length === 0` 访问 `/dashboard` 渲染 `<DashboardEmptyState>` (非空白页, 非 auto redirect); 主 CTA 跳 `/projects/new` (无 primaryBrandId 预填), 次 CTA 跳 `/industries`; 三张灰色预览卡用占位图 / CSS, 不触发 Recharts 实例化
- [ ] **零 Project 引导 - E2 Sidebar Empty (PRD §4.1.1d A/B)**: `ProjectSelector.jsx` 零 Project 分支渲染 "+ 创建第一个项目" 按钮 + "先探索行业数据" 次链接, **不再沿用** `'Select Industry'` / `'Select Brand'` / `· 主品牌` label (已登录且无 project 时这些文案是误导)
- [ ] **零 Project 引导 - E3 Landing Nav Quick Create (PRD §4.1.1d A/B)**: `<LandingNavQuickCreateButton>` 三态正确: 未登录 → 文案 "创建监测项目" 点击走 T9 `<AuthPromptModal>`; 已登录零 Project → 文案 "创建第一个项目"; 已登录有 Project → 文案 "+ 新项目", 均跳 `/projects/new` (已登录态带 `source=landing_nav_quick`)
- [ ] **零 Project 引导 - E4 Gated Page Banner (PRD §4.1.1d A/B)**: 已登录 + `projects.length === 0` 访问 `/brands/:id?tab=diag` / `/topics` 顶部渲染 `<ProjectRequiredBanner>`, 主 CTA 建项目, 次 CTA "先探索", 关闭按钮写 `sessionStorage.genpanoBannerDismissed` (同 tab 不重复弹, 跨 tab 仍提示)
- [ ] **零 Project 引导 - State Machine (PRD §4.1.1d C)**: 5 条路径 × zero/has project 组合行为与表格一致, 重点: 未登录点击任一零 Project CTA 均落 T9 Modal + `return_to=/projects/new&source=<enum>` + 注册后自动跳 /projects/new; 已登录零 Project 访问 /dashboard 永不白屏
- [ ] **零 Project 引导 - 硬编码清理 (PRD §4.1.1d E #5)**: `grep -rn "PROJECTS\[0\]\|SEED_PROJECTS\[0\]" frontend/src` 在 `DashboardLayout.jsx:112` / `BrandsPage.jsx:28` / `ProjectContext.jsx:48` 修复后 exit 0 (无匹配); 零 Project 态走 Empty State 而非 "默认第一个 Project" fallback
- [ ] **零 Project 引导 - 埋点 (PRD §4.11.4 #44-46)**: 3 新事件 (`dashboard_empty_state_shown` / `dashboard_empty_state_cta_clicked` / `project_creation_entry_clicked`) 接入; `entry_source` 6 个枚举值 (`empty_state_dashboard` / `empty_state_sidebar` / `landing_nav_quick` / `gated_banner` / `industry_row_cta` / `brand_detail_cta`) 在源码里全部出现; `project_created` (#42) 属性含 `entry_source` 做归因
- [ ] **零 Project 引导 - Harness 5 grep (PRD §4.1.1d E)**: (#1) `"Select (Industry|Brand|Project)"` 未出现在 ProjectSelector 零态分支; (#2) DashboardPage 存在 `projects.length === 0` 早返分支; (#3) i18n 键 `dashboard.empty.*` / `project.quick_create_cta` / `auth.hook.quick_create_project.*` 在 zh-CN/en-US 两份文案库齐全; (#4) `entry_source` 6 值 grep 全中; (#5) `PROJECTS[0]` 硬编码全清。CI 上 5 条均 exit 0
- [ ] **项目创建快速路径 (PRD §4.1.2 T9)**: 从 E1/E2/E3/E4 入口进入 /projects/new 时走"双步快路径" (Step 1 选主品牌, Step 2 确认竞品); 从 T4 brand 详情 "创建监测项目" 进入时保持原一步路径 (primaryBrandId 已预填, 仅确认竞品)
- [ ] **登出 - L1 UserMenu (PRD §4.1.1e A/B)**: 侧栏用户头像按钮点击弹 Radix Popover, 展开显示 `[个人设置] [语言切换] [登出]` 三项; [登出] 用危险色 `var(--color-danger)`; ESC / 点击外部关闭 Popover; 文案全部走 `t('common.userMenu.*')`, 无 JSX 硬编码中文
- [ ] **登出 - L2 SettingsPage inline 链接 (PRD §4.1.1e A)**: SettingsPage Account Card 底部新增分隔线 + "登出当前设备" 链接, 文案走 `t('settings.account.logout.*')`; 不用 Modal 二次确认
- [ ] **登出 - L3 SessionExpiredModal (PRD §4.1.1e A/E)**: silent refresh 失败触发 `<SessionExpiredModal>` (Radix Dialog), 无 × 关闭按钮; 主 CTA 跳 `/auth?return_to=${currentPath}&reason=session_expired`; 次 CTA "继续浏览公开数据" 清 auth state 后判断当前路由是否公开 (§4.1.1c C), 是则留原地, 否则跳 `/`
- [ ] **登出 - 动作契约 (PRD §4.1.1e C)**: `useAuth().logout(trigger)` 严格按 6 步顺序执行 (track → POST /logout → reset state → mixpanel.reset → broadcast → navigate); `user_logged_out` 事件在 `mixpanel.reset()` **之前**发送; `trigger === 'manual'` 跳 `/` (Landing), `trigger === 'session_expired'` 跳 `/auth?return_to=...`
- [ ] **登出 - 跨标签同步 (PRD §4.1.1e D)**: `BroadcastChannel('genpano-auth')` 建立; 任一标签登出后其他标签 `sessionStale = true`; 其他标签下一次路由切换时, 若目标是强制登录页 (§4.1.1c C "❌ 强制登录" 行)自动跳 `/`; BroadcastChannel 不可用时降级 `storage` event 监听 `genpanoSessionRevokedAt`
- [ ] **登出 - silent refresh (PRD §4.1.1e E)**: Axios response interceptor 拦截 401 `token_expired`; 并发 401 只触发一次 refresh (Promise 缓存防 refresh storm); refresh 成功后自动重试原请求用户无感知; refresh 失败触发 L3 Modal
- [ ] **登出 - 后端 endpoints (PRD §4.1.1e C/E)**: `POST /api/auth/logout` 返回 204 幂等 (即使 token 已过期或无 session); `POST /api/auth/refresh` 成功时轮换 refresh token (旧 refresh 立即 revoke, 写 `replacedBy` 链); `RefreshToken` 表只存 `tokenHash` 不存明文
- [ ] **登出 - 埋点 #47 (PRD §4.11.4 S11 + §4.1.1e G)**: `user_logged_out` 事件接入, 属性含 `trigger` / `session_duration_sec` / `had_project` / `locale`; Mixpanel 后台看到 47 个事件; `trigger` 3 个枚举值在源码全部出现
- [ ] **登出 - i18n 3 新命名空间 (PRD §4.1.1e H)**: `common.userMenu.*` / `auth.session.*` / `settings.account.logout.*` 在 zh-CN/en-US 两份文案库键完全对齐; Phase 2 `settings.dangerZone.*` 仅标注 TODO 不实施
- [ ] **登出 - Harness 4 grep (PRD §4.1.1e I)**: (#1) `/auth` 硬跳无 return_to 无输出; (#2) `mixpanel.reset()` 前有 `user_logged_out` track 无输出 = 次序正确; (#3) BroadcastChannel 或 storage event 二选一存在 (grep ≥ 1); (#4) JSX 中"登出"/"Log out" 文案未走 i18n 无输出. CI 上 4 条均 exit 0
- [ ] **登出 - Danger Zone 未实施占位 (PRD §4.1.1e F, Phase 2)**: 源码含注释 `// TODO Phase 2 Session: Settings Danger Zone 账户注销`; 事件 #48/#49 在 Mixpanel event catalog 不落地, PRD §4.11.4 Phase 2 事件列表里标注占位
- [ ] **i18n - UI**: 访问 `/zh-CN/*` 渲染中文，`/en-US/*` 渲染英文；中间件按 `Accept-Language` 自动推断
- [ ] **i18n - User 偏好**: User 模型有 `locale` 字段，用户可在设置页切换，切换后所有页面对应更新
- [ ] **i18n - 邮件**: 10 份邮件模板 (5 × 2) 渲染正确；发送时按 `User.locale` 选模板，未登录邮件按浏览器语言推断
- [ ] **i18n - 品牌名**: 图谱/列表/详情面板中品牌名按 `User.locale` 显示 `nameZh` 或 `nameEn`, 统一走 `formatBrand()` (PRD §4.10.4a.C), 禁止直接读 `brand.name`
- [ ] **i18n - 设置页 (PRD §4.10.4a.B)**: SettingsPage 所有文案经 `t('settings.*')`; `settings.{account,api_keys,mcp,notifications}.*` 命名空间在 zh-CN/en-US 两份文案库中键完全对齐; 切换 locale 整页实时生效
- [ ] **i18n - 日期 (PRD §4.10.4a.B)**: 注册时间、API key created_at 经 `formatDate()`, 不使用 `toLocaleDateString('zh-CN'/...)` 硬编码
- [ ] **i18n - CJK grep**: `grep -rnE '[\u4e00-\u9fff]' frontend/src/pages/{SettingsPage,AuthPage,IndustryPage}.jsx` 无匹配 (mock.js 结构化 `nameZh` 字段除外)

---

> **⚠️ PHASE GATE 4a: 人类 Review 检查点**
> - □ 注册→登录→选行业→探索视图 全流程体验顺畅？
> - □ 行业卡片的数据预览是否激发用户好奇心？
> - □ D3 知识图谱交互是否直观？
> - □ 品牌详情面板 → 创建项目的转化路径是否自然？
> - □ **零 Project 态 (刚注册 / 跳过行业选择 / 主动删除所有 Project) 访问 /dashboard 不会看到空白页或误导文案 (§4.1.1d E1)**
> - □ **侧栏 ProjectSelector 零态不再显示 "Select Industry · 主品牌" 这类迷惑 label (§4.1.1d E2)**
> - □ **Landing 顶栏 "+ 创建监测项目" 按钮在未登录 / 零 Project / 有 Project 三态下文案都合理 (§4.1.1d E3)**
> - □ **点击侧栏用户头像 → Popover 展开显示三项 (个人设置 / 语言切换 / 登出), 登出是危险色 (§4.1.1e L1)**
> - □ **登出后跳 `/` (Landing) 不是 `/auth`; 跳回后公开数据仍可浏览 (§4.1.1e C 契约)**
> - □ **开两个标签, 一个登出, 另一个切换路由时自动跳回 `/` (§4.1.1e D 跨标签同步)**
> - □ "这像一个我会用的产品入口吗?"
> - ⏱ ~30min

---

## Session 4b: Dashboard & 报告 & 咨询转化 (原 Session 4 下半)

### 前置依赖
- Session 4a 完成，用户认证 + Onboarding 可用
- Session 3 完成，API 全部可用

### Prompt

```
继续 GENPANO 项目开发。

开工前必读: 本文档顶部 "通用 Session Preamble (App Session 通用)" 段 (P.1-P.6) + `docs/ADMIN_CLAUDE_CODE_SESSIONS.md` 第 0 节 9 条公约 (line 55 起). 两者均为全 App Session 通用, 本 Prompt 不复写其内容, 以原文为准.

然后阅读 CLAUDE.md (尤其是 "设计锚点" 一节 + 决策 #15 Report 深化框架 + 决策 #19 Citation 模块 + 决策 #20 V2 分析页视觉统一 + DESIGN_TOKENS.md C1-C15 契约), 再阅读 PRD.md 的 4.6 节 (含 §4.6-IA-v2 Brand/Industry Mode) + 4.7 节 (报告系统) + 4.8 节 (GEO 优化诊断建议) + 4.9 节 (商业化转化).

本 Session 目标：构建完整的 Dashboard 页面、报告生成系统、线索收集与管理功能。

## 结构参照（⚠️ 开始写任何 UI 前必读）

本 Session 不重建 UI。大部分 UI 骨架已在 `frontend/`，本 Session 的核心工作是**把 mock 数据换成真实 API、把 URL 状态接进 React Query、把交互接进真实数据刷新**。布局 / 交互模式 / 视觉语言全部保留。

| 现有锚点文件 | PRD 节 | 保留什么 | Session 4b 要接什么 |
|---------|---------|---------|---------|
| `frontend/src/pages/DashboardPage.jsx` | 4.6.1a (面板) | EngineFilterBar / 顶栏筛选 / URL 持久化骨架可留用 | **按新 4 区块重构**: 顶栏 + **5 KPI 卡 (提及率/SoV/情感/引用份额/行业排名)** + 竞争视图 (SoV 饼图 + 竞品四象限) + 趋势 (PANO 对比 + KPI sparkline 汇总) + 告警条。**删除** PANO hero + 4 MetricHeadline + 4 Breakdown Tab 结构。⚠️ 2026-04-16 Frank 纠偏: 原 4 KPI 混淆了"提及率"(穿透率) 与 "SoV"(相对份额), 必须独立渲染, 数据源禁止串用 (见 PRD §4.6.1a "口径边界"表) |
| `frontend/src/pages/BrandsPage.jsx` | 4.6.1b (品牌列表 + 详情) | 品牌列表骨架 | 列表 → `/brands/:id` 详情; 详情页按 4 子 Tab 重构: 概览 / 诊断 / 产品 / 引擎对比 |
| `frontend/src/pages/ProductsPage.jsx` | 4.6.1d | — | **删除顶级 ProductsPage**, 改为 `/brands/:brandId/products/:productId` 独立详情 (SSR 友好); 品牌详情页 "产品" Tab 内复用 BCG 矩阵组件 |
| `frontend/src/pages/TopicsPage.jsx` | 4.2.5 | 4 层 drilldown（TopicsView / PromptsView / QueriesView / ResponseView）+ 面包屑 + stats cards | 真实 Topic/Prompt/Query/Response API、分页、搜索、intent 过滤 |
| `frontend/src/pages/IndustryPage.jsx` | 4.4 | 行业探索骨架 | 真实行业指标数据 |
| `frontend/src/pages/DiagnosticsPage.jsx` | 4.8 | 诊断卡片列表骨架 | 真实诊断 API + 咨询 CTA 接线索表单 |
| `frontend/src/pages/ReportsPage.jsx` | 4.7 | 报告列表 + 详情骨架 | 报告生成 Pipeline API、Markdown 渲染 |

**⚠️ 结构重大变更 (相对此前版本 PRD 4.6.1)**:
- 面板已不再是 "PANO hero + 4 MetricHeadline + 4 Breakdown Tab"。新面板是 **市场宏观视角**, 不承担单品牌 Breakdown (那搬到了品牌详情页的 4 子 Tab)。
- **顶层侧栏分析组从 4 项减为 3 项**: `面板 / 品牌 / Topics` (删除 "产品" 顶层项)。产品从侧栏移除, 变成品牌详情页子 Tab + 独立 URL (`/brands/:brandId/products/:productId`)。
- **`DashboardLayout.jsx` 改造**: 删掉 `navGroups[0].items` 中 `{ label: '产品', path: '/products' }` 这一项; 同步更新 `PAGE_TITLES` 去掉 `/products` 条目, 新增 `/brands/:brandId` 和 `/brands/:brandId/products/:productId` 的动态标题处理 (标题从实时数据取: `品牌: {brandName}` / `产品: {productName} · {brandName}`)。

**开工前 3 步**:
1. `cat frontend/src/pages/DashboardPage.jsx | head -80` 理解当前 state 结构
2. `ls frontend/src/components/` 核对已有 chart / UI 组件
3. 读 `docs/DESIGN_TOKENS.md` 全文

## 组件复用清单（⚠️ 禁止重写）

以下组件已在 `frontend/src/components/` 下存在，必须 import 复用：

- **Score / Metric**: `PanoRing`, `MetricHeadline`
- **Filter / Control**: `EngineFilterBar`（含 URL 持久化逻辑）
- **Charts**: `GlobalTrendChart`, `EngineTrendChart`（含 gradient fills）, `SentimentBar`
- **Base UI**: `Badge`, `Card`, `t-table` 表格类、`t-btn-primary` / `t-btn-secondary` / `t-input`

如果现有组件缺某个 prop（如 `onSegmentClick`、`loading` 状态），**扩展 props**，不要新造 `MetricHeadlineV2` / `PanoRing2`。

## 样式契约

- 所有颜色走 `var(--color-*)` / `.text-themed-*` / `.bg-themed-*` / `.t-*`
- Recharts 的 `stroke` / `fill` / `background` 必须用 `var(--color-chart-*)` / `var(--color-chart-line-grid)` / `var(--color-chart-axis-text)`，禁止写死 `#605BFF` 这类 hex
- Modal backdrop 允许 `rgba(0,0,0,0.4)`（目前无对应 token；如果本 Session 要加弹窗，顺手在 `DESIGN_TOKENS.md` 里补 `--color-scrim`）
- 图标全部 Lucide React
- 报告 Markdown 渲染用 `react-markdown` + `remark-gfm`（别手写 HTML 转换）

## 工程契约（⚠️ 不遵守会编译失败或导致样式失效）

- **文件扩展名即语法契约**：本项目前端是 **JSX + JSDoc**，不是 TypeScript。`.jsx` 文件内**禁止** `type Xxx = ...` / 泛型 `useForm<Foo>()` / 参数注解 `(data: FormData) =>`。需要类型提示时用 JSDoc 注释。新增 TypeScript 文件（`.ts` / `.tsx`）前先确认 `tsconfig.json` 和 Vite TS 插件已就位，否则直接写 `.jsx`。
- **新依赖 = 同一个 commit 里三件事**：(1) `npm install --save <pkg>` 让 package.json / package-lock.json 落盘 (2) import 到源码 (3) 如引入新生态（如 Radix / Framer Motion / TanStack Table）在 `CLAUDE.md` 依赖规则小节里确认映射已存在。**不允许**只 import 不装包——Vite dev server 会立刻报 `Failed to resolve import`。
- **class 名必须可溯源**：写 `className="xxx"` 前，先 `grep -rn "xxx" frontend/src/index.css frontend/tailwind.config.js`。如果该 class 既不是 Tailwind 内置工具类，也不在 `index.css` / `tailwind.config.js` 里定义，说明是**幻觉 class**（PurgeCSS 会直接丢弃，页面上什么样式都不生效）。此时改用 `style={{ accentColor: 'var(--color-accent)' }}` 这类 inline + CSS 变量写法，或先在 `index.css` 里定义一个 `.t-xxx` 组件类，不要臆造 `accent-themed-xxx` 这类看起来像的类名。

## 交付前自检（进入 PHASE GATE 4b 前必须全绿）

```bash
cd frontend
# 1. 无裸 hex（Google 品牌 logo 除外）
grep -rnE '#[0-9a-fA-F]{3,8}\b' src --include='*.jsx' --include='*.tsx' --include='*.css' | grep -v 'EA4335\|4285F4\|FBBC05\|34A853'
# 期望: 只有 index.css 里的 token 定义行

# 2. 无裸 rgba（modal backdrop 除外）
grep -rn 'rgba(' src --include='*.jsx' --include='*.tsx' | grep -v 'backdrop\|scrim\|overlay'
# 期望: 无匹配

# 3. 复用清单里的组件有被 import
grep -rn 'from.*MetricHeadline\|from.*PanoRing\|from.*EngineFilterBar' src/pages
# 期望: Dashboard 页面引用了这些组件，而不是局部自己写

# 4. Recharts color 走 var
grep -rn 'stroke="#\|fill="#' src --include='*.jsx'
# 期望: 无匹配

# 5. .jsx 文件无 TypeScript 语法
grep -rnE '^(type |interface )|: (string|number|boolean|FormData)[,)=]|<[A-Z][A-Za-z]+>\(' src --include='*.jsx'
# 期望: 无匹配（.jsx 不允许 type/interface/泛型/参数注解）

# 6. 所有 import 的包都在 package.json
node -e "const pkg=require('./package.json');const imports=require('child_process').execSync('grep -rhoE \"from [\\\"\\x27][^./][^\\\"\\x27]+[\\\"\\x27]\" src',{encoding:'utf8'}).split('\n').map(l=>l.match(/from [\"']([^\"']+)[\"']/)?.[1]).filter(Boolean);const deps=Object.keys({...pkg.dependencies,...pkg.devDependencies});const missing=[...new Set(imports)].filter(i=>{const root=i.startsWith('@')?i.split('/').slice(0,2).join('/'):i.split('/')[0];return !deps.includes(root)});console.log(missing.length?'MISSING: '+missing.join(', '):'OK')"
# 期望: OK

# 7. 幻觉 class 检测（非 Tailwind 内置 + 非 t-* + 非 themed-*）
# 人眼过一遍 grep -rn 'className=' src/pages | head -50，确认所有自定义 class 都能在 index.css / tailwind.config.js 找到定义
```

## 任务

### 1. Dashboard 页面

参考 PRD 4.6.1 的页面结构，实现以下页面。**视角分工是关键**: 面板 = 市场宏观视角 / 品牌详情 = 单品牌深度 / 产品详情 = 品牌下钻第三层。任何图表只在一处成为"主视图"，避免跨 tab 重复。

**项目列表页**
- 显示用户的所有监测项目
- 每个项目卡片显示核心指标概要 (来自平台数据)
- 创建新项目入口

**面板 `/dashboard`** (PRD 4.6.1a — **新结构，重构 `DashboardPage.jsx`**)

> 宏观市场视角, 永远以"我 (Project.primaryBrandId)"为主。单品牌深度走 `/brands/:id`。

- **顶栏 Toolbar**:
  - 左: `面板 · {primaryBrandName}`
  - 右 (主筛选, 始终可见): 时间范围 (7/30/90天, 默认 30) + `<EngineFilterBar>` 多选引擎 + **`<ProfileGroupFilter>` 用户画像筛选** (单选, 默认 `all` 全量; 列表来自 `GET /api/v1/profile-groups`, 参见 PRD §4.2.3a)
  - **扩展筛选 (折叠/展开, 2026-04-16 新增)**: "更多筛选" 按钮展开第二行, 含 `<DimensionFilter>` 维度筛选 (品类/品牌/产品/竞品, 单选, 默认全部) + `<IntentFilter>` 意图筛选 (informational/commercial/transactional/navigational, 单选, 默认全部); 已有非默认筛选时按钮显示角标 (如 "更多筛选 · 2"); 折叠时 toolbar 右侧展示活跃筛选 tag (如 `维度: 品类 ×`)
  - 状态全部通过 URL 持久化: `?range=30d&engines=chatgpt,doubao&profileGroup=young_female_tier1&dimension=品类&intent=commercial`
  - 选中非默认值时: 所有 KPI / 图表 / 告警条 tooltip 或副标题加对应标签, 点击标签可一键清除回到默认
  - 样本不足保护 (PRD §4.2.3a, §4.6.1a): 后端命中 `{ sufficient: false, sampleCount, fallback: 'use_all' }` 时, 前端展示黄色条提示 "当前筛选组合样本不足 ({n} < 50 Queries), 请扩大时间范围或调整筛选" + 提供"仍然查看部分数据"与"重置筛选"两个动作

- **区块 ⓪ Hero (品牌名 + PANO Score + 行业均值)** (2026-04-16 新增):
  - 面板第一视觉焦点, 用户打开 Dashboard 第一眼看到品牌整体健康度
  - **左侧**: 品牌名称 (大号, `formatBrand(primaryBrand, locale)`) + 英文副标题 + 行业标签 + 行业排名 + 环比变化
  - **右侧**: PANO Score 大号数字 (0-100) + 等级标签 (优秀 90+/良好 80+/中等 70+/及格 60+/需关注 <60) + 行业均值对比条 (两条水平进度条: "行业均值: {avg}" vs "我的品牌: {score}")
  - 数据: `myScore` = Brand PANO Score (V×0.30 + R×0.25 + S×0.20 + C×0.15 + A×0.10); `industryAvg` = 同行业所有品牌 PANO 均值
  - 点击 PANO Score → 跳 `/brands/:primaryBrandId?tab=overview`; 点击排名 → 滚动到区块 ② 竞品四象限
  - 受 Toolbar 筛选联动; 响应式: 桌面左右并列 ~120px, 移动上下堆叠
  - ⚠️ V (Visibility) 子维度使用 non-brand 提及率 (`topic.dimension='品类'`), 详见 PRD §4.4.2

- **区块 ① 五 KPI 核心指标卡** (桌面 5×1, 移动 2×3 或 3×2, 2026-04-16 Frank 纠偏从 4 KPI 恢复提及率):
  | KPI | 定义 | 回答用户问题 | 点击行为 |
  |-----|------|-------------|----------|
  | **提及率 (Mention Rate)** | **默认 non-brand 口径** (2026-04-16): 含主品牌 Response / `topic.dimension='品类'` 的 Query 总数 **(排除 brand Topic, 测真实穿透率)** | "AI 被问品类通用问题时, 有多大比例会主动想到我?" | 跳 `/brands/:primaryBrandId?tab=overview#visibility` |
  | **SoV (Share of Voice)** | 含主品牌 Response / 行业竞争集合至少命中 1 品牌的 Response **(分母已筛选, 相对份额)** | "有品牌出现的讨论里我占几份?" | 跳 `/brands/:primaryBrandId?tab=overview#sov` |
  | **情感得分** | 相关回答 sentiment 加权均值 | "AI 讲到我时语气正负?" | 跳品牌 overview |
  | **引用份额** | 自有域名引用占回答引用总数比 | "我的内容被 AI 引用多少?" | 跳品牌 overview |
  | **行业排名** | PANO 降序行业排位 | "我在行业第几?" | 跳 `/industry` |
  - 每张卡含 mini sparkline (30 天), 环比箭头, 绝对数值
  - ⚠️ 不再有"点击卡片 → 切 4 Metric Tab"行为, 该 Tab 结构已删除
  - ⚠️ **数据源绝不串用**: 提及率必须走 `metricSnapshot.mentionRate`, SoV 必须走 `metricSnapshot.sovValue`; frontend 现存 `DashboardPage.jsx:549` `sovValue = SOV_DATA.find(...)?.value || primary.mentionRate` 是**错误 fallback**, 本 Session 必须拆除, 两个 KPI 分别走各自的 API 字段

- **区块 ② 竞争视图** (左右并列, 面板独占, **品牌页不复制**):
  - 左: SoV 饼图 (主品牌 + Top 4 竞品 + 其他), 主品牌切片高亮品牌色
  - 右: **竞品四象限气泡图** (详见 PRD 4.6.1c):
    - X=SoV, Y=情感 (0 中线), 气泡大小=引用份额
    - 四角文字标注: 领跑者 / 高光但存风险 / 追赶者 / 警示品牌
    - 主品牌高亮 + 加粗标签, 竞品灰阶 hover 高亮
    - 点击气泡 → `/brands/:clickedBrandId`
    - Recharts `<ScatterChart>` + `<ZAxis>` 做气泡大小, 色值走 `var(--color-chart-*)`
    - 空态: 竞品 < 2 时提示去项目设置添加

- **区块 ③ 趋势视图** (左右并列):
  - 左: PANO 趋势 30 天折线, 只画"我 + Top 3 竞品" (最多 4 条线), 我高亮, 竞品灰阶
  - 右: **5 KPI sparkline 汇总面板** (每行一个指标 提及率/SoV/情感/引用份额/行业排名, 共享时间轴, 便于跨维度对比走势; 2026-04-16 Frank 纠偏新增 提及率 行)
    - ⚠️ **提及率与 SoV 必须画在两行独立 sparkline**, 不得合并或其中一个 fallback 到另一个 — 两者口径不同 (提及率分母 = `topic.dimension='品类'` 的 Query, non-brand 口径; SoV 分母 = 已命中任一品牌 Response), 分别回答"品类通用问题下 AI 主动想到我的概率"和"出现的品牌里我占几份"
    - 观察提示: 如 提及率走势与 SoV 走势背离 (一个涨一个跌), UI 标小 info 图标提示"可能为竞品退出/进入行业 AI 视野所致", 引导用户看对应品牌详情

- **区块 ④ 告警条**:
  - 数据源: `Diagnostics` 表, 过滤 `severity IN ('P0','P1')` AND `brandId = primaryBrandId`
  - 按 severity → 新鲜度 → quantifiedImpact 降序, 最多 3 条
  - 每条: 严重度 badge + 一句话描述 + "→查看品牌详情" → `/brands/:primaryBrandId?tab=diagnostics&diagId=...`
  - 无告警: 显示绿色 "✓ 当前无严重异常"

- **数据聚合**:
  - 所有指标按引擎筛选聚合 (加权聚合, 单引擎时切换为该引擎评分的独立排名, UI 标注"仅 {引擎名} 下的排名")
  - 趋势图引擎多选时支持"聚合 / 分引擎叠加"两种模式开关

- **🚫 本页不做的事**:
  - 不做 PANO hero 大卡 (PANO 搬到区块 ③ 趋势图主角)
  - 不做提及位置分布 / 情感分布 / 引用明细 (那些是品牌详情 Overview Tab)
  - 不做 4 Metric Breakdown Tab 结构 (完全删除)
  - 不做单一品牌的多维度诊断展开 (那是品牌详情 诊断 Tab)

**品牌列表 + 详情 (PRD 4.6.1b)**

- `BrandsPage.jsx` (列表): 表格 + 核心指标 + 进入按钮, 点击 `→ /brands/:id`
- `BrandDetailPage.jsx` (新增或在 BrandsPage 内 route split): 按 ID 加载单品牌, 支持**三种访问状态** (PRD §4.6.1b, 2026-04-16 新增):
  - **A 监控中** (品牌 ∈ 当前 Project): 完整体验, 无 Banner, 品牌切换器下拉可见
  - **B 未监控 (已登录)**: 顶部浅灰 upsell Banner, 品牌切换器折叠; 数据全显示, 竞品对比降级为"vs 行业 Top 5"; 诊断 Tab 完全展示 + 顶部黄色 upsell 条
  - **C 未登录**: 顶部浅蓝 CTA Banner + 页脚固定 CTA 条; 数据完全开放只读 (SEO 友好); 按钮"+ 免费注册监控此品牌"
- 顶栏 "+ 加入竞品监控" 按钮 (`<WatchBrandButton>`, PRD §4.1.2a): 6 状态按钮, 详见验收; 按状态渲染不同文案 + 交互 (只读 badge / 主 CTA / 下拉跨行业 / 创建 Project / 免费注册)
- 4 子 Tab 功能 (与三状态正交, 数据源都是平台全量):
  - `?tab=overview` (默认):
    - PANO Score 大环 (`<PanoRing>`) + V/S/R/A 4 维度条形
    - PANO 30 天趋势折线
    - 提及位置分布柱状图 (首位/前3/中段/末段)
    - 提及明细摘要 Top 20 (列表, 可进入 Topics 页看详情)
  - `?tab=diagnostics`:
    - 该品牌 Diagnostics 列表, 按 severity 分组 (P0/P1/P2), 可筛选
    - 右上角 "🔗 分享体检报告 PDF" 按钮 → 触发 PDF 生成
  - `?tab=products`:
    - **BCG 矩阵气泡图** (X=产品 SoV, Y=30 天增长率, 大小=提及绝对次数)
    - 产品列表表格 (name/nameEn/SoV/情感/Top Prompt 命中数, 可排序分页)
    - 点击产品 → `/brands/:id/products/:productId`
  - `?tab=engines`:
    - 3 引擎并排卡片 (ChatGPT / 豆包 / DeepSeek), 每张展示 提及率/情感/引用次数/提及位置分布
    - 引擎对比表格
    - 差异洞察文案 (LLM 生成, 降级: 模板)

- **🚫 品牌详情页不做**: 跨品牌市场份额饼图 / 竞品四象限 / 跨品牌 PANO 趋势对比 (这些是面板区块 ②③ 专属)

**产品详情 `/brands/:brandId/products/:productId` (PRD 4.6.1d, SSR 友好)**

- 新建 `BrandProductDetailPage.jsx`, 路由用 React Router 动态参数
- 内容:
  - 面包屑: `Industry → Category → Brand → Product`
  - 产品子指标 (SoV / 情感 / 引用)
  - 推荐语境分类 (水平柱状 / 饼图, 分类来自 Response 挖掘)
  - **关系视图**: 从 `kg_product_relations` 渲染 SUBSTITUTES/PAIRS_WITH/UPGRADES_TO/BUDGET_ALT_OF, 用 AntV G6 或 D3 force simulation 做简化局部关系图 (≤15 节点)
  - Prompt 命中 Top 20 列表, 点击下钻到 Topics 页 Query 详情
- Meta / OG image: 用 `@vercel/og` 动态生成 1200×630, 含产品名 + 品牌名 + 品类 (利于社交分享与长尾 SEO)
- **⚠️ 删除顶级 `ProductsPage.jsx`** 和对应路由 `/products`; 保留文件作为参考或删除, 由 `BrandProductDetailPage` 完全替代

**侧栏导航改造 (`DashboardLayout.jsx`)**

- 删除 `navGroups[0].items` 中 `{ label: '产品', icon: icons.product, path: '/products' }` 一项
- `PAGE_TITLES` 同步删除 `/products`, 新增 `/brands/:brandId` / `/brands/:brandId/products/:productId` 的动态标题 (从 React Router params + 数据 query 拼装, 不在静态 map 里)
- 其余 (行业全景 / 知识图谱 / 诊断 / 报告) 保持

**Topic 管理页 (PRD 4.2.5, 无结构变更)**
- 保留原结构: Topic → Prompt → Query → Response 4 层下钻 + 面包屑
- 接真实 API

**诊断总览页 (Diagnostics)**
- 全部诊断列表 (可按维度/严重度/时间过滤 + 按 priorityScore.composite 排序 + 按 readerHints 分组)
- 诊断详情页 (PRD 4.8.2 升级版 schema): 
  - **L1 观察**: evidence + responseSamples + industryBenchmark (结构化, myValue/median/top10Avg/topCompetitor/gapAnalysis)
  - **L2 解释**: causalChain (triggerMetrics + hypothesizedMechanism + confidence + supportingEvidence + alternativeHypotheses)
  - **L3 方向**: focusArea + 3-5 条 anchorQuestions (事实探查型, 非执行型, 详见 PRD 4.8.2a) + ifUntreated (不干预后果)
  - **优先级**: priorityScore (impact/ease/urgency 三维打分 + composite + rankWithinPeriod)
  - **时间线**: timeSeries (firstObservedAt + trendStatus: new/growing/persisting/improving/resolved + severityHistory)
  - **关联**: relatedDiagnostics (derivedFrom / childDiagnostics / historicalSimilar)
  - **读者标签**: readerHints badge (operator/manager/branding), 上级视图额外显示 decisionPrompt
- CTA 区域: "想要具体的优化方案？→ 联系 GEO 顾问" (基于 focusArea 定制文案)

**Topic 管理页 (含 Pipeline 下钻浏览, 参考 PRD 4.2.5)**
- Topic 列表: 分 Tab 显示 (平台 Topic / 用户自定义 Topic)，支持展开查看 Prompt
- **下钻浏览**: Topic → 展开 Prompt 列表 → 点击 Prompt 查看 Query 列表 → 点击 Query 查看 Response 原文
- 平台 Topic: 只读，展示状态 (已采集/采集中)
- 用户自定义 Topic: 可增删改，状态 (待执行/已执行/失败)
- 添加自定义 Topic (系统自动生成 Prompt)
- 标记 Topic 优先级 (关键/忽略)

### 2. 图表组件

使用 Recharts 实现 (遵循 CLAUDE.md 依赖规则):
- 折线图 (趋势)
- 柱状图 (对比)
- 饼图 (占比)
- 雷达图 (多维对比)
- 数据表格 (TanStack Table，支持排序、过滤、导出)

### 3. 报告系统 (参考 PRD 4.7.0 ~ 4.7.9)

> ⚠️ **2026-04-16 深化**: 报告从"指标堆砌"升级为"洞察 Stack + 三读者视角"架构。所有 Section 必须符合 PRD 4.7.0-a 定义的两套框架——违反任何一条视为验收不通过。

**核心框架** (PRD 4.7.0-a, 必读):
- **洞察 Stack 三层**: Layer 1 观察 (What) → Layer 2 解释 (Why, 含 causalChain + confidence) → Layer 3 方向 (What next, focusArea + anchorQuestions + ifUntreated); **Layer 3 只给锚点问题, 不给剧本**
- **三读者视角**: operator (执行者) / manager (上级) / branding (品牌策略); 每个 Section 必须在 schema 声明 `primaryReader` 和 `insightStackLayers`

**报告生成 Pipeline** (PRD 4.7.3):
- 实现 5 步 Pipeline: 数据聚合 → 诊断关联 → LLM 叙述生成 → 模板渲染 → 存储配送
- 数据聚合: 从 MetricSnapshot 查询指定 period 的各维度指标 + 环比数据
- LLM 叙述: 各 Section 并行调用火山引擎 API，生成中文叙述段落 (参考 PRD 4.7.3 Prompt 模板)
- 模板渲染: 输出 Markdown (MVP 主格式) + JSON (Agent 格式)

**报告类型** (PRD 4.7.0):
- 周报 (Weekly): cron 每周一 08:00 自动生成, ~2500 字
- 月报 (Monthly): cron 每月 1 号 08:00 自动生成, ~5500 字 (含 Branding Narrative)
- 即时报告 (On-Demand): 用户手动触发或 API/MCP 调用
- 线索诊断报告 (Lead Diagnostic): 4 层 section 架构 (Quick Wins / Strategic Bets / Branding Risks / Consulting Accelerators), ~2500 字 PDF (PRD 4.7.4a)

**报告内容 Section** (PRD 4.7.2 升级版, 10 个 Section):
1. **Executive Summary** · `manager` · L1+L2 · 5 秒扫读 + 1 分钟精读, 成果/风险/决策点三段
2. **PANO Score 详情** · `operator` · L1+L2 · V/S/R/A 瀑布图 + 因果链
3. **行业格局** · `manager` · L1+L2 · SoV 分布 + 竞品四象限 + 主题迁移
4. **品牌表现** · `operator` · L1+L2 · 3×4 引擎矩阵 + Topic 变动 + 引用来源 diff
5. **🆕 Branding Narrative** · `branding` · L1+L2 · 品牌人设 + 典型引语 + 竞品叙事矩阵 + 风险时间线 (月报/线索必含)
6. **产品竞争力** · `operator` · L1+L2 · BCG 矩阵 + 推荐语境 + 准确度
7. **竞品对比** · `operator`+`manager` · L1+L2 · 四维打分 + 竞品近期动向
8. **诊断摘要** · `operator` · L1+L2+L3 · 本 Section 是 Layer 3 主场, 含 anchorQuestions + ifUntreated
9. **🆕 Anchor Actions** · `operator` · L3 纯 · 本期 3-5 个 focus, 锚点问题呈现, 不给剧本 (周报/月报必含)
10. **CTA** · `manager`

> 详细 data recipe 和 narrative formula 见 PRD 4.7.2

**报告 API** (PRD 4.7.7):
- GET /api/v1/projects/:id/reports — 报告列表
- GET /api/v1/projects/:id/reports/latest — 最新报告
- GET /api/v1/projects/:id/reports/:reportId — 详情 (支持 Accept: text/markdown | application/json)
- POST /api/v1/projects/:id/reports/generate — 生成即时报告
- GET/PUT /api/v1/projects/:id/report-schedules — 调度配置

**前端**:
- 报告列表页 (按类型筛选、时间排序)
- 报告详情页 (渲染 Markdown，可下载)
- 报告调度设置 (MVP 用默认配置，显示当前设置即可)

**MVP 简化** (PRD 4.7.9):
- PDF 导出: 使用浏览器 window.print() 临时方案
- 图表: Markdown 报告用数据表格代替
- 邮件: 发送 Markdown 正文，PDF 附件推迟

### 4. 咨询转化功能 (参考 PRD 4.9) ⭐

**线索收集表单**:
- 诊断详情页 CTA → 弹出线索表单
- 字段: 品牌名(自动填充) + 联系人姓名 + 手机/邮箱 + 最关心的问题(多选: 可见度下降/负面情感/竞品威胁/其他)
- 提交后: 自动生成该品牌的 PDF 诊断报告 (PANO Score + 诊断摘要)
- 数据库: leads 表 (brand, contact, concerns, status, report_url, created_at)

**线索管理 Admin** (简单实现):
- GET /admin/leads — 线索列表 (新/已联系/已转化)
- PATCH /admin/leads/:id — 更新线索状态
- 简单 Admin 页面: 线索列表 + 状态筛选

**品牌 GEO 体检报告 PDF** (公开分享，遵循 PRD 4.6.3 功能 1):

> 不是社交截图 PNG，而是对标 Semrush Domain Overview 的**专业 PDF 体检报告**，7 页 (2026-04-16 升级: 上级导读 + 总览 + 引擎 + 竞品 + 诊断 Stack 扩展 + Branding Narrative + CTA)，公开无需登录即可下载。与"线索诊断报告" (PRD 4.7.0 类型 4, 4 层 section 架构) 不同——后者是提交咨询表单后触发的 BD 报告。

**入口 & 路由**:
- Dashboard 品牌 PANO Score 卡片右上角 "分享报告" 按钮 → 新标签打开公开页
- 公开页: `GET /brand-report/:brandId?locale=zh-CN|en-US` (SSR, SEO 友好, 无需登录)
- PDF 生成: `GET /api/v1/brands/:id/share-report.pdf?locale=...` (实时渲染, 流式返回)
- 数据源: `GET /api/v1/brands/:id/share-report` (JSON, 页面与 PDF 共用)

**PDF 规格**:
- 生成库: `@react-pdf/renderer` (禁止 HTML 转 PDF, 遵循 CLAUDE.md 依赖规则)
- A4 纵向, 7 页 (升级版)
- 图表: Recharts 渲染后通过 `svg2pdf` 或 `@react-pdf/renderer` 原生 `<Svg>` 嵌入
- 颜色 / 字体: 严格遵守 `docs/DESIGN_TOKENS.md` (PANO Score 走 `--color-pano-*`)
- 双语: zh-CN / en-US 两套模板，共享布局，文案从 `messages/{locale}/share-report.json` 读取

**7 页结构** (2026-04-16 升级, 详见 PRD 4.6.3):
- **P1 上级导读封面 (manager)**: 大号 PANO + **5 KPI 条 (提及率/SoV/情感/引用份额/排名)** + 一句话结论 + 成果/风险/决策点三行 + 二维码 (2026-04-16 Frank 纠偏从 4 KPI 恢复提及率, 两者口径不同须并列呈现)
- **P2 总览与子维度 (operator)**: 四维雷达 + 子维度条形 + 30 天趋势 + 3 条关键发现 (LLM)
- **P3 引擎分解 (operator)**: ChatGPT / 豆包 / DeepSeek 三卡片 + 对比表 + 1 句洞察 (LLM)
- **P4 竞品对标 (manager+operator)**: Top 4 竞品对比柱 + 表格 + **🆕 竞品四象限缩略** + 战略解读一句话
- **P5 诊断摘要 (operator, Stack L1+L2+L3 扩展)**: Top 3 P0/P1 诊断, 每条按三层呈现:
  - `[L1 观察]` evidence + industryBenchmark 差距
  - `[L2 解释]` causalChain + confidence
  - `[L3 方向]` focusArea + 3 anchorQuestions + ifUntreated
  - **严禁含执行步骤** (锚点问题必须是事实探查型)
- **P6 🆕 Branding Narrative (branding)**: AI 人设 Top5 高频词 + 漂移预警 + 3 条典型引语 (P/N/Risk) + 竞品人设矩阵 + 情感风险时间线
- **P7 关于 & CTA (manager)**: 方法说明 + 3 个 CTA + 报告唯一 ID

**页眉标签**: 每页右上角显示 `[读者 · Stack层级]` 小标签 (如 `[上级 · L1+L2]` / `[执行者 · L1+L2+L3]` / `[Branding · L1+L2]`)

**LLM 文案降级**: 一句话结论 / 关键发现 / 引擎差异 使用火山引擎 API 生成，失败时降级为模板文案 (数据驱动)

**限流与安全**:
- 同 IP 60 秒内最多 3 份 PDF (防刷)
- 报告内嵌唯一 ID 格式: `RPT-{industryCode}-{YYYYMMDD}-{random6}`
- Response API 输出 JSON 时不暴露 raw Response 内容, 只暴露聚合指标

**OG 图 (社交预览)**:
- 公开页 `/brand-report/:id` 的 Open Graph image 用 `@vercel/og` 或 satori 动态生成 (1200×630)
- 内容: 品牌名 + 大号 PANO Score + 等级, 保证 URL 贴到微信/LinkedIn 时有好看预览

**文件结构**:
```
src/share-report/
  ├── BrandReport.tsx        # React Email / PDF 共用的布局组件
  ├── pages/
  │   ├── ExecutiveCoverPage.tsx   # P1 上级导读封面
  │   ├── OverviewPage.tsx         # P2
  │   ├── EnginesPage.tsx          # P3
  │   ├── CompetitorsPage.tsx      # P4
  │   ├── DiagnosticsPage.tsx      # P5 按 Stack L1+L2+L3 扩展
  │   ├── BrandingNarrativePage.tsx # 🆕 P6 Branding 视角
  │   └── AboutPage.tsx            # P7
  ├── components/
  │   ├── PageHeaderTag.tsx  # 右上角 [读者 · Stack层级] 标签
  │   ├── StackLayerCard.tsx # 诊断 L1/L2/L3 三层卡
  │   └── NarrativeQuote.tsx # Branding 引语组件
  ├── generatePdf.ts         # @react-pdf/renderer 入口
  ├── generateOgImage.ts     # OG 图生成
  └── data.ts                # 从 MetricSnapshot/Diagnostics/KG 聚合
messages/{zh-CN,en-US}/share-report.json  # 双语文案
```

### 5. 响应式设计 & UI/UX 原则

- Desktop 优先，但手机端能查看关键指标
- 关键交互不依赖 hover
- 数据密度高，一屏展示关键信息
- 对比为王，支持竞品对比视图
- 趋势优先，展示时间变化
- 一键导出 (CSV, PNG)

### 6. 国际化 (PRD 4.10.4 / 4.10.4a / 4.10.5)

- Dashboard 所有 UI 文案来自 `messages/{locale}/dashboard.json`
- 图表 label、表格列标题、Tab 名称、KPI 卡片标签全部走 i18n
- 品牌/产品名统一走 `formatBrand(brand)` / `formatProduct(product)` (PRD §4.10.4a.C), 按 `User.locale` 返回 `nameZh` / `nameEn`，回退 `primaryName`。**禁止**组件内直接读 `brand.name` / `payload.brand` 字符串; chart tooltip / legend formatter 里也必须调用 `formatBrand`
- **面板告警条 (AlertBar / 区块 ④)** — PRD §4.10.4a.A:
  - UI 外壳文字 (栏标题、"→查看品牌详情"、"✓ 当前无严重异常") 走 `t('dashboard.alerts.*')`
  - DIAGNOSTIC 数据模型必须按 §4.10.4a.A 存双语或 i18n key, 两种模式二选一:
    - 模板型: `titleKey` + `titleParams` (+ `descriptionKey` + `descriptionParams`, `renderMode='key'`), 对应文案放 `messages/{locale}/alerts.json`
    - 叙述型: `titleZh` / `titleEn` / `descriptionZh` / `descriptionEn` 四字段 (`renderMode='bilingual'`)
  - Planner / Analyzer 生成告警时一次 LLM 调用产出目标语言所需字段, 不走"先存中文再翻译"
  - UI 渲染时按 `renderMode` 分支: `'key'` → `t(titleKey, titleParams)`; `'bilingual'` → 按 `User.locale` 取 `titleZh` / `titleEn`
  - 缺失目标 locale 字段时 fallback 到 zh-CN 并上报数据完整度告警, 禁止直接穿透显示 `undefined` / 原 key
- **项目设置页 (ProjectSettingsPage)** — PRD §4.10.4a.B:
  - `project_settings.section.*` / `field.*` / `competitor.*` / `report.*` / `alert.*` / `actions.*` / `summary.*` / `delete.*` 全量命名空间必须存在且两语言键对齐
  - 品牌名 (primary brand + competitors) 渲染走 `formatBrand()`; 副行显示另一语言
  - `positioning` / `priceRange` 通过 `brand_meta.positioning.{value}` / `brand_meta.price_range.{value}` 查表, 查不到 fallback 到原值
  - 项目创建时间走 `formatDate()`, 不写 `toLocaleDateString('zh-CN', ...)`
- **侧栏项目选择器**: `project_selector.{fallback_industry,fallback_brand,fallback_brand_row,primary_suffix,score_label,create_new}` 全量; 切换语言即时刷新
- 报告 (PRD 4.7):
  - Report.locale 字段: 报告按用户 locale 生成
  - LLM 叙述段落的系统 prompt 按 locale 切换 (中文 prompt → 中文叙述；英文 prompt → 英文叙述)
  - Markdown/JSON 输出中品牌名用对应 locale 版本 (经 `formatBrand(locale)`)
- 数值/日期格式化用 `date-fns` (locale-aware)
- 品牌 GEO 体检报告 PDF: 按 `?locale=zh-CN|en-US` 生成对应语言的 PDF 和公开预览页；LLM 生成的一句话结论/关键发现/引擎洞察按 locale 切换系统 prompt；品牌名用 `nameZh`/`nameEn`；PDF 文件名含语言码 (例 `chanel-geo-report-zh-CN.pdf`)

### 6a. i18n CI / Lint 强制规则 (PRD §4.10.4a.D)

**pre-commit + CI 必跑**:

```bash
# 1. CJK 字符检测 (allowlist 之外命中即失败)
grep -rnE '[\u4e00-\u9fff]' frontend/src --include='*.jsx' --include='*.js' \
  | grep -vE 'frontend/src/i18n/messages\.(js|ts)' \
  | grep -vE 'frontend/src/data/mock\.(js|ts).*nameZh|descriptionZh|titleZh'
# 期望: 无输出

# 2. 直读 brand.name 拦截 (必须走 formatBrand)
grep -rnE 'brand\.name\b(?!Zh|En)' frontend/src --include='*.jsx'
# 期望: 无输出 (含 brand.name 后接 Zh/En 的属性除外)

# 3. toLocaleDateString 硬编码 locale 拦截
grep -rnE "toLocaleDateString\(['\"]zh-CN|en-US" frontend/src --include='*.jsx'
# 期望: 无输出 (日期必须走 formatDate())
```

**PR checklist** (模板 `.github/pull_request_template.md` 中自动包含):
- [ ] 新增 UI 文案全部经由 `t()` / messages 文件
- [ ] 新增数据模型字段含 `Zh`/`En` 或 `titleKey`/`descriptionKey` 分枝
- [ ] 新增品牌名称展示点经由 `formatBrand()`
- [ ] 日期格式化经由 `formatDate()`, 未使用 `toLocaleDateString` 硬编码 locale

### 6b. Profile Group 筛选器 UI (PRD §4.2.3a / §4.6.1a)

Query 是基于 Profile 采样生成的, 所以 Dashboard / 品牌详情 / Topic 管理所有指标视图都必须支持按 Profile Group 切片。

**组件 `<ProfileGroupFilter>`** (新建 `frontend/src/components/filters/ProfileGroupFilter.jsx`):
- 单选下拉, 选项列表来自 `GET /api/v1/profile-groups` (返回含 `id / nameZh / nameEn / description`)
- 默认值 `all`; label 经 `t('filters.profile_group.*')` + `formatProfileGroup(group, locale)` 渲染
- URL 持久化: `?profileGroup=<id>`, 与 `?engines=...&range=...` 并列, router 变化立即刷数据
- 选中非 `all` 时在筛选栏右侧显示 `画像: {groupName}` tag, 含 × 一键清除
- 使用 Radix UI Select (CLAUDE.md 依赖规则)

**应用页面**:
- `DashboardPage.jsx` 顶栏 Toolbar (见 §1 区块描述)
- `BrandDetailPage.jsx` 概览 / 诊断 / 引擎对比 三子 Tab 顶部工具条都必须显示此筛选器, URL 与引擎筛选同构
- `TopicsPage.jsx` Pipeline 下钻时: Topic → Prompt 列表可按 Profile Group 过滤 (对应 Query.profileGroupIds ⊇ 选中)
- **不应用**: 产品详情页 `/brands/:brandId/products/:productId` (产品下钻粒度细, 样本更稀疏, 暂不加画像切片, 避免空数据)

**后端数据流**:
- 所有调用指标聚合 API 时带 `?profileGroups=<id>` (默认 `all` 不传)
- Response 若为 `{ sufficient: false, sampleCount: N, fallback: 'use_all' }`, 前端进入 degraded 模式:
  - 顶部黄色提示条: `t('filters.profile_group.insufficient_sample', { count: N, threshold: 50 })`
  - 数据卡片灰化, 显示"回到全量视图"主 CTA 与"切换其他画像"次 CTA
  - 不直接渲染噪声数据, 以免误导用户
- 聚合时顺便返回 `appliedProfileGroup: { id, nameZh, nameEn }` 供 UI tag 展示

**i18n 命名空间**:
- `filters.profile_group.{label, all, tag_prefix, clear, insufficient_sample, switch_group}` 双语对齐
- Profile Group 内容 (nameZh/nameEn) 走 `formatProfileGroup()`, 不直读 `group.name`
- 描述文案在 tooltip hover 时弹出, 帮助用户理解"谁是这群人"

### 6c. UI vs Prompt 指引边界 (PRD §4.6.0a, ⚠️ 强制)

**背景**: Session 4a 发布后审计发现, PRD/SESSIONS 里写给开发者的约束语被直接搬到了 `messages.js` 用户可见字符串里, 用户看到"本页不做 / 详情请进入"等话术, 像在读开发者备注而非产品引导。

**Session 4b 必须清理的已知泄露点** (在 `frontend/src/i18n/messages.js` 中):
- 第 266 行 `dashboard.hierarchy_note`: `'面板只回答"我在行业里的位置". 单品牌深度分析请进入「品牌详情」, 产品细节在品牌下钻第三层.'` — **删除**, 替换为区块 ① KPI 卡自带的"→查看品牌详情"click-through CTA + 卡片顶部简洁副标题 `dashboard.page_subtitle` (`市场宏观视角 · 我 vs 竞品 vs 行业`, 已存在, 保留)
- 第 323 行 `dashboard.no_dup_caption`: `'本页不做单品牌的诊断详情 / Topic 下钻 / 产品细节'` — **删除**, 不做任何替换 (如果用户需要提示, 应通过"查看完整诊断"链接引导, 而非告诉用户页面没有什么)
- 英文对应键 `dashboard.hierarchy_note` / `dashboard.no_dup_caption` 同步删除

**新增 UI 文案禁止词表** (写作任何新 `messages/{locale}/*.json` 时):
- "本页只做 / 本页不做 / 本页不提供"
- "详情请进入 / 深度分析请看 / 产品细节在 X 层"
- "🚫 / ⚠️ 本页"
- "4 Metric Breakdown Tab 已删除" 这类引用历史结构的话
- 开发约束语 (如 "单品牌深度分析走 /brands/:id") 禁止进入用户可见文本

**替换原则**:
- 用"交互可供性"代替"文字说教": 想让用户去品牌详情, 就在卡片上放可点击的 "查看品牌详情 →" CTA, 不要用文字解释"请进入"
- 需要引导时用极简 empty state (`t('common.empty_state.go_deep')` → "点任意竞品名进入品牌视图") 而不是整段约束语

**CI / Lint 拦截** (加入 `.github/workflows/i18n-lint.yml` 的新 step, PRD §4.6.0a.D):
```bash
# 4. 开发者约束语泄露到 UI 文案拦截
grep -rnE '本页(只|不)做|详情请进入|产品细节在|单品牌深度分析|4 Metric' frontend/src/i18n/messages.js frontend/src/i18n/messages/*
# 期望: 无输出

# 5. JSX 文本节点中的开发约束语拦截 (防止绕过 messages 直接硬编码)
grep -rnE '>\s*(本页|🚫 本页|⚠️ 本页)' frontend/src --include='*.jsx'
# 期望: 无输出
```

**Session 4b 预期产出新增**:
- `messages.js:266` `hierarchy_note` 删除, `messages.js:323` `no_dup_caption` 删除, 对应 JSX 引用点 (如 `DashboardPage.jsx` 中 `<Caption>{t('dashboard.no_dup_caption')}</Caption>`) 一并移除
- CI 加两条新 grep (开发约束语 + JSX 硬编码), 全部绿灯
- PR checklist 模板增加: "□ UI 文案不含开发者约束语, 未告诉用户'页面不做什么', 仅通过交互引导"

### 6d. 数据导出 (CSV) 规范 (PRD §4.6.4, ⚠️ Tier 1 必做)

**背景**: 每个图表/表格都应该"可带走". CSV 是 GENPANO 面向 SEO agency + 数据分析师的通用数据交付格式. 未登录用户点击 CSV 按钮 → 弹登录 modal → 登录后自动恢复导出 (把按钮当转化钩子, 2026-04-16 Frank 决策).

**通用 CSV 引擎 (后端)**:
- 新建 `src/export/csv/` 目录: `streamCsv.ts` (入口, BOM + `csv-stringify` streaming) + `formatters.ts` (日期/百分数/枚举翻译) + `exportTypes/` (8 个 exportType 的字段映射) + `permissions.ts` (userId 二次校验 / 防篡改)
- 路由: `GET /api/v1/export/csv/:exportType?filters=...`
- Response Headers:
  - `Content-Type: text/csv; charset=utf-8`
  - `Content-Disposition: attachment; filename="..."` + `filename*=UTF-8''...` (RFC 5987, 中文文件名兼容)
  - `Transfer-Encoding: chunked`
- 首字节写入 BOM `\uFEFF`
- CSV 库: **必须**用 `csv-stringify` (Node) 或同等成熟方案, 禁止手写引号转义拼接
- 行数上限: 10,000; 超出返回 413 + `{error: 'too_large', rowCount, limit: 10000}`, 前端弹 modal 引导收窄 filter
- 速率限制: 单用户 60 秒 ≤ 5 次, 超出返回 429

**前端导出触发点 (`<ExportCsvButton>` 新组件)**:
- 文件: `frontend/src/components/common/ExportCsvButton.jsx`
- 视觉: Lucide `Download` icon 20px + tooltip `t('export.csv.button')`, 位于组件标题栏右侧 (紧邻"分享 PDF")
- Props: `exportType` / `subject` / `filters` (从父组件传入当前 URL 的 range/engines/profileGroup/brandId)
- 点击流:
  - 未登录 → `<AuthPromptModal>` (新增, Radix UI Dialog) → `return_to=currentUrl&action=export_csv&exportType=...&subject=...&filters=...` → 登录成功后 `AuthPage` 检测到 `action=export_csv` 自动 trigger 导出
  - 已登录, rowCount 预估 > 1000 → 先弹 Radix UI Confirm Dialog `t('export.csv.confirm.title/body')` → 确认后再触发下载
  - 触发方式: `window.location.href = '/api/v1/export/csv/:exportType?...'` (浏览器原生下载, 禁用 Blob + URL.createObjectURL 大文件内存炸)
  - 成功 Toast (Sonner): `t('export.csv.toast.success', {fileName, rowCount})`
  - 错误 Toast: `rate_limit` (429) / `too_large` (413) 按 errorCode 分支

**8 个接入点 (Tier 1 全量, 无先后)**:

| # | 页面 / 区块 | exportType | 组件位置 |
|---|------------|-----------|---------|
| 1 | Dashboard 区块 ③ PANO 趋势 | `dashboard-pano-trend` | `GlobalTrendChart` 标题栏右上 |
| 2 | Dashboard 区块 ② 竞品四象限 | `dashboard-competitor-quadrant` | `CompetitorQuadrant` 标题栏右上 |
| 3 | BrandDetail 概览 Tab 提及明细 Top20 | `brand-mentions` | `MentionTable` 标题栏右上 |
| 4 | BrandDetail 诊断 Tab 列表 | `brand-diagnostics` | `DiagnosticsList` 标题栏右上 (与 "分享体检报告 PDF" 并列) |
| 5 | BrandDetail 产品 Tab BCG + 列表 | `brand-products` | `BcgMatrix` 工具栏 |
| 6 | BrandDetail 引擎对比 Tab | `brand-engines` | 引擎对比表标题栏 |
| 7 | TopicsPage 4 层 Pipeline 全量 | `pipeline-full` | 顶栏 toolbar, 按钮文案附带"⚠️ 大数据量, 建议 ≤7d + 单引擎"tooltip |
| 8 | IndustryPage List View | `industry-brands` | List View 标题栏右上 (Graph View 不提供, 无表格语义) |

**字段映射**: 详见 PRD §4.6.4 "Tier 1 — 8 个 CSV 数据字典" 表格, 每个 `exportType` 对应一个 `exportTypes/{type}.ts`, 内含:
- `columns: {key, labelZh, labelEn, format?}[]` — 列定义
- `fetchRows(filters, userId): AsyncIterable<Row>` — 查库 + 权限过滤
- `requiresAuth: true` — 全部 Tier 1 都要登录

**i18n 命名空间 `messages/{zh-CN,en-US}/export.json`** (新建):
- `export.csv.button` — "导出 CSV" / "Export CSV"
- `export.csv.tooltip` — "以 CSV 格式下载当前视图" / "Download current view as CSV"
- `export.csv.confirm.{title,body,confirm,cancel}` — 大行数确认弹窗
- `export.csv.auth_modal.{title,body,cta,cancel}` — 未登录转化弹窗 ("免费注册即可导出" / "Free signup to export")
- `export.csv.toast.{success,rate_limit,too_large,network_error}`
- `export.csv.column.{date,brand,pano_score,rank,sov_pct,sentiment,citation_share_pct,mention_count,quadrant,query_id,prompt_text,engine,profile_group,mention_position,snippet,collected_at,response_url,diag_id,severity,dimension,metric_name,my_value,industry_median,top10_avg,gap_pct,causal_chain_summary,hypothesis_confidence,priority_composite,impact,ease,urgency,first_observed_at,trend_status,reader_hints,focus_area,if_untreated,product_id,product_name,product_name_en,sub_category,growth_30d_pct,top_prompt_text,bcg_quadrant,relations,mention_rate_pct,citation_count,position_first_pct,position_top3_pct,position_middle_pct,position_last_pct,topic_id,topic_text,intent,prompt_id,prompt_language,applies_to_engines,profile_id,profile_group_ids,response_id,response_sentiment,mentioned_brands,my_brand_position,citation_domains,response_text,brand_id,brand_name,brand_name_en,aliases,positioning,price_range,primary_categories,pano_delta_7d,industry_rank,is_in_my_monitoring,is_primary}` 全量列头双语对齐
- `export.csv.enum.severity.{P0,P1,P2,P3}` — `P0 严重 / P1 高 / P2 中 / P3 低` vs `P0 Critical / P1 High / P2 Medium / P3 Low`
- `export.csv.enum.trend_status.{new,growing,persisting,improving,resolved}`
- `export.csv.enum.bcg_quadrant.{star,cash_cow,question_mark,dog}`
- `export.csv.enum.quadrant.{leader,spotlight_risk,challenger,warning}`
- `export.csv.enum.mention_position.{first,top3,middle,last}`
- `export.csv.enum.is_in_my_monitoring.{primary,competitor,none,not_logged_in}`

**数据格式工具 (`frontend/src/utils/exportFormatters.ts` + 后端同名)**:
- `formatCsvDate(date, granularity)` → ISO 8601 `YYYY-MM-DD` 或 `YYYY-MM-DDTHH:mm:ssZ`
- `formatCsvPercentage(value, decimals=2)` → 数值 0~100 保留 2 位, 不含 `%`
- `formatCsvRatio(value, decimals=4)` → 0~1 保留 4 位
- `formatCsvMulti(values)` → 分号分隔 (`a;b;c`)
- `formatCsvEmpty(value)` → `null`/`undefined` 转空字符串 (禁止 `null`/`N/A`/`-`)
- 品牌名 / 产品名必须经 `formatBrand(brand, locale)` / `formatProduct(product, locale)` 处理

**AuthPage 恢复导出处理**:
- `AuthPage.jsx` 登录/注册成功后, 读 URL `action=export_csv` 参数, 解析 `exportType/subject/filters`, 校验 `return_to` 白名单 (仅 `genpano.com` 内部路径 + 相对路径), 通过后 `navigate(return_to)` 并在目标页面 mount 时由 query param `?resume_export=1` 触发 ExportCsvButton 自动点击
- return_to 恶意值防御: `new URL(return_to, location.origin).origin !== location.origin` 直接拒绝, 降级回 Dashboard

**审计日志 (后端)**:
- 新表 `export_log(id, userId, exportType, filters JSONB, rowCount, fileName, ip, createdAt)`
- 保留策略: 90 天自动清理 (pg_cron / 周期任务)
- Admin Panel §A3 线索与数据管理页加一个"导出记录"Tab, 用于异常排查

**CI / Lint 新增拦截** (追加到 `.github/workflows/i18n-lint.yml`):
```bash
# 6. CSV 不得手写 quote 拼接 (必须用 csv-stringify / BOM)
grep -rnE 'join\(",\s*"\)|\.join\(","\)' src/export/csv --include='*.ts'
# 期望: 无输出 (如有必须在注释标注 "# SAFE: 已用 csv-stringify escape")

# 7. 导出路由不得跳过 userId 校验
grep -rnE 'export/csv' src --include='*.ts' | xargs grep -L 'requireAuth\|checkOwnership'
# 期望: 无输出 (每个 exportType handler 必须调用二次权限校验)
```

## 视觉回归 (TEST_STRATEGY Phase 3 - Playwright toHaveScreenshot)

> **目标**: 本 Session 是 UI 集中落地 Session, 是建 visual baseline 的最佳时机. CI 跑 `playwright test --project=visual`, 任何 pixel diff > 100 视为 UI 变动, 必须经人工审核 diff artifact 才能合并.

### V.1 Baseline 清单 (~40 张)

按关键信息架构分组, 每张 baseline 都锁死 DOM 结构 + 视觉 token + 数据契约:

- **Dashboard 面板** (8): Hero / 5 KPI 桌面 / 5 KPI 移动 / SoV 饼图 / 竞品四象限 / 趋势对比 / 告警条 / 零 Project Empty State (§4.1.1d E1)
- **Brand 详情 4 Tab** (8): 概览(PanoRing) / 诊断列表 / 产品 BCG / 引擎对比; 桌面 + 移动各一
- **Industry 页** (3): Treemap / List 模式 / 零数据 Empty
- **Topics 4 层 drilldown** (4): Topic → Prompt → Query → Response 每层主视图
- **Auth/Onboarding** (5): Login / Register / Forgot / SessionExpiredModal (§4.1.1e L3) / UserMenu Popover (L1)
- **Settings** (3): Profile / Account (logout inline §4.1.1e L2) / Preferences
- **报告** (5): 体检报告 7 页 PDF 每页截图 (P1-P7); 线索报告首屏
- **Empty States 扩展** (4): E2 Sidebar / E3 Landing Nav / E4 Gated Banner / CSV 导出未登录弹窗

### V.2 视觉测试实现

- 用 Playwright 内置 `expect(page).toHaveScreenshot({ maxDiffPixels: 100 })`, 不引入 Percy/Chromatic
- Baseline 存 `tests/visual/__snapshots__/{testName}-chromium.png`, 纳入 git (需 git-lfs 或直接 commit, 由 Frank 决定)
- **渲染确定性**: 每个 baseline 测试必须先 `page.routeFromHAR()` 或 mock API 响应, 数据不得来自真实后端 (避免环境差异漂移)
- 字体锁定: Playwright config 用 `--font-render-hinting=none`, 字体包锁 `tests/fixtures/fonts/`
- 动画禁用: `reduceMotion: 'reduce'` + CSS `* { transition: none !important; animation: none !important }`

### V.3 Diff 审查流程

- CI 失败时上传 diff artifact (Playwright HTML report 含三图对比: expected / actual / diff)
- Frank 在 PR 页面看 artifact, 三种操作:
  - 接受变更 → 本地跑 `npm run test:visual:update` 更新 baseline 推 commit
  - 拒绝变更 → 让实现回到 baseline
  - 部分接受 → 只更新指定测试的 baseline

### V.4 VISUAL_REGRESSION_GUIDE.md

本 Session 产出 `docs/VISUAL_REGRESSION_GUIDE.md` 文档, 含:
- 何时需要更新 baseline, 何时必须回退
- 如何在本地复现 CI 失败 (跨平台字体差异等)
- Baseline 命名约定
- 避免的陷阱 (非确定性数据 / 动画 / 字体包变动 / 显示器 DPR)

### V.5 本 Session 新增的 Harness 规则 (追加到 `scripts/ci-check.mjs`)

- 每个在 V.1 清单中的路由必须有对应的 visual test, missing 即拒合并
- Visual test 文件禁止 `await page.waitForTimeout(` (非确定性), 必须用 `waitFor` 或 `expect.toBeVisible`

执行完成后更新 CLAUDE.md。
```

### 预期产出
- 完整的 Dashboard 前端页面 (6+ 页面)
- 图表组件库 (Recharts + TanStack Table)
- 报告生成系统 (Pipeline + API + 前端)
- **线索收集表单 + 线索管理 Admin**
- **品牌 GEO 体检报告 PDF** (公开页 `/brand-report/:id` + `@react-pdf/renderer` 7 页模板 含上级导读+Branding Narrative + OG 图 + 双语)
- **Industry → Brand 直达导航 (PRD §4.1.1b 修订)**: `IndustryPage.jsx` 删除侧边 Panel, 点击节点/行直接 `navigate('/brands/:brandId?from=industry')`
- **Brand Detail 三状态 (PRD §4.6.1b)**: 监控中 / 未监控 (已登录) / 未登录 三种 Banner 样式 + 数据降级 (竞品对比降级为"vs 行业 Top 5") + 诊断 Tab 完全展示 + upsell 条
- **一键加入竞品监控 (PRD §4.1.2a)**: `<WatchBrandButton>` 6 状态按钮, 加入/移除竞品 API (含乐观更新/防抖/竞品上限/跨行业警告), Auth return_to 保留品牌上下文
- 响应式布局
- **i18n 覆盖完整 (PRD §4.10.4a)**: Dashboard alerts / Project Settings / Brand names / 日期格式全量双语; DIAGNOSTIC 数据模型含 `titleKey`/`titleParams` 或 `titleZh`/`titleEn` 分枝; 统一经 `formatBrand()` / `formatDate()`; CI 加 CJK + brand.name 直读 + toLocaleDateString 三条 grep 拦截
- **Profile Group 筛选器 (PRD §4.2.3a / §4.6.1a, §6b)**: `<ProfileGroupFilter>` 组件在 Dashboard / BrandDetail / Topics 顶栏 toolbar 接入, URL 持久化 `?profileGroup=<id>`, 样本不足降级 UI, tag 展示, `formatProfileGroup()` 统一入口
- **UI vs Prompt 边界清理 (PRD §4.6.0a, §6c)**: 删除 `messages.js:266` `hierarchy_note` + `messages.js:323` `no_dup_caption` 及其英文对应键, 移除对应 JSX 引用; CI 加 2 条新 grep (开发约束语 + JSX 硬编码) 拦截, 禁止 "本页不做 / 详情请进入 / 🚫 本页" 等开发备注语进入用户可见文案
- **CSV 数据导出 Tier 1 (PRD §4.6.4, §6d)**: 8 个 exportType (`dashboard-pano-trend` / `dashboard-competitor-quadrant` / `brand-mentions` / `brand-diagnostics` / `brand-products` / `brand-engines` / `pipeline-full` / `industry-brands`) 全量落地; `<ExportCsvButton>` 组件 + `<AuthPromptModal>` 未登录转化弹窗; 后端 `/api/v1/export/csv/:exportType` 使用 `csv-stringify` streaming + UTF-8 BOM + RFC 5987 文件名 + 行数上限 10,000 + 速率限制 5/min + `export_log` 审计表 90 天留存; `export.json` i18n 命名空间 (column 列头 + enum 枚举 + auth_modal + confirm + toast 全量双语); CI 追加 2 条 grep (禁止手写 CSV quote 拼接 + 导出路由必须含权限二次校验)
- **视觉回归基线 (TEST_STRATEGY Phase 3)**: ~40 张 Playwright `toHaveScreenshot()` baseline 覆盖 Dashboard / Brand / Industry / Topics / Auth / Settings / Reports / Empty States; `docs/VISUAL_REGRESSION_GUIDE.md` 说明 baseline 更新流程; CI 上传 diff artifact; `ci-check.mjs` 追加 2 条 Visual Harness (路由缺 visual test 拒合并 + 禁 `waitForTimeout`)

### 验收标准
- [ ] **面板 5 KPI 卡** (2026-04-16 Frank 纠偏从 4 KPI 恢复提及率): 提及率 / SoV / 情感 / 引用份额 / 行业排名 显示正确, 环比箭头和 sparkline 正常; 桌面 5×1, 移动 2×3 或 3×2
- [ ] **提及率默认 non-brand 口径** (2026-04-16): 面板 KPI 卡提及率分母 = `topic.dimension='品类'` 的 Query (non-brand); API 层 `metricSnapshot.mentionRate` 默认返回 non-brand 口径; 品牌详情页可按 dimension 分层查看
- [ ] **品类 dimension 纯净度**: 品类 Topic 标题和 Prompt 文本不含任何已知品牌名; grep 品类 Topic seed 数据确认无品牌名泄漏
- [ ] **提及率 vs SoV 数据源分离**: `metricSnapshot.mentionRate` 和 `metricSnapshot.sovValue` 分别请求, grep 确认 `DashboardPage.jsx` 不再含 `|| primary.mentionRate` 这类 fallback 表达式
- [ ] **i18n 双语完备**: `dashboard.kpi.mention_rate` / `mention_rate_help` / `sov` / `sov_help` 四键 zh-CN + en-US 全部就位, help 文案讲清口径差异 ("基于品类通用问题计算, AI 主动想到我的比例" vs "有品牌出现的讨论里我占几份")
- [ ] **面板 Hero 区块** (2026-04-16 新增): 品牌名 + PANO Score 大号数字 + 等级标签 + 行业均值对比条; 点击 Score 跳品牌详情; 受 Toolbar 筛选联动; 桌面左右并列, 移动上下堆叠
- [ ] **面板竞争视图**: SoV 饼图 (主品牌高亮) + 竞品四象限气泡图 (X=SoV, Y=情感, 大小=引用份额) 渲染正确, 点击气泡进入对应品牌详情
- [ ] **面板趋势**: PANO 30 天折线 (我 + Top 3 竞品) + **5 KPI sparkline** 汇总面板渲染正确 (每行一个指标: 提及率/SoV/情感/引用份额/行业排名); 提及率与 SoV 必须画在两行独立 sparkline, 不得合并或 fallback
- [ ] **面板告警条**: Top 3 P0/P1 诊断展示, "→查看" 跳到品牌详情 diagnostics Tab + diagId 锚点
- [ ] **引擎筛选器**: 全部/单引擎/多选切换后, 所有区块联动, URL (?range=...&engines=...) 持久化
- [ ] **面板不再有 4 Metric Breakdown Tab**: grep 确认 `DashboardPage.jsx` 不再含 `tab=mention/sentiment/citation` 相关逻辑
- [ ] **品牌详情 4 子 Tab**: 概览 / 诊断 / 产品 / 引擎对比, URL `?tab=overview` 可直链分享
- [ ] **品牌详情 概览 Tab**: PanoRing 大环 + V/S/R/A 条形 + 30 天趋势 + 提及位置分布 + 提及明细摘要 Top 20
- [ ] **品牌详情 诊断 Tab**: 单品牌 Diagnostics 列表 (P0/P1/P2 分组, 可筛选) + "分享体检报告 PDF" 按钮
- [ ] **品牌详情 产品 Tab**: BCG 矩阵 (X=SoV, Y=增长率, 大小=提及次数) + 产品列表, 点击产品进入 `/brands/:id/products/:productId`
- [ ] **品牌详情 引擎对比 Tab**: 3 引擎并排卡片 + 引擎对比表 + LLM 差异洞察 (含降级)
- [ ] **产品详情页独立 URL**: `/brands/:brandId/products/:productId` 可直链访问, 含面包屑、子指标、推荐语境、关系图 (AntV G6 或 D3)、Prompt 命中 Top 20
- [ ] **产品详情 OG 图**: `@vercel/og` 生成 1200×630 含产品名 + 品牌名 + 品类
- [ ] **顶级 `/products` 路由删除**: grep 确认 `DashboardLayout.jsx` 导航、`PAGE_TITLES`、React Router config 均不含 `/products` 顶级项
- [ ] **跨视角不重复图表**: SoV 饼图 / 竞品四象限 / 跨品牌 PANO 趋势只在面板出现; 品牌 4 子 Tab 不再复刻这些图表
- [ ] PANO Score 在品牌详情、产品详情级别页面正确展示 (含趋势)
- [ ] 诊断告警条按严重度排列
- [ ] **诊断 Schema 升级 (PRD 4.8.2)**: 每条 diagnostic 含 causalChain / industryBenchmark (结构化) / priorityScore / timeSeries / relatedDiagnostics / anchorQuestions / readerHints / focusArea / ifUntreated; 老字段 possibleCauses + direction + benchmarkReference (自由文本) 保留向后兼容但新数据必须用结构化字段
- [ ] **anchorQuestions 格式校验 (PRD 4.8.2a)**: 每条诊断必须含 3-5 个锚点问题, LLM Prompt 阶段加白名单校验禁用"要不要/应该/建议去..."等执行型引导词; 不通过的生成结果自动重跑或降级为模板
- [ ] **priorityScore 计算正确**: `composite = impact*0.5 + ease*0.2 + urgency*0.3`, `severity` 必须与 composite 档位对齐 (P0 ≥8.5 / P1 6.5-8.4 / P2 4.5-6.4 / P3 <4.5)
- [ ] **readerHints 分发**: 诊断列表页可按 operator/manager/branding 过滤, manager 视图隐藏 L3 锚点问题 + 显示 decisionPrompt
- [ ] 诊断详情页展示三层 Stack 布局 (Layer 1 观察 / Layer 2 解释 / Layer 3 方向), 每层独立卡片, 含对应字段
- [ ] **Topic 管理页支持 Pipeline 下钻浏览: Topic → Prompt → Query → Response 原文**
- [ ] **CTA → 线索表单 → 提交成功 → 自动生成 4 层 section PDF (Quick Wins / Strategic Bets / Branding Risks / Consulting Accelerators, PRD 4.7.4a)**
- [ ] **Admin 线索列表可查看和管理**
- [ ] **品牌 GEO 体检报告 PDF (2026-04-16 升级为 7 页)**: 公开页 `/brand-report/:id` 可访问，"下载 PDF" 按钮触发 `@react-pdf/renderer` 生成 7 页 PDF (上级导读/总览/引擎/竞品/诊断按Stack扩展/Branding Narrative/CTA)
- [ ] **PDF P1 上级导读**: 5 秒扫读区 (**5 KPI 条**: 提及率/SoV/情感/引用份额/排名) + 1 分钟精读区 (成果/风险/决策点 3 段) 布局正确
- [ ] **PDF P5 Stack 扩展**: 每条诊断按 Layer 1+2+3 分卡片呈现, Layer 3 卡片含 3 个 anchorQuestions + ifUntreated
- [ ] **PDF P6 Branding Narrative**: 不含数字表头, 含 AI 人设 Top5 词 + 3 条典型引语 (P/N/Risk) + 竞品人设矩阵 + 风险时间线
- [ ] **PDF 页眉读者标签**: 每页右上角显示 `[读者 · Stack层级]` 小标签 (上级 · L1+L2 / 执行者 · L1+L2+L3 / Branding · L1+L2 等)
- [ ] **PDF 数据准确性**: PANO Score / 子维度 / 引擎数据与 Dashboard 展示一致
- [ ] **PDF 诊断边界**: P5 anchorQuestions 必须是事实探查型 (grep 检查不含"要不要/应该/建议去"执行型措辞)
- [ ] **PDF 品牌化**: 色板走 DESIGN_TOKENS，图表为 SVG (非位图)，有 GENPANO 页眉页脚 + 唯一报告 ID
- [ ] **OG 图**: `/brand-report/:id` 的 Open Graph 图片动态生成 (1200×630)，包含品牌名 + PANO Score
- [ ] **限流**: 同 IP 60 秒内最多 3 份 PDF, 超出返回 429
- [ ] 图表可视化展示正常 (使用 Recharts，非手写)
- [ ] **报告 Section Schema**: ReportSection 含 primaryReader + insightStackLayers + insights + anchorQuestions + narrativeEvidence 字段
- [ ] **新 Section Type**: 周报/月报含 Anchor Actions section (纯 L3); 月报/线索含 Branding Narrative section
- [ ] **Executive Summary 格式**: 5 秒扫读区 (**5 KPI**: 提及率/SoV/情感/引用份额/排名 + Top3 变化) + 1 分钟精读区 (成果/风险/决策点 3 段, LLM 生成)
- [ ] 可生成 Markdown 格式的监测报告, 周报 ≥2500 字 / 月报 ≥5500 字
- [ ] 报告 LLM 叙述: 所有 Section 按 Narrative Formula 生成; Layer 2/3 内容必须含 confidence level + 证据引用 ID
- [ ] 周报/月报 cron 调度正常触发，生成报告存入 DB
- [ ] 报告 API: 列表/详情/生成 端点可用，支持 Markdown 和 JSON 格式; JSON 格式包含 insights/anchorQuestions/narrativeEvidence 结构化字段
- [ ] 移动端基本可用
- [ ] **i18n - Dashboard**: 所有 UI 文案来自 `messages/{locale}/dashboard.json`，切换 locale 后所有图表/表格/Tab 对应更新
- [ ] **i18n - 报告**: Report 模型含 `locale` 字段，中英报告分别用对应语言 LLM 系统 prompt 生成叙述，品牌名用对应 locale 版本
- [ ] **i18n - 体检报告**: `/brand-report/:id?locale=zh-CN|en-US` 公开页和 PDF 均按 locale 渲染，LLM 叙述用对应 locale prompt，品牌名和 PDF 文件名对应语言
- [ ] **i18n - Alerts 数据层 (PRD §4.10.4a.A)**: DIAGNOSTIC 表 / 告警源数据必须满足 `renderMode='key'` (含 titleKey+titleParams+descriptionKey+descriptionParams) 或 `renderMode='bilingual'` (含 titleZh/En + descriptionZh/En) 其一; 切换 `User.locale` 后告警条 Top3 文案跟随切换, 没有中文穿透
- [ ] **i18n - Alerts UI**: `dashboard.alerts.{title,empty_state,cta,severity.*}` 命名空间两语言键对齐; AlertBar 无裸中文字符串
- [ ] **i18n - Project Settings (PRD §4.10.4a.B)**: `project_settings.{section,field,competitor,report,alert,actions,summary,delete}.*` + `project_selector.*` + `brand_meta.{positioning,price_range}.*` 命名空间完整; 切换 locale 后页面所有标签、toggle 描述、危险区域确认弹窗都跟随切换
- [ ] **i18n - 品牌名显示 (PRD §4.10.4a.C)**: BrandDetailPage / BCG 矩阵 / 竞品四象限 tooltip / KPI 卡片 / 报告 PDF 中品牌名全部经 `formatBrand()`; `grep -rnE 'brand\.name\b(?!Zh|En)' frontend/src --include='*.jsx'` 无匹配
- [ ] **i18n - 日期统一 (PRD §4.10.4a.B)**: 所有日期渲染走 `formatDate()`; `grep -rnE "toLocaleDateString\(['\"]zh-CN" frontend/src` 无匹配
- [ ] **i18n - CI 强制 (PRD §4.10.4a.D)**: pre-commit / CI 跑 CJK grep + brand.name 直读 grep + toLocaleDateString grep, 全部绿灯; PR 模板含 4 条 i18n checklist
- [ ] **i18n - LLM 告警生成**: Planner / Analyzer 生成告警时一次 LLM 调用产出目标语言字段 (不走翻译链), mock-review: 抽样 10 条新告警记录, 不应有 `titleEn` 为中文内容的情况
- [ ] **Profile Group API 联通 (PRD §4.2.3a)**: `GET /api/v1/profile-groups` 返回 Session 2 种子的 6-10 个预置 group (all / young_female_tier1 / mid_age_female_tier23 / male_tier1 / price_sensitive / zh_chatgpt / en_chatgpt ...); 指标类 API `?profileGroups=<id>` 聚合正确, 命中 `Query.profileGroupIds ⊇ requestedGroups` 的 Response
- [ ] **Profile Group 筛选器 UI - Dashboard (§6b)**: `<ProfileGroupFilter>` 出现在顶栏 toolbar, Radix UI Select 实现, URL `?profileGroup=young_female_tier1` 持久化; 刷新页面保留选择
- [ ] **Profile Group 筛选器 UI - 品牌详情 + Topics (§6b)**: 同一组件在 `BrandDetailPage.jsx` 概览/诊断/引擎对比 Tab 顶栏显示, 在 `TopicsPage.jsx` Topic→Prompt 列表过滤 Query.profileGroupIds; 产品详情页 **不加**画像筛选 (样本稀疏)
- [ ] **Profile Group tag 展示 (§6b)**: 选中非 `all` 时每张 KPI 卡 / 图表副标题 / 告警条 tooltip 显示 `画像: {groupName}` tag, × 可一键清除
- [ ] **Profile Group 样本不足降级 UI (§6b, PRD §4.2.3a)**: API 返回 `{ sufficient: false, sampleCount: N, fallback: 'use_all' }` 时, 前端顶部显示黄色条 "当前画像样本不足 ({n} < 50 Queries), 已自动回退到全量视图" + "仍然查看部分数据" / "切换到其他画像" 双 CTA; 数据卡片灰化
- [ ] **Profile Group i18n (§6b)**: `filters.profile_group.{label,all,tag_prefix,clear,insufficient_sample,switch_group}` 双语对齐; Profile Group 名称经 `formatProfileGroup()` 不直读 `group.name`
- [ ] **UI/Prompt 边界 - 泄露文案删除 (PRD §4.6.0a.C, §6c)**: `messages.js:266` `dashboard.hierarchy_note` 删除, `messages.js:323` `dashboard.no_dup_caption` 删除, 英文 messages 对应键同步删除; `DashboardPage.jsx` 中引用这两个键的 JSX 节点 (`<Caption>` / `<Hint>`) 一并移除
- [ ] **UI/Prompt 边界 - CI 拦截 (PRD §4.6.0a.D, §6c)**: `.github/workflows/i18n-lint.yml` 新增 2 条 grep — (a) `grep -rnE '本页(只|不)做|详情请进入|产品细节在|单品牌深度分析|4 Metric' frontend/src/i18n` 无输出; (b) `grep -rnE '>\s*(本页|🚫 本页|⚠️ 本页)' frontend/src --include='*.jsx'` 无输出
- [ ] **UI/Prompt 边界 - PR 模板 (§6c)**: `.github/pull_request_template.md` 新增一条 checklist — "□ UI 文案不含开发者约束语, 未告诉用户'页面不做什么', 仅通过交互引导"
- [ ] **Industry → Brand 直达导航 (PRD §4.1.1b 2026-04-16 修订)**: `IndustryPage.jsx` 中 Graph View 点击节点 / List View 点击行 → `navigate('/brands/:brandId?from=industry&industryId=...')`; **不再**渲染旧的侧边"品牌详情 Panel" 组件 (如仍存在则删除); grep 确认 `IndustryPage.jsx` 不含 `<BrandSidePanel>` / `<BrandDetailPanel>` / `isPanelOpen` 相关逻辑
- [ ] **Brand Detail 三状态切换 (PRD §4.6.1b)**: `BrandDetailPage.jsx` 根据 (用户登录状态 × 品牌与当前 Project 关系) 渲染三个状态:
  - **A 监控中**: 无 Banner, 品牌切换器下拉可见, 按钮显示"✓ 主品牌" or "✓ 已在监控"
  - **B 未监控 (已登录)**: 顶部浅灰 Banner "{brand} 暂未加入你的监控 · 数据来自 GENPANO 平台全量采集...", 品牌切换器折叠为静态品牌名, 按钮显示"+ 加入竞品监控"
  - **C 未登录**: 顶部浅蓝 Banner + 页脚固定 CTA 条"免费注册持续监控 {brand} →", 按钮显示"+ 免费注册监控此品牌"
- [ ] **Brand Detail 竞品对比降级 (状态 B/C)**: 所有"竞品"相关的 tooltip / 副标题 / 对比基线从 "vs 我的 Project 竞品" 降级为 "vs 行业 Top 5", tooltip 加注 "(行业基线, 因尚未监控)"; 概览/诊断/产品/引擎对比 4 个 Tab 全部数据正常显示 (平台全量采集)
- [ ] **Brand Detail 诊断 Tab upsell (状态 B)**: 诊断列表顶部黄色 upsell 条 "加入监控后系统会持续追踪这些诊断的演变趋势 + 周报中重点提醒 + Branding Narrative 深度叙事"; 不隐藏诊断内容 (完全展示 — Frank 2026-04-16 决策)
- [ ] **一键加入竞品监控 - 6 状态按钮 (PRD §4.1.2a)**: `<WatchBrandButton>` 组件按状态机渲染:
  - #1 主品牌 → `✓ 主品牌 · {Project名}` 只读 badge
  - #2 已在竞品池 → `✓ 已在监控 · {Project名}` hover 下拉"移出竞品池"
  - #3 同行业未监控 → `+ 加入竞品监控` 主 CTA (乐观更新)
  - #4 跨行业未监控 → `+ 加入竞品监控 ▼` 下拉: 加入当前 / 创建新项目
  - #5 无 Project → `+ 创建项目监控此品牌` 跳 §4.1.2 (primaryBrandId 预填)
  - #6 未登录 → `+ 免费注册监控此品牌` 跳 /auth?return_to=&monitor_brand=
- [ ] **一键加入竞品 API**: `POST /api/v1/projects/{projectId}/competitors` + `DELETE /api/v1/projects/{projectId}/competitors/{brandId}` 工作正常, 乐观更新 + 失败 rollback + 30 秒防抖 (同 userId+brandId+projectId) + 竞品数量上限 10 (超出按钮变灰 + tooltip)
- [ ] **跨行业竞品警告 (状态 #4a)**: Project Settings 竞品列表单独分组显示跨行业竞品, Brand Detail / Dashboard 相关卡片在涉及跨行业竞品时显示灰色 ⚠️ tooltip "(跨行业, 数据口径不同)"
- [ ] **Auth return_to 保留 (状态 #6)**: `/auth?return_to=/brands/:id&monitor_brand=:id` 注册成功后自动跳回 brand detail; 若用户登录后仍无 Project, 自动走状态 #5 路径 (预填 primaryBrandId)
- [ ] **i18n - brand_watch 命名空间**: `brand_watch.{button.*, banner.*, dropdown.*, toast.*, confirm.*, crossindustry.*}` 全量双语对齐, 品牌名 / Project 名经 `formatBrand()` / `formatProject()`
- [ ] **CSV 导出 8 个接入点 (PRD §4.6.4, §6d)**: `<ExportCsvButton>` 出现在 Dashboard 区块 ②③ / BrandDetail 概览-提及明细 / BrandDetail 诊断 / BrandDetail 产品 BCG / BrandDetail 引擎对比 / TopicsPage toolbar / IndustryPage List View 共 8 处; 每个 Button 传入正确的 `exportType` + 当前页面 filter 上下文 (range / engines / profileGroup / brandId)
- [ ] **CSV 后端 streaming + BOM**: `GET /api/v1/export/csv/:exportType` 返回 `Transfer-Encoding: chunked` + 首字节 `\uFEFF` (Excel 打开中文不乱码); `Content-Disposition` 含 `filename="..."` + `filename*=UTF-8''...` (RFC 5987); 实际在 Windows Excel + macOS Numbers + Google Sheets 三端验证 CSV #3 (中文列头 + 中文品牌名) 无乱码
- [ ] **CSV 字段映射准确 (8 个 exportType)**: 每个 `exportTypes/{type}.ts` 列定义与 PRD §4.6.4 Tier 1 数据字典**完全一致**; 抽样 20 行数据比对 UI 上相同 filter 下看到的数据, 数值/日期/品牌名应匹配; 品牌名在 CSV 中按 `User.locale` 走 `formatBrand()`, 不穿透 `brand.name`
- [ ] **CSV 格式规范**: 日期 ISO 8601 (`YYYY-MM-DD` / `YYYY-MM-DDTHH:mm:ssZ`); 百分数 0~100 保留 2 位不带 `%`; 空值为空字符串 (非 `null` / `N/A` / `-`); 多值分号分隔 (`a;b;c`); 枚举字段按 locale 翻译 (如 `severity=P0` → zh "P0 严重" / en "P0 Critical")
- [ ] **CSV 未登录转化钩子**: 未登录点击 `<ExportCsvButton>` → 弹 `<AuthPromptModal>` 显示 `t('export.csv.auth_modal.{title,body,cta}')`; 登录 URL 含 `return_to=currentUrl&action=export_csv&exportType=...&subject=...`; 登录成功跳回目标页面后自动恢复导出; `return_to` 做 origin allowlist 校验, 恶意外链直接降级到 Dashboard
- [ ] **CSV 行数上限**: 预估 > 1000 行弹 Radix UI Confirm Dialog "即将导出 {n} 行, 确认?"; > 10,000 行后端返回 413, 前端弹 modal "数据量超限, 请收窄 filter (range ≤ 7d + 单引擎) 后再试"; Pipeline full (`pipeline-full`) 按钮 hover 时显示警告 tooltip
- [ ] **CSV 速率限制**: 同 user 60 秒内第 6 次导出后端返回 429, 前端 Toast `t('export.csv.toast.rate_limit')`; `export_log` 表正确累计
- [ ] **CSV 权限二次校验**: URL 参数篡改 (如伪造其他用户的 `projectId`) 的请求被后端拒绝 (401 或 403); `requireAuth` 中间件在所有 Tier 1 exportType 均生效; `csv/permissions.ts` 含 userId 对 Project/Brand 所属关系校验
- [ ] **CSV 审计日志**: `export_log` 表每次导出写一行 `(userId, exportType, filters JSONB, rowCount, fileName, ip, createdAt)`; 90 天清理任务落地 (pg_cron 或周期 Worker); Admin Panel 可查询
- [ ] **CSV i18n 命名空间**: `messages/{zh-CN,en-US}/export.json` 存在且两语言键对齐 (button / tooltip / confirm.* / auth_modal.* / toast.* / column.* 全量列头 / enum.severity / enum.trend_status / enum.bcg_quadrant / enum.quadrant / enum.mention_position / enum.is_in_my_monitoring); 列头 key 集合至少覆盖 8 个 exportType 所用字段; 切换 locale 后 CSV 列头和枚举值跟随切换
- [ ] **CSV 禁止手写拼接 CI**: `grep -rnE 'join\(",\s*"\)|\.join\(","\)' src/export/csv --include='*.ts'` 无输出 (除非注释标注 `# SAFE: 已用 csv-stringify escape`); 所有 CSV 生成路径必须经 `csv-stringify`
- [ ] **CSV 路由权限 CI**: `grep -rnE 'export/csv' src --include='*.ts' | xargs grep -L 'requireAuth\|checkOwnership'` 无输出 (每个 exportType handler 都必须含二次校验)
- [ ] **视觉回归 baseline ~40 张** (TEST_STRATEGY Phase 3): Dashboard 8 / Brand 详情 8 / Industry 3 / Topics 4 / Auth 5 / Settings 3 / Reports 5 / Empty States 4; 每张在 `tests/visual/__snapshots__/` 存在, `playwright test --project=visual` 全绿
- [ ] **视觉回归数据确定性**: 每个 visual test 用 `page.routeFromHAR()` 或 API mock, grep `tests/visual/` 无 `await fetch` / 真实后端依赖
- [ ] **视觉回归动画锁定**: `playwright.config.ts` 含 `reduceMotion: 'reduce'` + 全局 CSS 禁动画注入; 字体包锁定在 `tests/fixtures/fonts/`
- [ ] **Visual diff CI artifact**: CI 失败时上传 Playwright HTML report, Frank 能在 PR 看到 expected/actual/diff 三图对比
- [ ] **`docs/VISUAL_REGRESSION_GUIDE.md` 文档存在**: 含 baseline 更新流程 / 本地复现失败 / 命名约定 / 陷阱清单
- [ ] **Visual Harness CI**: V.1 清单中每个路由必须有对应 visual test, `scripts/ci-check.mjs` 能检测 missing 路由; visual test 文件中 `waitForTimeout` grep 无命中

> **⚠️ PHASE GATE 4b: 产品体验确认 (人类 Review)**
> - □ Dashboard 看一遍: 交互是否合理? 数据是否直观?
> - □ Onboarding: 选行业 → 立即看到品牌数据?
> - □ 诊断 → CTA → 线索表单流程顺畅?
> - □ 作为用户跑一遍完整流程
> - □ "这像一个我会用的产品吗?"
> - ⏱ ~1h

---

## Session 5: 上线打磨 & 中国引擎适配

### 前置依赖
- Session 0-4b 全部完成

### Prompt

```
继续 GENPANO 项目开发。

开工前必读: 本文档顶部 "通用 Session Preamble (App Session 通用)" 段 (P.1-P.6) + `docs/ADMIN_CLAUDE_CODE_SESSIONS.md` 第 0 节 9 条公约 (line 55 起). 两者均为全 App Session 通用, 本 Prompt 不复写其内容, 以原文为准.

然后阅读 CLAUDE.md (特别是决策 #18 测试高度自动化 A++ + 全 C1-C15 Harness 契约) + docs/TEST_STRATEGY.md 第 9-13 节 (异常覆盖矩阵 / P0-P2 优先级 / fixture 规范 / 38 规则血统表).

本 Session 是 MVP 的最后冲刺，目标是上线准备和打磨。

**MVP 目标指标**:
- 500 注册用户 (从 50 beta 用户扩展到 500)
- 50 WAU (Weekly Active Users)
- 3 个 AI 引擎稳定运行 (豆包 + DeepSeek + ChatGPT)
- 4 个行业完整覆盖

## 任务

### 1. AI 引擎完善 (Development Order: DeepSeek/豆包 → ChatGPT)

**第一优先级** (中国引擎):
- 完成 DeepSeek 和豆包的 Adapter (如 Session 1 未完成)
- 分析这两个引擎的 Web 界面交互流程
- 实现 Playwright 爬取逻辑 (使用国内住宅代理 IP 轮转)
- 结果解析适配 (中文 NLP 可能需要调整)

**第二优先级** (海外引擎):
- 实现 ChatGPT Web Adapter (海外住宅代理)
- 支持 API 降级 (备选方案)
- 测试阶段: 与其他 Worker 在同一台中国 VPS 上运行 (CN engines 直连/国内代理)
- 确保爬取稳定

### 2. Landing Page

创建一个有吸引力的 Landing Page:
- Hero: 一句话说清 GENPANO 是什么
- 核心功能展示 (3个差异化点)
- 产品截图/Demo
- CTA: 免费注册
- 简单的 FAQ
- SEO 友好 (meta tags, structured data)
- **双语** (PRD 4.10.4):
  - `/zh-CN/` 与 `/en-US/` 两份 Landing 文案
  - meta tags / OG tags / structured data (schema.org) 按 locale 生成
  - sitemap.xml 包含双语 URL (使用 `hreflang` 标注)
  - 首次访问按 `Accept-Language` 重定向，cookie 记住选择

### 3. Onboarding 流程 (Data-First, 单路径)

与 Session 4a 的 Onboarding 对齐 (PRD 4.1.1b):
- 选行业 (带数据预览卡片: 品牌数 + Top 3) → 直接进入行业探索视图
- 探索视图 = 产品主界面 (D3 图谱 + 列表)，用户在真实数据中浏览
- 品牌详情面板底部 CTA → 1 步创建 Project (确认竞品，带推荐理由)

### 4. 测试环境部署 (单节点)

**中国 VPS 单节点部署**:
- 全部服务: Backend API + DB + MCP Server + 所有 Scraping Workers
- CN 引擎 (豆包/DeepSeek): 直连或国内住宅代理
- 海外引擎 (ChatGPT): 通过海外代理 (住宅代理服务 或 自建 SOCKS5)
- 前端: 本地构建 / dev server / Nginx serve 静态文件
- 生产级环境变量配置 (为后续迁移做准备)
- 错误监控 (Sentry 或类似)
- 基础日志

**验证迁移就绪**:
- ScrapingWorker config 确认: 每个 Worker 通过 config (region/engines/proxy/resultEndpoint) 驱动
- 模拟双节点: 将 overseas worker 的 resultEndpoint 改为 HTTP 远程地址，验证结果回传逻辑可用
- docker-compose.yml 准备好双节点版本 (注释状态)

**正式上线迁移脚本/文档** (在 Session 5 完成但暂不执行):
- 海外 VPS 部署指南 (docker-compose + env vars)
- 中国 VPS 改为纯 worker 的配置变更
- Cloudflare Pages 部署指南
- DNS 切换步骤
- 回滚方案

### 5. 性能 & 稳定性

- 页面加载性能优化 (目标: Dashboard < 3s)
- API 响应时间优化 (目标: 核心查询 < 500ms)
- 爬取系统稳定性检查
- 数据库查询优化 (添加必要索引)
- 内存泄漏检查

### 6. 安全检查

- API Key 权限验证
- SQL 注入防护确认
- XSS 防护确认
- CORS 配置
- Rate limiting 确认
- 敏感信息不暴露 (env vars)

### 7. GTM 内容准备 (SEO & 传播) ⭐

利用平台数据自动生成首批获客内容:
- **4 个行业 GEO 趋势报告** (Markdown + PDF): 每行业的 PANO Score 排名 + 趋势分析
  - 公开访问 URL: /[locale]/reports/industry/:id (SEO 索引)
  - 结构: 行业概览 → Top 10 品牌排名 → 关键发现 → 趋势预测
  - 双语输出 (zh-CN 报告用品牌 nameZh，en-US 报告用 nameEn)
- **品牌 GEO 排行榜页面**: /[locale]/rankings/:industry — 行业内品牌 PANO Score 排名
  - 公开访问，SEO 友好
  - 每个品牌可点击跳转到 `/brand-report/:id` 查看/下载体检报告 PDF
  - CTA: "监测你的品牌 → 免费注册" / "Monitor your brand → Sign up free"
- **SEO meta tags + sitemap**: 为所有公开页面 (Landing + 行业报告 + 排行榜 + 品牌体检报告 PDF 页) 配置，sitemap 含 `hreflang` 双语标注
- **Open Graph / 社交分享**: `/brand-report/:id` 的 OG 图动态生成 (含品牌名 + PANO Score)，贴到微信/LinkedIn 时有预览；按 locale 生成不同标题

### 8. 最终测试

- 完整的用户流程测试 (注册→选行业→即刻看数据→创建项目→API调用→MCP查询)
- **咨询转化流程**: 看诊断→点CTA→填表单→收到PDF报告
- **Admin 线索管理**: 线索列表→状态更新
- 跨浏览器基本兼容性
- 移动端体验检查
- 公开页面 SEO 检查

执行完成后更新 CLAUDE.md，标注已知问题和 Phase 2 TODO。
```

### 预期产出
- ChatGPT + DeepSeek + 豆包 Adapter (按优先级)
- Landing Page (双语)
- Data-First Onboarding 流程
- 生产环境部署完成
- 性能优化
- 安全检查
- **4 个行业 GEO 趋势报告 (公开页面，双语)**
- **品牌 PANO Score 排行榜页面 (双语)**
- **GTM 就绪: SEO + 社交分享 + 公开内容 (含 hreflang 双语 sitemap)**

### 验收标准
- [ ] 单节点部署完成: 全部服务在一台中国 VPS 上运行
- [ ] 中国引擎: DeepSeek, 豆包 可爬取
- [ ] 海外引擎: ChatGPT 通过海外代理可爬取
- [ ] 三个引擎端到端: Topic→Prompt→Query→爬取→Response→解析→入库→指标计算→Dashboard 展示
- [ ] **平台采集 pipeline: 连续 3 天无故障全量采集**
- [ ] 迁移就绪验证: overseas worker 的 resultEndpoint 改为远程地址后仍可正常回传
- [ ] 双节点 docker-compose.yml 和迁移文档准备好
- [ ] Landing Page 上线 (SEO meta tags + sitemap，双语 `/zh-CN/` 与 `/en-US/`)
- [ ] 新用户 Onboarding 单路径: 选行业 (数据预览卡片) → 探索视图 → 品牌详情 → 创建项目 (确认竞品) < 2 分钟
- [ ] **咨询转化流程: 诊断CTA → 线索表单 → PDF 报告自动生成**
- [ ] **Admin 线索管理功能可用**
- [ ] **4 个行业 GEO 报告公开页面可访问 (中英双语)**
- [ ] **品牌 GEO 体检报告 PDF 可公开下载 (`/brand-report/:id`, 含 OG 预览图, 支持 `?locale=zh-CN|en-US`)**
- [ ] 核心用户流程端到端可用
- [ ] **sitemap.xml 含 hreflang 双语标注**
- [ ] 无明显安全漏洞

> **⚠️ PHASE GATE 5: 上线确认 (人类 Review)**
> - □ 部署是否正常?
> - □ 全引擎爬取跑一遍 (ChatGPT + 豆包 + DeepSeek)
> - □ 平台采集 pipeline 连续 3 天稳定?
> - □ 公开页面 (排行榜、评分卡) SEO 检查
> - □ 签字上线
> - ⏱ ~1h

---

## 跨 Session 注意事项

### CLAUDE.md 维护
每个 Session 结束时，让 Claude Code 更新 CLAUDE.md:
- 新增的模块和文件说明
- 新增的开发命令
- 架构决策变更
- 已知问题和 TODO

如果 CLAUDE.md 超过 500 行，拆分子文档 (docs/architecture.md 等)，CLAUDE.md 保留索引。

### Session 中断恢复
如果一个 Session 因为 context 限制中断:

**中断时**:
```
请总结: 已完成的任务、正在进行的任务、剩余任务、当前代码状态。
然后更新 CLAUDE.md。
```

**恢复时** (新 session):
```
请阅读 CLAUDE.md 了解项目上下文。

我们正在执行 Session X。
已完成: [从中断总结中复制]
请继续完成: [剩余任务]

验收标准 (尚未通过的):
- [ ] [复制未完成的条目]
```

### Fix Session 模板
Session 5 完成后的修复 Session:

```
请阅读 CLAUDE.md。

以下是 MVP 端到端测试中发现的问题，请逐个修复:

## 严重 (必须修)
1. [问题描述 + 复现步骤 + 期望行为]

## 一般 (尽量修)
2. ...

## 体验优化 (有时间就修)
3. ...

修复后跑一遍相关测试，更新 CLAUDE.md 的已知问题列表。
```

### 调试技巧
- 如果爬取失败，让 Claude Code 用 Playwright 的 trace viewer 分析
- 如果 LLM 生成质量不佳，让 Claude Code 调整 prompt 并展示 before/after 对比
- 如果性能问题，让 Claude Code 用 profiling 工具分析

### 完整方法论
Harness Engineering 完整方法论 (含 Phase 0-3 全生命周期、Agent 自动化质量保障、反模式、资源估算) 参见 [HARNESS_ENGINEERING.md](./HARNESS_ENGINEERING.md)

---

## Agent 自动化验证: 每个 Session 的三层检查

> 详细框架见 HARNESS_ENGINEERING.md 第 10 节
> 以下是每个 Session 具体的 Agent-executable 验证规则

### Session 0 验证

**verify-session-0.sh 要点**:
```bash
# 结构
[ -f "package.json" ] && [ -f "CLAUDE.md" ] && [ -f ".env.example" ]
[ -d "src/" ]

# 功能
npm install 2>&1 | tail -1  # 无 error
npm run dev &                # 可启动
sleep 10 && curl -s localhost:3000/api/health | grep -q '"ok"'

# 数据库
npx prisma migrate status   # 无 pending migrations

# 代码质量
npm run lint                 # 无 error
```

**对抗性审查重点**: 技术选型合理性、目录结构可扩展性、环境变量模板完整性、CI 配置正确性

**规约对齐**: PRD 5.1 (技术约束) ↔ 实际选型

### Session 1 验证

**verify-session-1.sh 要点**:
```bash
# 结构
for f in browser-manager engine-adapter chatgpt doubao deepseek account-pool scheduler; do
  find src/ -name "*${f}*" | grep -q . || echo "MISS: $f"
done

# 接口合规
grep -rq "implements.*EngineAdapter\|extends.*EngineAdapter" src/

# 降级机制
grep -rq "fallback\|degrade\|switchTo.*api\|API_FALLBACK" src/scraping/ src/engines/

# 测试
npm test -- --testPathPattern="scraping|engine|adapter" --passWithNoTests=false

# 安全
! grep -rn "sk-[a-zA-Z0-9]\{20,\}" src/
! grep -rn "password.*=.*['\"]" src/

# 并发安全 (账号池)
grep -rq "mutex\|lock\|atomic\|semaphore\|queue" src/accounts/ src/scraping/
```

**对抗性审查 Prompt**:
```
审查 src/scraping/ 和 src/engines/ 和 src/accounts/:
1. Playwright browser context 是否在 finally 中关闭? 列出所有未保护的 launch/newContext
2. 账号池并发: 两个 worker 同时 acquire 同一账号的竞争条件?
3. 代理失败: IP 被封后的 fallback 链完整吗?
4. 内存: 长时间运行后 browser instance 是否会泄露?
5. 反检测: stealth plugin 配置是否完整? 有无指纹泄露?
6. 鲁班SMS 集成: 超时/失败/余额不足的处理?
```

**规约对齐**: PRD 4.3 ↔ 爬取系统 (重点: Web-First 是否真的优先于 API? 降级链是否符合 PRD 描述?)

### Session 1.5 验证

**verify-session-1.5.sh 要点**:
```bash
# 结构
for f in brand-discovery product-discovery platform-scheduler topic-pool; do
  find src/ -name "*${f}*" | grep -q . || echo "MISS: $f"
done
[ -f "scripts/seed-platform-data.ts" ] || echo "MISS: seed script"

# 行业种子
INDUSTRIES=$(curl -s localhost:3000/admin/platform/industries | jq '. | length')
[ "$INDUSTRIES" -ge 4 ] || echo "FAIL: Only $INDUSTRIES industries (need 4)"

# 品牌发现
BRANDS=$(curl -s localhost:3000/admin/platform/industries/beauty/brands | jq '. | length')
[ "$BRANDS" -ge 20 ] || echo "FAIL: Only $BRANDS beauty brands (need 20+)"

# 产品发现
PRODUCTS=$(curl -s localhost:3000/admin/platform/brands/estee-lauder/products | jq '. | length')
[ "$PRODUCTS" -ge 5 ] || echo "FAIL: Only $PRODUCTS products for Estee Lauder (need 5+)"

# 数据质量
curl -s localhost:3000/admin/platform/industries/beauty/brands | \
  jq '.[].aliases | length' | awk '{sum+=$1} END {print sum/NR}' # 平均别名数 > 0

# 发现日志
curl -s localhost:3000/admin/platform/discovery-logs | jq '. | length' | \
  xargs -I{} [ {} -gt 0 ] || echo "FAIL: No discovery logs"

# 调度器
grep -rq "PlatformScheduler\|platformScheduler\|platform.*schedule" src/platform/
grep -rq "tierConfig\|tier.*config\|high.*medium.*low" src/platform/scheduler/

# Platform vs User 数据隔离
# 确认 platform_ 前缀表存在
npx prisma db execute --stdin <<< "SELECT count(*) FROM information_schema.tables WHERE table_name LIKE 'platform_%';" | grep -q "[5-9]\|[1-9][0-9]"
```

**对抗性审查 Prompt**:
```
审查 src/platform/:
1. LLM 品牌发现: prompt injection 风险 (行业名/品牌名包含恶意指令)?
2. 品牌去重: "雅诗兰黛" vs "Estée Lauder" vs "EL" 是否能识别为同一品牌?
3. 发现 Pipeline 幂等性: 重复运行是否会产生重复数据?
4. 平台调度器: 每日爬取量是否有硬上限? 超限后是否停止而非继续?
5. 成本失控: 如果 LLM 返回异常多的品牌 (100+)，是否有截断保护?
6. 数据隔离: Platform 表和 User 表之间是否有外键约束防止交叉污染?
```

**规约对齐**: PRD 4.0 ↔ 平台数据基础设施 (重点: 行业覆盖范围、品牌/产品发现逻辑、分层采集频率)

### Session 2 验证

**verify-session-2.sh 要点**:
```bash
# 功能: Topic/Prompt 生成
RESULT=$(curl -s -X POST localhost:3000/api/v1/projects/test/queries/generate \
  -H "Content-Type: application/json" \
  -d '{"industry":"美妆","brands":[{"name":"雅诗兰黛"}],"products":[{"name":"小棕瓶"}]}')
QUERY_COUNT=$(echo "$RESULT" | jq '.queries | length')
[ "$QUERY_COUNT" -ge 50 ] || echo "FAIL: Only $QUERY_COUNT queries (need 50+)"

# Bottom-Up 层级
echo "$RESULT" | jq '.queries[].level' | sort | uniq -c
# 应包含 product, brand, industry 三个级别

# 意图分类
echo "$RESULT" | jq '.queries[].intent' | sort | uniq -c
# 应包含 informational, navigational, commercial, transactional

# Agent Profile
PROFILES=$(curl -s localhost:3000/api/v1/profiles | jq '. | length')
[ "$PROFILES" -ge 10 ] || echo "FAIL: Only $PROFILES profiles (need 10+)"

# API 端点
for endpoint in "queries" "queries/generate" "queries/custom"; do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" localhost:3000/api/v1/projects/test/$endpoint)
  [ "$STATUS" != "404" ] || echo "FAIL: $endpoint returns 404"
done
```

**对抗性审查 Prompt**:
```
审查 src/topic-planner/ 和 src/prompt-generator/:
1. Topic/Prompt 质量: 从生成结果中抽取 10 条，评估是否像真实用户关注和提问 (vs SEO关键词堆砌)
2. Bottom-Up 严格性: 是否真的先生产品再品牌再行业? 还是并行生成?
3. 去重逻辑: 语义相近但字面不同的 Topic 是否能合并?
4. LLM prompt: 有无 prompt injection 风险 (用户输入的品牌名包含恶意指令)?
5. Profile 采样: 是否真随机? 有无偏向性?
```

**规约对齐**: PRD 4.2 ↔ Topic/Prompt/Query Pipeline (重点: Bottom-Up 顺序、四层 Pipeline 完整性、Agent Profile 维度覆盖)

### Session 3 验证

**verify-session-3.sh 要点**:
```bash
# API 全面性
SWAGGER=$(curl -s localhost:3000/api-docs)
echo "$SWAGGER" | jq '.paths | keys[]' | wc -l  # 应 >= 10 个端点

# 分析准确性 (用已知数据验证)
# 插入 mock 数据 → 调用分析 API → 对比预期值
npx ts-node scripts/verify-analytics.ts

# PANO Score
PANO=$(curl -s localhost:3000/api/v1/projects/test/pano-score)
echo "$PANO" | jq '.brand.score'    # 0-100 之间
echo "$PANO" | jq '.brand.grade'    # A+/A/B+/B/C/D/F 之一
echo "$PANO" | jq '.brand.dimensions | length'  # >= 5 个子维度

# 诊断引擎
DIAG=$(curl -s localhost:3000/api/v1/projects/test/diagnostics)
echo "$DIAG" | jq '.[0].severity'        # P0-P3
echo "$DIAG" | jq '.[0].evidence'        # 非空
echo "$DIAG" | jq '.[0].possibleCauses'  # 非空数组
echo "$DIAG" | jq '.[0].direction'       # 非空字符串
# 验证 direction 不含具体执行步骤
echo "$DIAG" | jq -r '.[].direction' | grep -qiE "步骤|step [0-9]|具体操作|how to" \
  && echo "FAIL: direction contains execution steps"

# MCP Server
npx ts-node scripts/verify-mcp.ts  # MCP tool 调用测试

# 认证
curl -s -o /dev/null -w "%{http_code}" localhost:3000/api/v1/projects \
  | grep -q "401"  # 无 API Key 应返回 401
```

**对抗性审查 Prompt**:
```
审查 src/analytics/ 和 src/api/ 和 src/mcp-server/:
1. 计算正确性: PANO Score 的加权公式实现与 PRD 4.4 定义是否一致? 找出偏差
2. 除零/空值: 当某维度无数据时 PANO Score 如何处理? 会崩溃吗?
3. 诊断边界: direction 是否严格不含执行步骤? (这是商业模式的关键)
4. API 安全: 有无未认证的端点? 有无 SQL 注入风险?
5. MCP: tool description 是否足够清晰让 Agent 正确调用?
6. 速率限制: 是否可被绕过?
```

**规约对齐**: PRD 4.4 + 4.5 + 4.8 ↔ 分析/API/MCP/诊断 (重点: PANO Score 公式、诊断 CTA 边界)

### Session 4a 验证

**verify-session-4a.sh 要点**:
```bash
# 页面存在性
for page in "/login" "/register" "/onboarding"; do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" localhost:3000$page)
  [ "$STATUS" = "200" ] || echo "FAIL: $page returns $STATUS"
done

# 认证流程
npx playwright test tests/e2e/auth-flow.spec.ts
# 覆盖: 注册→邮箱验证→登录→找回密码→重置密码

# 未登录保护
STATUS=$(curl -s -o /dev/null -w "%{http_code}" localhost:3000/dashboard)
[ "$STATUS" = "302" ] || [ "$STATUS" = "401" ] || echo "FAIL: Dashboard not protected"

# Onboarding 单路径
npx playwright test tests/e2e/onboarding-flow.spec.ts
# 覆盖: 选行业(数据预览) → 探索视图 → 品牌详情 → 创建项目(确认竞品)

# Project 数量限制
npx ts-node scripts/verify-project-limit.ts
# 创建 3 个 Project 成功，第 4 个被拒绝

# 邮件模板
for template in verify-email welcome reset-password password-changed login-alert; do
  [ -f "src/emails/${template}.tsx" ] || echo "MISS: $template email template"
done

# i18n 文案库 (PRD 4.10.4)
for locale in zh-CN en-US; do
  for ns in common auth onboarding dashboard email; do
    [ -f "messages/${locale}/${ns}.json" ] || echo "MISS: messages/${locale}/${ns}.json"
  done
done

# i18n 路由
STATUS_ZH=$(curl -s -o /dev/null -w "%{http_code}" localhost:3000/zh-CN/login)
STATUS_EN=$(curl -s -o /dev/null -w "%{http_code}" localhost:3000/en-US/login)
[ "$STATUS_ZH" = "200" ] || echo "FAIL: /zh-CN/login returns $STATUS_ZH"
[ "$STATUS_EN" = "200" ] || echo "FAIL: /en-US/login returns $STATUS_EN"

# i18n 邮件 (发送时按 locale 选模板)
npx ts-node scripts/verify-email-i18n.ts
# 模拟 User.locale=zh-CN 和 en-US 各发一封 E1, 校验 subject 和 body 对应语言

# i18n 品牌名渲染
npx playwright test tests/e2e/i18n-brand-names.spec.ts
# 切换 locale 后，图谱/列表中的品牌名在 nameZh ↔ nameEn 之间切换
```

**对抗性审查 Prompt**:
```
审查 src/auth/ 和 src/emails/ 和 src/onboarding/ 和 messages/:
1. 认证: JWT 是否安全签发? refresh token 机制?
2. 邮件安全: token 是否 hash 后存储? 是否一次性?
3. 频率限制: 找回密码 API 是否可被暴力枚举?
4. 行业选择卡片: 数据预览 API 是否有缓存? 首屏加载速度?
5. 探索视图: D3 图谱在大量节点 (100+ 品牌) 时性能是否可接受?
6. Project 限制: 是否只在前端限制? 后端 API 是否也有校验?
7. 品牌提交: LLM 验证是否有 prompt injection 风险?
8. i18n 文案完整性: zh-CN 和 en-US 文案 key 是否完全对齐? 是否有缺失 key 导致 fallback 文案?
9. i18n 品牌渲染: nameZh 或 nameEn 缺失时是否正确回退到 primaryName?
10. i18n 邮件: 未登录用户 (仅浏览器 Accept-Language) 发邮件时 locale 判定是否稳健?
```

**规约对齐**: PRD 4.1 + 4.10 ↔ 用户系统/Onboarding/Project/国际化

### Session 4b 验证

**verify-session-4b.sh 要点**:
```bash
# Dashboard 页面存在性
for page in "/dashboard" "/dashboard/industry" "/dashboard/brands" "/dashboard/diagnostics"; do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" -H "Cookie: $AUTH_COOKIE" localhost:3000$page)
  [ "$STATUS" = "200" ] || echo "FAIL: $page returns $STATUS"
done

# PANO Score 展示
npx playwright test tests/e2e/pano-display.spec.ts

# 引擎筛选器联动
npx playwright test tests/e2e/engine-filter.spec.ts

# 诊断 CTA
npx playwright test tests/e2e/diagnostics-cta.spec.ts
# 验证: CTA 按钮存在、链接到咨询入口

# 线索表单
npx playwright test tests/e2e/lead-form.spec.ts
# 覆盖: CTA → 填写表单 → 提交 → PDF 报告生成

# 报告生成
REPORT=$(curl -s -X POST localhost:3000/api/v1/projects/test/reports/generate \
  -H "Authorization: Bearer $API_KEY")
echo "$REPORT" | jq '.format'  # markdown
echo "$REPORT" | grep -q "PANO Score"   # 报告包含 PANO Score
echo "$REPORT" | grep -q "诊断"         # 报告包含诊断摘要

# Topic 下钻浏览
npx playwright test tests/e2e/topic-drilldown.spec.ts
# 覆盖: Topic → Prompt → Query → Response 原文

# 移动端 (viewport 375px)
npx playwright test tests/e2e/mobile-basic.spec.ts

# i18n - Dashboard 双语渲染
npx playwright test tests/e2e/dashboard-i18n.spec.ts
# 覆盖: 切换 locale 后图表 label/表格列/Tab/品牌名对应更新

# i18n - 报告双语生成
npx ts-node scripts/verify-report-i18n.ts
# 生成 zh-CN 和 en-US 报告各一份，校验 Executive Summary 语言 + 品牌名对应 locale

# 品牌 GEO 体检报告 PDF (Session 4b)
npx playwright test tests/e2e/brand-report.spec.ts
# 覆盖: 公开页可访问 → 下载 PDF → PDF 为 7 页 → 含上级导读/总览/引擎/竞品/诊断Stack/Branding/CTA

# 体检报告 PDF 限流
for i in $(seq 1 5); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    "localhost:3000/api/v1/brands/test-brand/share-report.pdf?locale=zh-CN"
done | grep -q "429" || echo "FAIL: rate limit not enforced"

# 体检报告 PDF 双语
curl -s -o /tmp/r-zh.pdf "localhost:3000/api/v1/brands/test/share-report.pdf?locale=zh-CN"
curl -s -o /tmp/r-en.pdf "localhost:3000/api/v1/brands/test/share-report.pdf?locale=en-US"
[ -s /tmp/r-zh.pdf ] && [ -s /tmp/r-en.pdf ] || echo "FAIL: bilingual PDF generation"
# 用 pdf-parse 或 pdftotext 抽文本校验 zh/en 语言
pdftotext /tmp/r-zh.pdf - | grep -q "PANO 评分" || echo "FAIL: zh-CN PDF text missing"
pdftotext /tmp/r-en.pdf - | grep -q "PANO Score" || echo "FAIL: en-US PDF text missing"

# OG 图
OG_URL=$(curl -s "localhost:3000/brand-report/test?locale=zh-CN" | grep -oP 'og:image" content="\K[^"]+')
curl -s -o /dev/null -w "%{http_code}" "$OG_URL" | grep -q "200" || echo "FAIL: OG image missing"
```

**对抗性审查 Prompt**:
```
审查前端代码 (Dashboard + 报告) 和 messages/:
1. XSS: 用户输入 (品牌名、Topic、Prompt) 在渲染时是否转义?
2. 状态管理: 大量数据加载时是否有 loading/error/empty 三态?
3. 响应式: 在 375px 宽度下关键信息是否可见?
4. 图表: 数据为空/极端值时图表是否崩溃? 是否使用 Recharts (非手写)?
5. 诊断 CTA: 是否每个诊断卡片都有 CTA? direction 是否不含具体执行步骤?
6. 线索表单: 提交后是否有确认反馈? PDF 生成失败是否有降级?
7. 报告: LLM 叙述生成失败时报告是否仍可输出 (降级为纯数据)?
8. i18n - 报告: zh-CN 和 en-US 报告模板的 Section 结构是否一致? LLM prompt 是否使用对应 locale 的版本?
9. i18n - 数字/日期: 不同 locale 下数字千分位和日期格式是否正确 (date-fns locale)?
```

**Harness 断言（ProfileGroupFilter 覆盖）**:
```bash
# 验证 ProfileGroupFilter 组件在三大页面均被正确使用
grep -l "ProfileGroupFilter" src/pages/BrandDetailPage.jsx src/pages/TopicsPage.jsx src/pages/DiagnosticsPage.jsx
# 预期：三个文件均命中（exit 0）；如缺失任一文件则 exit 1
```

**规约对齐**: PRD 4.6 + 4.7 + 4.8 + 4.9 + 4.10 ↔ Dashboard/报告/诊断展示/咨询转化/国际化

### Session 5 验证

**verify-session-5.sh 要点**:
```bash
# 端到端全引擎
for engine in chatgpt deepseek doubao; do
  RESULT=$(curl -s "localhost:3000/api/v1/scraping/test?engine=$engine")
  echo "$RESULT" | jq '.status' | grep -q "success" \
    || echo "WARN: $engine scraping failed"
done

# 部署验证
docker-compose -f docker-compose.yml config  # 配置有效
docker-compose up -d && sleep 30
curl -s localhost:3000/api/health | grep -q '"ok"'

# 迁移就绪
# 改 overseas worker 的 resultEndpoint 为远程地址
REMOTE_TEST=$(RESULT_ENDPOINT=http://remote-test:3000 \
  npx ts-node scripts/test-remote-result.ts)
echo "$REMOTE_TEST" | grep -q "success" || echo "FAIL: Remote result endpoint broken"

# 双节点 compose 存在
[ -f "docker-compose.production.yml" ] || echo "FAIL: No production compose file"

# Landing Page (双语)
curl -s localhost:3000/zh-CN | grep -qi "genpano" || echo "FAIL: Landing zh-CN missing"
curl -s localhost:3000/en-US | grep -qi "genpano" || echo "FAIL: Landing en-US missing"

# i18n sitemap (hreflang)
curl -s localhost:3000/sitemap.xml | grep -q 'hreflang="zh-CN"' \
  || echo "FAIL: sitemap missing hreflang zh-CN"
curl -s localhost:3000/sitemap.xml | grep -q 'hreflang="en-US"' \
  || echo "FAIL: sitemap missing hreflang en-US"

# 性能
LOAD_TIME=$(curl -s -o /dev/null -w "%{time_total}" localhost:3000/dashboard)
[ "$(echo "$LOAD_TIME < 3" | bc)" -eq 1 ] || echo "WARN: Dashboard slow ($LOAD_TIME s)"

# 安全
npx ts-node scripts/security-check.ts  # 检查 CORS, 注入, 密钥泄露
```

**对抗性审查 Prompt**:
```
审查部署配置和安全:
1. Docker: 容器是否以非 root 运行? 不必要的端口是否暴露?
2. 环境变量: .env 中是否有生产密钥? .gitignore 是否覆盖?
3. 代理配置: 海外代理凭证是否在代码中硬编码?
4. 日志: 是否有敏感信息 (密码、token) 写入日志?
5. CN 引擎: 在单节点上运行全部 Worker 的资源消耗 (2核4G 够吗)?
6. 迁移文档: 步骤是否完整? 有无遗漏的环境变量?
```

**规约对齐**: PRD 5.4 ↔ 部署架构 (重点: 单节点→双节点迁移零代码变更)

### Phase Gate 节点

```
Session 0 完成 → [Gate 1: 架构确认] → Session 1 → Session 1.5 连续执行
Session 1.5 完成 → [Gate 2: 平台数据+爬取引擎确认] → Session 2-3 连续执行
Session 3 完成 → [Gate 3: 核心引擎+API 确认] → Session 4a → [Gate 4a: 用户系统确认] → Session 4b
Session 4b 完成 → [Gate 4b: 产品体验确认] → Session 5
Session 5 完成 → [Gate 5: 上线确认] → Fix Sessions → Launch
```

非 Gate 节点的 Session 之间由 Agent Pipeline 自动流转 (Layer 1-3 全部 PASS 且无 P0 即可继续)。

### 升级规则

| 条件 | 动作 |
|------|------|
| 任何 Layer 报告 P0 | Fix Session 自动修复，修复后重新验证 |
| Fix 3 轮未收敛 | 暂停 Pipeline，升级人类 |
| Adversarial 发现 ≥3 个 P1 | 升级人类审查 |
| Compliance 发现 PRD P0 功能未实现 | 阻断，升级人类 |
| Phase Gate 节点 | 必须等待人类审查通过 |

---

## Brand/Industry Mode IA Sessions (2026-04-20 新增, ⭐ SUPERSEDES Triad T1-T4)

> **背景**: Triad T1-T4 基于 "Dashboard 要存续, 只是需要新内容" 假设; 2026-04-20 Frank 决议反转: Dashboard 路由整个废除, 侧栏 IA 重构为 Brand Mode / Industry Mode 二 Mode (Stripe 风格 pill toggle)。Project 在 MVP solo-user 场景下隐身, 零 Project 态强制跳 `/onboarding` 独立引导页。顶层 `/diagnostics` / `/topics` / `/knowledge-graph` / `/reports` / `/industry` 全部按 Mode 重新归属。
>
> **阅读前置**: 每个 Session 开工前按顺序读:
> 1. `docs/PRD.md` §4.6-IA-v2 全文 (权威 IA 源) + §4.1.1-gate (Auth-Required) + §4.6.0a (UI 文案边界)
> 2. `CLAUDE.md` 关键设计决策 #2 (Brand/Industry Mode) + #9 (Auth-Required) + #10 (Route Guard → /onboarding) + 设计锚点表 (新 sub-view 文件映射)
> 3. `docs/DESIGN_TOKENS.md` 全文 + C8 Drawer 契约
> 4. `docs/TEST_STRATEGY.md` 4 层 4 支柱
>
> **反模式红线**:
> - 禁止保留 `/dashboard` / `/brands/:id` / `/topics` (顶层) / `/industry` / `/industries/:id` / `/knowledge-graph` / `/diagnostics` 任何一条作为可达路由 (全部 301 redirect)
> - 禁止在 i18n JSON 或 JSX 文本写 "Brand Mode" / "Industry Mode" / "sub-view" / "Mode Toggle" 等开发语 (§4.6.0a / §4.6-IA-v2.H4)
> - 禁止把 Mode 落 localStorage (URL 是唯一真相源)
> - 禁止在 MVP 侧栏再渲染 `<ProjectSelector>` (Settings 页除外)
> - 禁止把 Engine 对比做成独立路由 (§4.6-IA-v2.E, 是 filter 不是 page)
> - 禁止新建 DashboardEmptyState / ProjectRequiredBanner / LandingNavQuickCreateButton (§4.1.1d 废除)
> - 禁止继续维护跨品牌聚合 `/diagnostics` (删除组件, 不是重命名)

**执行顺序**: T1' → T2' → T3' → T4' → T5' (严格串行)

**核心参考**: PRD §4.6-IA-v2 (A-G) + CLAUDE.md "设计锚点" §1-§5

---

### Session T1' (ia-v2-S1): DashboardLayout 重构 — 顶栏 Mode Toggle + 侧栏 Mode-Aware

**目标**: 将现有 `DashboardLayout.jsx` 重构为双模架构的 Shell: 顶栏包含 Mode Toggle (Stripe pill)、全局筛选条、工具栏; 侧栏根据当前 URL prefix (`/brand/*` 或 `/industry/*`) 动态渲染不同导航组。

**前置**:
- Session 0-5 基础设施就绪 (路由、i18n、mock data、组件库)
- PRD §4.6-IA-v2 A-G 已读 (特别是 C.1 顶栏 + C.2.1 Brand 侧栏 + C.3.1 Industry 侧栏)
- CLAUDE.md "设计锚点" 全文已读

**任务清单**:

1. **Mode 检测 Hook** `frontend/src/hooks/useAppMode.js`
   - 从 `useLocation().pathname` 解析当前 Mode: `/brand/*` → `'brand'`, `/industry/*` → `'industry'`
   - 默认 fallback: `'brand'` (无匹配前缀时)
   - **不落 localStorage** — Mode 完全 URL-driven (§4.6-IA-v2.C.1)
   - 返回 `{ mode, isBrand, isIndustry, togglePath }` — `togglePath` 为 "切到另一 Mode 的对称路由" (如 `/brand/overview` ↔ `/industry/overview`)

2. **Mode Toggle 组件** `frontend/src/components/topbar/ModeToggle.jsx`
   - Stripe 风格 pill toggle: `🎯 品牌 | 🌍 行业`
   - Active 态: `bg-themed-accent text-white`, Inactive: `bg-transparent text-themed-muted`
   - 点击 → `navigate(togglePath)`, 保留 search params
   - 动效: Framer Motion `layoutId` 滑块过渡 (≤200ms)
   - i18n keys: `topbar.mode_brand`, `topbar.mode_industry`
   - 埋点 #67 `mode_toggle_clicked` (属性: `{ from_mode, to_mode, from_sub_view }`)
   - **禁止**在组件内写 "Brand Mode" / "Industry Mode" 等字面量

3. **顶栏重构** `DashboardLayout.jsx` 顶栏区域
   - 布局 (左→右): Logo + **ModeToggle** + 弹性空间 + 全局筛选条 (Brand Mode only) + 🔍 ⌘K + 🔔 告警铃 + 👤 UserMenu
   - **全局筛选条** (Brand Mode only, §4.6-IA-v2.C.1): Engine Segmented Control (全部/ChatGPT/豆包/DeepSeek), 时间范围 DatePicker, ProfileGroup 下拉
   - 筛选条用 `EngineFilterBar` 扩展 (已有), 增加 `isGlobal` prop 控制全局 vs 页内模式
   - 🔔 告警铃 `AlertBell.jsx`: 气泡显示跨品牌 Top 5 未读 Alert 数, 点击展开 Popover (Alert 标题 + 品牌名 + 严重度 Badge), 点击条目跳 `/brand/diagnostics?alertId=`
   - ⌘K 搜索按钮: MVP 只渲染 placeholder 按钮, 点击不响应 (Phase 2 CommandPalette)
   - 👤 UserMenu `UserMenu.jsx`: 头像下拉 (用户邮箱 / Settings / 语言切换 / 登出), 登出契约 6 步 (§4.1.1e L1)

4. **侧栏 Mode-Aware 重构** `DashboardLayout.jsx` 侧栏区域
   - **Brand Mode 侧栏** (§4.6-IA-v2.C.2.1):
     ```
     [BrandPicker]                    ← 顶部
     ─────────────────
     📊 分析
       总览        /brand/overview
       可见性      /brand/visibility
       Topics      /brand/topics
       情感        /brand/sentiment
       引用        /brand/citations
       产品        /brand/products
       竞品        /brand/competitors
     ─────────────────
     🔧 运营
       诊断        /brand/diagnostics
       报告        /brand/reports
     ─────────────────
     [Project 小灰字 + ⚙️]           ← 底部
     ```
   - **Industry Mode 侧栏** (§4.6-IA-v2.C.3.1):
     ```
     [IndustryPicker]                 ← 顶部
     ─────────────────
     📊 分析
       总览        /industry/overview
       排行榜      /industry/ranking
       Topics 热度 /industry/topics
       知识图谱    /industry/knowledge-graph
     ─────────────────
     💡 切回品牌模式 →               ← 引导 CTA
     ─────────────────
     [Project 小灰字 + ⚙️]           ← 底部
     ```
   - 侧栏宽度: 240px 固定, 响应式 < 768px 折叠为 Hamburger
   - 活跃项: `text-themed-accent font-medium border-l-2 border-themed-accent` 左侧高亮
   - i18n: 每项 `sidebar.brand_*` / `sidebar.industry_*` key

5. **BrandPicker 组件** `frontend/src/components/sidebar/BrandPicker.jsx`
   - 顶部搜索框 (filter by name, debounce 200ms)
   - 主品牌 ⭐ 置顶 (从 `activeProject.primaryBrandId` 取)
   - 竞品列表 (从 `activeProject.competitorBrandIds` 取, 按 SoV desc)
   - 点击品牌 → `setSearchParams({ brandId: id })`, **不改 sub-view 路径**
   - 底部: "查看所有品牌 →" link → `/brands` (品牌集市 grid)
   - 当前选中高亮: `bg-themed-accent-soft rounded`
   - 埋点 #68 `brand_picker_switched`

6. **IndustryPicker 组件** `frontend/src/components/sidebar/IndustryPicker.jsx`
   - 下拉 Select (Radix UI Select): 已订阅行业列表
   - 切换 → `setSearchParams({ industryId: id })`
   - 底部: "添加行业订阅 →" link → `/settings`
   - 埋点 #69 `industry_picker_switched`

7. **路由配置更新** `frontend/src/App.jsx`
   - 新增 Brand Mode 9 条路由: `/brand/overview`, `/brand/visibility`, `/brand/topics`, `/brand/sentiment`, `/brand/citations`, `/brand/products`, `/brand/products/:productId`, `/brand/diagnostics`, `/brand/reports`
   - 新增 Industry Mode 4 条路由: `/industry/overview`, `/industry/ranking`, `/industry/topics`, `/industry/knowledge-graph`
   - **11 条 301 redirect** (§4.6-IA-v2.E): `/dashboard` → `/brand/overview`, `/brands/:id` → `/brand/overview?brandId=:id`, `/brands/:id/products/:pid` → `/brand/products/:pid`, `/topics` → `/brand/topics`, `/industries` → `/industry/overview`, `/knowledge-graph` → `/industry/knowledge-graph`, `/diagnostics` → `/brand/diagnostics`, `/reports` → `/brand/reports`, `/brands/:id/simulator` → `/brand/citations?sub=simulator`, `/brands/:id?tab=content-gap` → `/brand/citations?sub=content-gap`, `/brands/:id?tab=products` → `/brand/products`
   - 根路径 `/` → `/brand/overview` (已登录) 或 `/` Landing (未登录)

8. **i18n 新增命名空间** `frontend/src/i18n/messages.*.json`
   - `topbar.*`: mode_brand, mode_industry, search_placeholder, alerts_title, alerts_empty, alerts_view_all, user_menu_settings, user_menu_logout
   - `sidebar.brand_*`: overview, visibility, topics, sentiment, citations, products, competitors, diagnostics, reports, section_analysis, section_operations
   - `sidebar.industry_*`: overview, ranking, topics, knowledge_graph, section_analysis, switch_to_brand
   - `brand_picker.*`: search_placeholder, primary_badge, view_all_brands
   - `industry_picker.*`: select_industry, add_subscription
   - zh-CN + en-US 双语全覆盖
   - ⚠️ 禁止 value 出现 "Mode" / "sub-view" / "Brand Mode" / "Industry Mode"

9. **测试**:
   - L1 Harness (5 条):
     ```bash
     # H1: Mode 不落 localStorage
     grep -r 'localStorage.*mode' frontend/src --include='*.jsx' --include='*.js' | grep -v node_modules
     # 预期: 零输出

     # H2: 侧栏 Brand Mode 9 项必须存在
     grep -c '/brand/overview\|/brand/visibility\|/brand/topics\|/brand/sentiment\|/brand/citations\|/brand/products\|/brand/competitors\|/brand/diagnostics\|/brand/reports' frontend/src/layouts/DashboardLayout.jsx
     # 预期: ≥ 9

     # H3: 侧栏 Industry Mode 4 项必须存在
     grep -c '/industry/overview\|/industry/ranking\|/industry/topics\|/industry/knowledge-graph' frontend/src/layouts/DashboardLayout.jsx
     # 预期: ≥ 4

     # H4: 11 条 legacy redirect 已配置
     grep -c 'Navigate.*replace\|redirect' frontend/src/App.jsx
     # 预期: ≥ 11

     # H5: i18n 禁 "Brand Mode" 开发语
     grep -rn "Brand Mode\|Industry Mode" frontend/src/i18n
     # 预期: 零输出
     ```
   - L2 Vitest: `useAppMode` hook (各路径返回正确 mode) + ModeToggle (渲染 + active 态)
   - L4 视觉基线: `layout-brand-mode.png`, `layout-industry-mode.png`, `mode-toggle-brand-active.png`, `mode-toggle-industry-active.png`

**交付物**:
- `useAppMode.js` hook
- `ModeToggle.jsx` + `AlertBell.jsx` + `UserMenu.jsx` 组件
- `BrandPicker.jsx` + `IndustryPicker.jsx` 组件
- `DashboardLayout.jsx` 重构 (顶栏 + 双模侧栏)
- `App.jsx` 路由更新 (13 条新路由 + 11 条 redirect)
- i18n 全量 key (zh-CN + en-US)
- 测试 + 视觉基线

**完成标志 (T1')**:
- `npm run ci` 全绿
- `/brand/overview` 渲染 Brand Mode Shell (侧栏 9 项 + BrandPicker)
- `/industry/overview` 渲染 Industry Mode Shell (侧栏 4 项 + IndustryPicker)
- 点击 Mode Toggle 正确切换 URL + 侧栏
- `/dashboard` 301 到 `/brand/overview`
- H1-H5 Harness 全部达标

---

### Session T2' (ia-v2-S2): Brand Mode 5 个深度分析页实现

**目标**: 将 Brand Mode 的 5 个分析子页面从骨架升级为生产级深度分析页。这是 T1'-T5' 中**最大的 Session**, 实现 PRD §4.6-IA-v2 C.2.2 + 附录 §C.2.2a-§C.2.2e 的完整功能规格。

> ⚠️ 本 Session 同时覆盖 Overview / Topics / Diagnostics / Reports 的迁移, 但这 4 页内容已从 V1 迁移完成, **本 Session 重点是 5 个深度新页**: Visibility / Sentiment / Competitors / Citations / Products。

**前置**:
- T1' 完成 (DashboardLayout 双模 Shell 可用)
- **必读 PRD 章节**: §C.2.2a (Visibility) / §C.2.2b (Sentiment) / §C.2.2c (Competitors) / §C.2.2d (Citations) / §C.2.2e (Products)
- **必读锚点**: `docs/DESIGN_TOKENS.md` 全文 + CLAUDE.md §1 结构锚点 + §4 组件复用清单
- `ls frontend/src/components/` 确认已有组件 (避免重写)

**⚠️ 开工前 3 步** (CLAUDE.md §5 强制):
1. `cat docs/DESIGN_TOKENS.md`
2. 读本 Prompt 中点名的 5 个目标文件 + V1 对应实现 (`snapshot-before-ia-v2-7ed0bc5/frontend/src/pages/DashboardPage.jsx` + `BrandDetailPage.jsx`)
3. `ls frontend/src/components/` 确认组件库存

**任务清单**:

#### T2'.1 — 👁️ BrandVisibilityPage `/brand/visibility` (§C.2.2a)

现状: 160 行骨架, 2 KPI 卡 + 1 TrendChart + 1 competitor 表 + 3 position 卡.

目标: 7 区深度分析页.

**子任务**:

1.1 **Hero 双 KPI 卡** (区块 ①)
   - 复用 `BrandPanoramaPanel` 的 KPI 卡模式, 提取为独立 `KpiCard` 组件 (如尚未拆分)
   - 左卡: 提及率 (non-brand 口径), 大数字 + Δ pill + `MiniSparkline` + 按引擎 3 小柱
   - 右卡: SoV, 同上结构
   - Δ pill: 正 = `bg-themed-success`, 负 = `bg-themed-danger`, 零 = `bg-themed-muted`

1.2 **可伸缩筛选栏** (区块 ②)
   - 主筛选 (始终可见): 时间范围 + 引擎 + ProfileGroup (继承顶栏全局, 但可页内覆盖)
   - 扩展筛选 (折叠/展开): dimension 下拉 (品类/品牌/场景) + Intent 下拉 (informational/commercial/transactional/navigational)
   - "更多筛选" 按钮 + 活跃数角标 + 已选 tag 清除
   - 复用 `ProfileGroupFilter` + 新建 `DimensionIntentFilter`

1.3 **SoV 饼图 + 竞品象限散点图** (区块 ③)
   - 左半: Recharts `PieChart` (主品牌 + Top 4 竞品 + "其他"), 主品牌 accent 高亮, C3 约束 ("其他" ≤ 任一真实品牌)
   - 右半: Recharts `ScatterChart` + `ZAxis` — X=SoV, Y=情感, Z=引用份额; 主品牌 accent 色大圆, 竞品灰色; Hover tooltip; 点击跳 `/brand/overview?brandId=`
   - 两图 `grid grid-cols-1 md:grid-cols-2` 并排

1.4 **按引擎/按 Dimension 拆分柱图** (区块 ④)
   - Recharts `BarChart` grouped/stacked: X 轴=引擎或 dimension, Y=提及率, 3 色柱 (提及率 / SoV / 引用)
   - Toggle: "按引擎" / "按维度" 切换

1.5 **PANO 综合趋势折线** (区块 ⑤)
   - 复用 `TrendChart`, 但 series 扩展为 V+S+R+A 四线 + PANO Score 粗线
   - Y 轴双轴: 左 % (V/S/R/A), 右 分值 (PANO)
   - 时间粒度: 日/周 toggle

1.6 **Top 10 未命中 Prompt** (区块 ⑥)
   - 按 "品牌未被提及的高流量 Prompt" desc 排序, 显示 Prompt 文本 + 引擎 + 日期 + "目标" badge
   - 每行可展开看完整 Response 摘要
   - 数据源: mock 新增 `VISIBILITY_UNMISSED_PROMPTS`

1.7 **提及位置分布** (区块 ⑦)
   - Recharts `BarChart` 水平: X=出现次数, Y=位置 (首段/中段/末段/未提及)
   - 数据源: `MENTION_POSITION_DATA`
   - 配色: 首段 = success, 中段 = accent, 末段 = warning, 未提及 = muted

**mock 数据**: 现有 `SOV_DATA`, `MENTION_TREND_BY_ENGINE`, `MENTION_POSITION_DATA`, `COMPETITOR_MENTION_MATRIX`, `TREND_DATA` 应满足大部分需求。如缺数据, 在 `mock.js` 末尾新增, 命名 `VISIBILITY_*` 前缀。

---

#### T2'.2 — 💭 BrandSentimentPage `/brand/sentiment` (§C.2.2b)

现状: 121 行骨架, DonutChart + keyword badges + TrendChart + 6 样本.

目标: 7 区深度分析页.

**子任务**:

2.1 **Hero 情感 + PanoRing** (区块 ①)
   - 左: `PanoRing` (复用现有, score 传当前品牌 sentimentScore)
   - 右: 情感 KPI 卡 (综合情感分 + Δ + MiniSparkline) + 正面/负面/中性占比 3 数字

2.2 **情感分布饼 + 按引擎堆叠柱** (区块 ②)
   - 左: `DonutChart` (正面/负面/中性/混合 4 片, 复用现有)
   - 右: Recharts `BarChart` stacked — X=引擎, Y=response 数, 3 色堆叠 (positive/negative/neutral)

2.3 **情感趋势折线** (区块 ③)
   - 复用 `TrendChart`, series = 3 引擎各自的情感分 (0-1), yFormat `v => Math.round(v*100)+'%'`
   - 时间粒度: 日/周 toggle
   - 数据源: `SENTIMENT_TREND_BY_ENGINE`

2.4 **情感归因 — Topic 下跌驱动** (区块 ④)
   - "哪些 Topic 拉低了情感?" 卡片列表
   - 按 Topic 的 negative response 占比 desc, 前 5 个
   - 每卡: Topic 名 + 负面 response 数 + 典型负面摘要 + "查看详情 →" 跳 `/brand/topics?topicId=`
   - **新 mock 数据**: `SENTIMENT_TOPIC_ATTRIBUTION` (topicId, topicName, negativeCount, negativeRatio, sampleSnippet)

2.5 **正面/负面关键词** (区块 ⑤)
   - 复用现有 keyword badges 结构但升级: 点击关键词 → 筛选下方 Response 样本
   - 正面 `Badge tone="success"`, 负面 `Badge tone="danger"`
   - 数据源: `SENTIMENT_KEYWORDS`

2.6 **竞品情感对比矩阵** (区块 ⑥)
   - Recharts `ScatterChart`: X=提及量, Y=正面占比, Z(气泡大小)=负面占比
   - 或退化为 Table: 品牌 / Volume / Positive% / Negative%
   - 数据源: `COMPETITOR_SENTIMENT_BUBBLE`
   - 主品牌行高亮 `bg-themed-accent-soft`

2.7 **Response 样本** (区块 ⑦)
   - 复用现有样本卡片, 增加: polarity filter (正面/负面/全部 tabs), 点击 "查看完整 →" 展开 Dialog
   - 数据源: `SENTIMENT_DETAIL_LIST`

---

#### T2'.3 — ⚔️ BrandCompetitorsPage `/brand/competitors` (§C.2.2c)

现状: 168 行骨架, HorizontalBar + authority 表 + same-group 列表 + sentiment 表.

目标: 7 区深度分析页.

**子任务**:

3.1 **SoV × 情感四象限气泡图** (区块 ①)
   - Recharts `ScatterChart` + `ZAxis` + `ReferenceArea` 四象限背景:
     - 右上 (高 SoV + 高情感) = "领导者" 浅绿
     - 左上 (低 SoV + 高情感) = "口碑派" 浅蓝
     - 右下 (高 SoV + 低情感) = "争议品牌" 浅黄
     - 左下 (低 SoV + 低情感) = "弱势品牌" 浅灰
   - Z(气泡大小) = 引用份额
   - 主品牌 accent 色, 竞品用各自 brand color 或灰色
   - Hover tooltip: 品牌名 + SoV + 情感 + 引用份额
   - 数据源: `COMPETITOR_SENTIMENT_BUBBLE` + `BRANDS`

3.2 **Authority Radar 5 维雷达图** (区块 ②) — **从 Table 升级为真图表**
   - Recharts `RadarChart` + `PolarGrid` + `PolarAngleAxis` + `PolarRadiusAxis`
   - 5 维: 官方引用(official) / 权威媒体(authority) / KOL(kol) / UGC(ugc) / 来源多样性(diversity)
   - 主品牌: accent 色粗线 (strokeWidth=2, fillOpacity=0.15)
   - 竞品: 灰色细线 (strokeWidth=1, fillOpacity=0.05)
   - Legend 列出所有品牌, 可点击 toggle 显示/隐藏
   - 数据源: `AUTHORITY_RADAR_DATA`
   - **复用**: `components/citation/AuthorityRadarChart.jsx` (如已有雷达逻辑则扩展; 如只有表格版则重构为 Recharts RadarChart)

3.3 **多维对比表** (区块 ③)
   - TanStack Table (带排序 + 固定首列)
   - 列: 品牌 / PANO Score / SoV / 情感 / 引用份额 / 行业排名 / Δ30d
   - 主品牌行高亮 `bg-themed-accent-soft`
   - 每列可 click sort, 默认按 PANO desc

3.4 **竞品 PANO 趋势对比** (区块 ④)
   - `TrendChart` (复用), series = 主品牌 + Top 4 竞品各一条线
   - 时间范围: 近 30d
   - 主品牌 accent + 竞品灰阶
   - **新 mock 数据**: 每个 `BRANDS` 条目增加 `sparkPano: Array(14)` (竞品趋势对比用)

3.5 **SoV 对比柱图** (区块 ⑤)
   - 升级现有 `HorizontalBar` 为 Recharts `BarChart` horizontal — 每品牌一条, 主品牌 accent
   - 或保留 HorizontalBar 但增加 animation + tooltip

3.6 **Same-Group 共享域** (区块 ⑥)
   - 复用 `SameGroupAndAcquisition.jsx` 的共享域部分
   - 增加 Tier badge + "覆盖/未覆盖" 标识
   - 数据源: `SAME_GROUP_SHARED`

3.7 **Acquisition 事件时间轴** (区块 ⑦, v1.1 placeholder)
   - 简单时间轴: 日期 + 事件描述 (集团并购/合资/投资)
   - MVP: 展示 `ACQUISITION_EVENTS` mock 数据
   - v1.1 badge 标注 "即将上线"

---

#### T2'.4 — 🔗 BrandCitationsPage `/brand/citations` (§C.2.2d)

现状: 200 行, sub-tab 结构可用, overview 中等, content-gap 和 simulator 为 placeholder.

目标: 4 个 sub-tab 全部填实.

**子任务**:

4.1 **概览 Sub-tab** (sub=overview, 区块 ①-④)
   - ① Authority Share 时序图: 复用 `AuthorityShareTimeSeries.jsx` (已有), 传 `AUTHORITY_SHARE_SERIES`
   - ② 来源构成饼图: 复用 `DonutChart`, 传 `CITATION_SOURCE_COMPOSITION`
   - ③ Top 域名 + Top 页面列表: 保留现有实现, 增加 Tier badge 排序 + "覆盖/丢失/新增" 状态标签
   - ④ 按引擎 Citation 趋势: `TrendChart`, series = 3 引擎, 数据 `CITATION_TREND_BY_ENGINE`

4.2 **内容差距 Sub-tab** (sub=content-gap, 区块 ⑤-⑥) — **从 placeholder 升级**
   - ⑤ 复用 `ContentGapPanel.jsx` (已有): 品牌被提及但未被引用归因的 Topic 列表, 按 gap 大小 desc
   - ⑥ 页面类型对比堆叠柱图: Recharts `BarChart` stacked — X=页面类型(产品页/百科/评测/新闻/论坛), Y=引用数, 品牌 vs 竞品均值双色堆叠
   - 数据源: `CONTENT_GAP_TOPICS`, `CONTENT_GAP_PAGE_TYPE_DISTRIBUTION`

4.3 **PR 目标 Sub-tab** (sub=pr-targets, 区块 ⑦-⑨) — **从 placeholder 升级**
   - ⑦ 复用 `PrTargetsPanel.jsx` (已有): `PR_TARGETS` 排序表, 含 domain / tier / pr_score / covered 列
   - ⑧ Tier 2 覆盖矩阵: 热力图/Grid — 行=Tier 2 域名, 列=品牌(主+竞品), 单元格 ✓/— + 颜色
   - ⑨ KOL 评分卡: 3 张卡片, 每张 = KOL 名 + Shannon 多样性分 + 覆盖引擎列表 + 近期引用数
   - 数据源: `PR_TARGETS`, `TIER2_COVERAGE_MATRIX`, `KOL_SCORECARDS`

4.4 **模拟器 Sub-tab** (sub=simulator, 区块 ⑩-⑫) — **从 placeholder 升级**
   - ⑩ Tier delta 滑杆组: 4 个滑杆 (Tier 1-4), 每个 range [-5, +10], 步长 1, 显示当前 delta 值
   - ⑪ 预设场景按钮组: 3 个预设 (保守/中等/激进), 点击自动设置滑杆值 + label 说明
   - ⑫ PANO 预估结果卡: 实时计算 `PANO_A_new = Σ(tier_weight × (baseline + delta) × authorityConfidence)`, 显示 before / after / Δ
   - 底部 CTA: "获取定制优化方案 →" (跳咨询表单 Phase 2, MVP 用 mailto)
   - 数据源: `SIMULATOR_BASELINE`, `SIMULATOR_PRESETS`
   - **注意**: `basePriceByTier` 为 Admin 参数, MVP mock 值写在 `SIMULATOR_BASELINE.basePriceByTier` 中, 不硬编码在组件里

---

#### T2'.5 — 📦 BrandProductsPage `/brand/products` (§C.2.2e)

现状: 120 行骨架, BCG 用 Card 文字象限, 简单 table.

目标: 4 区可视化丰富的产品分析页.

**子任务**:

5.1 **BCG 气泡矩阵** (区块 ①) — **从文字卡升级为真散点图**
   - Recharts `ScatterChart` + `ZAxis` + `ReferenceArea` 四象限:
     - X = 产品 SoV (or mentionRate)
     - Y = 近 30d 环比增长率 (trend)
     - Z (气泡大小) = 提及绝对次数
   - 四象限背景色: 明星(右上, 浅绿) / 问题(左上, 浅黄) / 金牛(右下, 浅蓝) / 瘦狗(左下, 浅灰)
   - 气泡标签 = 产品名 (Recharts `LabelList`)
   - Hover tooltip: 产品名 + SoV + trend + 提及数
   - 点击气泡跳 `/brand/products/:productId?brandId=`
   - 数据源: `PRODUCTS` (按 brandId 过滤), 需要 `mentionCount` 字段 (mock 中如无则新增)

5.2 **产品趋势 Sparkline Grid** (区块 ②)
   - 3×N grid 卡片, 每卡: 产品名 + SoV 大数字 + `MiniSparkline` (近 14d 趋势) + Δ pill
   - 按 SoV desc 排列, 最多 9 张
   - **新 mock 数据**: 每产品需 `sparkData: number[]` (14 点), 如 PRODUCTS 中无此字段则新增

5.3 **产品列表 TanStack Table** (区块 ③)
   - 列: 产品名 / 品类 / 提及率% / SoV% / 情感% / 趋势 (Sparkline 内嵌) / 行业排名
   - 排序: 所有数值列可 click sort, 默认 SoV desc
   - Sparkline 内嵌: 每行的"趋势"列渲染 `MiniSparkline` (width=80 height=24), **C1 约束: 宽高用 string '100%' 或固定小像素, 不锁父容器**
   - 分页: 如产品 > 10 则分页 (TanStack Table pagination)
   - 点击行跳 `/brand/products/:productId?brandId=`

5.4 **产品关系快照** (区块 ④)
   - D3.js force simulation 小图 (300px 高): 节点 = 产品, 边 = 关系 (COMPETES_WITH 红虚线 / SUBSTITUTES 蓝实线 / PAIRS_WITH 绿实线 / UPGRADES_TO 箭头 / BUDGET_ALT_OF 橙虚线)
   - 当前品牌产品高亮, 其余灰色
   - Hover 节点: tooltip 显示产品名 + 关系类型
   - 如产品数 < 3, 不渲染此区块 (条件渲染)
   - 数据源: `PRODUCT_RELATIONS` (mock 中已有)

---

#### T2'.6 — Mock 数据补全

统一在 `frontend/src/data/mock.js` 末尾新增本 Session 所需的 mock 数据:

- `SENTIMENT_TOPIC_ATTRIBUTION` — 5 条 (topicId, topicName, negativeCount, negativeRatio, sampleSnippet)
- `VISIBILITY_UNMISSED_PROMPTS` — 10 条 (promptText, engine, date, volume, mentionRate=0)
- 每个 `PRODUCTS` 条目增加 `sparkData: Array(14)` + `mentionCount: number`
- 每个 `BRANDS` 条目增加 `sparkPano: Array(14)` (竞品趋势对比用)
- 确保已有 export 的字段完整性 (无 undefined 炸裂)

---

#### T2'.7 — 通用组件新增/扩展

- `KpiCard.jsx` (如未独立拆出): 从 `BrandPanoramaPanel` 提取, props = { label, value, delta, sparkData, subMetrics[] }
- `DimensionIntentFilter.jsx`: 扩展筛选区的 dimension + intent 下拉
- `CompetitorQuadrantChart.jsx`: 封装 ScatterChart+ZAxis+ReferenceArea 四象限, 可复用于 Visibility + Competitors + Products (BCG)
- `TimeGranularityToggle.jsx`: 日/周切换, Segmented Control

---

#### T2'.8 — Brand Mode `/brand/topics` 挂载 Topic × Intent 共享矩阵 (2026-04-21 v3.2)

**背景**: Frank 2026-04-21 反"Topic × Intent 交叉矩阵这个挺好, 是不是也可以放到品牌这个地方". 组件原路径 `components/industry/IndustryTopicIntentMatrix.jsx`, 内部仅依赖 `topic.topicName / topic.mentionCount` + `topicIntentBreakdown(topic)`, 零 brand 上下文 → 可直接跨 Mode 复用, 无需 fork 或 prop 扩展。

**动作**:

1. **组件 `git mv` 到共享路径**:
   ```bash
   git mv frontend/src/components/industry/IndustryTopicIntentMatrix.jsx \
          frontend/src/components/topics/TopicIntentMatrix.jsx
   ```
   - 默认导出名重命名: `IndustryTopicIntentMatrix` → `TopicIntentMatrix`
   - JSDoc 更新: 声明 Mode-agnostic, 列出两个 Mode 调用点 (`/brand/topics` TopicsView + `/industry/topics` 段 ④)

2. **Brand Mode 挂载 (`frontend/src/pages/TopicsPage.jsx` 的 `TopicsView` 子视图)**:
   ```jsx
   import TopicIntentMatrix from '../components/topics/TopicIntentMatrix';
   import { INDUSTRY_TOPIC_HEATMAP } from '../data/mock';

   // 在 TopicsView 的 ProfileGroupSampleWarning 与 4-stat grid 之间插入:
   <TopicIntentMatrix
     topics={INDUSTRY_TOPIC_HEATMAP}
     limit={8}
   />
   ```
   - **数据源 MVP**: 沿用 `INDUSTRY_TOPIC_HEATMAP` Top 8 (字段正确: `topicName` / `mentionCount` / `isEmerging`)
   - **Phase 2**: 改为 `filterTopicsByPrimaryBrand(TOPICS, activeProject.primaryBrandId)` — 按主品牌覆盖的 Topic 子集渲染, 真实 Prompt.intent 聚合
   - **MVP 不挂 onClick** — 后续可扩展跳到 Layer 2 Prompts 并预筛 dominant Intent

3. **Industry Mode 同步更新 `IndustryTopicsPage.jsx`**:
   ```jsx
   // 将旧 import
   import IndustryTopicIntentMatrix from '../../components/industry/IndustryTopicIntentMatrix';
   // 改为
   import TopicIntentMatrix from '../../components/topics/TopicIntentMatrix';
   // JSX 同步改名: <IndustryTopicIntentMatrix ... /> → <TopicIntentMatrix ... />
   ```

**Harness**:
```bash
# 共享组件物理存在
test -f frontend/src/components/topics/TopicIntentMatrix.jsx || echo "T2'.8 FAIL: TopicIntentMatrix missing"

# 旧路径必须已删除 (防止 git mv 只复制未删除)
test ! -f frontend/src/components/industry/IndustryTopicIntentMatrix.jsx || echo "T2'.8 FAIL: old path still exists"

# Brand Mode TopicsPage 必须 import
grep -q "components/topics/TopicIntentMatrix" frontend/src/pages/TopicsPage.jsx || echo "T2'.8 FAIL: Brand Mode not mounted"

# Industry Mode IndustryTopicsPage 必须 import 新路径 (不能还引用旧路径)
grep -q "components/topics/TopicIntentMatrix" frontend/src/pages/industry/IndustryTopicsPage.jsx || echo "T2'.8 FAIL: Industry Mode not updated"
grep -q "components/industry/IndustryTopicIntentMatrix" frontend/src/pages/industry/IndustryTopicsPage.jsx && echo "T2'.8 FAIL: Industry Mode still imports old path"
```

**PRD 交叉引用**: §4.2.5 (Brand Topics 第 1 层 补充) + §4.6.1g v3.2 段 ④

**测试**:
- Vitest smoke: Brand Mode TopicsView 挂载后 `<TopicIntentMatrix>` 能渲染 ≥ 4 个 Intent 色块
- 视觉基线: `topics-view.png` 重拍 (原基线不含 Topic × Intent 面板, 会 drift)

---

**测试** (T2' 整体):
- L1 Harness:
  ```bash
  # 5 页文件必须存在且非空
  for f in BrandVisibilityPage BrandSentimentPage BrandCompetitorsPage BrandCitationsPage BrandProductsPage; do
    wc -l frontend/src/pages/brand/${f}.jsx
  done
  # 预期: 每个 ≥ 200 行

  # C1: Sparkline 默认值禁止数字像素
  grep -nE "(width|height)\s*=\s*[0-9]+\s*[,}]" frontend/src/components/charts/MiniSparkline.jsx
  # 预期: 零输出

  # C4: Sentiment 展示禁止 .toFixed(2) 小数
  grep -rnE "sentiment.*\.toFixed\(2\)|\.toFixed\(2\).*sentiment" frontend/src/pages --include='*.jsx' | grep -v '// C4-exempt'
  # 预期: 零输出

  # C5: Sparkline 禁止锯齿模数
  grep -rnE "spark[A-Za-z]+\s*=.*i\s*%\s*[0-9]+\s*===\s*0\s*\?" frontend/src/pages --include='*.jsx'
  # 预期: 零输出

  # 禁止内联 hex 颜色 (品牌 logo SVG 除外)
  grep -rnE "fill=['\"]#[0-9a-fA-F]{3,8}['\"]|stroke=['\"]#[0-9a-fA-F]{3,8}['\"]" frontend/src/pages --include='*.jsx' | grep -v 'logo\|Logo\|icon\|Icon'
  # 预期: 零输出

  # 禁止开发者约束泄漏到 i18n
  grep -rnE '本页(只|不)做|只回答|不承担|详情请进入|请去.*查看|严禁|🚫|⚠️ ?(本页|本段)' frontend/src/i18n --include='*.json'
  # 预期: 零输出
  ```
- L2 Vitest: 每页至少 1 个 render smoke test (mount + 断言关键元素存在)
- L4 视觉基线: 5 页各 1 张全页截图 (`brand-visibility.png`, `brand-sentiment.png`, `brand-competitors.png`, `brand-citations-overview.png`, `brand-products.png`)
- L4 E2E: 导航到 5 页各自 URL, 断言 H1 标题 + 至少 3 个 Card 渲染

**交付物**:
- 5 个深度分析页 JSX (每个 250-500 行)
- 4+ 新增通用组件
- mock.js 数据补全
- i18n key 新增 (5 × ~30 key = ~150 key, zh-CN + en-US)
- 测试 + 基线

**完成标志 (T2')**:
- `npm run ci` 全绿
- 5 页均可在浏览器中渲染完整内容 (非 placeholder)
- 所有 Harness grep 零输出
- 视觉基线已保存
- mock 数据无 undefined / NaN 报错

---

### Session T3' (ia-v2-S3): Industry Mode 4 页实现

**目标**: 实现 Industry Mode 的 4 个分析页, 使 `/industry/*` 路由可用。Industry Mode 是"行业宏观横向视角", 与 Brand Mode 的"单品牌纵深"互补。

**前置**:
- T1' (Shell 可用) + T2' (Brand Mode 页面完成, 共享组件已就绪)
- PRD §4.6-IA-v2 C.3.2 + §4.6.1e (Plan S 行业总览) + §4.6.1d-KG (知识图谱)
- CLAUDE.md 结构锚点中的 4 个 Industry 页参考

**任务清单**:

1. **IndustryOverviewPage** `/industry/overview` (§4.6-IA-v2.C.3.2 + §4.6.1e **Plan S v3 6 段式**)
   - **演化脉络**: v1 (5 段) → v2 (8 段, 追加集团版图/Topic 热度/Top 引用源) → **v3 (6 段, 本次生效版)**: Frank 反馈 "你可以考虑把第一页拆分一下", 段 ⑦ Topic 热度 Scatter 迁到 §4.6.1g Topics 页 (作新段 ③), 段 ⑧ Top 10 引用源 迁到 §4.6.1f Ranking 页 (作新段 ⑧)。本页保留最适合 "行业级横截面" 的 6 段。
   - **v3 六段结构**:
     - ① 筛选栏: 复用 `<BrandAnalysisFilterBar>` (时间 + 引擎 + Profile Group), Sticky top, URL state via `useBrandAnalysisFilters`
     - ② 行业 Hero: 行业名 + 覆盖品牌数 / 活跃 Topic 数 / 品类数 三 count + 近 30d 全行业 Response 总数
     - ③ **5 KPI IQR 箱线 (本页独有)**: 5 张箱线卡 (提及率/SoV/情感/引用份额/排名), 每卡 P25/P50/P75 + 主品牌 ▲ marker + "距行业中位数" 文案. IQR 走 `lib/industry/statistics.js` 的 `computeIQR` (唯一真相源, §G.3 harness 拦截)
     - ④ Top 10 Leaderboard + SoV Pie: 左表 (TanStack Table, 行 click → `/brand/overview?brandId=:id`) + 右饼 (Top 6 + 其他, §DESIGN_TOKENS C3 约束)
     - ⑤ 行业趋势 + 异动 Top 3: 双线 LineChart (行业均值 + 主品牌) + Top 3 异动卡 (按 `Math.abs(change)` desc, 正负色区分)
     - ⑥ **集团版图**: `aggregateByGroup(BRANDS)` 按 `parentCompany` 聚合, Top 5 集团卡 + "其他"; 每卡: 集团名 / 旗下品牌数 / 合计 SoV / 最大品牌; 点击卡展开 modal 显示全部旗下品牌
   - **数据源 (零新增 mock)**:
     - 段 ②③④⑤: 从 `BRANDS.filter(b => b.industryId === id)` 实时派生 (IQR / 排行 / SoV / 异动)
     - 段 ⑥: `BRANDS.parentCompany` 字段 groupBy (已存在, 无需 mock 扩展)
   - **v3 瘦身动作**: IndustryOverviewPage.jsx 必须移除 v2 遗留的 `<IndustryTopicHeatScatter>` / `<IndustryTopCitationDomains>` JSX + 对应 import + `INDUSTRY_TOPIC_HEATMAP` / `TOP_CITED_DOMAINS` import (迁到新宿主页); 两个组件文件本身保留 (被 Topics/Ranking 页新引用)
   - **遗留清理 (v2 已完成, v3 无追加动作)**: mock.js 的 `INDUSTRY_KPI_DISTRIBUTION` / `INDUSTRY_TRENDING_EVENTS` 已在 v2 删除
   - **组件清单 (v3: 7 个 Industry 组件 + 1 statistics)** — 见 PRD §4.6.1e.H
     - `IndustryHero` / `IndustryDistributionCard` / `IndustryLeaderboardTable` / `IndustrySovPie` / `IndustryTrendChart` / `IndustryMoversRow` / `IndustryGroupMap` + `lib/industry/statistics.js`
     - ⚠️ 本页**不再** import `IndustryTopicHeatScatter` / `IndustryTopCitationDomains` (迁出)

2. **IndustryRankingPage** `/industry/ranking` (§4.6-IA-v2.C.3.2 + **§4.6.1f 深度扩展**)
   - **背景 (2026-04-20)**: Frank 反馈"除 Overview 外三 tab 敷衍 + broken field reference (b.primaryName / b.isPrimary / b.categoryName 都不存在)". 本页从"Multi-tab 单列排序表" 升级为 "**多口径交叉深挖**" 8 段结构, 严格区别于 Overview 段 ④ 的 "Top 10 静态快照"。
   - **与 Overview 段 ④ 的边界**:
     - Overview 段 ④: 单一 KPI 排序 + SoV 饼图 (一眼看谁领跑)
     - Ranking: 多口径交叉 / 动态趋势 / 引擎分位 / 赛道分层 (结构化深挖, 支持"为什么 / 谁在变")
   - **八段结构** (见 PRD §4.6.1f.B):
     - ① 筛选栏: `<BrandAnalysisFilterBar>` sticky (C10-1 必装)
     - ② **Ranking Hero + "我的位置" Panel**: 行业名 + 覆盖品牌数 / 集团数 / 平均 PANO 三 count; 主品牌存在时并列 "我综合 #N / SoV #N / 引用 #N / 情感 #N + 近 30d ±N 位 + 最弱维度"
     - ③ **Tier 分层 Breakdown**: 4 档 (Top 3 / 4-10 / 11-25 / 26+), 高度按档内合计 SoV 等比; Tier 1 高亮, Tier 4 浅灰
     - ④ **多指标交叉排名矩阵**: Top 15 品牌 × (PANO / SoV / 引用 / 情感) 4 列排名 + "排名离散度 σ" 列 (rankDispersion helper); 主品牌行高亮; hover 显示 Radar mini chart
     - ⑤ **30d 排名异动 Top 5 涨/跌**: 上涨 5 / 下跌 5 两列并排; 每卡: Δ (from #M → #N) + 30 点 sparkline (Y 倒置) + 环比 PANO
     - ⑥ **引擎分位矩阵**: Top 10 品牌 × 3 引擎 heatmap, 色带 `--color-heatmap-seq-0..5`, 行 click 跳 `/brand/overview?brandId=:id&engines=:engine`
     - ⑦ **赛道分层 Ranking**: 按 `positioning` 分 3 列 (国际高端 / 大众高端 / 小众-新锐), 每列 Top 5
     - ⑧ **Top 10 引用源** (v3 从 Overview 迁入): 复用 `<IndustryTopCitationDomains>` + `TOP_CITED_DOMAINS` mock
   - **数据派生 (零新增 mock)**: 新增 3 个 `lib/industry/statistics.js` helper:
     - `rankingDelta30d(brand)` — hash `brand.id` seed 合成 `{ rankFrom, rankTo, trend[30], primaryDriver }`, 围绕 `b.ranking` ±5 位
     - `rankingByEngine(brand)` — hash seed 合成 `{ chatgpt, doubao, deepseek }` 3 值, 都围绕 `b.ranking` ±3 位
     - `rankDispersion(brand, allBrands, kpiFields)` — 对 4 KPI 分别排名, 计算 rank 数组标准差
     - 段 ⑧: 直接复用 `TOP_CITED_DOMAINS`, "我是否被引用" 由 `brandsAttributed.includes(primaryBrandId)` 实时算
   - **字段 bug 修复 (硬拦截)**: 禁 `b.primaryName` / `b.isPrimary` / `b.categoryName` (不存在字段, §4.6.1f.D grep #4); 禁 `Math.round(v * 100)` 应用 sov/citationShare (已 0-100, grep #5)
   - **组件清单 (6 新 + 1 复用)**:
     - `IndustryRankingHero` (段 ②) / `IndustryTierBreakdown` (段 ③) / `IndustryMultiMetricMatrix` (段 ④) / `IndustryRankingMoversGrid` (段 ⑤) / `IndustryEngineRankingMatrix` (段 ⑥) / `IndustrySegmentRanking` (段 ⑦)
     - 复用: `IndustryTopCitationDomains` (段 ⑧, 从 Overview v2 迁入)
   - **MVP 边界**: Tier 抽屉 / 引擎差异归因 / Admin 赛道维护全部 Phase 2 (§4.6.1f.G)

3. **IndustryTopicsPage** `/industry/topics` (§4.6-IA-v2.C.3.2 + **§4.6.1g v3.2 深度扩展**)
   - **演化脉络**: v1 (7 段含 Scatter + Coverage Heatmap) → v2 (7 段, 字段契约修复) → v3.1 (6 段, Frank 反"数据都是模拟的, 热度上并不科学" → 删 Topic Scatter + Hero/Drawer 绝对量卡 + Radar 删"N 次提及" + "Topics 热度"→"Topic 格局") → **v3.2 (5 段, 本次终态)**: Frank 反"Brand × Topic 覆盖矩阵和 Visibility 里面的矩阵有什么区别" → 识别 Industry Coverage Heatmap 与 Brand Mode `<BrandTopicHeatmap>` 回答同一问题 (brand × topic 覆盖强弱), Brand Mode 那张用真实 `mentionRate` 0-1, Industry 这张用 `brandTopicHits` 0-100 合成 ordinal, MVP mock 期保留后者没有语义增量 → 删除 Coverage Heatmap 段。同时 Frank 反"Topic × Intent 交叉矩阵这个挺好, 是不是也可以放到品牌这个地方" → 组件上移到 `components/topics/TopicIntentMatrix.jsx` 共享 Brand Mode `/brand/topics` (§4.2.5)。
   - **与 Brand Mode `/brand/topics` 的边界**:
     - Brand Mode: 单品牌纵深 (该品牌在各 Topic 的覆盖 / 情感 / Intent 分布), `<BrandTopicHeatmap>` 真实 `mentionRate` 色带
     - Industry Mode: 行业横截面 (谁是新兴 Topic / Topic 整体 Intent 格局), Coverage 维度由 Visibility 页承接
   - **五段结构** (v3.2 终态, 见 PRD §4.6.1g.B):
     - ① 筛选栏: `<BrandAnalysisFilterBar>` sticky
     - ② Topics Hero: 活跃 Topic 数 / 新兴 Topic 数 / 行业平均情感 **3 count** (v3.1 删"总提及量")
     - ③ **新兴 / 衰退 Topic 雷达**: 左列新兴 Top 5 (emergingScore desc, isEmerging=true) 金边; 右列衰退 Top 5 (emergingScore asc) 灰边; 卡面**仅**显示"首次出现 Xd / 降幅 N%" (v3.1 删"N 次提及"前缀); 点击卡展开段 ⑤ 抽屉
     - ④ **Topic × Intent 交叉矩阵 (共享组件)**: Top 8 Topic × 4 Intent 堆叠 100% 条 (informational/commercial/transactional/navigational), 尾列"主导 Intent" badge; **组件路径 `components/topics/TopicIntentMatrix.jsx` 共享给 Brand Mode `/brand/topics`**
     - ⑤ **Topic 详情抽屉** (600px Framer Motion 右滑): Topic 名 + dimension tag + **3 KPI 卡** (情感 / 覆盖品牌数 / 主导 Intent, v3.1 删"提及量") + 前 3 引用域 + 关联 Top 3 品牌 (`brandTopicHits` 排序) + "去 Brand Mode 看我的表现 →" CTA
   - **v3.2 删除段 (不再渲染)**:
     - ~~原段 ③ Topic 热度 Scatter~~ (v3.1 删)
     - ~~原段 ④ Brand × Topic Coverage Heatmap~~ (v3.2 删, 与 Visibility heatmap 数据语义重复)
   - **组件文件清理**:
     - `IndustryTopicHeatScatter.jsx` — v3.1 已 `rm` (不再引用)
     - `IndustryTopicCoverageHeatmap.jsx` — **v3.2 必须 `rm`** (不再引用)
     - `IndustryTopicIntentMatrix.jsx` — **v3.2 必须 `git mv`** 到 `components/topics/TopicIntentMatrix.jsx` (删除原路径, 新路径导出默认组件名 `TopicIntentMatrix`)
   - **数据派生 (零新增 mock)**: `lib/industry/statistics.js` 保留 3 个 helper:
     - `brandTopicHits(brand, topic)` — **v3.2 保留** (仍用于 Radar + Drawer 的 Top 3 品牌排序)
     - `emergingScore(topic)` — hash `topic.topicId` 合成: `isEmerging === true` 正值 (10-80), 否则负值 (-60 - 0)
     - `topicIntentBreakdown(topic)` — hash 合成 4 个占比 (informational/commercial/transactional/navigational), sum = 100
   - **字段 bug 修复 (硬拦截)**: 禁 `topic.title` / `topic.heat` / `topic.industryId` / `topic.categoryName` (§4.6.1g.D grep #2); 正确字段: `topic.topicName` / `topic.mentionCount` / `topic.dimension`
   - **Frank 2026-04-20 否决 (v3.1 起)**: 抽屉禁展示"典型 Prompt 样本"、Hero 禁展示"总提及量"、Radar 禁展示"N 次提及", 只展示聚合指标 + 相对排名 + 比较视觉
   - **组件清单 (v3.2: 3 Industry 专属 + 1 共享 + 1 statistics)**:
     - `IndustryTopicsHero` (段 ②) / `IndustryTopicEmergingRadar` (段 ③) / `IndustryTopicDetailDrawer` (段 ⑤)
     - 共享: `TopicIntentMatrix` (段 ④, 路径 `components/topics/`, Brand Mode `/brand/topics` 也消费)
     - 支持: `lib/industry/statistics.js`
     - 已删除: `IndustryTopicHeatScatter` (v3.1) / `IndustryTopicCoverageHeatmap` (v3.2) / `IndustryTopicIntentMatrix` (v3.2 `git mv`)
   - **MVP 边界**: 段 ③ 真实衰退识别 / 段 ④ 真实 Intent NLU 管道全部 Phase 2 (§4.6.1g.G); Phase 2 若复活 "cross-brand coverage scan" 必须用 Visibility 的 `mentionRate` 真实 0-1, 不得回退 `brandTopicHits` 合成 ordinal

4. **IndustryKnowledgeGraphPage** `/industry/knowledge-graph` (§4.6-IA-v2.C.3.2)
   - 迁移现有 `KnowledgeGraphPage.jsx` 内容到新路径
   - AntV G6 v5: Industry → Category → Brand → Product 4 层
   - 保持 CLAUDE.md 中 G6 8 个踩坑点 (radial / 不用 hover-activate / 放大胜利者 / shadowBlur / label 外置 / autoFit / 单一 composer / base style 显式 opacity)
   - 增加: 点击品牌节点 → popover (品牌名 + PANO Score + "查看详情 →" 跳 Brand Mode)
   - 数据源: `CATEGORIES`, `BRANDS`, `PRODUCTS`, `BRAND_RELATIONS`, `PRODUCT_RELATIONS`

5. **i18n 新增**: `industry_overview.*`, `industry_ranking.*`, `industry_topics.*`, `industry_kg.*` (zh-CN + en-US)

6. **测试**:
   - L1 Harness:
     ```bash
     # 4 页文件必须存在
     for f in IndustryOverviewPage IndustryRankingPage IndustryTopicsPage IndustryKnowledgeGraphPage; do
       wc -l frontend/src/pages/industry/${f}.jsx
     done
     # 预期: 每个 ≥ 100 行
     ```
   - L2 Vitest: 4 页 render smoke test
   - L4 视觉基线: 4 页各 1 张
   - L4 E2E: `tests/e2e/industry-mode.spec.ts` — 导航到 4 页, 断言 H1 + 核心内容

**交付物**:
- 4 个 Industry Mode 页面 JSX
- 知识图谱迁移 (从旧路径到新路径)
- mock 数据补全
- i18n 全量 key
- 测试 + 基线

**完成标志 (T3')**:
- `npm run ci` 全绿
- `/industry/overview` 渲染 **v3 6 段式** 行业总览 (① FilterBar / ② Hero / ③ 5 KPI IQR / ④ Top 10 + SoV / ⑤ 趋势+异动 / ⑥ 集团版图); 不再包含 Topic Scatter / Top 引用源
- `/industry/ranking` 渲染 **§4.6.1f 8 段** (Hero+我的位置 / Tier / 多指标矩阵 / 30d 异动 / 引擎分位 / 赛道分层 / Top 引用源); broken field reference 全部修复
- `/industry/topics` 渲染 **§4.6.1g v3.2 5 段** (FilterBar / Hero 3 cards / 新兴衰退雷达 / Topic×Intent 矩阵 [共享] / 详情抽屉 3 KPI); topic.title/heat/industryId/categoryName 全部修复; `IndustryTopicHeatScatter` (v3.1) + `IndustryTopicCoverageHeatmap` (v3.2) + `IndustryTopicIntentMatrix` (v3.2 `git mv`) 三文件从 `components/industry/` 物理删除
- `/industry/knowledge-graph` G6 图谱渲染
- 点击品牌名可跨 Mode 跳到 Brand Mode
- `IndustryTopCitationDomains` 组件被 Ranking 页引用, 不被 Overview 页引用 (v3 迁移已完成)
- `TopicIntentMatrix` (`components/topics/`) 同时被 `/industry/topics` 段 ④ 和 `/brand/topics` TopicsView 引用 (v3.2 跨 Mode 共享)

---

### Session T4' (ia-v2-S4): Onboarding + Route Guards + Auth-Required + 301 Redirects + 遗留清理

**目标**: (A) 实现 §4.6-IA-v2.F 的零 Project 态 Route Guard → `/onboarding` 4 步引导; (B) 落地 §4.1.1-gate Auth-Required; (C) 实现 11 条 301 redirect; (D) 清理废弃组件和路由。

**前置**:
- T1'-T3' 全部完成 (所有页面就绪)
- PRD §4.6-IA-v2.F (Onboarding) + §4.1.1-gate (Auth-Required)

**任务清单**:

1. **OnboardingPage** `/onboarding` (§4.6-IA-v2.F)
   - **独立页面, 无 App Shell** (不渲染 DashboardLayout)
   - 4 步引导:
     - Step 1: 选行业 (Grid 卡片, 最多选 3 个)
     - Step 2: 选主品牌 (搜索框 + 行业下品牌列表, 单选)
     - Step 3: 选竞品 (3-5 个, 多选 checkbox)
     - Step 4: 偏好 (语言 / 通知频率 / 关注 KPI)
   - 底部: 进度条 (1/4 → 4/4) + "上一步" / "下一步" / "完成" 按钮
   - 完成 → 创建 Project + navigate('/brand/overview')
   - 草稿逻辑: 中途退出 → localStorage 存草稿 (72h TTL), 下次 Route Guard 检测到 → 续上
   - Framer Motion: 步间横滑动效
   - i18n: `onboarding.*` (step1_title, step1_subtitle, step2_*, step3_*, step4_*, btn_prev, btn_next, btn_finish)
   - 埋点 #70 `onboarding_step_completed` (step_number, step_name, time_on_step_seconds)

2. **RequireAuth HOC** `frontend/src/components/guards/RequireAuth.jsx`
   - 未登录 → `/register?redirect=<encodeURIComponent(path+search)>`
   - 如 path 含 brandId → 附加 `&brandHint=<brandName>`
   - 发 Mixpanel #63 `auth_gate_redirect`

3. **RequireProject HOC** `frontend/src/components/guards/RequireProject.jsx`
   - 已登录 + `user.projects.length === 0` → `/onboarding`
   - 已登录 + 有草稿 Project → `/onboarding?resume=<draftId>`
   - 发 Mixpanel #70 `onboarding_redirect`

4. **Route Guard 串联** (App.jsx)
   - 所有 `/brand/*` + `/industry/*` 路由包裹: `<RequireAuth><RequireProject><Page /></RequireProject></RequireAuth>`
   - `/onboarding` 只包裹 `<RequireAuth>` (不检查 Project)
   - `/`, `/auth`, `/register` — 无 guard

5. **301 Redirect 实现** (App.jsx)
   - 11 条 (§4.6-IA-v2.E): 用 React Router `<Navigate to={...} replace />` 组件
   - 每条 redirect 保留 search params 透传
   - 完整映射表:
     ```
     /dashboard            → /brand/overview
     /brands/:id           → /brand/overview?brandId=:id
     /brands/:id/products/:pid → /brand/products/:pid?brandId=:id
     /brands/:id/simulator → /brand/citations?sub=simulator&brandId=:id
     /topics               → /brand/topics
     /industry             → /industry/overview
     /industries/:id       → /industry/overview?industryId=:id
     /knowledge-graph      → /industry/knowledge-graph
     /diagnostics          → /brand/diagnostics
     /reports              → /brand/reports
     /project-settings     → /settings?section=project
     ```

6. **废弃组件清理**:
   - 删除 `DashboardEmptyState.jsx` (E1 废除)
   - 删除 `ProjectRequiredBanner.jsx` (E4 废除)
   - 删除 `LandingNavQuickCreateButton.jsx` 的三态逻辑 (简化为普通 Login/Register)
   - 删除旧路由: `/dashboard`, `/brands/:id` (4 tab 版), `/diagnostics` (跨品牌聚合)

7. **埋点**:
   - #63 `auth_gate_redirect` (RequireAuth 触发)
   - #64 `brand_hint_register_success` (注册成功 + brandHint 非空)
   - #70 `onboarding_step_completed` (step_number, step_name, time_on_step_seconds)
   - 弃用 #44 `landing_quick_create_click`, #45 的 `brand_direct_anonymous` source, #46 `gated_banner_cta_click`

8. **测试**:
   - L4 E2E: `tests/e2e/onboarding.spec.ts` — 新用户登录 → 重定向 /onboarding → 完成 4 步 → 到达 /brand/overview
   - L4 E2E: `tests/e2e/auth-gate.spec.ts` — 匿名访问 /brand/overview → 重定向 /register?redirect=...
   - L4 E2E: `tests/e2e/redirects.spec.ts` — 11 条旧 URL 全部 → 正确新 URL
   - L1 Harness:
     ```bash
     # 废弃组件已删除
     test ! -f frontend/src/components/empty/DashboardEmptyState.jsx && echo "OK"
     test ! -f frontend/src/components/ProjectRequiredBanner.jsx && echo "OK"
     
     # 弃用事件不再被 track
     grep -r 'landing_quick_create_click\|gated_banner_cta_click' frontend/src --include='*.jsx' --include='*.js' | grep -v node_modules
     # 预期: 零输出
     ```
   - L4 视觉基线: `onboarding-step1.png` ~ `onboarding-step4.png`

**交付物**:
- `OnboardingPage.jsx` (4 步引导)
- `RequireAuth.jsx` + `RequireProject.jsx` HOC
- `App.jsx` 路由更新 (guard 包裹 + 11 redirect)
- 废弃组件删除
- 埋点新增 + 弃用
- 测试 + 基线

**完成标志 (T4')**:
- `npm run ci` 全绿
- 新用户流: register → /onboarding → 完成 → /brand/overview ✓
- 匿名访问任何 data 页 → /register ✓
- 11 条 legacy URL 全部正确 redirect ✓
- 废弃组件文件不存在 ✓

---

### Session T5' (ia-v2-S5): 全局打磨 + Harness 全量验证 + 视觉回归基线 + 性能

**目标**: T1'-T4' 功能完整后的打磨 Session。验证所有 Harness 规则、建立完整视觉基线、修复 UI 细节、确保 i18n 100% 覆盖、性能优化。

**前置**:
- T1'-T4' 全部完成
- 所有页面可渲染, 路由可导航

**任务清单**:

1. **Harness 全量验证** — 运行所有 CI grep 规则, 逐条修复:
   ```bash
   # === CLAUDE.md 强制 Harness ===
   
   # H1: Mode 不落 localStorage
   grep -r 'localStorage.*mode' frontend/src --include='*.jsx' --include='*.js'
   
   # H2-H5: 侧栏路由项数量、redirect 数量、i18n 覆盖 (见 T1')
   
   # === DESIGN_TOKENS C1-C7 ===
   
   # C1: Sparkline 默认值
   grep -nE "(width|height)\s*=\s*[0-9]+\s*[,}]" frontend/src/components/charts/MiniSparkline.jsx
   
   # C4: Sentiment .toFixed(2)
   grep -rnE "sentiment.*\.toFixed\(2\)|\.toFixed\(2\).*sentiment" frontend/src/pages --include='*.jsx' | grep -v '// C4-exempt'
   
   # C5: Sparkline 锯齿模数
   grep -rnE "spark[A-Za-z]+\s*=.*i\s*%\s*[0-9]+\s*===\s*0\s*\?" frontend/src/pages --include='*.jsx'
   
   # === §4.6.0a UI 边界 ===
   
   # 禁止开发者约束泄漏
   grep -rnE '本页(只|不)做|只回答|不承担|详情请进入|请去.*查看|严禁|🚫|⚠️ ?(本页|本段)' frontend/src/i18n --include='*.json' --include='*.js' --include='*.ts'
   grep -rnE '>\s*(本页(只|不)做|详情请进入|请去.*查看|严禁|🚫)' frontend/src --include='*.jsx' --include='*.tsx'
   
   # === 图表颜色契约 ===
   
   # 禁止内联 hex (logo SVG 除外)
   grep -rnE "fill=['\"]#[0-9a-fA-F]{3,8}['\"]|stroke=['\"]#[0-9a-fA-F]{3,8}['\"]" frontend/src/pages --include='*.jsx' | grep -v 'logo\|Logo'
   grep -rnE "fill=['\"]#[0-9a-fA-F]{3,8}['\"]|stroke=['\"]#[0-9a-fA-F]{3,8}['\"]" frontend/src/components --include='*.jsx' | grep -v 'logo\|Logo'
   ```
   - 每条 grep 预期零输出, 有输出则修复

2. **i18n 覆盖矩阵验证**:
   ```bash
   # 所有 t() 调用的 key 必须在 zh-CN 和 en-US 中同时存在
   node scripts/check-i18n-coverage.mjs
   ```
   - 如脚本不存在, 新建: 提取 JSX 中所有 `t('...')` key, 对比两个 messages JSON, 报告缺失
   - 修复所有缺失 key

3. **视觉回归基线 (完整集)**:
   - Brand Mode: `brand-overview.png`, `brand-visibility.png`, `brand-sentiment.png`, `brand-competitors.png`, `brand-citations-overview.png`, `brand-citations-content-gap.png`, `brand-citations-pr-targets.png`, `brand-citations-simulator.png`, `brand-products.png`
   - Industry Mode: `industry-overview.png`, `industry-ranking.png`, `industry-topics.png`, `industry-knowledge-graph.png`
   - Shell: `layout-brand-mode.png`, `layout-industry-mode.png`, `mode-toggle-brand.png`, `mode-toggle-industry.png`
   - Onboarding: `onboarding-step1.png` ~ `onboarding-step4.png`
   - **总计 ~21 张基线** (CI < 12min 预算内)

4. **响应式检查** (768px / 1024px / 1440px):
   - 侧栏 < 768px 折叠为 Hamburger
   - 图表 < 768px 堆叠为单列
   - 表格 < 768px 水平滚动
   - 每个断点抽查 3 页 (brand-overview + brand-visibility + industry-overview)

5. **性能优化**:
   - 懒加载: 所有页面组件 `React.lazy()` + `Suspense` (减少首屏 bundle)
   - 图表按需 import: `import { PieChart } from 'recharts'` (tree-shake 友好)
   - AntV G6 仅在 KnowledgeGraph 页面加载 (`React.lazy`)
   - mock.js 拆分: 如文件 > 2000 行, 按 domain 拆为 `mock-brands.js`, `mock-citations.js` 等, 入口 `mock/index.js` re-export

6. **交互细节打磨**:
   - 所有 `navigate()` 跳转增加 `scroll-to-top` (useEffect 或 ScrollRestoration)
   - 所有表格行 hover 态一致 (`hover:bg-themed-subtle`)
   - 所有图表 Tooltip 风格统一 (bg-themed-card, rounded-card, shadow-card)
   - 所有 Badge tone 统一: success/danger/warning/accent/muted (不出现未定义 tone)
   - 空态: 每个列表/图表在数据为空时显示优雅的空态 (图标 + 一行文案)

7. **C3/C7 运行时断言** (如尚未建立):
   - `scripts/check-data-contracts.mjs`:
     - C3: SoV/占比数据中"其他" ≤ 任一真实品牌
     - C7: BRANDS ranking 字段 = 按 panoScore desc 索引+1
   - 加入 `npm run ci` 脚本链

8. **废弃文件最终清理** (直接 `git rm`):
   - `frontend/src/pages/DashboardPage.jsx`
   - `frontend/src/pages/BrandDetailPage.jsx`
   - `frontend/src/pages/BrandSimulatorPage.jsx`
   - `frontend/src/pages/DiagnosticsPage.jsx` (跨品牌聚合)
   - `frontend/src/pages/TopicsPage.jsx` (顶层)
   - `frontend/src/pages/IndustryPage.jsx` (已迁)
   - `frontend/src/pages/KnowledgeGraphPage.jsx` (已迁)
   - `frontend/src/pages/ReportsPage.jsx` (已迁)
   - `frontend/src/pages/ProjectSettingsPage.jsx` (并入 Settings)

9. **CLAUDE.md 更新**:
   - 更新结构锚点表: 标注所有新页面为"T2'/T3' 建立"
   - 更新组件复用清单: 新增 `KpiCard`, `CompetitorQuadrantChart`, `DimensionIntentFilter`, `TimeGranularityToggle`
   - 标注 T1-T4 (Triad) 为 "SUPERSEDED by T1'-T5'"
   - 文档 cross-ref 审计: grep `docs/` 找 "面板 (/dashboard)" / "/brands/:id" 等 drift 表述, 修正或加脚注

**测试**:
- `npm run ci` 全绿 (所有 L1-L4 层)
- Harness grep 全量零输出
- 21 张视觉基线已保存
- i18n 覆盖 100% (零缺失)

**交付物**:
- Harness 修复补丁
- i18n 缺失 key 补全
- 21 张视觉基线图
- 响应式修复
- 性能优化 (lazy load + mock 拆分)
- 交互细节修复
- `check-data-contracts.mjs` + `check-i18n-coverage.mjs` 脚本
- 废弃文件删除
- CLAUDE.md 更新

**完成标志 (T5')**:
- `npm run ci` 全绿 (包括新增的 data contract + i18n coverage 脚本)
- 所有 Harness grep 全部零输出
- 21 张视觉基线在 `tests/e2e/screenshots/` 下
- 浏览器 3 断点抽查无布局溢出
- mock.js 无 undefined / NaN
- `grep -rn "DashboardPage\|BrandDetailPage\|DiagnosticsPage" frontend/src` 无输出
- CLAUDE.md 已更新为最新状态

---

### IA v2.0 Gate (在 T5' 完成后)

```
T1' (Topbar + Mode Toggle + Shell) 独立, 先行
  ↓
T2' (Brand Mode 5 深度分析页 + 迁移 4 页)
  ↓
T3' (Industry Mode 4 页)
  ↓
T4' (Onboarding + Route Guard + 301 Map + 废弃组件清理)
  ↓
T5' (全局打磨 + Harness 全量 + 视觉基线 + 性能)
  ↓
[IA v2.0 Gate: Frank 验证 BrandPicker 切换 / Mode Toggle / Onboarding / 301 重定向 / Engine 对比 filter / 5 深度页面全部体验对]
```

---

### Session T6' (ia-v2-S6): V2 分析页视觉统一 + 全局 Filter Bar + Heatmap + 竞品叙事重构 + 数据口径

**目标**: Frank 2026-04-20 下午反馈 9 问的全量一次性修复。Brand Mode 7 个分析 sub-view 视觉统一, 全局 Filter Bar 跨页共享状态, Visibility/Sentiment 引入 Heatmap, Competitors 重构为"我输在哪"叙事, 修复 1620% bug 与 Sentiment Distribution 文字化 bug, 产品页 BCG 修复。

**对应 PRD**:
- §4.6-IA-v2.K 全局 Filter Bar 规范
- §4.6-IA-v2.L Heatmap 组件规范
- §4.6-IA-v2.M 竞品页重构
- §4.6-IA-v2.N 数据口径统一

**前置**:
- T1'-T5' 已完成 (V2 App shell + 7 Brand Mode 页 + 4 Industry Mode 页已 mount)
- 现 V2 页可渲染但有 Frank 反馈的 9 个具体问题

**任务清单**:

**1. 数据层修复 (mock.js + 口径统一)**

- `frontend/src/data/mock.js`: `BRANDS[].mentionRate` 从百分比 (18.5, 16.2, ...) 改为小数 (0.185, 0.162, ...)
- `COMPETITOR_SENTIMENT_BUBBLE[].sov`: 从 `22, 18, 15, 12` 改字段名 `sovPct` 或改为小数 `0.22, 0.18, ...` (二选一, 全局一致)
- `TOPICS[].mentionRate` / `PRODUCTS[].mentionRate` 审计, 确保全部 ∈ [0, 1]
- 新增 `scripts/check-data-contracts.mjs` C11 断言: `BRANDS.forEach(b => assert(b.mentionRate >= 0 && b.mentionRate <= 1, '...'))`

**2. 新组件: BrandAnalysisFilterBar + useBrandAnalysisFilters**

文件: `frontend/src/components/filters/BrandAnalysisFilterBar.jsx`
Hook: `frontend/src/hooks/useBrandAnalysisFilters.js`

接口:
```jsx
// hook
const { filters, setFilter, resetFilters } = useBrandAnalysisFilters();
// filters = { from, to, engines: [], profileGroup, dimensions: [], intents: [] }

// 组件
<BrandAnalysisFilterBar />
// 内部从 hook 读值并渲染:
// 主行: [时间段] [引擎多选] [画像组下拉] [更多筛选 ▾]
// 扩展 (展开后): [维度多选] [Intent 多选]
```

实现要点:
- URL 是唯一真相源 (`useSearchParams`)
- Mode Toggle 切换 (/brand ↔ /industry) 时, filters 不传递 (URL prefix 改变自动丢失)
- brandId 切换 (同 Brand Mode 内) 时保留所有 filters
- 扩展筛选默认折叠, 展开态用 `useState` 本地 (不入 URL)

**3. 新组件: BrandTopicHeatmap**

文件: `frontend/src/components/charts/BrandTopicHeatmap.jsx`

使用 Recharts 的 `<ScatterChart>` + 自定义 `<Cell>` 方案, 或自写 SVG 方阵 (不超 80 行, 色块 + tooltip)。优先方案: D3-scale (`scaleSequential` from `d3-scale` 已在依赖) + Recharts ScatterChart:

```jsx
<BrandTopicHeatmap
  rows={brands.map(b => ({
    brandId: b.id,
    brandName: b.name,
    values: topics.map(t => ({ topicId: t.id, topicLabel: t.label, value: lookupRate(b.id, t.id), sample: 42 }))
  }))}
  scale="sequential"  // or "diverging"
  metric="mentionRate"
  highlightBrandId={currentBrandId}
  onCellClick={(brandId, topicId) => navigate(`/brand/topics?topicId=${topicId}&brandId=${brandId}`)}
/>
```

内部色带 mapping: 从 `var(--color-heatmap-seq-0)` 到 `var(--color-heatmap-seq-5)` (6 档 sequential) 或 `-div-neg / -div-zero / -div-pos` (5 档 diverging)。Tooltip 用 Recharts 默认风格 + 覆盖样式。

**4. 重构 BrandVisibilityPage**

删除:
- 原 section 6 (unmissed prompts 列表) — 若实装了 (源代码未包含), 保留
- 原 section 7 (position bar + sentiment bar) — sentiment 完全移除 (决策: Sentiment 独立页专项)
- 原 `CompetitorQuadrantChart` section (叙事低效)

新结构:
1. 页头 + Filter Bar
2. KPI 双卡 (提及率 + SoV) — 保留, 但渲染改 `(mentionRate * 100).toFixed(1)%` (修 1620%)
3. 提及率分布 Donut (情感 tab 有独立 donut, 这里是"提及 vs 未提及" 或按 engine 分布) + 引擎分布 BarChart (2 列网格)
4. 趋势图 TrendChart (提及率 + SoV 双线) — 保留
5. **NEW Brand × Topic 热力图** (用 `<BrandTopicHeatmap scale="sequential" metric="mentionRate">`, 行: 我 + Top 5 竞品; 列: Top 10 Topic)
6. 竞品对比表 (精简: 5 列, 品牌/提及率/SoV/Delta/样本)

**5. 重构 BrandSentimentPage**

删除:
- 原 lines 85-99 的 3 个大号文字百分比 Distribution
- 原 "竞品情感对比表" (由 heatmap 替代)

新结构:
1. 页头 + Filter Bar
2. **Distribution Donut** (左: `<DonutChart size={180}>` 正/中/负 三段; 右: 图例 + 每段样本数) — 修 Frank 反馈 7
3. 引擎 stacked bar (正/中/负 占比) + 趋势图 (2 列网格)
4. Topic 归因 (正面 Top 5 / 负面 Top 5) — 保留
5. **NEW Brand × Topic 情感热力图** (`<BrandTopicHeatmap scale="diverging" metric="sentiment">`) — 修 Frank 反馈 8
6. 典型 Response 正面/负面样例 (收紧为 2 列网格, 各 3 条)

**6. 重构 BrandCompetitorsPage (叙事重构)**

删除:
- 原 section 4 (SoV 水平条 独立) — 合并到对比表
- 原 section 5 (PANO 趋势 全量竞品 5 条线) — 改为选中竞品 2 条线
- 原 section 2 (Authority Radar 全量重叠) — 改为选中竞品 2 条

新结构 (按 §4.6-IA-v2.M):
1. 页头 + Filter Bar
2. **Top 3 威胁品牌卡片** (grid-cols-3): 每卡 logo + 名称 + 3 delta 数字 (V/S/R 相对我) + "查看详情 →"。排序按 gap 降序。点击后 `?vs=brand-id` 并高亮
3. **5 维雷达图**: 我 vs 选中竞品 (2 条折线, 半透明填色)
4. **Topic 胜负矩阵** (`<BrandTopicHeatmap scale="diverging" metric="sovDelta">`, 2 行: 我 + 选中竞品, 10 列: 共同覆盖 Top Topic)
5. **30d 动态时间线**: 双线 PANO 趋势 (我 + 选中竞品)
6. Same-Group 共享域 + Acquisition 事件 (保留原 §4.2.7.D 底部两块)

状态: `const vsId = searchParams.get('vs') || top3Threats[0]?.id`

**7. Patch BrandProductsPage**

- 修 BCG primary detection bug (line 38-40 原 `.reduce` 逻辑):
  ```jsx
  // 旧 (bug):
  const primaryId = products.reduce((max, p) => p.panoScore > max.score ? { id: p.id, score: p.panoScore } : max, { id: null, score: -1 }).id;
  // 改为:
  const primaryProduct = [...products].sort((a, b) => b.panoScore - a.panoScore)[0];
  const primaryId = primaryProduct?.id;
  ```
- 添加 Filter Bar
- mentionRate 渲染: `(p.mentionRate * 100).toFixed(1)%` (PRODUCTS 已是 decimal, 但保险起见)
- BCG 填充度: 在 `CompetitorQuadrantChart` 参考线基础上, 若产品 < 6, 追加 3-5 个 ghost 节点 (淡灰, 无标签, tooltip 提示"行业基准") 增加聚类感

**8. Patch BrandCitationsPage**

- 添加 Filter Bar (顶部, 所有 sub-tab 共享)
- 其他保持不变 (已是视觉最干净的页)

**9. Harness 拦截 (新增 K1/K2/C11/C12)**

更新 `scripts/check-harness.sh` (或等效 CI step):

```bash
# K1: Brand Mode 分析页必须 import BrandAnalysisFilterBar
for f in frontend/src/pages/brand/Brand{Visibility,Topics,Sentiment,Citations,Products,Competitors}Page.jsx; do
  if ! grep -q "BrandAnalysisFilterBar\|useBrandAnalysisFilters" "$f"; then
    echo "MISSING FILTER BAR: $f"; FAIL=1
  fi
done

# K2: 禁止硬编码时间范围
grep -rnE "const\s+(from|to|dateRange)\s*=\s*['\"\(]" frontend/src/pages/brand/ --include='*.jsx' && FAIL=1

# C11: mentionRate 若出现 `>= 1` 的 literal 视为违约
grep -rnE "mentionRate[^a-zA-Z_].*[1-9][0-9](\.[0-9]+)?" frontend/src/data/mock.js && FAIL=1

# C12: BrandSentimentPage 必须 import DonutChart
grep -q "import.*DonutChart" frontend/src/pages/brand/BrandSentimentPage.jsx || { echo "Sentiment page missing DonutChart"; FAIL=1; }
```

**10. 视觉基线追加**

- `brand-visibility-v2.png` (new layout)
- `brand-sentiment-v2.png` (new layout)
- `brand-competitors-v2.png` (new narrative)
- `brand-products-v2.png` (new BCG)
- `brand-citations-v2.png` (+ FilterBar)
- 共 5 张替换原 T5' 基线

**11. Wave-3 追加 (2026-04-20 傍晚 Frank 反馈 3 问)**

**11.1 CompetitorQuadrantChart 气泡尺寸 + 标签契约 (DESIGN_TOKENS C13)**

- 文件: `frontend/src/components/charts/CompetitorQuadrantChart.jsx`
- 新增 prop `bubbleRadius`: `[rMin, rMax]`, 默认 `[8, 24]`
- 新增 prop `showLabels`: `boolean`, 默认 `true`
- 半径映射改 sqrt 面积正比: `zNorm = Math.sqrt((z - zMin) / (zMax - zMin || 1))`; 删除旧 `radius = 40 + zNorm * 360`
- 标签渲染在气泡正下方 `cy + radius + 10`, `fontSize=10`; `rawName.length > 10` 截断为 `slice(0,9) + '…'`
- Primary 品牌: `fillOpacity=0.85` + stroke accent + 标签 accent 色 + fontWeight 600; 其余: `fillOpacity=0.55` + stroke subtle + 标签 muted + fontWeight 400
- Harness: C13-1 / C13-2 / C13-3 (DESIGN_TOKENS.md C13)

**11.2 BrandCompetitorsPage 新增 Tier 2 覆盖矩阵卡 (PRD §4.6-IA-v2.M.5)**

- 文件: `frontend/src/pages/brand/BrandCompetitorsPage.jsx`
- 位置: Top 3 威胁卡之后, Radar 之前 (section ③)
- 数据源: `TIER2_COVERAGE_MATRIX` (mock.js 已有)
- 渲染: HTML `<table>`, 行 = 权威域 8 个, 列 = 我 + Top 3 竞品
- 单元格色: `color-mix(in srgb, var(--color-accent) ${alpha}%, transparent)` for "我" 列, `color-mix(in srgb, var(--color-text-muted) ${alpha}%, transparent)` for 竞品列, alpha = `(count / maxCount) * 45`; 零值显示 `—`
- 底部图例: 跳转 `/brand/citations?sub=content-gap` 和 `/brand/citations?sub=pr-targets` 的双 anchor
- 禁止内联 hex (C9-2); 禁止用 heatmap 色带 (C9-1)

**11.3 BrandCompetitorsPage Same-Group 卡加元信息 + 解释段 (PRD §4.6-IA-v2.M.6)**

- 文件: `frontend/src/pages/brand/BrandCompetitorsPage.jsx`
- Header 行: `隶属集团: {SAME_GROUP_SHARED.group} · 共享占总引用 {Math.round(sharedRatio * 100)}%`
- Header 下紧跟 `<p className="text-[11px] text-themed-muted leading-relaxed mb-2">` 解释段, 内容 (或等价 i18n):
  > 你和以下子品牌属于同一母集团。当 AI 引擎引用这些官方/权威域名时, 母集团叙事会被加强, 但**同一母集团的兄弟品牌之间也会在同一 Topic 里互相稀释 SoV** — 这些不算"敌方竞品", 但在做 Topic 层策略时需要识别出来, 以免和自家人抢占位。
- 子品牌列表前加 "子品牌:" 前缀 label
- ⚠️ 解释段严禁开发者约束措辞 (`本页不做` / `详情请进入` 等, §4.6.0a)

**11.4 BrandProductsPage i18n interpolation 修复 (bug fix, 不是契约变更)**

- 文件: `frontend/src/pages/brand/BrandProductsPage.jsx`
- bug: `t('brand_products.page_subtitle', '品牌下产品的提及、SoV 和增长趋势')` — 第二参数是 fallback string, 导致模板 `{brand} · 共 {count} 款产品` 不 interpolation, placeholders literally 渲染
- 修复: `t('brand_products.page_subtitle', { brand: primary.name, count: products.length })`
- 一般规则: 当 messages key 包含 `{xxx}` 占位符时, 第二参数必须是 values 对象; fallback string 只在无占位符 key 上允许

**11.5 V2 分析页密度统一 (DESIGN_TOKENS C14)**

对 6 个分析页全部应用:
- 根节奏 `space-y-3` (禁 space-y-4+)
- 页标题 `text-xl font-brand font-bold` (禁 text-2xl/3xl)
- 副标题 `text-xs text-themed-muted` (禁 text-sm)
- Card padding `p-3` (禁 p-4/5/6)
- Card section header `text-[13px] font-semibold text-themed-primary`
- Card section meta `text-[11px] text-themed-muted`
- Threat/KPI card 数字 `text-lg font-bold`, 标签 `text-[11px] uppercase tracking-wide`
- Harness: C14-1 / C14-2 / C14-3 (DESIGN_TOKENS.md C14)

**Wave-3 交付物**:
- PRD §4.6-IA-v2.M.5 + M.6 (已新增)
- DESIGN_TOKENS.md C13 + C14 (已新增)
- CLAUDE.md 决策 #20 扩展 + §"V2 分析页统一契约 C9-C14 Harness" (已更新)
- `CompetitorQuadrantChart.jsx` 新 props + sqrt 映射
- `BrandCompetitorsPage.jsx` Tier 2 Coverage 卡 + Same-Group 解释段
- `BrandProductsPage.jsx` i18n interpolation 修复
- 全 6 页应用 C14 密度规范

---

**12. Wave-4 追加 (2026-04-20 傍晚 Frank 校正: "不对, 我的意思是下钻到某个产品时需要这样的具体的页面" → "目前点击某一个详细的产品后, 应该是基于这些产品的 GEO 数据, 但是目前是空的")**

> **⚠️ 开发者约束 (不作为 UI 文案)**: 本节限制仅指导实施, 不以解释性文字呈现给用户。

**Wave-4 真主题 (取代初版 "列表页扩 7 区" 方案)**: 初版把锚点 URL `/brands/estee-lauder/products/elixir-mini` 误读为"请求提升列表页的信息密度"; Frank 看到输出后校正意图: **真正的问题是点进任一产品详情页 `/brand/products/:productId?brandId=:brandId` 当前渲染 "暂无数据" 空白**。本 Wave-4 任务从"扩列表页"**转为** "修详情页空白 bug + 固化详情页路由契约"。列表页回滚到 4 区原状。

**12.1 BrandProductDetailPage.jsx 路由参数读取修复 (P0 Bug Fix)**

- 文件: `frontend/src/pages/BrandProductDetailPage.jsx`
- Bug: 组件入口曾 `const { brandId, productId } = useParams()`, 但 V2 路由 `<Route path="/brand/products/:productId" />` 只含 productId 路径参数, brandId 走 query string (`?brandId=:id`); 结果 `brandId === undefined` → `BRANDS.find(...)` 返回 undefined → 空状态守卫 `if (!brand || !product)` 触发 → 整页空白
- Fix:
  ```jsx
  import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
  // ...
  const { productId } = useParams();
  const [searchParams] = useSearchParams();
  const brandId = searchParams.get('brandId');
  const product = useMemo(() => PRODUCTS.find(p => p.id === productId), [productId]);
  const brand = useMemo(() => {
    if (brandId) return BRANDS.find(b => b.id === brandId);
    if (product) return BRANDS.find(b => b.name === product.brand || b.nameEn === product.brandEn);
    return null;
  }, [brandId, product]);
  if (!product) return <EmptyCard />; // brand 可为 null, 不进空状态
  ```
- 下游引用统一做 null-safe: `industry = brand ? INDUSTRIES.find(...) : null`; JSX 中品牌链接 `disabled={!brand}`, 品牌名 `{brand?.name || product.brand}`

**12.2 BrandProductsPage.jsx 回滚至 4 区**

- 文件: `frontend/src/pages/brand/BrandProductsPage.jsx`
- 回滚: 初版 Wave-4 添加的 ⓪ Portfolio KPI Strip / ② Flagship Spotlight / ⑥ Portfolio Prompt Hits + "主推语境"列 + `buildContexts` helper + Recharts (BarChart/Bar/XAxis/YAxis/CartesianGrid/Tooltip/Cell) imports + MENTION_DETAIL_LIST import **全部删除**
- 最终结构: ① BCG 气泡矩阵 / ③ Sparkline Grid / ④ 产品列表表格 (8 列, 不含主推语境) / ⑤ 产品关系快照
- 点击产品跳 `/brand/products/${productId}?brandId=${brandId}` 保留

**12.3 Harness (DESIGN_TOKENS C15, CLAUDE.md §V2 分析页统一契约 C9-C15)**

- C15-1: `BrandProductDetailPage.jsx` 禁从 `useParams()` 解构 `brandId` (grep `useParams\(\)[^{]*\{[^}]*\bbrandId\b` 无输出)
- C15-2: `BrandProductDetailPage.jsx` 必须 `import ... useSearchParams`
- C15-3: 空状态守卫禁基于 `!brand` 返回空页 (brand 缺失必须降级渲染)

**12.4 UI 文案边界 (§4.6.0a)**

- 详情页 brand null 时降级文案使用 `product.brand` / `product.brandEn` 原生字段, **不写** "品牌未知 / 请先选品牌" 等解释性段落
- 空状态仅在 productId 不匹配时触发, 用 `t('common.empty')` 通用 key

**Wave-4 交付物 (取代初版)**:
- PRD §4.6-IA-v2.O 已重写为"详情页路由契约 + 空状态修复"(取代原 7 区 portfolio 扩张方案)
- DESIGN_TOKENS.md C15 已重写为"BrandProductDetailPage 路由契约"(取代原 Portfolio 契约) + 3 条 Harness grep (C15-1/2/3)
- CLAUDE.md 决策 #20 Wave-4 段已重写 (取代"列表页扩 7 区") + §"V2 分析页统一契约 C9-C15 Harness" 中 C15-1/2/3 已改为详情页契约
- `frontend/src/pages/BrandProductDetailPage.jsx` 已 patch: import `useSearchParams`, brandId 从 query 读, brand 可为 null, 下游 null-safe, SoV card value bug (原用 mentionRate) 已改回 sov, 3 处 legacy `/brands/...` navigate 已改为 V2 路径
- `frontend/src/pages/brand/BrandProductsPage.jsx` 已回滚至 4 区 clean 版 (Write, ~270 行)

**测试 (Wave-4, 取代初版)**:
- `npm run build` 通过 (Vite 构建无报错)
- Harness C15-1/2/3 零输出
- 手动验证:
  - 访问 `/brand/products/elixir-mini?brandId=estee-lauder` 渲染完整 GEO 数据 (hero 区 + 4 KPI + BarChart 语境 + Sparkline + 关系图 + Prompt Hits 表), **不再**显示 "暂无数据"
  - 访问 `/brand/products/elixir-mini` (不带 brandId) 也能渲染 (反查 product.brand 字段)
  - Legacy URL `/brands/estee-lauder/products/elixir-mini` → 301 重定向到 `/brand/products/elixir-mini?brandId=estee-lauder`, 不丢数据
  - 从 `/brand/products` 列表点任一 BCG 气泡/表格行/sparkline tile → 正确跳到详情页并渲染
- 视觉基线: 新增 1 张 `brand-product-detail-elixir-mini.png` 作为详情页基线 (取代原 `brand-products-wave4.png` 列表页基线)

**测试**:

- `npm run ci` 全绿
- Harness K1/K2/C11/C12 零输出
- 手动验证:
  - 在 /brand/visibility 设置 engines=chatgpt, 切到 /brand/sentiment, URL 保留 engines=chatgpt
  - 1620% 已不出现 (改为 16.2%)
  - Sentiment Distribution 是 Donut (不是 3 个大号文字)
  - Competitors 默认选中 gap 最大竞品, 点击其他卡切换
  - Products BCG primary (最大 panoScore) 用品牌色高亮

**交付物**:

- PRD §4.6-IA-v2.K-N (本 Session 的真相源)
- DESIGN_TOKENS.md C11 + C12 + heatmap 色带定义 (seq/div)
- CLAUDE.md 决策 #19 (V2 分析页统一) 新增
- mock.js BRANDS.mentionRate 数据修复
- `BrandAnalysisFilterBar.jsx` + `useBrandAnalysisFilters.js`
- `BrandTopicHeatmap.jsx`
- 5 个页面重构 (Visibility/Sentiment/Competitors/Products/Citations)
- Harness 脚本更新
- 5 张新视觉基线

**完成标志 (T6')**:

- Frank 验证 9 反馈全部修复
- Brand Mode 7 个分析页视觉统一 (padding/标题/间距)
- Filter Bar 跨 sub-view 状态同步
- 无 1620% 类 bug
- Sentiment Distribution 是 Donut
- Competitors 页单一叙事 (我输在哪)
- `npm run ci` 全绿 + 5 张新基线通过

Gate 通过后, IA v2.0 稳定, Phase 2 的多 Project 扩展 (ProjectSwitcher 出现在侧栏底部) 作为独立 Session 单独立项, 不与 IA v2.0 收敛混淆。
