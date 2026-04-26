# GENPANO Session 进度总览

> 更新日期: 2026-04-22
> 真相源: `docs/CLAUDE_CODE_SESSIONS.md` (App) + `docs/ADMIN_CLAUDE_CODE_SESSIONS.md` (Admin)
> 本文档只做"索引 + 状态"汇总, 不重复真相源内容。

---

## 图例

| 符号 | 含义 |
|------|------|
| ✅ | 已完成 (含 Phase Gate 全过 + CLAUDE.md 决策登记) |
| 🟡 | 进行中 |
| ⬜ | 待启动 |
| ⛔ | 依赖未满足, 暂不可启动 |
| 🗑 | 已废弃 / 被取代 |

---

## 三条并行 Track

GENPANO 工程拆成三条 Track, 各有依赖关系:

1. **App Track** (`CLAUDE_CODE_SESSIONS.md`): Session 0-rev / 1 / 1.2 / 1.5 / 2 / 2.1 / 3 / 4a / 4b / 5 — 用户侧完整闭环 (爬虫 → KG → Pipeline → API/MCP → Onboarding → Dashboard → 上线)
2. **Admin Track** (`ADMIN_CLAUDE_CODE_SESSIONS.md`): Session A0 / A1 / A2 / A2.1 / A2.2 / A2.3 / A2.4 / A3 / A3.1 / A3.2 / A3.3 / A4 / A5 — 运营后台 (认证 → 审计 → Pipeline 监控 → KG 运营 → 成本告警 → Citation Tier)
3. **UI Prototype Track** (CLAUDE_CODE_SESSIONS.md §"T" 段): T1' / T2' / T3' / T4' / T5' / T6' — 原型级 IA v2 重构 (evolve `frontend/`, Frank 明确为"原型, 正式工程放 App Session 4a/4b")

---

## App Track 进度

| Session | 主题 | 状态 | 备注 |
|---------|------|------|------|
| Session 0 (deprecated) | 项目初始化 & 技术选型 | 🗑 | 被 Session 0-rev 取代 (2026-04-21 Preflight 后重写) |
| **Session 0-rev** | 测试地基 + Backend 脚手架 (38 Harness / 5 self-seeded fixture / Vitest 覆盖率 / openapi baseline) | ✅ | CLAUDE.md #21 触发源; 交付 backend/ + scripts/ci-check.mjs 等 |
| **Session 1** | 核心监测引擎 · AI 爬取系统 (Adapter/Parser/Scheduler/Account Pool/HAR) | ✅ | **CLAUDE.md #22** (2026-04-21); 结构框架 + 纯逻辑 13 套 Vitest; execute() TIMEOUT sentinel 留给 1.2 |
| Session 1.2 | Adapter Hardening (Camoufox / CAPTCHA / HAR 回归 / 鲁班 SMS 真实 client) | ⬜ | 依赖 Session 1 ✅ (已满足); 接 execute() 真实 Playwright 路径 + 3 家 golden HAR |
| **Session 1.5** | 平台数据基础设施 · 行业知识图谱冷启动 (LLM 端口/仓库/Discovery/KG/Scheduler/Seed) | ✅ | **CLAUDE.md #23** (2026-04-21); InMemory + Prisma 双 Repository + `seed-platform-data.ts` dry-run 全绿 |
| **Session 2** | 智能监测 Pipeline (Topic → Prompt → Query 三层 Planner) | ✅ | **CLAUDE.md #26** (2026-04-22); 9 套 Vitest 399/399 + Golden Case 语义断言 + Group G Harness 4 规则 + 3 Admin 只读端点 + 20260422 baseline migration (persona 走 attempts.browser_profile, 不加列) |
| **Session 2.1** | Planner LLM Refinement (Topic 真实度 + Prompt naturalize + Profile-Aware Prompt Rewrite) | ✅ | **CLAUDE.md #27** (2026-04-22); 3 层 LLM 编排 (refine→naturalize→rewrite) + canned transport 保 CI 脱网绿 + 20260423 migration (audit 字段进 platform_topics/platform_prompts, rewrite_meta 进 query_executions.attempts JSONB 不加列, 守 #26.C1) + Group H Harness 3 规则 (H1/H2/H3) + 18/18 selftest + Vitest 464/464 + 20/20/20 sample dump (canned, live VOLC 见 `docs/SESSION_2_1_LIVE_SMOKE_DEFERRED.md`) |
| Session 3 | 分析引擎 + API + MCP Server (含 Citation §4.2.6 A-H + §4.2.7 A-H) | ⬜ | 依赖 Session 1 + 1.5 + 2 ✅ (已满足) + Session 2.1 强烈推荐前置 (Response 采集前 Query 应已 LLM-rewrite); MCP 工具 `genpano_get_citations` / `list_pr_targets` / `simulate_authority_boost` 在此 Session 交付; 开工前先 patch `docs/DATA_MODEL.md §2.5` 落地 CLAUDE.md #26 C1 偏差 |
| Session 4a | 用户系统 + Onboarding (AuthPage + /onboarding 4 步 + Route Guard) | ⬜ | 依赖 Session 3; 含 CLAUDE.md #10 零 Project 态 Route Guard 实施 |
| Session 4b | Dashboard + 报告 + 咨询转化 (Brand/Industry Mode IA v2 所有页面实现 + PDF 报告生成) | ⬜ | 依赖 Session 4a; T1'-T6' 原型正式工程化 |
| Session 5 | 上线打磨 + 中国引擎适配 (最终部署 / 运维脚本 / 最后一轮视觉回归) | ⬜ | 依赖 Session 4b; MVP 终点 |

### App Track Gate 链 (CLAUDE_CODE_SESSIONS.md §Session 中断恢复)
```
Session 0-rev ✅ → [Gate 1 架构] → Session 1 ✅ → Session 1.5 ✅
    → [Gate 2 平台数据+爬取] → Session 2 ✅ → Session 2.1 ⬜ → Session 3
    → [Gate 3 引擎+API] → Session 4a → [Gate 4a 用户系统] → Session 4b
    → [Gate 4b 完整闭环] → Session 5 → MVP 上线
```

**当前进度**: Gate 2 已过, Session 2 已宣绿 (2026-04-22)。**强烈推荐下一步**: Session 2.1 (Planner LLM Refinement) — 把 Topic/Prompt/Query 三层从纯规则模板升级到 LLM-naturalize + Profile-aware rewrite, 保证 Response 采集前 Query 已"像真人问法"。Session 3 可在 2.1 之后启动; Session 1.2 Adapter Hardening 可在 2.1 和 3 之间的空档补。

---

## Admin Track 进度

| Session | 主题 | 状态 | 备注 |
|---------|------|------|------|
| **Session A0** | Admin 认证脚手架 & 登录页 (JWT + bcrypt + rate limiter + /admin middleware + bootstrap) | ✅ | **2026-04-21 宣绿** (Step 11/11.5/11.6/12/13/14 全过) · Phase Gate 9/9 PASS · CLAUDE.md #24 (A/B/C1.1-C1.3/C2/C3/C4/D/E/F/G) + #25 (Harness D8/D9/D10) 登记完成 |
| Session A1 | Admin 脚手架 + 账号身份 + 审计 (多角色 ops_admin/viewer + 操作日志) | ⛔ | 依赖 A0 宣绿 + App Session 0-3 完成 (per `ADMIN_CLAUDE_CODE_SESSIONS.md` 首行批注) |
| Session A2 | Pipeline Dashboard + Planner 核心 + 基础数据模型 | ⬜ | 依赖 A1 |
| Session A2.1 | Planner 深化 · Prompt 模板 + ProfileGroup | ⬜ | 依赖 A2 |
| Session A2.2 | Tracker 核心 · Attempt 列表 + 引擎健康 | ⬜ | 依赖 A2 |
| Session A2.3 | Tracker 深化 · Trace & Lineage + 变更审批中心 | ⬜ | 依赖 A2.2 |
| Session A2.4 | Analyzer · 质量分析 + 人工质检 (5 层抽样 + Trust Score 11 边界) | ⬜ | 依赖 A2 + A2.2 |
| Session A3 | 知识图谱运营中心 (KG CRUD + LLM 审批 + 8 种 change_type) | ⬜ | 依赖 A1 + A2 |
| Session A3.1 | 实体合并/拆分 & 信任分 (KG 深化 Part 1) | ⬜ | 依赖 A3 |
| Session A3.2 | KG Diff Viewer (KG 深化 Part 2) | ⬜ | 依赖 A3 + A3.1 |
| Session A3.3 | KG 质量监控 & LLM 预算闸门 (KG 深化 Part 3) | ⬜ | 依赖 A3 + A3.1 + A3.2 |
| Session A4 | 成本 & 告警 & 调度 & 商务 & MCP | ⬜ | 依赖 A1-A3 |
| **Session A5** | Citation Tier CRUD + MCP Token 签发 (CLAUDE.md #21 新增 2026-04-21) | ⬜ | 依赖 A4; 被 App Session 3 MCP server 依赖 (交叉依赖) |

### Admin Track 当前状态

**Session A0 已宣绿 (2026-04-21)**: Phase Gate 9/9 全过, CLAUDE.md #24 + #25 登记完毕.
**下一步**: Admin Track 后续 Session (A1 及以后) 按文档首行批注等 **App Session 0-3 完成** 后才可启动. 当前阻塞在 App Session 2/3 未开工.
**Step 13 pending**: A1 §2 inline schema 反向同步 patch (删 phantom totp_secret + 引用式补充 A0 已落 3 字段 + §0 新规则 8 固化) — Frank 会在本 Step 完成后单发给 CC.

---

## UI Prototype Track 进度 (`frontend/` 原型级)

> Frank 明确: "frontend/ 目前当作原型图, 正式工程通过 App Session 4a/4b 重做"。T1'-T6' 是原型 evolve, 不是正式工程。

| Session | 主题 | 状态 | 备注 |
|---------|------|------|------|
| Session T1' | DashboardLayout 重构 · 顶栏 Mode Toggle + 侧栏 Mode-Aware | ✅ (原型) | CLAUDE.md #20 Brand/Industry Mode IA v2.0 落地 |
| Session T2' | Brand Mode 5 个深度分析页 | ✅ (原型) | 含 v3.2 Topics 跨 Mode 复用 (2026-04-21) |
| Session T3' | Industry Mode 4 页 | ✅ (原型) | 含 v3.2 删 IndustryTopicCoverageHeatmap (2026-04-21) |
| Session T4' | Onboarding + Route Guards + Auth-Required + 301 + 遗留清理 | ✅ (原型) | CLAUDE.md #9/#10 落地到原型 |
| Session T5' | 全局打磨 + Harness 全量 + 视觉回归基线 + 性能 | ✅ (原型) | |
| Session T6' | V2 分析页视觉统一 + Filter Bar + Heatmap + 竞品叙事 + 数据口径 + Wave-4 详情页 brandId query string 契约 | ✅ (原型) | CLAUDE.md #20 (含 Wave-4 回滚 + 最终形态) |

**UI Prototype Track 状态**: 原型已到 v3.2, 不再推进。正式实现在 App Session 4a/4b。

---

## 当前关键路径 (2026-04-22 Session 2 宣绿后)

```
[Admin Track A0 已宣绿, 后续 Admin Session 阻塞 App Session 0-3 完成]
     │
     ▼
┌─────────────────────────────┐
│  当前可推进 (App Track)     │
├─────────────────────────────┤
│  Session 2.1 · Planner LLM  │ (强烈推荐, 解决"Session 2 是纯规则、不像真人"的 gap)
│  Session 3 · 分析+API+MCP   │ (Gate 2 → Gate 3 关键, Citation §4.2.6-7 + 3 MCP 工具)
│  Session 1.2 · Adapter      │ (2026-04-22 Prompt 真相源校准已升级, 见下)
└─────────────────────────────┘
              │
              ▼ (App Session 0-3 全绿后)
      Admin Session A1 解锁
```

**建议**: Session 2.1 ✅ 已宣绿 (2026-04-22 64c4201 + G5 live smoke). 当前在推 **Session 1.2** (Adapter Hardening - 真实 Playwright + HAR L3 + 5 项 Schema 补丁). Session 3 随后跟进。

**Session 1.2 Prompt 2026-04-22 真相源校准更新** (CLAUDE_CODE_SESSIONS.md §Session 1.2):
- 新增 `§Session 1 已交付基础` 表 — 7 个已就位模块禁重做, 只升级 (humanize / errors / retry / solve / state-machine+pool / sms-luban / har-sanitize)
- 新增 `## 0. Pre-Flight 环境依赖 + Cross-Session 契约` — 5 项环境依赖 (Camoufox / Ninja Clash / CapSolver / Volc Vision / pg_cron) 带 stub 降级路径 + `attempts.browser_profile` JSONB 跨 Session 硬约束 (CLAUDE.md #26.C1 + #27 G) + 5 项 Schema 补丁 (Account.lastProxyId / AccountRegistrationLog / engine_health_5min / ProxyNode / ProxyHealthLog 到 migration `20260424000000_session_1_2_adapter_hardening/`)
- §1-§7 每个任务条目已标注 **[Session 1 已落 XXX, 本 Session 升级 YYY]** / **[本 Session 全新]**, 防止 CC 重做
- §6.2 Harness 新规则从"4 条"收敛到 "3 条 (inner-text / xpath-absolute / bare page.fill→submit)" + harness selftest 18 → 21 (Session 1 的 F1/F2/F3 不得重复)
- §验收 "8 种错误码" 修正为 "9 种", 分"升级 / 新建 / 硬约束 / 环境"四类勾

**Session 3 开工第一批动作** (Session 1.2 宣绿后): patch `docs/DATA_MODEL.md §2.5` 落地 CLAUDE.md #26 C1 (persona_snapshot 改描述为 `query_executions.attempts[].browser_profile` 子字段)。

---

## CLAUDE.md 决策号与 Session 对照

| CLAUDE.md 决策号 | Session | 主题 | 日期 |
|-----------------|---------|------|------|
| #21 | Session 0-rev | 2026-04-21 Review 修复闭环 (38 Harness + 7 数据契约 + 5 fixture) | 2026-04-21 |
| #22 | Session 1 | AI 引擎爬取框架 (Adapter/Parser/Scheduler/Pool/Humanize/Proxy/HAR + 13 Vitest + F1/F2/F3 Harness) | 2026-04-21 |
| #23 | Session 1.5 | 行业知识图谱 Platform Layer (LLM/KG/Discovery/Scheduler/Seed + 10 Vitest 132 例) | 