# SESSION_4A_PRIME_PROMPT.md — Session 4a' · 用户 Auth + Onboarding 4 步 (Python 重写, 吸收合并仓 frontend)

> **使用者**: Claude Code (本 Prompt 直接交付给 Claude Code 执行)
> **状态**: M1 Milestone (Auth E2E + Preview 基线) 第 3 个 Session, 接 Session 0' (基础设施) + Session A0' (Admin Auth) 之后
> **依赖**: Session 0' merged + Session A0' merged + Session 1.5' KG seed 至少有 4 行业静态数据 (实际 1.5' 可后置交付, 4a' 用 mock industries 不阻塞 — 见 §3 Type B)
> **写作公约**: CLAUDE.md 决策 #25 (12 条 Prompt 编写公约), 决策 #29 (Python 全栈反转), 决策 #30 (每 Session preview 环境 + 可验证), 决策 #31 (每 Session 一分支)

---

## §0 Pre-flight Grep 契约 (开工第一动作)

> 规则 2 · Pre-Flight Grep Contract — Claude Code 第一批动作必须运行下列 grep, 输出与本 Prompt §1 一致才能开工; 不一致则停下走 alignment, 严禁靠"猜"前进.

```bash
cd C:\Users\frank.wang\genpano

# F1 · CLAUDE.md 决策 #9/#10/#21/#25/#29/#30/#31 仍存在 (Auth-Required + Onboarding 替 E1-E4 + Review 闭环 + 公约 + Python 反转 + preview env + 分支策略)
grep -nE '^\s*9\.\s|^\s*10\.\s|^\s*21\.\s|^\s*25\.\s|^\s*29\.\s|^\s*30\.\s|^\s*31\.\s' CLAUDE.md | head -30

# F2 · PRD §4.1.1-gate / §4.1.1d.C / §4.1.1e / §4.10.4a / §4.11.4 真相源仍存在
grep -nE '4\.1\.1-gate|4\.1\.1d\.C|4\.1\.1e|4\.10\.4a|4\.11\.4' docs/PRD.md | head -20

# F3 · DraftProject schema 字段名锁定 (userId unique / step Int / industryId / primaryBrandId / competitorBrandIds / preferences Json / expiresAt)
grep -nE 'DraftProject|draft_projects|expiresAt|lastStepCompletedAt' docs/PRD.md | head -15

# F4 · 埋点 #63/#64/#65/#70 在 PRD §4.11.4 / §4.6-IA-v2 仍是真相源
grep -nE '#63\s|#64\s|#65\s|#70\s|onboarding_step_completed|onboarding_draft_created|onboarding_draft_resumed|onboarding_draft_expired' docs/PRD.md | head -15

# F5 · 验证 Session 0' + A0' 已 merge (FastAPI app/main.py, app/admin/auth/*, alembic 至少 2 个 migration)
ls app/main.py app/admin/auth/jwt.py 2>/dev/null
ls alembic/versions/ | head -5

# F6 · 验证 frontend 合并仓页面 (LoginPage / RegisterPage / EmailSentPage / SetupPage) 存在 (本 Session 接通真实 API)
ls frontend/src/pages/auth/ 2>/dev/null || ls frontend/src/pages/Login*.jsx frontend/src/pages/Register*.jsx 2>/dev/null

# F7 · Auth-Required Route Guard (RequireAuth) 在 frontend 存在或留空 (本 Session 实现 user-side, A0' 已实现 admin-side)
grep -rnE 'RequireAuth|requireAuth|AuthRouteGuard' frontend/src/ 2>/dev/null | head -10
```

**期望输出**:
- F1: 7 条决策行 (#9 Auth-Required / #10 零 Project Onboarding / #21 Review 闭环 / #25 公约 / #29 Python pivot / #30 preview env / #31 branch-per-session)
- F2: PRD §4.1.1-gate (line ~608) / §4.1.1d.C (line ~1177) / §4.1.1e (line ~1244) / §4.10.4a / §4.11.4 各 ≥ 1 命中
- F3: DraftProject schema 至少 10 行命中, 字段名与 §1 一致
- F4: #63 auth_gate_redirect / #64 brand_hint_register_success / #65 mcp_auth_failure / #70 onboarding_step_completed 4 事件均命中
- F5: app/main.py 存在 + admin/auth/jwt.py 存在 + alembic versions ≥ 2 个 (Session 0' + A0')
- F6: 合并仓 frontend 至少 LoginPage + RegisterPage 存在 (若不存在, 走 §3 Type A STOP)
- F7: 0 命中可接受 (本 Session 实现); 若已存在则确认与 A0' AdminRouteGuard 模式一致

**任何 ❌**: 立即停下, 按 §3 STOP 模板报告.

---

## §1 真相源索引

> 规则 5 · Session Prompt §1 必须声明"本 Session 引用 / 修改的真相源".

### 1.1 引用 (本 Session 不改, 严格 honor)

| # | 真相源 | 段号 / 文件 / 行 | 用途 |
|---|--------|------------------|------|
| 1 | PRD `Auth-Required Data Viewing Policy` | docs/PRD.md §4.1.1-gate (~line 608) | 所有数据页 + API 必须登录, Landing/auth/register 才是匿名入口 |
| 2 | PRD `Onboarding 草稿存储` | docs/PRD.md §4.1.1d.C (~line 1177-1241) | DraftProject schema + 状态机 + Route Guard 检查 + 清理任务 + 埋点 + Harness |
| 3 | PRD `登出 & 会话管理` | docs/PRD.md §4.1.1e (~line 1244-1458) | silent refresh / 跨标签 / 6 步登出契约 / 登出 vs 注销分离 |
| 4 | PRD `i18n 覆盖矩阵` | docs/PRD.md §4.10.4a | Resend 邮件双语 + UI 命名空间 (auth.* / onboarding.* / common.userMenu.*) + formatBrand 唯一入口 |
| 5 | PRD `埋点全量清单` | docs/PRD.md §4.11.4 | #63 auth_gate_redirect / #64 brand_hint_register_success / #65 mcp_auth_failure / #70 onboarding_step_completed |
| 6 | PRD `Brand/Industry Mode IA v2.0` | docs/PRD.md §4.6-IA-v2 | Onboarding 完成后落 `/brand/overview` (URL prefix), 不是 `/dashboard` |
| 7 | CLAUDE.md 决策 #9 | Auth-Required Data Viewing Flip | MCP API day-1 require Bearer token; Brand 直链 → /register?brandHint= |
| 8 | CLAUDE.md 决策 #10 | 零 Project 态 → /onboarding | 替 E1-E4 Empty State, Route Guard 强制重定向 |
| 9 | CLAUDE.md 决策 #21.D | DraftProject Prisma model 字段全清单 | userId unique / step / industryId / primaryBrandId / competitorBrandIds[] / preferences Json / expiresAt + 3 事件 |
| 10 | CLAUDE.md 决策 #25 | Prompt 编写 12 公约 | 规则 1-7 + 10/11/12 |
| 11 | CLAUDE.md 决策 #29 | Python 全栈反转 | FastAPI / SQLAlchemy 2.0 / Alembic / Celery / Redis / Pydantic v2 / passlib / python-jose / Resend |
| 12 | CLAUDE.md 决策 #30 | 每 Session preview env + Frank 浏览器自验 | Phase Gate Layer 3 必须 Frank 在浏览器走完 §4 G_4A.3 全部脚本 |
| 13 | CLAUDE.md 决策 #31 | 每 Session 一分支 | 从 main fork `session-4aprime`, 不 cherry-pick 历史 TS 代码 |
| 14 | Session A0' 已交付模块 | app/admin/auth/{jwt,refresh-token,password,cookies,middleware,rate-limiter}.py | 复用 password hash / JWT sign-verify / cookie helper / rate-limiter — 改命名空间到 `app/auth/` (user-side), 不与 admin/auth/ 共享单例 |
| 15 | REPLAN_2026_04_26.md §4 Session 4a' | docs/REPLAN_2026_04_26.md (line 153-168) | Session 4a' 范围 / 依赖 / 关系到 master / Phase Gate 锚点 |
| 16 | TEST_STRATEGY v1.1 §9-§13 | docs/TEST_STRATEGY.md | 异常场景矩阵 + Auth/Onboarding 失败路径 + harness fixture 命名 |

### 1.2 修改清单 (本 Session 写入)

| # | 文件 | 操作 | 用途 |
|---|------|------|------|
| 1 | `app/db/models/user.py` | 新建 | SQLAlchemy User model: id / email unique / password_hash / locale / created_at / verified_at / last_login_at |
| 2 | `app/db/models/project.py` | 新建 | SQLAlchemy Project model: id / user_id / industry_id / primary_brand_id / competitor_brand_ids ARRAY / preferences JSONB / created_at |
| 3 | `app/db/models/draft_project.py` | 新建 | SQLAlchemy DraftProject model: 严格对齐 PRD §4.1.1d.C 字段, @@unique(user_id) + @@index(expires_at) |
| 4 | `alembic/versions/xxxx_user_project_draft.py` | 新建 | Alembic 迁移 3 张表 + CHECK 约束 (step IN [1,2,3,4]) + 索引 |
| 5 | `app/auth/{constants,jwt,password,cookies,middleware,rate-limiter}.py` | 新建 (复用 admin/auth/ 算法, 换 cookie 命名 + path) | User auth 镜像版: cookie path=`/`, JWT_AUDIENCE_ACCESS=`genpano-user-access`, BCRYPT_COST=12 单一入口 |
| 6 | `app/api/v1/auth/{register,verify_email,login,logout,forgot_password,reset_password}.py` | 新建 | 6 个 FastAPI 端点 (register/verify-email/login/logout/forgot/reset) |
| 7 | `app/api/v1/onboarding/{step,submit,resume,abandon}.py` | 新建 | 4 个 onboarding 端点: POST step (累进存草稿) / POST submit (4 步走完落 Project) / GET resume (返回当前草稿状态) / DELETE abandon |
| 8 | `app/api/middleware/route_guard.py` | 新建 | FastAPI middleware: 已登录 + projects.length===0 → 检查 draft_projects → 302 `/onboarding?resumeStep=N` 或 `/onboarding`; projects ≥ 1 → 放行 |
| 9 | `app/email/templates/{verify_email,reset_password,welcome}.{en,zh}.html` | 新建 | React Email 双语 (zh-CN + en-US) HTML, Resend 发送 |
| 10 | `app/email/sender.py` | 新建 | Resend client wrapper, 按 user.locale 选模板 |
| 11 | `app/tasks/onboarding_cleanup.py` | 新建 | Celery beat task: 每小时跑一次 `DELETE FROM draft_projects WHERE expires_at < NOW()`, 删除每批触发 `onboarding_draft_expired` 埋点 |
| 12 | `app/tracking/mixpanel_client.py` | 新建 (本 Session 起步, 后续复用) | Mixpanel server-side client: distinct_id / event / properties (PII 黑名单) |
| 13 | `frontend/src/lib/auth/RequireAuth.jsx` | 新建 (User-side, mirror Admin AdminRouteGuard) | 4 状态机 (initializing/authenticated/anonymous/expired) + redirect 写 `?redirect=` |
| 14 | `frontend/src/lib/auth/UserAuthContext.jsx` | 新建 | silent refresh 14min 间隔 + BroadcastChannel (login/logout/expire) |
| 15 | `frontend/src/pages/{Login,Register,EmailSent,Setup,Onboarding}*.jsx` | 修改 (合并仓已起步) | 替换 mock fetch 为 fetch('/api/v1/auth/*') + 接 UserAuthContext |
| 16 | `frontend/src/lib/userApi.js` | 新建 | userFetch wrapper + userAuthApi 6 端点 (镜像 adminApi.js) |
| 17 | `app/harness/__ci_fixtures__/D11_*.cifixture.py` | 新建 (3 个) | D11-1 onboarding step 状态机 / D11-2 RequireAuth 必须包数据路由 / D11-3 DraftProject 72h cleanup task wired |
| 18 | `scripts/ci-check.mjs` | 修改 | 新增 D11/D12/D13 三条 grep 规则 + EXPECTED_POSITIVES 由 6 → 9 |
| 19 | `scripts/ci-harness-selftest.mjs` | 修改 | EXPECTED_POSITIVES 6 → 9 |
| 20 | `scripts/verify-session-4aprime.sh` | 新建 | Phase Gate Layer 1 验收 shell |
| 21 | `docs/SESSION_4APRIME_DELIVERY.md` | 新建 (Step 12) | 交付报告, 偏差登记, CLAUDE.md 决策追加 |
| 22 | `CLAUDE.md` | 追加决策 #34 | Session 4a' 交付追溯 |
| 23 | `docs/PRD.md` 若有偏差 | 追加 §4.1.1d.C 偏差注脚 (规则 4) | 仅当实施偏离 schema 时, 否则不动 |

### 1.3 版本警告

> ⚠️ **TS 代码已废 (CLAUDE.md 决策 #29 全栈反转 2026-04-26)**: master Session 4a / 决策 #24 中 `frontend/src/admin/lib/adminApi.js` 是 admin-side 模板, **不是** user-side 实现; 复用其状态机 / silent refresh / BroadcastChannel 算法, 但命名空间从 `admin*` 改 `user*`, cookie path `/admin` 改 `/`.
> ⚠️ **决策 #24.C2 (super_admin 单值 CHECK)** 与本 Session 无关, 本 Session 是 User 侧, 无 role 字段 (User 不分角色, MVP 单一身份).
> ⚠️ **DraftProject `competitor_brand_ids` 是 PostgreSQL ARRAY**, SQLAlchemy 用 `Column(ARRAY(String), nullable=False, server_default='{}')`, 不是 JSONB; PRD §4.1.1d.C 写的 `competitorBrandIds String[]` 是 Prisma DSL, 翻译到 SQLAlchemy 是 ARRAY(String).
> ⚠️ **Resend bilingual templates** 模板按 user.locale ('zh-CN' / 'en-US') 选择 — 注册时 user.locale 默认从 Accept-Language 头解析, 落库不变 (用户 Settings 后续可改, 本 Session 不实现 Settings).
> ⚠️ **REFRESH_TOKEN_TTL 双层差异 (intentional, NOT inconsistency)**: User 侧 `REFRESH_TOKEN_TTL_SECONDS = 2592000` (30d) — UX 更友好, 大众用户低权限, 30 天减少重登摩擦。Admin 侧 (Session A0') 用 `REFRESH_TOKEN_TTL_SECONDS = 604800` (7d) — 安全更紧, Admin 用户少且高权限, 7 天强制再认证可接受。**两常量分别定义在 `app/auth/constants.py` 和 `app/admin/auth/constants.py`, 不共享单例**, 这是有意识的安全/UX trade-off, 不是配置疏忽。见 Session A0' §1.3 (REFRESH_TOKEN_TTL 双层差异 bullet) 反向交叉引用本段。

---

## §2 MVP Scope

> 规则 10 · MVP Scope-Cut Declaration — 本 Session 严格只做下方 ✅, 严格不做 ❌; 任何"做着做着发现需要扩"必须按 §3 Type C STOP 报告.

### 2.1 ✅ 本 Session 做 (按交付顺序)

| # | 内容 | 锚点 | 验收信号 |
|---|------|------|----------|
| 1 | SQLAlchemy 3 模型 (User / Project / DraftProject) | §1.2 #1-#3 | `from app.db.models import User, Project, DraftProject` 导入成功, mypy strict 全绿 |
| 2 | Alembic 迁移 + CHECK (step IN 1-4) + ARRAY 类型 | §1.2 #4 | `alembic upgrade head` 后 `\d+ users / projects / draft_projects` 三表存在, `\d draft_projects` 显示 step CHECK + expires_at index |
| 3 | User-side auth 算法层 (镜像 Admin A0' 6 文件) | §1.2 #5 | 单元测试覆盖率 ≥ 80%, BCRYPT_COST=12 + ACCESS_TOKEN_TTL=900s + REFRESH_TOKEN_TTL=2592000s (30d, 用户侧比 Admin 长) |
| 4 | 6 endpoint: register / verify-email / login / logout / forgot-password / reset-password | §1.2 #6 | curl 端到端 register → email link → verify → login → forgot → reset 全跑通, 401/200/429 边界 OK |
| 5 | 4 onboarding endpoint: step / submit / resume / abandon | §1.2 #7 | 4 步累进写 DraftProject → submit 转 Project → DraftProject 删除; resume 返回当前 step + form state |
| 6 | Route Guard FastAPI middleware | §1.2 #8 | 已登录 + 0 projects + 有未过期 draft → 302 `/onboarding?resumeStep=2`; 已登录 + ≥1 project → 放行 |
| 7 | Resend 双语邮件模板 (verify / reset / welcome 各 zh-CN + en-US) | §1.2 #9-#10 | Frank 在 Mailtrap (preview) 收 zh-CN + en-US 各 3 封, HTML 渲染正确 |
| 8 | Celery beat: onboarding_cleanup 每小时跑 | §1.2 #11 | 手动 INSERT 一行 expires_at = NOW() - 1h → 等待或手动触发 task → 行被删 + Mixpanel `onboarding_draft_expired` 1 次 |
| 9 | Mixpanel server-side client (PII 黑名单) | §1.2 #12 | 单元测试: track event with `email='x@y.com'` → email 字段被剔除, 只剩 distinct_id 哈希 |
| 10 | 4 events 接通: #63 / #64 / #65 / #70 | §1.2 #6/#7 | 端到端 register 触发 #64 (有 brandHint) / 未登录访问 /brand/overview 触发 #63 / step 完成触发 #70 / 无 token 调 MCP 触发 #65 |
| 11 | frontend 合并仓页面接通真实 API (Login/Register/EmailSent/Setup/Onboarding) | §1.2 #15 | 5 页面 mock fetch 全替换为真实 fetch, 无 console error |
| 12 | RequireAuth + UserAuthContext (镜像 Admin) | §1.2 #13-#14 | 未登录访问 `/brand/overview` 自动 redirect /register?redirect=/brand/overview |
| 13 | userFetch wrapper + userAuthApi | §1.2 #16 | adminApi.js 模式, credentials: 'include', AdminApiError class |
| 14 | Harness D11 三条新规则 + 3 个 self-seeded fixture | §1.2 #17-#19 | EXPECTED_POSITIVES 6 → 9, `node scripts/ci-harness-selftest.mjs` 打印 `● selftest: PASS  (9 / 9 fixture expectations met)` |
| 15 | verify-session-4aprime.sh + Phase Gate Layer 1 | §1.2 #20 | shell exit 0 (ruff/mypy/pytest/alembic/CHECK/harness/celery 7 步全绿) |
| 16 | Preview env 部署 + Frank Layer 3 浏览器实测 | 决策 #30 | Frank 完成 §4 G_4A.3 全部 5 个 scenarios |
| 17 | 文档同步 (SESSION_4APRIME_DELIVERY.md / CLAUDE.md #34 追加) | §1.2 #21-#22 | 规则 4 双向同步, PR 引用 ChangeLog |
| 18 | pytest ≥ 80% (User auth + onboarding + middleware + tasks) | §1.2 全部 | `pytest --cov=app/{auth,api/v1/auth,api/v1/onboarding,db/models,tasks,email,tracking} --cov-fail-under=80` 全绿 |
| 19 | ruff + mypy strict 零错 | 全 Session | `ruff check app/ && mypy app/` 零输出 |
| 20 | Branch `session-4aprime` 从 main fork, ≤ 12 atomic commits | 决策 #31 | git log 显示 12 commits, 标题格式 `Session 4a' Step <N>: <主题>` |

### 2.2 ❌ 本 Session 不做 (推迟到对应 Session)

| # | 不做内容 | 推迟到 | 理由 |
|---|----------|--------|------|
| N1 | MFA / OAuth / SSO | Phase 2 | MVP 不上 MFA, 邮箱 + 密码足够 |
| N2 | Settings 页面 (修改 locale / 密码 / 头像) | Session 4b' | Settings 是 Brand Mode IA 的一环, 与 Onboarding 后的主功能一并交付 |
| N3 | 注销账户 (PIPL 删除权 30 天删号) | Phase 2 | 决策 #21 / PRD §4.1.1e 已明确分离, MVP 只做"登出" |
| N4 | E5 异常登录提醒邮件 | Phase 2 (Session A4 系统健康一并) | E5 需要 device fingerprint + IP 地理库, 超出本 Session 范围 |
| N5 | E6 登出通知邮件 | 不做 (PRD §4.1.1e 已明确禁) | 噪音过高 |
| N6 | 多 Project 切换 (ProjectPicker) | Phase 2 | MVP 1 user 1 project, 决策 #2 IA v2.0 把 Project 在 MVP 隐身 |
| N7 | Onboarding 第 1 步行业选择的 KG 真数据 | Session 1.5' merged 后接通 | 4a' 用静态 4 行业 mock seed (`app/onboarding/mock_industries.py`), Session 1.5' 把 mock 替换为真 KG repo lookup |
| N8 | 品牌选择的 KG 真数据 (Step 2 主品牌 + Step 3 竞品) | Session 1.5' merged 后接通 | 同上, 4a' 用每行业 5-8 静态品牌 mock |
| N9 | brandHint-aware register 表单顶部预填 (PRD §4.1.1-gate Brand 直链场景) | Session 4b' | 需要 BrandPicker 组件, 与 IA v2.0 一并交付; 4a' 只在 register 接 `?brandHint=` query param 但 UI 暂不渲染 (后端事件 #64 仍触发) |
| N10 | E2E Playwright 视觉回归 + HAR routeFromHAR | Session 6 (TEST_STRATEGY Phase 4) | 4a' 走 pytest 单元 + 集成 + Frank Layer 3 三层够用 |
| N11 | i18n 中除 auth.* / onboarding.* / common.userMenu.* 命名空间外 (e.g. brand.* / industry.*) | Session 4b' | 4a' 只交付 auth + onboarding 命名空间双语 (zh-CN + en-US) |
| N12 | Mixpanel 事件 #63-#65/#70 之外 (e.g. #66 dashboard_layout_switched / #67 mode_toggle_clicked) | Session 4b' | 4a' 只接 4 个事件, 其他随对应功能落 |

---

## §3 STOP Triggers

> 规则 12 · 三类 STOP 作为地板, Session 专属 STOP 在此之上 append 而非替换.

### Type A · 环境失败

- **A1**: F5 grep 0 命中 → Session 0' / A0' 未 merge → STOP 报告"前置依赖缺失", 等待 main HEAD 推进
- **A2**: F6 grep 0 命中 → 合并仓 frontend LoginPage/RegisterPage 未到位 → STOP 询问 Frank 是否 (a) 等待合并仓 PR (b) 在 4a' 内从零写
- **A3**: 环境变量缺失 (`RESEND_API_KEY` / `MIXPANEL_TOKEN` / `DATABASE_URL` / `REDIS_URL` / `JWT_SECRET`) → STOP 列出 .env.example 模板, 等待 Frank 填值
- **A4**: Supabase preview 无法连 → STOP 报告 connection string + retry 策略, 等待 Frank 切到 staging 或重启 db
- **A5**: alembic upgrade head 失败 (Session 0' / A0' migration 与 4a' 冲突) → STOP 报告冲突 SQL, 走 alembic merge

### Type B · 真相源冲突

- **B1**: PRD §4.1.1d.C DraftProject schema 字段名与决策 #21.D 写法不一致 → STOP 列出 diff, 询问 Frank 哪个为准 (PRD §X.Y 优先, 决策 # 附录可批量同步)
- **B2**: Resend 双语模板必须命名空间 (auth.email.verify.subject / .body / .footer) 在 §4.10.4a 与 §4.1.1e 不一致 → STOP 走 §4.10.4a (i18n 矩阵唯一权威)
- **B3**: Onboarding 4 步顺序 (industry → primaryBrand → competitors → preferences) 在 PRD §4.6-IA-v2.F 与 §4.1.1d.C 不一致 → STOP 走 §4.1.1d.C (本 Session 主真相源)
- **B4**: Mixpanel 事件名 (#70 onboarding_step_completed) 在 §4.11.4 与 §4.6-IA-v2 拼写不一致 → STOP 走 §4.11.4 (S14 段)

### Type C · 范围溢出

- **C1**: 实施过程发现"必须先做 Settings 页面 (用户改 locale)" → STOP 不做, 走 mock: 注册时 user.locale 从 Accept-Language 头解析, 落库不可改 (本 Session 不暴露 Settings)
- **C2**: 实施过程发现"Onboarding Step 1 需要 KG 真数据 (1.5' 未 merge)" → STOP 不做, 走 §2.1 #11 + §2.2 N7 mock industries
- **C3**: 实施过程发现"必须做 Brand/Industry Mode 路由切换" → STOP 不做, Onboarding 完成后简单 redirect 到 `/brand/overview`, Brand Mode IA 全部委托 Session 4b'

### STOP 报告模板

```markdown
# Session 4a' STOP Report

**Type**: A / B / C (选一)
**Trigger**: <具体哪一条 A1-A5 / B1-B4 / C1-C3>
**Observed**: <实际看到的 grep / 文件 / 错误输出>
**Expected**: <§1 真相源说应该是什么>
**Diff**:
\`\`\`
<diff 内容>
\`\`\`
**Proposed Resolution**:
- Option 1: <建议方案 1>
- Option 2: <建议方案 2>
**Blocking Step**: <Session 4a' 第几步阻塞, §5 Step N>
**Time at STOP**: <ISO 时间>
```

---

## §4 Phase Gate (Layer 1/2/3 验收)

### G_4A.1 — `verify-session-4aprime.sh` Layer 1 自动验收

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

echo "==> 1. ruff + mypy strict"
ruff check app/auth/ app/api/v1/auth/ app/api/v1/onboarding/ app/db/models/ app/tasks/ app/email/ app/tracking/
mypy --strict app/auth/ app/api/v1/auth/ app/api/v1/onboarding/ app/db/models/ app/tasks/ app/email/ app/tracking/

echo "==> 2. pytest 覆盖率 ≥ 80%"
pytest tests/auth/ tests/onboarding/ tests/middleware/ tests/tasks/ tests/email/ tests/tracking/ \
  --cov=app/auth --cov=app/api/v1/auth --cov=app/api/v1/onboarding --cov=app/db/models \
  --cov=app/tasks --cov=app/email --cov=app/tracking \
  --cov-fail-under=80 --cov-report=term-missing

echo "==> 3. Alembic 迁移到 head"
alembic upgrade head

echo "==> 4. 3 张表 + CHECK + index 验证"
psql "$DATABASE_URL" -c '\dt users; \dt projects; \dt draft_projects;'
psql "$DATABASE_URL" -c '\d draft_projects' | grep -E 'step.*CHECK|expires_at.*btree' || (echo "❌ DraftProject CHECK / index 缺失"; exit 1)

echo "==> 5. Harness selftest"
node scripts/ci-harness-selftest.mjs | tee /tmp/selftest.log
grep -q '● selftest: PASS  (9 / 9 fixture expectations met)' /tmp/selftest.log

echo "==> 6. 6 endpoint 端到端 smoke"
# register
RESP=$(curl -fsS -X POST -H 'Content-Type: application/json' \
  -d '{"email":"smoke-4aprime@example.com","password":"PaSswOrD12345#","locale":"zh-CN"}' \
  http://localhost:8000/api/v1/auth/register)
test "$(echo "$RESP" | jq -r .status)" = "verification_sent"
# (verify-email link 来自邮件, smoke 跳过, 见 G_4A.3 Frank Layer 3)

echo "==> 7. Celery beat onboarding_cleanup 注册"
celery -A app.celery_app inspect registered | grep -q 'onboarding_cleanup' || (echo "❌ Celery beat 未注册"; exit 1)

echo "✅ Session 4a' Phase Gate Layer 1 全绿"
```

### G_4A.2 — Harness selftest Layer 2

```bash
node scripts/ci-harness-selftest.mjs
# 期望: ● selftest: PASS  (9 / 9 fixture expectations met)
# 9 = Session 0' 的 F1/F4/D8 (3) + Session A0' 的 D8/D9/D10 (3) + Session 4a' 的 D11-1/D11-2/D11-3 (3)
```

**3 条 D11 新规则**:
- **D11-1** `onboarding-step-state-machine-locked` — 扫 `app/api/v1/onboarding/step.py`, 必须出现 `STEP_TRANSITIONS = {1: 2, 2: 3, 3: 4, 4: None}` 字面量 (锁状态机, 防有人写成 `step += 1` 跳级或回退)
- **D11-2** `require-auth-must-wrap-data-routes` — 扫 `frontend/src/App.jsx` (或 router 集中点), 所有 `path="/brand/*"` / `path="/industry/*"` 必须被 `<RequireAuth>` 包裹 (Auth-Required, 决策 #9)
- **D11-3** `draft-project-72h-cleanup-task-wired` — 扫 `app/celery_app.py` 必须 import `from app.tasks.onboarding_cleanup import cleanup_expired_drafts` 并在 `beat_schedule` 配置 `crontab(minute=0)` (每小时), 不能写成 `crontab(hour=*/24)` (那会变 24h)

### G_4A.3 — Frank Layer 3 浏览器实测 (决策 #30)

> Frank 在 preview env (e.g. `https://session-4aprime.preview.genpano.app`) 浏览器手动跑.

**Scenario S1 · 注册 → 验证邮件 → 登录 → Onboarding → /brand/overview**:
1. 浏览器开 `https://session-4aprime.preview.genpano.app/register`
2. 填邮箱 `s1-4aprime@frankwang.test` + 密码 `S1pass!2026Pwd!` + locale 自动检测 zh-CN
3. 点 "注册" → 落 `/email-sent`
4. 切到邮箱 (Mailtrap preview) → 收到 zh-CN "GENPANO 验证邮箱" 邮件 → 点验证链接
5. 跳到 `/login` (verified) → 用刚注册凭据登录
6. Route Guard 检测 0 projects → 302 `/onboarding`
7. Step 1 选行业 "美妆个护" → 落 `/onboarding?step=2`
8. Step 2 选主品牌 "雅诗兰黛" → 落 `step=3`
9. Step 3 选 3 个竞品 (兰蔻 / 资生堂 / SK-II) → 落 `step=4`
10. Step 4 选偏好 (默认 7d 时间窗 + 全 3 引擎) → 点 "完成"
11. 落到 `/brand/overview` (空数据, 因 Pipeline 还没跑数据, 但页面正常渲染 + 顶栏显示 "雅诗兰黛")

**Scenario S2 · 草稿 72h 续期 (PRD §4.1.1d.C 主验收点)**:
1. 浏览器开 `/register` 注册新账号 `s2-4aprime@frankwang.test`
2. 走到 Onboarding Step 2 (主品牌) → **关闭浏览器**
3. 等 5 分钟 (或不等)
4. 重新打开 → `/login` 登录
5. **期望**: Route Guard 自动重定向 `/onboarding?resumeStep=2`, 顶部显示 "继续上次 · 第 2/4 步" (i18n key `onboarding.resume.banner`)
6. 第 1 步选的"美妆个护"应该已经预选 (form state 从 DraftProject hydrate)
7. 继续走完 Step 2-4 → 落 `/brand/overview`

**Scenario S3 · 草稿过期 (72h 后)**:
1. 数据库手动 `UPDATE draft_projects SET expires_at = NOW() - INTERVAL '1 hour' WHERE user_id = '<s2 user id>'`
2. 等待 Celery beat 1 小时跑 (或手动 `celery -A app.celery_app call app.tasks.onboarding_cleanup.cleanup_expired_drafts`)
3. 检查 Mixpanel: `onboarding_draft_expired` event 收到 1 次 (per batch, 不 per user)
4. 重新登录 s2 → Route Guard 检测无草稿 → 302 `/onboarding` (全新开始, 不是 resumeStep)

**Scenario S4 · Auth-Required gate (决策 #9)**:
1. 浏览器开 incognito 模式 (无 session)
2. 直接访问 `https://.../brand/overview` → 自动 redirect `/register?redirect=%2Fbrand%2Foverview`
3. 检查 Mixpanel: `#63 auth_gate_redirect { redirect_path: '/brand/overview', has_brand_hint: false }` 收到
4. 直接访问 `https://.../brands/estee-lauder` (Brand 直链) → redirect `/register?redirect=...&brandHint=estee-lauder` (后端 #64 fire 在 register success 时, 此处只验 redirect URL 含 brandHint param)
5. Onboarding 第 1 步无 brandHint UI 渲染 (§2.2 N9, 但 redirect URL 含 param 等待 Session 4b')

**Scenario S5 · 登出 + 跨标签 (PRD §4.1.1e)**:
1. 同账号同时开 2 个标签 A/B 都已登录 + 都在 `/brand/overview`
2. 标签 A 的 UserMenu 点 "登出"
3. 标签 A 跳 `/` (Landing)
4. **期望**: 标签 B 在 ≤ 2s 内通过 BroadcastChannel 收到 logout, 自动跳 `/login` (silent, 无 reload), 不该停在过期态显示数据
5. 检查浏览器 cookies: `user_access_token` + `user_refresh_token` 在两个标签都被清

**Frank 完成 5 scenarios 后**: 在 PR 描述里贴勾选清单 ☑ S1 ☑ S2 ☑ S3 ☑ S4 ☑ S5; 任一红 → 回 §3 STOP 记录原因.

---

## §5 12 步交付顺序 (原子 commit, ≤ 5 文件 / commit)

> 决策 #31 · 每 Session 一分支. 从 main HEAD fork `session-4aprime`, 12 步每步 commit, format: `Session 4a' Step <N>: <主题>`.

### Step 0 · 分支 + Pre-flight Grep
```bash
git checkout main && git pull
git checkout -b session-4aprime
# 跑 §0 F1-F7 grep, 任一 ❌ 走 §3 STOP
```
Commit: 无 (只是建分支)

### Step 1 · SQLAlchemy 3 模型 + Alembic 迁移
- `app/db/models/{user,project,draft_project}.py` 三模型
- `alembic/versions/<timestamp>_user_project_draft.py` 迁移 (CHECK + index)
- 单元测试: 新建 → upsert → 查询基本 CRUD

Commit: `Session 4a' Step 1: SQLAlchemy User/Project/DraftProject + Alembic`

### Step 2 · User Auth 算法层 (镜像 Admin A0')
- `app/auth/{constants,jwt,refresh_token,password,cookies,middleware,rate_limiter}.py`
- 复用 admin/auth/ 算法 + 改命名 (USER_ACCESS_TOKEN_COOKIE / USER_REFRESH_TOKEN_COOKIE / cookie path `/`)
- 单元测试 7 文件 ≥ 80% (镜像 admin/auth/ 测试覆盖)

Commit: `Session 4a' Step 2: User auth primitives (jwt/refresh/password/cookies)`

### Step 3 · 6 endpoint (register / verify-email / login / logout / forgot / reset)
- `app/api/v1/auth/{register,verify_email,login,logout,forgot_password,reset_password}.py`
- 集成测试: register → verify-email link → login → logout 全链路

Commit: `Session 4a' Step 3: 6 user-side auth endpoints`

### Step 4 · Resend 双语邮件 + Welcome
- `app/email/templates/{verify_email,reset_password,welcome}.{en,zh}.html` (6 个 template)
- `app/email/sender.py` Resend wrapper, locale-aware

Commit: `Session 4a' Step 4: Resend bilingual email templates`

### Step 5 · 4 onboarding endpoint + DraftProject 状态机
- `app/api/v1/onboarding/{step,submit,resume,abandon}.py`
- 集成测试: step 1 → 2 → 3 → 4 → submit → Project 落, DraftProject 删

Commit: `Session 4a' Step 5: Onboarding endpoints + DraftProject state machine`

### Step 6 · Route Guard middleware + RequireAuth 路由策略
- `app/api/middleware/route_guard.py` (后端: API 层 401 / 0 project 重定向 hint)
- 单元测试: projects.length===0 + draft → 302 hint / projects ≥ 1 → 放行

Commit: `Session 4a' Step 6: Route Guard middleware (Auth-Required + Onboarding redirect)`

### Step 7 · Celery beat onboarding_cleanup + Mixpanel
- `app/tasks/onboarding_cleanup.py` (每小时 cron)
- `app/tracking/mixpanel_client.py` (PII 黑名单)
- 单元测试: 手动插过期行 → run task → 行被删 + Mixpanel mock 收到 1 event
- `app/celery_app.py` beat_schedule 注册

Commit: `Session 4a' Step 7: Celery onboarding_cleanup + Mixpanel client`

### Step 8 · 前端 RequireAuth + UserAuthContext + userApi
- `frontend/src/lib/auth/{RequireAuth,UserAuthContext}.jsx` (镜像 Admin)
- `frontend/src/lib/userApi.js`
- 单元测试 (vitest): 4 状态机 + silent refresh + BroadcastChannel

Commit: `Session 4a' Step 8: Frontend RequireAuth + UserAuthContext + userApi`

### Step 9 · 接通合并仓页面 (Login / Register / EmailSent / Setup / Onboarding)
- `frontend/src/pages/{Login,Register,EmailSent,Setup,Onboarding}*.jsx` mock fetch → real API
- App.jsx router 用 RequireAuth 包 `/brand/*` `/industry/*`
- 端到端: register → email link → login → Onboarding 4 步 → `/brand/overview`

Commit: `Session 4a' Step 9: Wire frontend pages to real APIs`

### Step 10 · Harness D11-1/2/3 + selftest 9/9 + verify shell
- `scripts/ci-check.mjs` 添 D11 三规则
- `scripts/ci-harness-selftest.mjs` EXPECTED_POSITIVES 6 → 9
- `app/harness/__ci_fixtures__/D11_*.cifixture.py` 3 fixture
- `scripts/verify-session-4aprime.sh` 7 步 shell

Commit: `Session 4a' Step 10: Harness D11 + verify shell + Phase Gate Layer 1`

### Step 11 · Preview env + Frank Layer 3 实测
- 推 PR `session-4aprime` → 触发 GitHub Actions preview workflow → 拿到 `https://session-4aprime.preview.genpano.app`
- Frank 跑 §4 G_4A.3 S1-S5 5 scenarios

Commit: 无 (deploy 自动)

### Step 12 · 文档 + 决策追溯
- `docs/SESSION_4APRIME_DELIVERY.md` 写交付报告 (§6 模板)
- `CLAUDE.md` 追加决策 #34 (Session 4a' 交付追溯)
- `docs/PRD.md` 若有偏差注脚 (规则 4 双向同步)

Commit: `Session 4a' Step 12: Delivery report + CLAUDE.md decision #34`

---

## §6 交付报告模板 (Step 12 写入 SESSION_4APRIME_DELIVERY.md)

```markdown
# Session 4a' 交付报告

## 1. Phase Gate 通过证据

### G_4A.1 Layer 1 (机器自动)
- ruff + mypy: ✅ 零输出
- pytest: ✅ <X>/<X> tests, coverage <stmts>% / <branches>% / <funcs>% / <lines>%
- alembic: ✅ upgrade head 成功, 3 表 + CHECK + index 齐
- harness selftest: ✅ 9/9
- celery beat: ✅ onboarding_cleanup registered

### G_4A.2 Layer 2 (Harness)
- D11-1 / D11-2 / D11-3 各 1 fixture pass

### G_4A.3 Layer 3 (Frank 浏览器)
- ☑ S1 / ☑ S2 / ☑ S3 / ☑ S4 / ☑ S5

## 2. 偏差登记 (规则 3)

- **C1**: <发现的偏差 1, 字段名 / 类型 / 行为>
  - 理由: <为什么不能照真相源严格写>
  - 解决: <怎么 reconcile>
  - 真相源同步: <已 / 未在 PRD §X.Y 加注脚>

## 3. 真相源同步 (规则 4)

- PRD §4.1.1d.C: <若无偏差则"无修改"; 有则注脚行号>
- PRD §4.10.4a (i18n 矩阵): 新增 6 个 i18n key (auth.email.verify.subject 等)
- PRD §4.11.4 (S14 段): #70 已接, 注脚 "Session 4a' 交付"

## 4. CLAUDE.md 决策 #34 内容
<追加的 #34 全文, 模仿 #24 / #26 / #27 结构: A. 交付内容 / B. 接口 / C. 偏差 / D. Harness / E. Vitest+Pytest 覆盖率 / F. 下一步依赖>

## 5. 下一 Session 依赖确认
- Session 1' (Adapter 框架): 不依赖 4a' (但都依赖 0' / A0')
- Session 1.5' (KG 冷启动): 4a' Onboarding mock 应在 1.5' merge 后接通真 KG (§2.2 N7 / N8)
- Session 4b' (IA v2.0 + JSX→TSX): 强依赖 4a' (RequireAuth / UserAuthContext / userApi 必须先到位)
```

---

## §7 Closing Consistency Loop (Step 12 末尾)

> 规则 7 · Session 完成时反查一致性.

```bash
# 重跑 §0 F1-F7
# 期望: 与 Step 0 时一致, 无 ❌
# 若 F2 (PRD §X.Y 行号) 漂移 → 在 SESSION_4APRIME_DELIVERY.md §3 真相源同步章节注明
# 若 F4 (#63/#64/#65/#70 命中数) 减少 → STOP 报告 (规则 4 双向同步漏掉了)
```

---

## §8 10 条最终提醒

1. **真相源不重抄**: Prompt 引用 PRD §4.1.1d.C, 不重写 schema 字段定义; 实施时 grep PRD 当时点版本, 不靠记忆.
2. **commit 格式严格**: `Session 4a' Step <N>: <主题>`, 标题不超 80 字符, 不用 / ✅ / — / 全角空格 (memory `feedback_genpano_session_commit_rule.md`).
3. **常量单一入口**: BCRYPT_COST=12 / ACCESS_TOKEN_TTL_SECONDS=900 / REFRESH_TOKEN_TTL_SECONDS=2592000 (30d) / DRAFT_TTL_HOURS=72 全在 `app/auth/constants.py`, 禁散落字面量.
4. **SameSite 字面**: cookie `sameSite='strict'` 字面禁出现 `lax` / `none` (D10 harness 拦, 镜像 A0' 已存在).
5. **JWT_SECRET 走 env**: `process.env.USER_JWT_SECRET` 必须 ≥ 32 字节, boot-time fast-fail (复用 D8 拦硬编码).
6. **命名锁定**: `competitor_brand_ids` (Python snake_case) ↔ `competitorBrandIds` (TS / JSX) ↔ `competitor_brand_ids` (PostgreSQL ARRAY 列) 三者 1:1 映射, 不允许 `competitorBrands` / `competitors` 之类的别名.
7. **6 步登出契约 (PRD §4.1.1e)**: track 先于 mixpanel.reset / clearLocalStorage 在 reset 前 / 跨标签 BroadcastChannel 在 cookie clear 后 fire / Service Worker 不强制 unregister (MVP); 6 步顺序在 `app/auth/logout.py` 注释里写死, 别人改顺序立刻看到为什么.
8. **双语模板对偶**: 每个 i18n key 必须 zh-CN + en-US 成对 (§4.10.4a 矩阵), 缺一被 A1/A2 harness (Session 0' 已存) 拦. Resend 邮件按 user.locale 选模板, locale 缺省时 fallback Accept-Language → 默认 en-US.
9. **每 commit 跑 ruff + mypy + 相关 pytest**: 不全跑 pytest (太慢), 但每 commit 至少 `ruff check <changed_paths>` + `mypy --strict <changed_paths>` + `pytest tests/<related>/` 必须绿; Step 10 起步 verify shell 全跑.
10. **关闭回路 (规则 7)**: Step 12 必须重跑 §0 F1-F7 grep 并贴在交付报告 §3, 数字漂移即偏差登记; 若全绿则收尾.

---

> **当此 Prompt 交给 Claude Code 时**: Claude Code 第一动作必须是 §0 F1-F7 grep, 输出贴在第一个 reply, 任一 ❌ 走 §3 STOP. 不允许"我先看一下代码再说"这种延迟启动 — 6 grep 是 30 秒动作, 必须先做.
