# Session A1' · Admin User / KG / Pipeline 监控 (Python rewrite)

> **Status**: Phase A 规划锁定 (2026-04-26) — 由 `docs/REPLAN_2026_04_26.md` §4 触发的 Python pivot 第 11/11 个 Session Prompt (Admin 域 M4 milestone, 倒数第二; SESSION_4B 收尾)
>
> **Description**: 在已就位的 App 后端 (Sessions 0' / A0' / 4a' / 1' / 1.5' / 1.2' / 2' / 2.1' / 3') + Admin auth scaffold (A0') 之上,
> 落地 Admin 三大业务域 — **Module A 用户管理** (3 子页) + **Module B Pipeline 监控** (摘要 + 深化, 取 Pipeline Dashboard / 引擎健康 / 队列 / 账号池视图 / 代理订阅健康 / 重试中心 6 个 MVP 必需子页) + **Module C 知识图谱运营** (摘要 + 深化, 取行业品类树 / 品牌审核 / 产品审核 / 别名关系 / Brand Submission Inbox / Discovery Logs 6 个 MVP 必需子页) + **Module D 横切微 MVP** (Cost Dashboard 只读看板 + Audit Log 全局视图 — D 其余 5 子页推 Phase 2)。
>
> **Dependencies (硬前置)**:
>   - **Session A0'** Admin auth (JWT + cookies + `requireAdminSession()` / `requireReauth()` middleware)
>   - **Session 1.2'** Account Pool Platform Layer (`backend/src/accounts/**` — 决策 #28.A 边界纪律: Admin **必须 wrap 不得 rewrite**)
>   - **Session 1.5'** KG Platform Layer (`backend/src/platform/**` 的 KG 仓储 + Brand Submission 模型)
>   - **Session 3'** 分析 + Cost monitor + Audit log infra (`cost_paused` Redis flag / `admin_audit_log` 表)
>   - **Session 0'** CI/CD + preview env (Render Admin service / Vercel admin subdomain)
>
> **Milestone**: M4 (Admin MVP) — A1' Phase Gate Frank 接受标准 = 在 preview admin 子域上看见**真实** doubao 账号池水位 + 当日累计成本 + 一条 Brand Submission 从用户提交流向 Admin Inbox 流向 active 的端到端审核动作; M4 = MVP 完成 (剩 4b' IA v2.0 完整 JSX→TSX 迁移)
>
> **Branch (决策 #31)**: `session-A1prime` 从 main fork; **不 cherry-pick** 历史 claude/* 分支代码; 所有提交按 §5 12-Step Delivery 原子化, 每步独立 commit
>
> **Truth Source Authority**: 本 Session 以 `docs/ADMIN_PRD.md` (master) + `docs/ADMIN_PRD_B_PIPELINE.md` (B 模块深化, supersedes §4.2 摘要) + `docs/ADMIN_PRD_C_KG.md` (C 模块深化, supersedes §4.3 摘要) + `docs/ADMIN_CLAUDE_CODE_SESSIONS.md` (Session 实施约束) 四份为唯一真相源, **不引用 App 端 `docs/PRD.md`** (`feedback_genpano_app_truth_source.md`)。Adapter / 账号池 / KG 行为细节 cross-ref `docs/ADAPTER_CONTRACT.md`。

---

## §0 Pre-Flight Grep Contract (决策 #25 Rule 2 + Rule 11)

**开工第一批动作必须先跑下列 11 条 grep, 输出与本 Prompt §1 真相源索引一致才能进入 §5 实施步骤; 不一致则停在 §3 STOP Type B 等 Frank alignment, 严禁推进。**

```bash
# F1. 确认 ADMIN_PRD.md §4.1 Module A (用户管理) 三子页未漂移
rg -n "/admin/users(/|$)" docs/ADMIN_PRD.md | head -20

# F2. 确认 §4.2 Pipeline 摘要 6 子页 + B 深化 3 模块结构稳定
rg -n "/admin/pipeline/(planner|tracker|analyzer|dashboard|changes)" docs/ADMIN_PRD_B_PIPELINE.md | head -30

# F3. 确认 §4.3 KG 摘要 6 子页未变 (C 深化只是 +3 ★ 子页 entity-ops/diff/quality, MVP 不开)
rg -n "/admin/kg/" docs/ADMIN_PRD_C_KG.md | head -20

# F4. 确认 §4.4 Module D 7 子页全名不漂移 (本 Session MVP 只取 cost/daily + audit-log)
rg -n "^####? §?4\.4\.\d" docs/ADMIN_PRD.md

# F5. 确认 §5 Cross-cutting 6 段 (权限矩阵 / 审计规范 / 部署 / 数据层 / API prefix / Admin Auth) 未漂移
rg -n "^### §?5\.\d" docs/ADMIN_PRD.md

# F6. 确认 A0' 已交付 admin auth 4 表 (admin_users / admin_sessions / admin_password_resets / admin_login_attempts)
rg -n "class Admin(User|Session|PasswordReset|LoginAttempt)" backend/app/models/admin/*.py

# F7. 确认 1.2' 已交付 Account Pool Platform Layer 单一入口 (决策 #28.A: Admin 必须 import, 不得 rewrite)
rg -n "from app\.accounts\." backend/app/admin/api/v1/ 2>/dev/null | head -5
ls backend/app/accounts/

# F8. 确认 3' 已交付 cost_paused Redis flag + admin_audit_log 表
rg -n "cost_paused|admin_audit_log" backend/app/

# F9. 确认 admin_users.role CHECK 仅 super_admin 单值 (A0 决策 #24.C2)
rg -n "role.*CHECK|role.*IN \(" backend/alembic/versions/*admin*.py

# F10. CLAUDE.md 最近 3 条决策对 A1' 范围影响 (Rule 11)
rg -n "^\d+\." CLAUDE.md | tail -3

# F11. .auto-memory 近 7 天新增 feedback (规则 11)
ls -lt .auto-memory/feedback_*.md 2>/dev/null | head -5
```

**Pre-flight 失败的 per-grep STOP 映射 (决策 #25 规则 12 + 规则 11)**:

| Grep | 失败条件 | STOP 类型 | 处置 |
|---|---|---|---|
| F1 | ADMIN_PRD §4.1 `/admin/users(/...)` 三子页路径漂移或重命名 | **Type B** | 走 §3 STOP B1; 等 Frank 决定改 PRD 还是改 Prompt |
| F2 | ADMIN_PRD_B 6 子页结构 (planner/tracker/analyzer/dashboard/changes) 任一缺失或重排 | **Type B** | 走 §3 STOP B1; v2 重构契约不可漂 |
| F3 | ADMIN_PRD_C KG 摘要 6 子页路径漂移 | **Type B** | C 深化 +3 ★ 推 Phase 2, MVP 不开 — 任何 ★ 子页混进 MVP 即 STOP |
| F4 | ADMIN_PRD §4.4 Module D 7 子页未列全 (本 Session MVP 取 cost/daily + audit-log) | **Type B** | 走 §3 STOP B1 |
| F5 | ADMIN_PRD §5 Cross-cutting 6 段缺失 | **Type B** | 权限 / 审计 / 部署 / 数据层 / API prefix / Auth 任一段号漂移立即 STOP |
| F6 | A0' admin auth 4 表 (admin_users/admin_sessions/admin_password_resets/admin_login_attempts) 任一缺失 | **Type A** (依赖未就绪) | 暂停实施, 等 A0' 落地; 不做 best-effort |
| F7 | `from app.accounts.` 反向 import 出现在 `backend/app/admin/api/v1/` (违反决策 #28.A 边界) | **Type B** | 走 §3 STOP B3 (J2 violation); 立即拆掉重来 |
| F8 | Session 3' 未交付 `cost_paused` Redis flag 或 `admin_audit_log` 表 | **Type A** | 暂停, 等 3' 落地; 决策 #28.A 边界硬约束 |
| F9 | `admin_users.role` CHECK 约束变多值 (出现 ops_admin 等) 与 A0 决策 #24.C2 super_admin 单值不符 | **Type B** | 走 §3 STOP B2; 决议 schema rollback 还是 A1' 内顺手扩 (走规则 4 双向同步) |
| F10 | CLAUDE.md 最新 3 条决策对 A1' 范围有影响 (规则 11) | **不一定 STOP** | 列变化清单进 §1 引用项; 若变更涉及 admin RBAC / audit / module IA 走 Type B; 仅文档微调可继续 |
| F11 | .auto-memory 近 7 天新增 feedback 包含 admin / RBAC / audit 关键字 | **不一定 STOP** | 列 diff, 若与本 Prompt §1 / §2 范围矛盾走 Type B; 仅 cosmetic 可继续 |

**任一 F1-F9 STOP 立即停下, 写 alignment note 给 Frank, 等回复后再决定调整 Prompt 还是调整代码; F10/F11 列 diff 进 §1 freshness check 段。**

---

## §1 Truth Source Index (决策 #25 Rule 5)

### 引用 (Read-only, 本 Session 不修改)

| 真相源 | 段号 / 文件 | 用途 |
|---|---|---|
| ADMIN_PRD.md | §3 信息架构 | 侧栏 4 模块 + 子页树 (Admin/Pipeline/KG/Cross) |
| ADMIN_PRD.md | §4.1 Module A 用户管理 | A1-A3 三子页 IA + 状态机 + 权限边界 (Admin **不得直改** 用户邮箱/密码/Project) |
| ADMIN_PRD.md | §4.4.1 Cost Dashboard | KPI 4 卡 + 3 级下钻 + 80%/100% 预算阈值规则 (本 Session MVP 只读, 不实现 emergency raise budget input) |
| ADMIN_PRD.md | §4.4.7 Audit Log | 全局视图 + 筛选 + super_admin CSV export 自身写 audit |
| ADMIN_PRD.md | §5.1 权限矩阵 | super_admin 单值 CHECK; ops/data_ops/support/bizdev schema 预留 |
| ADMIN_PRD.md | §5.2 审计规范 | `kg_*` / `scrape_account_pool` / `engine_runtime_config` / `budget_config` / 用户 status 改 / 数据导出 / 手工 trigger / 角色变更 — 必须 INSERT 进 `admin_audit_log` |
| ADMIN_PRD.md | §5.3 部署 | `admin.genpano.internal` 子域 + Cloudflare Access (Layer 1) + app session (Layer 2); MVP 无 2FA, schema 留 `admin_users.totp_secret` |
| ADMIN_PRD.md | §5.4 数据层 | Admin 共享 App Postgres + admin_* 小表; **写**仅限 KG/Pipeline/Config (须审计); 用户数据**只**写 `status` |
| ADMIN_PRD.md | §5.5 API prefix | `/admin/api/v1/*` 与 App `/api/v1/*` 严格隔离 |
| ADMIN_PRD.md | §5.6 Admin Auth | A0' 已落地: 15min access / 7d refresh / 30min re-auth / silent refresh |
| ADMIN_PRD_B_PIPELINE.md | §0.2 侧栏 | 数据管道 4 段 (Planner / Tracker / Analyzer / 横切) |
| ADMIN_PRD_B_PIPELINE.md | §1.1 采集调度总控 | 当日批次进度 + Planner 状态 + 历史批次 (本 Session MVP **只读**, 不开启 kill switch + 立即运行 Planner) |
| ADMIN_PRD_B_PIPELINE.md | §1.5 采集资源 | 账号池 + 代理池子页规范 |
| ADMIN_PRD_B_PIPELINE.md | §2.2 执行追踪 (Attempts) | Pending/Running/Failed/Completed Tab + MAX_RETRY=3 + 失败 Attempt 重试 (本 Session MVP **只看不重试**) |
| ADMIN_PRD_B_PIPELINE.md | §2.3 引擎健康 | engine_health_5min materialized view + 8 错误码 + DOM change P1 alert |
| ADMIN_PRD_C_KG.md | §1 K1-K12 运营场景 | KG 12 工作流, MVP 取 K1/K2/K3/K4/K6/K11 共 6 项 |
| ADMIN_PRD_C_KG.md | §2 子页总览 | C1-C6 (MVP) + C7-C9 ★ (Phase 2) |
| ADMIN_PRD_C_KG.md | §3.C1-§3.C6 | 子页七段式规范 (目的/IA/交互/UI/边界/权限审计/验收) |
| ADAPTER_CONTRACT.md | §5.1 账号状态机 | 4 状态 ACTIVE↔COOLDOWN(12h)↔FROZEN↔BANNED |
| ADAPTER_CONTRACT.md | §5.3a Pre-Warm | 7 步流程 + PRE_WARMING/QUARANTINED 变体 |
| ADAPTER_CONTRACT.md | §5.4 自动注册 | 鲁班 SMS + doubao/deepseek-CN 自动入池 |
| ADAPTER_CONTRACT.md | §6 错误码 | 9 种 AdapterError + 重试策略矩阵 (Pipeline 错误展示用) |
| ADMIN_CLAUDE_CODE_SESSIONS.md | §A1 / §A2 / §A3 / §A5 | 旧 TS 实现指南; Python rewrite 不照搬代码, 但 IA / 验收点 / RBAC 范围以这里为准; A5 (Citation Tier CRUD + MCP Token) 已并入本 Session, 见决策 #21.E |
| PRD.md | §4.2.6 (citation tier 表 5 级权重) | 决策 #19 锁定: 0 未知 / 1 官方 1.0 / 2 权威媒体 0.7 / 3 KOL 0.4 / 4 UGC 0.15; Citation Tier CRUD UI + 回溯 recompute 任务的语义真相源 |
| PRD.md | §4.5.2 (3 个 MCP 工具契约) | `genpano_get_citations` / `list_pr_targets` / `simulate_authority_boost` 工具 schema; MCP Token 签发与吊销服务的消费方契约 |
| CLAUDE.md | 决策 #21.E (Session A5 规格) | Citation Tier CRUD + 回溯 recompute Celery 任务 + `mcp_api_tokens` 表 + 60s Redis pub-sub 吊销黑名单; 半天工作量, 已并入本 Session |
| TEST_STRATEGY.md | §10 (Admin 测试矩阵) | A1-A5 测试任务 + 7 条 Admin-specific 异常 (Auth/RBAC/Audit/KG QA/Pipeline/Cost/Cross) |
| TEST_STRATEGY.md | §11 (P0/P1/P2 优先级清单) | 本 Session 承担 P2-1 (Admin KG QA 5 层抽样 + Trust Score 11 边界) + P2-2 (Admin Pipeline 监控面板) — 详见 `docs/TEST_COVERAGE_MAP.md` §4 A1' 段 |
| TEST_COVERAGE_MAP.md | §1 P0 / §3 P2 / §4 A1' 责任清单 | Plan K.1 索引: A1' 不直接承担 P0/P1, 仅 P2-1/P2-2 覆盖 (Phase 2 标 ❌, MVP 内只走 L2 单测占位) |
| CLAUDE.md | 决策 #9 / #19 / #21 / #24 / #25 / #28 / #29 / #30 / #31 | Auth-Required / Citation Tier / 测试地基 / A0 / 公约 / Platform Layer / Python pivot / preview env / branch-per-session |

### 修改 (本 Session 写入或新建)

| 真相源 | 修改类型 | 落点 |
|---|---|---|
| `backend/app/admin/api/v1/users/**` | 新建 | 用户列表 / 详情 / 登录审计 / 冻结 / 强制改密 / 软删除 (5 endpoints) |
| `backend/app/admin/api/v1/pipeline/**` | 新建 | dashboard / engines / queue / accounts / proxy / retry-center 6 子页 API (12 endpoints) |
| `backend/app/admin/api/v1/kg/**` | 新建 | industries / brands / products / aliases-relations / brand-submissions / discovery-logs 6 子页 API (16 endpoints) |
| `backend/app/admin/api/v1/cost/**` | 新建 | 当日 KPI + 7d/30d 时序 + 引擎/行业/品牌下钻 (3 endpoints) |
| `backend/app/admin/api/v1/audit-log/**` | 新建 | 全局 list + filter + CSV export (export 自身写 audit) |
| `backend/app/models/admin/*.py` | 扩展 | `UserModerationAction` / `UserActivityStat` / `KgReviewQueue` / `AliasConflict` / `BrandSubmission` / `Alert` / `CostDaily` / `BudgetConfig` SQLAlchemy 模型 |
| `backend/alembic/versions/*_admin_a1.py` | 新建 | 8 张新表 + 必要的 CHECK 约束 (status 枚举 / 角色 / Brand Submission 状态机 / Alert state) |
| `backend/app/services/admin_audit.py` | 新建 | `record_audit(operator_id, action, target_type, target_id, diff_json, reason, ip, ua)` 单一入口; ADMIN_PRD §5.2 列出的写操作必须经此函数 |
| `backend/app/services/account_pool_admin.py` | 新建 | 决策 #28.A wrapper: 调 `app.accounts.pool` / `app.accounts.auto_register` / `app.accounts.crypto_noop`; **零业务逻辑** |
| `backend/app/admin/middleware/rbac.py` | 新建 | `require_role('super_admin')` decorator + audit context injection |
| `backend/tests/admin/**` | 新建 | pytest async tests, 80% 覆盖率, 5 个 self-seeded fixture (J1-J5) |
| `frontend/src/admin/pages/**` | 新建 | Module A 3 页 + Module B 6 页 + Module C 6 页 + Module D 2 页 (cost overview + audit log) — 共 17 页 React+TSX, **不含** 设计稿之外的子页 |
| `scripts/ci_check.py` | 扩展 | Group J 5 条新规则 (J1-J5, 见 §4 Layer 2) |
| `scripts/ci_harness_selftest.py` | 扩展 | EXPECTED_POSITIVES 27 → 32 (J1-J5 fixture self-seeded) |
| `docker-compose.yml` | 扩展 | admin 子服务条目 (Vercel admin 子域 preview) |
| `docs/CLAUDE_CODE_SESSIONS_PYTHON.md` | 更新 | A1' 完成标志 + Phase Gate 验收记录 + 偏差登记锚点 |

### 真相源版本警告 (规则 11)

1. **决策 #28.A 必读**: Account Pool 业务逻辑全部在 `backend/app/accounts/**` (Platform Layer); Admin Pipeline `accounts` 子页 API 必须 `from app.accounts.pool import ...` / `from app.accounts.auto_register import ...`, **绝对不允许** 在 `app.admin.api.*` 重写鲁班 SMS / 自动注册 / cookie crypto 逻辑。开工前 `rg "from app\.accounts\." backend/app/admin/` 必须有命中, 否则代表走错路径。
2. **决策 #28.C1 plaintext cookie**: Admin UI 显示 cookies 永远 mask 为 `***`, 审计日志不记明文 cookie; `crypto_noop.py` 是未来加密升级的唯一入口, 本 Session 不替换。
3. **ADMIN_PRD §5.2 audit 必触发列表是 hard requirement**: 任何对 `kg_*` / `scrape_account_pool` / `engine_runtime_config` / `budget_config` 的写操作 + 用户 status 变更 + 数据导出 + 手工 trigger + 角色变更, 必须经 `record_audit()`; missed audit = J1 Harness block。
4. **决策 #24.C2 super_admin 单值**: A1' 仍然只开 super_admin, ops/data_ops/support/bizdev schema 留位但 CHECK 不放行; A2' (未规划) 才扩多角色; RBAC decorator 现在只接受 `super_admin` 一值, 加多值会触发 J3 Harness。
5. **ADMIN_PRD_B_PIPELINE §0.2 v2 重构**: 旧 v1 的 13 个子页 (B1-B13) 已映射到 v2 三模块 (Planner/Tracker/Analyzer); 本 Session 取 v2 路径 (`/admin/pipeline/dashboard` + `/admin/pipeline/planner/{scheduler,resources}` + `/admin/pipeline/tracker/{attempts,engines}` + retry-center 落在 tracker/attempts 之内), 不实现 Analyzer 页面 (推 Phase 2)。
6. **ADMIN_PRD_C_KG §2 C7-C9 ★ 不开**: Entity Merger / KG Diff / Quality Monitor 是深化新增 3 页, **MVP 不实现**, A1' 只开 C1-C6 摘要 6 页。
7. **ADMIN_PRD §4.4 Module D 7 子页 MVP 只开 2**: cost dashboard (只读) + audit-log; alerts / schedule kill switch / comms / commercial leads / mcp-ops 推 Phase 2。
8. **决策 #19 + 决策 #21.E Citation Tier CRUD + MCP Token 已并入本 Session (Plan J D1, 2026-04-26)**: 旧 Session A5 规格 (Citation Tier 5 级权重 CRUD + 回溯 recompute Celery 任务 + `mcp_api_tokens` 表 + 60s Redis pub-sub 吊销黑名单) 整体合入 A1', 不再单独排期 A5。Tier 表 5 级 (0 未知 / 1 官方 1.0 / 2 权威媒体 0.7 / 3 KOL 0.4 / 4 UGC 0.15) 走 DB seed + Admin CRUD UI, **禁** 硬编码进代码 (决策 #19 硬约束 + Harness E1)。MCP Token 签发面向 `genpano_get_citations` / `list_pr_targets` / `simulate_authority_boost` 三个 MCP 工具 (PRD §4.5.2), 吊销走 Redis pub-sub channel 60s 内全节点生效。
9. **决策 #9 Auth-Required 仍然成立**: Admin API 全线 `Depends(requireAdminSession)`; `/admin/api/v1/*` 与 `/api/v1/*` 严格分离 (ADMIN_PRD §5.5)。
10. **决策 #30 Frank Layer 3 验收**: Phase Gate 接受标准是在 preview admin 子域上**实操**完成 — 看真实账号池水位 + 真实当日成本 + 真实一条 Brand Submission 全流程, 不接受 mock 截图。

---

## §2 MVP Scope-Cut Declaration (决策 #25 Rule 10)

### ✅ 本 Session 做 (Y1-Y28)

**Module A · 用户管理 (3 子页, 5 endpoints)**
- **Y1** `GET /admin/api/v1/users` — 用户列表 (邮箱 / locale / 注册日期 / 最后活动 / status: active|frozen|deleted, 支持 search + status filter + pagination 50/page)
- **Y2** `GET /admin/api/v1/users/:id` — 用户详情 4 Tab (基本信息 / Project 列表只读 / 登录审计 30d / Moderation Actions 历史)
- **Y3** `POST /admin/api/v1/users/:id/freeze` — 冻结 (status='frozen' + 写 `user_moderation_actions` + audit log + 强制 invalidate 该用户所有 session)
- **Y4** `POST /admin/api/v1/users/:id/force-password-reset` — 触发"下次登录强改密" (写 `User.force_password_change_at = now()` + Resend reset 邮件 + audit log)
- **Y5** `DELETE /admin/api/v1/users/:id` — soft delete (status='deleted' + Project 标 archived 但**不删** + audit log)
- **Y6** `GET /admin/api/v1/users/login-audit` — 全局登录审计 (倒序时间 + 失败码筛选 + IP 筛选)

**Module B · Pipeline 监控 (6 子页, 12 endpoints — Planner/Tracker MVP 子集)**
- **Y7** `GET /admin/api/v1/pipeline/dashboard` — 三模块 KPI 一屏 (今日批次进度 + 4 层漏斗 + 总成本预估 + ETA + Planner 最后运行)
- **Y8** `GET /admin/api/v1/pipeline/planner/scheduler` — 当日批次 + 历史批次 30d + Planner 状态 (kill switch 字段读出, 但**不写**)
- **Y9** `GET /admin/api/v1/pipeline/planner/resources/accounts` — 账号池水位 (按引擎 ACTIVE / COOLDOWN / FROZEN / BANNED + PRE_WARMING / QUARANTINED 计数 + Top 10 即将冷却完成账号)
- **Y10** `POST /admin/api/v1/pipeline/planner/resources/accounts/:id/inject` — 手工注入 cookie bundle (调 `app.accounts.cli.inject` wrapper, 调 `crypto_noop.encode`, 写 audit, **决策 #28.A 严格 wrap 不 reimplement**)
- **Y11** `POST /admin/api/v1/pipeline/planner/resources/accounts/auto-register` — 触发 doubao 或 deepseek-CN 自动注册 (调 `app.accounts.auto_register.run`, 不超过每分钟 1 次速率, audit log)
- **Y12** `GET /admin/api/v1/pipeline/planner/resources/proxy` — Ninja Clash 订阅健康 (订阅最后 fetch / 节点总数 / healthy / blacklisted; **MVP 只读**)
- **Y13** `GET /admin/api/v1/pipeline/tracker/attempts` — Pending / Running / Failed / Completed Tab (按 query_id / engine / failure_code 筛选, pagination 100/page)
- **Y14** `GET /admin/api/v1/pipeline/tracker/attempts/:id` — 单 Attempt 详情 (含 sanitized HAR 链接 / 失败码 / 重试链)
- **Y15** `GET /admin/api/v1/pipeline/tracker/engines` — engine_health_5min 物化视图 + 8 错误码分布 + DOM change 监控 (3 连续 EXTRACT_EMPTY → P1 alert flag, **MVP 只展示 alert flag, 不实现 alert routing**)
- **Y16** `GET /admin/api/v1/pipeline/retry-center` — 失败 Attempt 分组 (CAPTCHA_UNSOLVED / PARSER_FAIL / PROXY_BLOCK / OTHER, **MVP 只展示**, retry trigger 是 Y17)
- **Y17** `POST /admin/api/v1/pipeline/retry-center/:attempt_id/retry` — 单条 Attempt 手工重试 (调 Celery enqueue, audit log, MAX_RETRY 仍受 Pipeline 全局限制 ADAPTER_CONTRACT §6)
- **Y18** `GET /admin/api/v1/pipeline/account-registration-log` — 自动注册历史 (success / failure 分组, 按引擎)

**Module C · 知识图谱运营 (6 子页, 16 endpoints — C1-C6 摘要)**
- **Y19** `GET /admin/api/v1/kg/industries` + `GET /admin/api/v1/kg/industries/:slug/categories` — 4 行业 + 3 级品类树
- **Y20** `POST /admin/api/v1/kg/categories` / `PATCH /admin/api/v1/kg/categories/:id` / `DELETE /admin/api/v1/kg/categories/:id` — 新建 / soft rename / soft deprecated (保留 `previous_names[]`, audit log)
- **Y21** `GET /admin/api/v1/kg/brands` — 品牌审核列表 (status: pending / approved / rejected / merged / inactive, 筛选 + 抽屉详情)
- **Y22** `POST /admin/api/v1/kg/brands/:id/approve` / `POST .../reject` / `POST .../merge` — 审核 3 操作 (audit log, merge 二次确认 + Brand × 2 → 1)
- **Y23** `GET /admin/api/v1/kg/products` + 3 审核操作端点 — 产品审核 (类似 brands)
- **Y24** `GET /admin/api/v1/kg/aliases-relations` — 别名冲突 + 关系审核统一面板 (按 `alias_conflicts.status='pending'` + 关系置信度 < 0.5 警示)
- **Y25** `POST /admin/api/v1/kg/aliases-conflicts/:id/resolve` — 仲裁别名归属 (audit log)
- **Y26** `GET /admin/api/v1/kg/brand-submissions` — 用户提交收件箱 (24h SLA 计时器, trust score 列, 高 trust 标 fast-track)
- **Y27** `POST /admin/api/v1/kg/brand-submissions/:id/{approve|reject}` — 用户提交审核 (approve → 流入 `kg_brands` status='approved', audit log)
- **Y28** `GET /admin/api/v1/kg/discovery-logs` — LLM Response 挖掘日志 (按 entity_type / status='pending'|'rejected', 拒绝时回流负例标记)

**Module D · 横切微 MVP (2 子页, 4 endpoints)**
- **Y29** `GET /admin/api/v1/cost/today` — 当日总成本 / 月累计 / 预算余额 / 预估月度 (4 KPI 卡)
- **Y30** `GET /admin/api/v1/cost/breakdown` — 3 级下钻 (by engine 时序堆叠 / by industry pie / Top 10 brand bar; query string `?level=engine|industry|brand&from=&to=`)
- **Y31** `GET /admin/api/v1/audit-log` — 全局审计列表 (operator_id / action / target_type / from / to filter)
- **Y32** `GET /admin/api/v1/audit-log/export.csv` — super_admin CSV 导出 (UTF-8 BOM, 10k 行上限, **导出本身写 audit**, slowapi 5/min rate limit)

**Module E · Citation Tier + MCP Token (并入自旧 A5, Plan J D1, 2026-04-26 — 决策 #19 + #21.E)**
- **Y33** `GET /admin/api/v1/citations/tiers` — 列出 5 级 Tier (0/1/2/3/4) 当前权重 + 修改历史 (`citation_domain_authority` 表 + audit log)
- **Y34** `PATCH /admin/api/v1/citations/tiers/:tierLevel` — 修改单个 Tier 权重 (super_admin only, audit 必写, 触发 Y35 recompute, body schema 限 `{weight: float ∈ [0, 1]}`)
- **Y35** `POST /admin/api/v1/citations/recompute` — 触发回溯 recompute Celery 任务 (PANO A 公式重算, idempotent by `recompute_job_id`, 任务进度查 `GET /admin/api/v1/citations/recompute/:jobId`)
- **Y36** `mcp_api_tokens` 表 (Alembic migration): `id uuid / user_id uuid FK / token_hash text / scopes text[] / created_at / last_used_at / revoked_at`; `POST /admin/api/v1/mcp-tokens` 签发 (返回 token plaintext **仅一次**, 入 audit) / `GET /admin/api/v1/mcp-tokens` 列表 / `DELETE /admin/api/v1/mcp-tokens/:id` 吊销
- **Y37** Redis pub-sub 吊销黑名单 worker — `DELETE` 端点写入 Redis channel `mcp:token:revoked`, 60s 内全节点 (App + Admin + Worker) 订阅生效; in-memory `Set<tokenHash>` 合 Redis subscriber, 60s TTL 防内存膨胀; 配 Celery beat 任务清扫已过期 token
- **Y38** Citation Tier UI 页 `/admin/citations/tiers` (5 行 Tier 表 + inline weight 编辑 + 修改历史抽屉 + recompute trigger 按钮 + 进度面板, super_admin only)
- **Y39** MCP Token UI 页 `/admin/mcp-tokens` (列表 + 签发对话框 (scopes 多选 = `genpano_get_citations` / `list_pr_targets` / `simulate_authority_boost` 三工具任选) + 吊销 + token plaintext 一次性 reveal modal)

**横切**
- **Y40** RBAC decorator `require_role('super_admin')` + audit context injection (operator_id 从 JWT claims, ip + ua 从 request)
- **Y41** Group J Harness 6 条 (J1 audit-must-fire / J2 admin-must-not-rewrite-account-pool / J3 rbac-super-admin-only / J4 cookie-mask-in-response / J5 user-data-write-only-status / J6 citation-tier-weight-no-hardcode 与 Group E E1 联防)
- **Y42** 19 React+TSX 页面 (17 + Citation Tier + MCP Token 共 19, 按 §1 修改清单), 共享 admin layout shell + AdminRouteGuard (复用 A0' 已交付)
- **Y43** docker-compose.admin 子服务 + Vercel admin.preview.genpano.dev 子域 + Render admin worker (含 Celery worker for recompute + Redis subscriber for token blacklist)
- **Y44** Phase Gate 3-Layer 验收 (§4)

### ❌ 本 Session 不做 (N1-N13)

- **N1** Module D 其余 5 子页 (alerts inbox / schedule kill switch / comms 公告 + 邮件模板 / commercial leads / mcp-ops) — Phase 2
- **N2** ADMIN_PRD_B_PIPELINE Analyzer 模块 (§3.1 quality / §3.2 QA) — Phase 2
- **N3** Pipeline §1.2 生成管线 single-page 三层 Tab (Topic→Prompt→Query 内联编辑) — Phase 2, 本 Session 只展示 dashboard 漏斗数字, 不开生成管线编辑器
- **N4** Pipeline §1.3 Prompt 模板 A/B testing — Phase 2
- **N5** Pipeline §1.4 ProfileGroup 权重调整 — Phase 2 (现行 4 个静态 seed 即可, 见 1.5' Profile Groups)
- **N6** Tracker §2.4 链路追溯 (Trace & Lineage) — Phase 2
- **N7** Pipeline §4.3 横切变更审批中心 — Phase 2 (本 Session 走 RBAC + audit, 不另开审批工作流)
- **N8** KG §C7-C9 ★ 三深化页 (Entity Merger / KG Diff / Quality Monitor) — Phase 2
- **N9** Multi-role RBAC 扩展 (ops/data_ops/support/bizdev) — Phase 2 Session A2 (尚未规划); A1' 仍只开 super_admin
- **N10** 2FA / TOTP — Phase 2; `admin_users.totp_secret` 字段保留但不启用
- **N11** Cloudflare Access 集成 — Phase 2 部署任务, 本 Session preview 上仅靠 Admin auth (cookie + JWT) 守门
- **N12** Pipeline kill switch 写入 + 立即运行 Planner 按钮 — Phase 2 (太危险, MVP 不开 hard write 路径)
- **N13** Brand Submission Trust Score 自动降权算法 — MVP 用静态字段, 不实现动态 score 计算; UI 只展示

---

## §3 STOP-Trigger Template (决策 #25 Rule 12)

### Type A · 环境失败

- **A1**: `psql` 连不上 preview Postgres → 停 (检查 Render database 服务 + DATABASE_URL secret)
- **A2**: alembic head 与 Session 3' 不一致 (出现 multi-head) → 停 (跑 `alembic merge heads`, 让 Frank 确认合并叙事再续)
- **A3**: `from app.accounts.pool import ...` import error → 停 (1.2' 未交付完整, 不能 wrap; 让 Frank check 1.2' 状态)
- **A4**: Redis 连不上, `cost_paused` flag 读不出 → 停 (3' 未交付完整, 检查 REDIS_URL)
- **A5**: Resend SMTP key 无效, `force-password-reset` 邮件发不出 → 停 (Y4 实现 PR 不可推, alignment Frank 是否切换 Resend account 或先 mock)
- **A6**: GitHub Actions 在 preview branch CI fail (ruff / mypy / pytest 任一红) → 停 (修绿才推 §5 下一步)
- **A7**: Vercel admin.preview.genpano.dev 子域 DNS / build / deploy 任一失败 → 停 (Frank 在 Vercel dashboard 检查 + 重试; 不让 stale UI 跑)

### Type B · 真相源冲突

- **B1**: §0 Pre-flight grep F2 / F3 输出与 ADMIN_PRD_B / ADMIN_PRD_C 描述不符 (sub-page URL 漂移) → 停, 让 Frank 决定改 PRD 还是改 Prompt
- **B2**: §0 grep F6 admin_users 表与 A0 决策 #24.C2 super_admin CHECK 不符 (出现 ops_admin 等多值) → 停, 决议 schema 是否 rollback
- **B3**: §0 grep F7 出现 `from app.admin.api... import luban` 类反向 import → 停, 立即 J2 violation, 拆掉重来
- **B4**: ADMIN_PRD §4.4 Module D 子页数 ≠ 7 (Frank 在 PRD 里悄悄加 / 删) → 停, 决策 N3 deferral list 是否需要重排
- **B5**: ADMIN_PRD §5.2 audit 必触发列表新增条目而 §1 真相源索引未同步 → 停, 走 Rule 4 双向同步
- **B6**: ADMIN_PRD_C_KG §2 C7-C9 ★ 转入 MVP (Frank 决定开) → 停, 重排 §2 Y/N 列表与 §5 step 数量
- **B7**: ADAPTER_CONTRACT §5.1 账号状态机增加新状态 (如 RATE_LIMITED) → 停, Account Pool wrapper Y10/Y11 边界需要重画
- **B8**: PRD §4.2.6 Citation Tier 5 级权重表数值漂移 (例 Tier 1 从 1.0 改 0.95, 与 CLAUDE.md 决策 #19 不符) → 停, 走 Rule 4 双向同步, 决议是改 PRD 还是 Y33-Y34 默认 seed
- **B9**: PRD §4.5.2 MCP 工具列表 ≠ 3 (`genpano_get_citations` / `list_pr_targets` / `simulate_authority_boost`) — 出现新增或删除 → 停, Y36 scopes 枚举需重排
- **B10**: Redis pub-sub channel 名称在 App / Admin / Worker 三端不一致 (例 `mcp:token:revoked` vs `mcp_token_revoked`) → 停, 60s 全节点生效契约破坏

### Type C · 范围溢出

- **C1**: 实施进入 Module D alerts inbox / schedule / comms 任一 (N1 列表) → 停, 这是 Phase 2 推手
- **C2**: 实施进入 Analyzer / Trace / 生成管线编辑器 (N2/N3/N6) → 停
- **C3**: RBAC decorator 接受第二个角色值 (N9) → 停
- **C4**: 出现"先在 admin handler 里写一遍 luban 注册再 import 一下"的双轨实现 → 停, J2 violation
- **C5**: Brand Submission Trust Score 出现自动 +/- 算法 (N13) → 停, MVP 只静态读
- **C6**: 任何对 `users.email` / `users.password_hash` / `projects.*` 的 PATCH/DELETE 路径 → 停, ADMIN_PRD §5.4 violation
- **C7**: Audit log 表出现 UPDATE / DELETE 路径 → 停 (§5.2 INSERT-only 强约束)
- **C8**: Cost CSV export 没有写自身的 audit log → 停 (Y32 验收点)
- **C9**: Citation Tier 权重出现硬编码进 `app/services/citation/**` 或 `app/parsers/citation*.py` (regex `tier_weight\s*=\s*[\d.]+` 或 `{0:\s*0\.0,\s*1:\s*1\.0` 类) → 停, 必须走 DB seed + Y33-Y34 CRUD, J6 + Group E E1 联防
- **C10**: MCP Token plaintext 出现于 audit log / 服务端日志 / DB 列 (除签发瞬间响应体外) → 停, 安全违反 (token 应只 hash 入库)
- **C11**: Redis token blacklist worker 未配置 60s TTL 内存清扫 → 停, 长期跑会内存膨胀
- **C10**: Pipeline kill switch / 立即运行 Planner 按钮被实现 (N14) → 停
- **C11**: 多于 17 个 admin React 页面被新建 → 停 (Y35 数量上限)
- **C12**: alembic 单 migration 文件超过 800 行 → 停 (拆成 2 个原子 migration; 太大不可 review)

---

## §4 Phase Gate 3-Layer (决策 #30)

### L3/L4 Phase Gate 卡控 (Hard Fail, 决策 2026-04-26)

**真相源**: `docs/REPLAN_2026_04_26.md §5` L3/L4 测试覆盖矩阵 + §5.3 Hard Fail 卡控规范.

**Hard Fail 强制**: 下列 L3/L4/Visual 任一未跑绿, GitHub Actions branch protection 拦截 merge. 不允许 soft warning, 不允许临时跳过.

**本 Session 必跑 L3 集成测试 (2 项)**:
- Citation Tier CRUD + 修改 Tier 2 权重触发 recompute Celery 任务 + PANO A 数值刷新 (idempotent by recompute_job_id); MCP Token 签发 + Redis pub-sub `mcp:token:revoked` 60s 全节点生效

**本 Session 必跑 L4 E2E 测试 (1 项)**:
- Frank 在 preview /admin/citations/tiers 改 Tier 2 0.7→0.8 → 看 PANO A 重算 → /admin/mcp-tokens 签发 token → curl 200 → 吊销 → 60s 后 401

**补救测试**: **TS A1+A5 → Python** (master 旧 A5 整体并入 A1', Plan J D1)

**Phase Gate 通过条件 (在原有 Layer 1-3 基础上追加)**:
- G_L3.1: Citation Tier CRUD + MCP Token 签发/吊销 2 项集成测试全部绿
- G_L4.1: Frank 浏览器 /admin/citations/tiers 改权重 → PANO A 重算 + /admin/mcp-tokens 签发/吊销
- G_Remedial.1: master A1 + A5 (原 5 session) 测试翻译到 Python

### Layer 1 · `scripts/verify_a1.sh` 单脚本本地全绿

```bash
#!/usr/bin/env bash
# scripts/verify_a1.sh — 本地 + CI 共用 (preview 部署前必须 0 错误)
set -euo pipefail

# L1.1 ruff lint
cd backend && ruff check app/ tests/

# L1.2 mypy --strict
mypy --strict app/

# L1.3 pytest 80% 覆盖率
pytest --cov=app --cov-report=term-missing --cov-fail-under=80 tests/

# L1.4 alembic upgrade-downgrade roundtrip
alembic upgrade head
alembic downgrade -1
alembic upgrade head

# L1.5 psql 禁列检查 (Module A 不得对 users.email / users.password_hash / projects.* 加 admin 写路径)
psql "$DATABASE_URL" -c "SELECT count(*) FROM information_schema.routines WHERE routine_schema='public' AND routine_name LIKE 'admin_set_user_%' AND routine_name NOT LIKE 'admin_set_user_status%';" | grep -q "0"

# L1.6 ci_check.py Group J 5 条 (audit / no-rewrite / rbac / cookie-mask / user-data-status-only)
python ../scripts/ci_check.py --group J

# L1.7 harness selftest 27 → 32
python ../scripts/ci_harness_selftest.py | grep -q "selftest: PASS  (32 / 32"

# L1.8 admin seed verification (super_admin 1 行 + 0 行其他角色)
psql "$DATABASE_URL" -c "SELECT role, count(*) FROM admin_users GROUP BY role;" | grep -q "super_admin"

# L1.9 audit log 路径完整 (跑一次 Y3 freeze 用例 + assert audit row 落地)
pytest tests/admin/integration/test_audit_path.py -k "freeze_user_writes_audit"

# L1.10 admin API curl smoke (登录 + 6 个核心端点全部 200, 1 个 forbid 路径 403)
bash scripts/smoke_admin_a1.sh

# L1.11 frontend admin build (Vite 产物完成, 17 页路由 manifest 齐)
cd ../frontend && npm run build && grep -c "admin/users\|admin/pipeline\|admin/kg\|admin/cost\|admin/audit-log" dist/manifest.json | awk '{ if ($1 < 17) exit 1 }'

echo "[verify_a1] ALL GREEN"
```

### Layer 2 · Harness Group J 5 条 + selftest 27 → 32

| Rule | 名称 | 扫描路径 | 拦截语义 |
|---|---|---|---|
| **J1** | `admin-write-must-record-audit` | `backend/app/admin/api/**/*.py` | 任何 POST/PATCH/DELETE handler 必须出现 `record_audit(` 调用 (除登录刷新等 auth 路径) |
| **J2** | `admin-must-not-rewrite-account-pool` | `backend/app/admin/api/v1/pipeline/**/*.py` | 黑名单: `import luban`, `def auto_register`, `def encrypt_cookies`, `class CookieEncoder`; 必须经 `from app.accounts.` |
| **J3** | `rbac-super-admin-only` | `backend/app/admin/middleware/rbac.py` + 所有 require_role 调用点 | `require_role(` 后单一参数必须等于 `'super_admin'`; 出现第二个 role literal 立即 block |
| **J4** | `cookie-mask-in-admin-response` | `backend/app/admin/api/v1/pipeline/planner/resources/accounts/*.py` | response model `cookies` 字段必须经 `mask_secret()`; 直接 `return account.cookies` 黑名单 |
| **J5** | `user-data-write-only-status` | `backend/app/admin/api/v1/users/*.py` | `User.email`, `User.password_hash`, `User.locale`, `Project.*` 任一作为 SQLAlchemy `update()` 目标 → block; 仅 `User.status` 与 `User.force_password_change_at` 允许 |

5 个 self-seeded fixture 在 `backend/app/__ci_fixtures__/J{1..5}_*.cifixture.py`, 每个故意触发对应规则; `EXPECTED_POSITIVES` 27 → 32; selftest 必须打印 `selftest: PASS  (32 / 32 fixture expectations met)`。

### Layer 3 · Frank 浏览器实操验收 (preview env, 决策 #30)

Frank 在 admin.preview.genpano.dev 子域执行下列 6 步, 全部成功后 A1' 关闭:

- **S1** 用 super_admin 账号登录 → 看到 Dashboard 真实当日成本 KPI (非 0, 非 mock)
- **S2** 进 `/admin/pipeline/planner/resources/accounts` → 看到 doubao 引擎 ACTIVE 账号水位 ≥ 1 (来自 1.2' Phase Gate 注入的真账号), COOLDOWN 字段呈倒计时
- **S3** 进 `/admin/users` → 选一个测试用户 → 点击 "冻结" → 跳确认弹窗 → 输入理由 "test freeze" → 提交 → 1s 内列表 status 变 "frozen" + 抽屉显示 Moderation Action 历史 + `/admin/audit-log` 立即出现一行新审计
- **S4** 进 `/admin/kg/brand-submissions` → 测试用户从 App 端提交一条品牌建议 (Frank 用另一标签页操作) → Inbox 24h SLA 计时启动 → super_admin 点 "approve" → 1s 内该 brand 在 `/admin/kg/brands` 出现, status='approved'
- **S5** 进 `/admin/audit-log/export.csv` 点导出 → 浏览器下载 utf-8 csv → 同时下一行 audit 出现自身导出记录 (闭环)
- **S6** Frank 在终端 `curl -H "Cookie: admin_session=..." https://admin.preview.genpano.dev/admin/api/v1/pipeline/dashboard` → 返回真实 JSON (不是 503 / 不是 401), 字段对应 PRD §1.1 IA 描述

只要任一 S 步红, A1' Phase Gate 不绿, 回 §5 修后再来。**Frank 不接受截图替代浏览器实操** (`feedback_genpano_session_preview_env_2026_04_26.md`)。

---

## §5 12-Step Delivery Order (原子 commit)

每步独立 commit, 标题格式 `Session A1' Step N: <topic>` (决策 #25 + commit rule):

| Step | 主题 | 关键交付物 |
|---|---|---|
| **0** | branch + 依赖 + RBAC scaffold | `git checkout -b session-A1prime`; 在 `pyproject.toml` 加 `python-multipart` (csv export 用) + `slowapi` (已有 3' 引入则跳); `backend/app/admin/middleware/rbac.py` `require_role('super_admin')` decorator + audit context fixture |
| **1** | 8 张新表 alembic + SQLAlchemy 模型 | `backend/alembic/versions/xxxx_admin_a1.py`: `user_moderation_actions` / `user_activity_stats` / `kg_review_queue` / `alias_conflicts` / `brand_submissions` / `alerts` / `cost_daily` / `budget_config` + `models/admin/*.py` 8 模型 + CHECK 约束走 raw SQL |
| **2** | `record_audit()` 单一入口 + 模型 + 单测 | `backend/app/services/admin_audit.py` 单函数; INSERT-only 表约束 (raw SQL trigger 拒绝 UPDATE/DELETE); pytest 7 例 (write 6 个必触发场景, INSERT-only enforcement) |
| **3** | Module A 用户管理 5 endpoints + RBAC + audit | Y1-Y6 实现; user.email / password_hash / Project.* 写路径全 raise NotImplementedError + J5 fixture 自验; pytest 12 例覆盖 freeze / force-reset / soft-delete 全路径 + audit assert |
| **4** | Module C KG 16 endpoints | Y19-Y28 全实现; brand approve/reject/merge 状态机 + alias 仲裁 + brand-submission 24h SLA 字段; pytest 18 例; J1 audit assert; soft rename `previous_names[]` 历史 |
| **5** | Account Pool wrapper + Module B 资源页 | `backend/app/services/account_pool_admin.py` `from app.accounts.pool/auto_register/crypto_noop` (J2 强制); Y9-Y12 + Y18; cookie 字段 response model 经 `mask_secret()` (J4 强制); pytest 8 例 |
| **6** | Module B Pipeline Tracker + Dashboard | Y7-Y8 + Y13-Y17; engine_health_5min 物化视图 SQL + cron refresh fixture; 失败 Attempt 重试经 Celery enqueue; pytest 10 例 |
| **7** | Module D Cost Dashboard + Audit Log | Y29-Y32; csv export 经 `csv-stringify` (Python `csv` stdlib + UTF-8 BOM); 10k 行上限; slowapi 5/min; export 自身写 audit (闭环验收 S5) |
| **8** | Group J Harness 5 条 + 5 self-seeded fixture | `scripts/ci_check.py` Group J 段; 5 fixture 在 `__ci_fixtures__/`; `ci_harness_selftest.py` EXPECTED_POSITIVES 27→32 |
| **9** | 17 React+TSX 页面 (admin layout + 路由 + 占位 + 数据接入) | `frontend/src/admin/pages/` Module A×3 + B×6 + C×6 + D×2; AdminRouteGuard 复用 A0'; AntV G6 v5 用于 KG 品类树 (`feedback_genpano_g6_knowledge_graph.md` 8 坑点); shadcn/ui Drawer/Tabs/Table |
| **10** | docker-compose.admin + Vercel 子域 + Render service | `docker-compose.yml` admin profile; Vercel `vercel.json` admin subdomain rewrite; Render `render.yaml` admin worker (跑 Celery + cron job for engine_health_5min refresh) |
| **11** | verify_a1.sh + smoke_admin_a1.sh + L1-L3 三层全绿 | `scripts/verify_a1.sh` (§4 Layer 1) + `scripts/smoke_admin_a1.sh` (curl 序列) + GitHub Actions workflow `admin-preview.yml` 接 Layer 1; preview push → Vercel + Render 自动 deploy |
| **12** | Frank Layer 3 验收 + CLAUDE.md 决策 #32 落档 + .auto-memory 落档 + git 合并到 main | Frank 在浏览器跑完 S1-S6 全绿; 我写决策 #32 (Session A1' 交付细节 + 偏差 C1/C2/...) 进 CLAUDE.md; 写 `.auto-memory/project_genpano_session_a1_delivery.md`; PR `session-A1prime` → main fast-forward |

每步收尾必须先跑 `scripts/verify_a1.sh` 全绿 → `git add -A && git commit -m "Session A1' Step N: <topic>"` → 推送; 中间任一步 verify 红, **不推**, 修绿再推。

---

## §6 完成判定 + 收尾动作 (规则 7)

A1' Phase Gate 关闭条件 ≡ §4 三层全绿 (L1.1-L1.11 全 green + L2 selftest 32/32 + L3 Frank S1-S6 全过)。

收尾必做 4 件事 (规则 7 一致性回路):
1. **回跑 §0 Pre-flight grep F1-F11**: 真相源未漂移确认; 若漂移走 §3 Type B 流程
2. **CLAUDE.md 决策 #32 写入**: 含 A 段 (实施摘要) / B 段 (偏差登记 C1/C2/... 按 Rule 3) / C 段 (与 §1 修改清单的 actual delta)
3. **`.auto-memory/project_genpano_session_a1_delivery.md` 写入**: 索引添加到 MEMORY.md, 记录 8 张新表 + 5 Group J Harness + Frank 实操验收完成
4. **`docs/CLAUDE_CODE_SESSIONS_PYTHON.md` 状态更新**: A1' 标 ✅; 4b' (最后一个 Session) 仍 pending; M4 milestone 5/6 完成 (剩 4b')

---

## §7 后续依赖 (M4 收尾)

A1' 完成 ≡ Admin 域 Python rewrite 全部就位 ≡ App 后端 + Admin 后端双轨完成。**剩下唯一 Session = 4b'** — IA v2.0 完整 JSX→TSX + 真实 FastAPI 集成 + 17 个 admin 页面再细化 + 18 个 app 页面 (5 KPI + Brand Mode 9 + Industry Mode 4) 接入真后端。4b' 完成 = MVP 完成。

A5' (Citation Tier CRUD + MCP Token + Redis 60s 吊销黑名单) **已并入本 A1' Session**, 不再单独排期 (Plan J D1, 2026-04-26 — 决策 #19 + #21.E + DECISION_LOG.md 同步索引)。A2' (multi-role RBAC) / Phase 2 Module D / Phase 2 Pipeline Analyzer 等仍推 Phase 2 排期, 不属 MVP 关键路径。

---

## §8 Decision-Freshness Final Check (规则 11)

| Check | 状态 | 备注 |
|---|---|---|
| CLAUDE.md 最近 3 决策 (#29 Python pivot / #30 preview env / #31 branch-per-session) | ✅ 已 thread 入 §1 真相源 + §3 STOP A6/A7 + §4 Layer 3 |
| .auto-memory 近 7 天: `feedback_genpano_session_commit_rule.md` / `feedback_genpano_app_truth_source.md` / `feedback_genpano_no_api_scraping.md` / `feedback_genpano_branch_per_session.md` / `feedback_genpano_session_preview_env_2026_04_26.md` | ✅ commit 规则 / 真相源分立 / response_source labeling / branch / preview env 全部 thread 入 §3 + §4 + §5 Step 12 |
| ADMIN_PRD.md 最新版本号 (header date) | 需 Step 0 grep 确认; 出现 newer than 2026-04-19 → §3 Type B 检查变更 |
| ADAPTER_CONTRACT.md §5.1 / §5.3a / §5.4 | ✅ Y9-Y12 wrapper 边界对齐 |
| 决策 #19 Citation Tier 是否进 A1' | ❌ 已锁 N1, 推 A5/4b' |

**Frank**: 收到本 Prompt 后, 让 Claude Code 第一批动作必须是跑 §0 11 条 grep + 输出对照清单, 与 §1 一致才能进 §5; 不一致 stop alignment。**接受 §2 / §3 / §4 后再发 "go"**。
