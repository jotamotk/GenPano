# GENPANO Session 进度总览

> 更新日期: 2026-04-26 (架构反转后重写, 决策 #29)
> 真相源: `docs/CLAUDE_CODE_SESSIONS.md` (Python 后端 11 Sessions) + `docs/REPLAN_2026_04_26.md` (M1-M4 路线图)
> 本文档只做"索引 + 状态"汇总, 不重复真相源内容。

---

## 重大架构反转 · 2026-04-26 (决策 #29)

Frank 用 jotamotk/GenPano.git 实验代码合并 PRD 后, 决策最优架构 = **FastAPI + SQLAlchemy 2.0 async + Alembic + Celery + Redis + Pydantic v2 + Playwright/Camoufox** 后端 + **React 18 + Vite + JSX + Tailwind** 前端 (JSX 不动, 不切 TSX)。

**报废范围 (Next.js 时代)**: master 分支 Session 0-rev / 0' (Next.js Frontend+Backend) / Session 1 (TS Adapter 框架) / Session 1.5 (TS Platform Layer + InMemory + Prisma) / Session 2 (TS Planner) / Session 2.1 (TS LLM Refinement) / Session A0 (Next.js Admin Auth) — **所有后端 TS 代码作废**, 只保留 PRD/CLAUDE.md/SESSIONS 文档资产 + frontend/ 原型 (T1'-T6' JSX) 继续用。

**保留范围 (前端原型)**: `frontend/` 全量 React 18 + JSX + recharts + d3 + framer-motion + @antv/g6 + @radix-ui + mixpanel-browser + lucide-react, IA v2.0 设计逐步迁移到 Python 后端的 React 客户端中。

**新规划主入口**: `docs/REPLAN_2026_04_26.md` — MVP 4 Milestone × 11 Session × 8-10 周。

---

## 图例

| 符号 | 含义 |
|------|------|
| ✅ | 已完成 (含 Phase Gate 全过 + CLAUDE.md 决策登记) |
| 🟡 | 进行中 |
| ⬜ | 待启动 |
| ⛔ | 依赖未满足, 暂不可启动 |
| 🗑 | 已废弃 / 被取代 |
| 📜 | 已归档 (Next.js 时代历史, 不再推进, 保留只为可追溯) |

---

## 两条 Track (架构反转后)

GENPANO 工程在 2026-04-26 反转后只剩两条 Track:

1. **Python Backend Track** (`CLAUDE_CODE_SESSIONS.md` § 0'-§ 13): Session 0' / A0' / 4a' / 1' / 1.5' / 1.2' / 2' / 2.1' / 3' / A1' / 4b' — 11 Sessions, 全部用 FastAPI + SQLAlchemy + Celery + Alembic + Pydantic v2 重写
2. **UI Prototype Track** (CLAUDE_CODE_SESSIONS.md §"T" 段, 已冻结): T1' / T2' / T3' / T4' / T5' / T6' — 原型级 IA v2 重构 (evolve `frontend/`, JSX 不切 TSX)

**已归档 Track (Next.js 时代, 2026-04-26 报废)**:
- App Track (Session 0/0-rev/1/1.2/1.5/2/2.1/3/4a/4b/5): 后端代码全部报废, 资产保留为决策依据
- Admin Track (Session A0/A1/A2/A2.1/A2.2/A2.3/A2.4/A3/A3.1/A3.2/A3.3/A4/A5): A0 已宣绿但落在 Next.js 上, 也作废, A0' 在 Python 重写

---

## Python Backend Track 进度 (REPLAN_2026_04_26.md, 11 Sessions)

| Session | 主题 | 状态 | 备注 |
|---------|------|------|------|
| **Session 0'** | 项目初始化 + CI/CD + Preview Env (FastAPI 脚手架 / Alembic 初始 migration / pytest 框架 / GitHub Actions / Docker / Preview env one-click deploy) | ⬜ | M1 起点; 决策 #29/#30/#31 落地; 必须达成 Phase Gate 1 (架构, 见 HARNESS_ENGINEERING.md §10.6) |
| **Session A0'** | Admin 认证脚手架 Python 重写 (FastAPI Depends + python-jose JWT + passlib bcrypt + slowapi rate limiter + /admin/* middleware + Alembic admin tables) | ⬜ | M1; 依赖 0'; Next.js A0 决策资产 (#24 A/B/C1.1-C1.3/C2/C3/C4/D/E/F/G + #25 D8/D9/D10) 全部 transpose 到 Python; harness D8/D9/D10 重写为 pytest grep |
| **Session 4a'** | 用户系统 + Onboarding (FastAPI Auth + AuthPage 接 React 客户端 + /onboarding 4 步 + Route Guard + DraftProject 72h 草稿) | ⬜ | M1; 依赖 0' + A0'; 决策 #9 + #10 落地到 Python |
| **Session 1'** | 核心监测引擎 · AI 爬取系统 Python 重写 (Playwright + Camoufox + Adapter/Parser/Scheduler/Account Pool/Luban SMS + Celery beat + HAR sanitize) | ⬜ | M2 起点; 依赖 0' (CI/CD); ADAPTER_CONTRACT.md 12 章 transpose 到 Python; 9 错误码 + retry policy 矩阵保留; pytest L1 grep + L2 单测 + L3 routeFromHAR 三层 |
| **Session 1.5'** | 平台数据基础设施 · 行业知识图谱冷启动 Python 重写 (LLM client / SQLAlchemy KG repos / Discovery / KG 关系挖掘 / Scheduler tier-based / Seed CLI) | ⬜ | M2; 依赖 0' + 1'; CLAUDE.md #23 (端口/适配器范式 + 50 LLM call budget + confidenceFromEvidence 公式 + InMemory 单测策略) 全 transpose; Phase Gate 2 |
| **Session 1.2'** | Adapter Hardening (Camoufox stealth + 真实 HAR 录制 + routeFromHAR 契约测试 + Luban SMS live + auto-register live + 3 引擎 cookies/localStorage 注入 + CLI accounts:list/register/inject) | ⬜ | M2; 依赖 1'; CLAUDE.md #28 (Platform Layer 边界 + 双修正基线 + Phase A 规划 C1/C2) 全 transpose |
| **Session 2'** | 智能监测 Pipeline (Topic → Prompt → Query 三层 Planner Python 重写 + Intent×Engine×Locale 23 行矩阵 + Category Purity + Persona snapshot 注入 attempts.browser_profile JSONB) | ⬜ | M3 起点; 依赖 1.5'; CLAUDE.md #26 (含 C1/C2/C3 偏差 + Group G G1-G4 harness) 全 transpose; persona 不加列契约硬保留 |
| **Session 2.1'** | Planner LLM Refinement (Topic Refine + Prompt Naturalize + Profile-Aware Query Rewrite + canned LLM transport + 4 Gate intent/brand-vocab/category-leak 守卫) | ⬜ | M3; 依赖 2'; CLAUDE.md #27 (Group H H1-H3 harness + rewrite_meta JSONB 守 #26.C1) 全 transpose |
| **Session 3'** | 分析引擎 + API + MCP Server Python 重写 (Citation §4.2.6 A-H + §4.2.7 A-H + 3 MCP 工具 `genpano_get_citations` / `list_pr_targets` / `simulate_authority_boost` + FastAPI user-facing endpoints + Pydantic v2 schemas) | ⬜ | M3 终点 / Phase Gate 3 (引擎+API); 依赖 2.1'; 在此 Session 之前 patch `docs/DATA_MODEL.md §2.5` 落地 #26 C1 |
| **Session A1'** | Admin 用户管理 + 审计 + KG 审核 (审核队列/alias merge/relation 晋升) + Pipeline Dashboard 起步 (multi-role super_admin/ops_admin/viewer + 操作日志 + KG QA + Pipeline 监控起步) | ⬜ | M4 起点; 依赖 A0' + 3'; CLAUDE.md #24 C2 (单值 → 3 角色) 在此 Session 落地 |
| **Session 4b'** | Dashboard + 报告 + 咨询转化 (Brand/Industry Mode IA v2 全部页面 React 实现 + PDF 报告 + 咨询入口 + 视觉回归 baseline) | ⬜ | M4 终点 / Phase Gate 4 (UI 完成); 依赖 4a' + 3' + A1'; T1'-T6' 原型正式工程化 |

### Python Backend Track Gate 链 (HARNESS_ENGINEERING.md §10.6 重映射)

```
Session 0' ⬜ → [Phase Gate 1 架构: FastAPI/SQLAlchemy/Alembic/CI/Preview]
    → A0' ⬜ → 4a' ⬜
    → 1' ⬜ → 1.5' ⬜ → [Phase Gate 2 平台数据+爬取]
    → 1.2' ⬜
    → 2' ⬜ → 2.1' ⬜ → 3' ⬜ → [Phase Gate 3 引擎+API]
    → A1' ⬜ → 4b' ⬜ → [Phase Gate 4 UI 完整]
    → Preview env → Production 切换 → [Phase Gate 5 上线]
```

**当前进度**: 全部 ⬜ pending, M1 未启动。**下一步**: Session 0' (架构反转后第一 Session, 必须先消化 CI/CD 基建 + Preview env 一键部署 per 决策 #30, 全部其他 Session 都依赖)。

---

## UI Prototype Track 进度 (`frontend/` 原型级, 已冻结)

> Frank 明确: "frontend/ 目前当作原型图, 正式工程通过 Session 4b' 重做"。T1'-T6' 已全部到 v3.2, 不再推进, 等 4b' 工程化。

| Session | 主题 | 状态 | 备注 |
|---------|------|------|------|
| Session T1' | DashboardLayout 重构 · 顶栏 Mode Toggle + 侧栏 Mode-Aware | ✅ (原型) | CLAUDE.md #20 Brand/Industry Mode IA v2.0 落地 |
| Session T2' | Brand Mode 5 个深度分析页 | ✅ (原型) | 含 v3.2 Topics 跨 Mode 复用 (2026-04-21) |
| Session T3' | Industry Mode 4 页 | ✅ (原型) | 含 v3.2 删 IndustryTopicCoverageHeatmap (2026-04-21) |
| Session T4' | Onboarding + Route Guards + Auth-Required + 301 + 遗留清理 | ✅ (原型) | CLAUDE.md #9/#10 落地到原型 |
| Session T5' | 全局打磨 + Harness 全量 + 视觉回归基线 + 性能 | ✅ (原型) | |
| Session T6' | V2 分析页视觉统一 + Filter Bar + Heatmap + 竞品叙事 + 数据口径 + Wave-4 详情页 brandId query string 契约 | ✅ (原型) | CLAUDE.md #20 (含 Wave-4 回滚 + 最终形态) |

**UI Prototype Track 状态**: 原型已到 v3.2, 已冻结. JSX 栈保留. Session 4b' 把这套页面接到 Python FastAPI 后端, 不切 TSX (决策 #29 明确)。

---

## 已归档 Track (Next.js 时代, 2026-04-26 报废)

> 决策 #29 反转后, 以下 Sessions 的代码全部作废. 文档资产 (PRD 决策 / 架构理由 / 偏差登记 / harness 规则) 全部保留并 transpose 到 Python 重写的对应 Session, 不再推进, 不再 merge.

### App Track (旧, 已归档)

| Session | 主题 | 状态 | 备注 |
|---------|------|------|------|
| Session 0 (deprecated) | 项目初始化 & 技术选型 | 📜 | 被 Session 0-rev 取代后再被 Session 0' (Python) 取代 |
| Session 0-rev | 测试地基 + Backend 脚手架 (Next.js + Vitest + 38 Harness) | 📜 | CLAUDE.md #21; 资产 transpose → Session 0' (Python) |
| Session 1 | AI 爬取系统 (TS Adapter/Parser/Scheduler/Pool/HAR) | 📜 | CLAUDE.md #22; 资产 transpose → Session 1' (Python) |
| Session 1.2 | Adapter Hardening (TS Camoufox + Luban) | 📜 | CLAUDE.md #28; 进行中时反转, 资产 → Session 1.2' |
| Session 1.5 | 行业知识图谱 Platform Layer (TS InMemory + Prisma) | 📜 | CLAUDE.md #23; 资产 transpose → Session 1.5' |
| Session 2 | 智能监测 Pipeline (TS Topic→Prompt→Query) | 📜 | CLAUDE.md #26; 资产 transpose → Session 2' |
| Session 2.1 | Planner LLM Refinement (TS Refine→Naturalize→Rewrite) | 📜 | CLAUDE.md #27; 资产 transpose → Session 2.1' |
| Session 3 | 分析引擎 + API + MCP (TS) | 📜 (未开工) | 规划资产 → Session 3' |
| Session 4a | 用户系统 + Onboarding (TS) | 📜 (未开工) | 规划资产 → Session 4a' |
| Session 4b | Dashboard + 报告 (TS) | 📜 (未开工) | 规划资产 → Session 4b' |
| Session 5 | 上线打磨 (TS) | 📜 (未开工) | Phase Gate 5 现在 Python 重写后再发生 |

### Admin Track (旧, 已归档)

| Session | 主题 | 状态 | 备注 |
|---------|------|------|------|
| Session A0 | Admin 认证脚手架 (Next.js + jose JWT + Edge middleware) | 📜 (曾宣绿) | 2026-04-21 宣绿 9/9 PASS; 资产 transpose → Session A0' (Python) |
| Session A1-A5 | Admin 用户/Pipeline/KG/Cost/Citation Tier (Next.js) | 📜 (未开工) | 资产合并到 Session A1' (Python, M4) |

---

## 当前关键路径 (2026-04-26 架构反转后)

```
[全部 Track 重启, 11 Sessions ⬜ pending]
     │
     ▼
┌─────────────────────────────────────┐
│  M1 Foundation (3 Sessions, ~2 周)  │
├─────────────────────────────────────┤
│  Session 0'  · CI/CD + Preview     │ (必须先做, 决策 #30)
│  Session A0' · Admin Auth Python   │ (依赖 0')
│  Session 4a' · 用户系统 + Onboard  │ (依赖 0' + A0')
└─────────────────────────────────────┘
     │ Phase Gate 1
     ▼
┌─────────────────────────────────────┐
│  M2 Pipeline (3 Sessions, ~2-3 周) │
├─────────────────────────────────────┤
│  Session 1'   · 爬取引擎 Python    │
│  Session 1.5' · KG 冷启动 Python   │ (Phase Gate 2)
│  Session 1.2' · Adapter Hardening  │
└─────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────┐
│  M3 KG+Planner (3 Sessions, ~2 周) │
├─────────────────────────────────────┤
│  Session 2'   · Topic→Prompt→Query │
│  Session 2.1' · LLM Refinement     │
│  Session 3'   · Analyzer+API+MCP   │ (Phase Gate 3)
└─────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────┐
│  M4 Analyzer+UI (2 Sessions, ~2 周)│
├─────────────────────────────────────┤
│  Session A1'  · Admin 用户/Audit   │
│  Session 4b'  · Dashboard+Reports  │ (Phase Gate 4)
└─────────────────────────────────────┘
     │
     ▼
[Preview env → Production] (Phase Gate 5)
```

**总预算**: 8-10 周, 11 Sessions, M1 (~2w) + M2 (~2-3w) + M3 (~2w) + M4 (~2w) + 缓冲 (~1w)。

**横切要求 (决策 #30/#31)**: 每个 Session 结束必须 (1) 代码经 Git CI/CD 上 preview env, (2) 前后端联动可点击产物, (3) Frank 能在浏览器自验; 每 1-几个 Session 一个 feature 分支从 main fork (决策 #31.C, claude/* 旧分支不再 merge 沉淀)。

---

## CLAUDE.md 决策号与 Session 对照

### 历史决策 (Next.js 时代, 资产保留为 transpose 依据)

| CLAUDE.md 决策号 | 旧 Session (📜) | 主题 | 日期 | 资产去向 (新 Python Session) |
|-----------------|---------|------|------|----------|
| #21 | Session 0-rev | 2026-04-21 Review 修复闭环 (38 Harness + 7 数据契约 + 5 fixture) | 2026-04-21 | → Session 0' (pytest grep + Alembic check + 5 fixture pytest 重写) |
| #22 | Session 1 | AI 引擎爬取框架 (Adapter/Parser/Scheduler/Pool/Humanize/Proxy/HAR + 13 Vitest + F1/F2/F3 Harness) | 2026-04-21 | → Session 1' (Playwright + Camoufox Python + pytest + Group F transpose) |
| #23 | Session 1.5 | 行业知识图谱 Platform Layer (LLM/KG/Discovery/Scheduler/Seed + 10 Vitest 132 例) | 2026-04-21 | → Session 1.5' (SQLAlchemy + Alembic + pytest 单测) |
| #24 | Session A0 | Admin 认证脚手架 (Next.js JWT + Edge middleware) | 2026-04-21 | → Session A0' (FastAPI Depends + python-jose + passlib + slowapi) |
| #25 | (横切) | Session Prompt 编写 12 公约 (规则 1-12) | 2026-04-21 + 2026-04-23 | 全部继承, 应用到 11 Python Sessions |
| #26 | Session 2 | 智能监测 Pipeline + Group G G1-G4 + persona attempts.browser_profile 契约 | 2026-04-22 | → Session 2' (SQLAlchemy JSONB + Pydantic v2 + Group G transpose) |
| #27 | Session 2.1 | Planner LLM Refinement + Group H H1-H3 + rewrite_meta JSONB | 2026-04-22 | → Session 2.1' (FastAPI httpx LLM client + canned transport + Group H transpose) |
| #28 | Session 1.2 | Camoufox + 双修正基线 + Phase A Platform Layer 边界 + Luban live | 2026-04-22 / 2026-04-23 | → Session 1.2' (Python Playwright Camoufox + Luban httpx client) |
| #29 | (横切) | 全 Python 后端架构反转 | 2026-04-26 | 触发本次重写, 是所有 Python Session 的根因 |
| #30 | (横切) | 每 Session 必须 preview env + 前后端联动可验证 | 2026-04-26 | Session 0' 消化 CI/CD 基建 |
| #31 | (横切) | 工作仓切换到 jotamotk/GenPano.git + 每 Session 一个分支 | 2026-04-26 | 全部 Python Session 在新仓推进 |

### 决策与 PRD/IA 关联 (frontend/ 设计稿层)

| CLAUDE.md 决策号 | 主题 | Python Session 落地 |
|-----------------|------|-----------|
| #2 | Brand/Industry Mode IA v2.0 (Stripe pill toggle + 9+4 sub-views) | Session 4b' (React 客户端实现, JSX) |
| #9 | Auth-Required Data Viewing | Session 4a' (FastAPI middleware + React Route Guard) |
| #10 | 零 Project 态 Route Guard → /onboarding | Session 4a' |
| #15 | 提及率 non-brand 口径 (dimension='品类') | Session 2' (Category Purity transpose) + Session 3' (analyzer 分母) |
| #18 | 测试高度自动化 A++ | Session 0' (CI 框架) + 全 Session (pytest L1-L4) |
| #19 | Citation 全链路 §4.2.6/§4.2.7 | Session 3' (FastAPI endpoints + 3 MCP 工具) |
| #20 | V2 分析页统一 + Filter Bar + Heatmap + Wave-4 productId/brandId 契约 | Session 4b' (React 实现) |

---

## 文档真相源索引 (Phase 2 文档审查后)

| 文档 | 角色 | 当前状态 |
|------|------|----------|
| `docs/PRD.md` | 产品需求真相源 (App) | 现存 v1.3, 决策 #29 后内容仍 100% 适用 (PRD 不绑技术栈) |
| `docs/ADMIN_PRD.md` | 产品需求真相源 (Admin) | 现存, 决策 #29 后仍适用 |
| `docs/REPLAN_2026_04_26.md` | M1-M4 路线图 + 11 Session 总览 | 决策 #29 直接产出, 是本进度文档的上游 |
| `docs/CLAUDE_CODE_SESSIONS.md` | Python 11 Session 详细规划 + 附录 A (Next.js 时代归档) | 2026-04-26 重写 |
| `docs/HARNESS_ENGINEERING.md` | 方法论 + Phase Gate 1-5 + L1-L3 Agent quality | 2026-04-26 transpose 到 Python (本次审查 §8 + §10.3-§10.6) |
| `docs/DESIGN_TOKENS.md` | 设计 token + C1-C15 chart 契约 | 决策 #29 后**不动** (consumer 全是 JSX, 前端栈不变) |
| `docs/TEST_STRATEGY.md` | 4 层测试策略 + 异常场景矩阵 | 待 Session 0' 时 transpose pytest 命令 |
| `docs/DATA_MODEL.md` | Prisma schema 语义 + CHECK 约束 | 待 Session 1.5' 之前重写为 SQLAlchemy + Alembic |
| `docs/ADAPTER_CONTRACT.md` | 3 引擎 Adapter 契约 | 待 Session 1' 之前 transpose 接口签名 (语义保留) |

---

## 历史快照 (2026-04-22, 架构反转前最后一次进度更新, 仅供回溯)

> 反转前的最后一次绿状态: Session 0-rev ✅ / Session 1 ✅ / Session 1.5 ✅ / Session 2 ✅ / Session 2.1 ✅ / Session A0 ✅. 这些 Session 在 Next.js 栈上全部宣绿但代码作废, 决策资产已 transpose 到上方 Python 11 Session 的对应行。

