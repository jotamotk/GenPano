# SESSION_A0_PRIME_PROMPT.md — Session A0' · Admin 认证脚手架 (Python 重写)

> **本 Session 处于 Milestone 1 · 依赖 Session 0' (基础设施已就绪)**
>
> 阅读优先级 (开工前必读):
> 1. `docs/CLAUDE_CODE_SESSIONS_PYTHON.md` (Session 总索引)
> 2. `docs/SESSION_0_PRIME_PROMPT.md` (Session 0' 是格式范本 + 基础设施真相源)
> 3. `docs/REPLAN_2026_04_26.md §4` (Session A0' 规格 line 132-152)
> 4. `CLAUDE.md` 决策 #24 (master Session A0 算法保留 + C1.1-C4 偏差登记) + #25 (Prompt 公约 12 条)
> 5. `docs/ADMIN_PRD.md §5.6` (Admin schema 真相源 - **本 Session 修改 §5.6.8**)
> 6. `docs/ADMIN_CLAUDE_CODE_SESSIONS.md §0` (Admin Session Prompt 公约)

---

## §0 Pre-flight Grep 契约 (开工第一动作)

开工前必须跑以下 6 条 grep 验证真相源仍成立, 任一不一致先 alignment 不写代码:

```bash
# F1 · CLAUDE.md 决策 #24/#25/#29 仍存在 (master A0 + 公约 + Python 反转)
grep -n "Session A0 · Admin 认证脚手架交付" CLAUDE.md
grep -n "Session Prompt 编写公约固化" CLAUDE.md
grep -n "全 Python 后端架构反转" CLAUDE.md

# F2 · ADMIN_PRD §5.6.8 真相源标记仍存在 (admin_users / admin_sessions / admin_password_resets / admin_login_attempts)
grep -n "5.6.8" docs/ADMIN_PRD.md

# F3 · REPLAN §4 Session A0' 规格 line 132-152 仍是 11 Session 的第 2 个
grep -n "Session A0' · Admin 认证脚手架" docs/REPLAN_2026_04_26.md

# F4 · 验证 Session 0' 已 merge (basic infra 就绪)
test -f backend/pyproject.toml && echo "✅ pyproject.toml 存在" || echo "❌ Session 0' 未完成, 停"
test -f backend/app/main.py && echo "✅ FastAPI skeleton 存在" || echo "❌ Session 0' 未完成, 停"
test -f backend/alembic.ini && echo "✅ Alembic 已 init" || echo "❌ Session 0' 未完成, 停"

# F5 · 验证决策 #24 关键偏差 C1.2 (forcePasswordChangeAt vs mustChangePasswd) 仍是真相源
grep -n "forcePasswordChangeAt DateTime?" CLAUDE.md
grep -n "C1.2 (字段命名 + 类型双偏差" CLAUDE.md

# F6 · 验证 PRD §5.6.8 与 CLAUDE.md #24.C1-C4 偏差对齐 (purpose 字段 / role CHECK / 工具链 NodeNext - NodeNext 不需要 Python 翻译)
grep -n "purpose VARCHAR" docs/ADMIN_PRD.md
grep -n "role IN" docs/ADMIN_PRD.md

# F7 · 验证 merge 仓 frontend admin 4 页 + 3 component + adminApi.js 已存在 (复用 baseline, 非新建)
test -f frontend/src/admin/pages/AdminLoginPage.jsx && echo "✅ AdminLoginPage 复用基线存在" || echo "❌ 缺失, 需评估是否回到新建"
test -f frontend/src/admin/pages/AdminForgotPasswordPage.jsx && echo "✅ AdminForgotPasswordPage" || echo "❌"
test -f frontend/src/admin/pages/AdminChangePasswordPage.jsx && echo "✅ AdminChangePasswordPage" || echo "❌"
test -f frontend/src/admin/pages/AdminDashboardPage.jsx && echo "✅ AdminDashboardPage" || echo "❌"
test -f frontend/src/admin/context/AdminAuthContext.jsx && echo "✅ AdminAuthContext" || echo "❌"
test -f frontend/src/admin/components/AdminRouteGuard.jsx && echo "✅ AdminRouteGuard" || echo "❌"
test -f frontend/src/admin/components/SessionExpiredModal.jsx && echo "✅ SessionExpiredModal" || echo "❌"
test -f frontend/src/admin/lib/adminApi.js && echo "✅ adminApi.js (TS 版, 待 rewire 到 Python /admin/api/v1/auth/)" || echo "❌"

# F8 · 决策号引用格式合规 (决策 #25 规则 6 + Plan J D4): Prompt 内引用 CLAUDE.md 必须 `决策 #N (短标题)` 格式
grep -nE "决策 #[0-9]+\.[A-Z]?" docs/SESSION_A0_PRIME_PROMPT.md  # 预期段号引用 (#24.C1.2 等) 仍合规, 单独 #N 必须有短标题
```

**期望结果**: F1-F3 + F5 + F6 + F8 全部命中, F4 + F7 全 ✅。任一失败立即 STOP (见 §3 Type B)。
**F7 全 ✅ 的语义**: §2.1 frontend 5 项 (Item 16-20) 是 **"复用 + API rewire"** (从 master 决策 #24 的 TS adminApi.js 切到 Python `/admin/api/v1/auth/` 6 endpoint), 不是新建; 任何文件 ❌ 立即 STOP 评估是否回退为新建。

---

## §1 真相源索引

### 1.1 引用 (本 Session 不改, 严格 honor)

| # | 真相源 | 段号 | 类型 | 用途 |
|---|--------|------|------|------|
| 1 | `docs/PRD.md` | §4.1.1e (登出 & 会话管理) | [引用] | Admin 登出契约 6 步 (含 mixpanel.reset 顺序) |
| 2 | `docs/PRD.md` | §4.10.4a (i18n 覆盖矩阵) | [引用] | Admin 邮件模板 zh-CN/en-US 双语 |
| 3 | `CLAUDE.md` | 决策 #24 (master A0) | [反向工程入口] | 算法语义 (JWT TTL 15min/7d, BCrypt cost 12, Rate limit 5/15min, 4 状态机, BroadcastChannel) |
| 4 | `CLAUDE.md` | 决策 #24.C1-C4 (偏差登记) | [引用] | 历史偏差: forcePasswordChangeAt 类型 / super_admin 单值 / NodeNext 工具链 / purpose 列 gap |
| 5 | `CLAUDE.md` | 决策 #25 (Prompt 公约 12 条) | [引用] | Prompt 编写公约 (规则 1-12) |
| 6 | `CLAUDE.md` | 决策 #29 (Python 反转) | [引用] | 整体架构 |
| 7 | `CLAUDE.md` | 决策 #30 (preview 强制) | [引用] | Phase Gate Layer 3 强制 |
| 8 | `CLAUDE.md` | 决策 #31 (分支规则) | [引用] | 从 main fork `session-a0prime` |
| 9 | `docs/ADMIN_PRD.md` | §5.6.8 (admin_users / admin_sessions / admin_password_resets / admin_login_attempts) | [反向工程入口] | 4 张表字段 + CHECK 约束 |
| 10 | `docs/ADMIN_PRD.md` | §5.6.1 (3 角色) | [引用] | super_admin / ops_admin / viewer (本 Session 仅落 super_admin, A1' 扩) |
| 11 | `docs/ADMIN_CLAUDE_CODE_SESSIONS.md` | §0 (Admin Prompt 公约) | [引用] | 7 公约 (规则 1-7) + Phase 2 追加 (规则 10-12) |
| 12 | `docs/REPLAN_2026_04_26.md` | §4 line 132-152 (Session A0' 规格) | [引用] | 范围 / 依赖 / Phase Gate 验收 |
| 13 | `docs/HARNESS_ENGINEERING.md` | §10.6 (Group D Auth harness) | [引用] | D8/D9/D10 Python 翻译方案 |
| 14 | `docs/SESSION_0_PRIME_PROMPT.md` | 全文 | [引用] | 基础设施前置 + 格式范本 |
| 15 | `docs/TEST_STRATEGY.md` | §10 (Admin 测试矩阵) | [引用] | A0 测试场景 |

### 1.2 修改清单 (本 Session 写入)

| # | 文件 | 操作 | 原因 |
|---|------|------|------|
| 1 | `backend/app/admin/auth/` (新目录) | 创建 12 文件 | Auth 业务逻辑 |
| 2 | `backend/app/admin/api/v1/auth/` (新目录) | 创建 6 endpoint | login/refresh/logout/forgot-password/reset-password/change-password |
| 3 | `backend/alembic/versions/<timestamp>_admin_auth_baseline.py` | 创建 migration | 4 张表 + CHECK 约束 |
| 4 | `backend/app/models/admin.py` | 创建 SQLAlchemy 模型 | AdminUser / AdminSession / AdminPasswordReset / AdminLoginAttempt |
| 5 | `backend/scripts/admin-bootstrap.py` | 创建 | 幂等 super_admin 种子 |
| 6 | `frontend/src/admin/` (新目录) | 创建 4 页 + 4 component + 1 lib | Admin 前端 |
| 7 | `backend/.harness_fixtures/D8_*` + `D9_*` + `D10_*` | 创建 fixture | Harness 自验证 |
| 8 | `backend/harness/rules.py` (扩展) | append D8/D9/D10 | Python harness |
| 9 | `docs/CLAUDE_CODE_SESSIONS_PYTHON.md` | 更新状态 | A0' 状态待起草 → 已交付 |
| 10 | `CLAUDE.md` | 新增决策 #33 (本 Session 交付) | 决策追溯 |

### 1.3 版本警告

- **决策 #24 中 master A0 的 TS 实现完全报废**, 但算法语义 (JWT 配置 / BCrypt cost / Rate Limit 窗口 / 4 状态机 / BroadcastChannel / Cookie 策略) 100% 保留
- **决策 #24.C3 (NodeNext 配置) 不适用 Python**: webpack `extensionAlias` 偏差是 TS 工具链问题, Python 不存在
- **决策 #24.C4 (purpose 列 gap) 必须在本 Session 关闭**: 创建 `admin_password_resets.purpose` 列默认 `'reset'` + CHECK IN ('reset','invitation'), 启用 invitation 流程为 A1' 准备
- **`forcePasswordChangeAt` 命名锁定**: 决策 #24.C1.2 已确认这是字段名, 禁止误写 `mustChangePassword` 等变体
- **REFRESH_TOKEN_TTL 双层差异 (intentional, NOT inconsistency)**: Admin 侧 `REFRESH_TOKEN_TTL_SECONDS = 604800` (7d) — 安全更紧, Admin 用户少且高权限, 7 天强制再认证可接受。User 侧 (Session 4a') 用 `REFRESH_TOKEN_TTL_SECONDS = 2592000` (30d) — UX 更友好, 大众用户低权限, 30 天减少重登摩擦。**两常量分别定义在 `app/admin/auth/constants.py` 和 `app/auth/constants.py`, 不共享单例**, 这是有意识的安全/UX trade-off, 不是配置疏忽。Session 4a' §1.3 同步声明此差异并反向交叉引用本段。

---

## §2 MVP Scope

### 2.1 ✅ 本 Session 做 (按交付顺序)

| # | 项 | 锚点 | 验收信号 |
|---|---|------|---------|
| 1 | SQLAlchemy 模型: `AdminUser` (email/passwordHash/role/status/forcePasswordChangeAt/lastPasswordAt/lastLoginAt) + `AdminSession` (refreshTokenHash/userId/jti/userAgent/ipAddress/expiresAt/revokedAt) + `AdminPasswordReset` (userId/tokenHash/purpose/expiresAt/consumedAt) + `AdminLoginAttempt` (email/ipAddress/success/failureCode/userAgent/createdAt) | ADMIN_PRD §5.6.8 + 决策 #24.A | `backend/app/models/admin.py` 4 类齐全 + 字段类型对齐 |
| 2 | Alembic migration `<timestamp>_admin_auth_baseline.py` + raw SQL CHECK 约束 (role / status / failureCode / purpose) | ADMIN_PRD §5.6.8 + 决策 #24.C2/C4 | `alembic upgrade head` 全绿 + 4 表 + 6 CHECK 约束生效 |
| 3 | `app/admin/auth/jwt.py` — python-jose HS256 access (15min) + refresh (7d) + 4 失败码 (expired/signature/malformed/claims) + ADMIN_JWT_SECRET 启动 fast-fail (< 32 byte 抛 `AdminJwtSecretMissingError`) | 决策 #24.B | pytest 7 例 (含 expired / wrong signature / future iat / clock skew) 全过 |
| 4 | `app/admin/auth/refresh_token.py` — secrets.token_urlsafe(32) + sha256 + `constant_time_eq_hex()` 包 `hmac.compare_digest` + 双 length check + malformed hex try/except | 决策 #24.B | pytest 8 例全过 |
| 5 | `app/admin/auth/password.py` — passlib bcrypt cost 12 (单一入口 `BCRYPT_COST = 12` 常量) + zxcvbn-python score ≥ 3 + length ≥ 12, 返回 `(ok, reason)` 元组 | 决策 #24.B + Harness D9 | pytest 8 例全过 + bcrypt hash 前缀 `$2b$12$` 实测 |
| 6 | `app/admin/auth/cookies.py` — Set-Cookie 字符串生成 (HttpOnly + SameSite=Strict + Path=/admin + Secure (env-dependent) + Max-Age) + `clear_auth_cookies()` 双 delete | 决策 #24.B + Harness D10 | pytest 11 例 (含 dev 不 Secure / prod 必 Secure / SameSite='strict' literal) |
| 7 | `app/admin/auth/middleware.py` — FastAPI dependency `require_admin_session()` + `decide_admin_auth(pathname, access_token, force_password_change_at)` 纯决策函数返回 `{'action':'allow'\|'redirect'\|'unauthorized', 'target':?, 'reason':?}` + 白名单 `AUTH_WHITELIST_PREFIXES` | 决策 #24.E | pytest 15 例 (含 force-change-password gating / API path / whitelist match) |
| 8 | `app/admin/auth/reauth_gate.py` — `evaluate_reauth(last_password_at, now=None, max_age_ms=30*60_000)` 3 决策 (allowed / required:stale / required:never_authenticated) + 时钟偏移容错 (future last_password_at 视为 allowed) | 决策 #24.B | pytest 7 例全过 |
| 9 | `app/admin/auth/rate_limiter.py` — slowapi-based + Redis backend (生产) / in-memory fallback (本地) sliding-window: `check_email_limit(email)` 5/15min + `check_ip_limit(ip)` 20/15min, denied 也计入窗口 | 决策 #24.B | pytest 7 例 + 5 次失败触发 429 实测 |
| 10 | `app/admin/auth/session_repo.py` — Prisma-coupled 等价 (SQLAlchemy async session + admin_sessions 表读写 + rotation 逻辑: refresh 成功旧 row.revoked_at = now() + 新 row insert) | 决策 #24.B | 集成测试: 旧 token replay 401 + 新 token 200 |
| 11 | `app/admin/auth/audit.py` — 写 admin_login_attempts (4 字段 email/ip/success/failure_code), 禁写密码/token | 决策 #24.B | pytest 5 例 + 实测 5 失败 1 成功 6 行 audit |
| 12 | `app/admin/auth/email.py` — Resend client + React Email `AdminPasswordResetEmail` + `AdminInvitationEmail` 双语模板 + ADMIN_BASE_URL 缺失 fallback `http://localhost:5173` | 决策 #24.B + PRD §4.10.4a | pytest 4 例 (含 zh-CN / en-US locale switching) |
| 13 | `app/admin/auth/constants.py` — TTL/长度/algorithm/audience/issuer 单一真相源 (ACCESS_TOKEN_TTL_SECONDS=900 / REFRESH_TOKEN_TTL_SECONDS=604800 / REAUTH_WINDOW_MS=30*60_000 / BCRYPT_COST=12 / MIN_PASSWORD_LENGTH=12 / MIN_ZXCVBN_SCORE=3 / JWT_ALGORITHM='HS256' / JWT_ISSUER='genpano-admin' / JWT_AUDIENCE_ACCESS='genpano-admin-access' / ACCESS_TOKEN_COOKIE='admin_access_token' / REFRESH_TOKEN_COOKIE='admin_refresh_token' / COOKIE_PATH='/admin') | 决策 #24.B | grep `BCRYPT_COST = 12` 单点出现; harness D9 失败若硬编码任意位置 |
| 14 | 6 个 FastAPI endpoint `app/admin/api/v1/auth/`: `POST /login` / `POST /refresh` / `POST /logout` / `POST /forgot-password` / `POST /reset-password` / `POST /change-password` 全部接 `app/admin/auth/*` 模块 | 决策 #24.B + 决策 #24.E | pytest endpoint 整合 ≥ 18 例 + curl 实测每端点 200/401/429 |
| 15 | `scripts/admin-bootstrap.py` — 幂等 super_admin 种子 (env: `ADMIN_BOOTSTRAP_EMAIL` + `ADMIN_BOOTSTRAP_PASSWORD`), 检测已存在 super_admin 直接 exit 0 | 决策 #24.G (Frank 实测的种子机制) | 运行 2 次结果一致 + DB 行数不变 |
| 16 | **复用 (非新建)** Frontend `frontend/src/admin/pages/`: `AdminLoginPage.jsx` (env-aware 顶条 dev/staging/prod 三色) + `AdminForgotPasswordPage.jsx` + `AdminChangePasswordPage.jsx` + `AdminDashboardPage.jsx` (Phase Gate stub) — 4 页 merge 仓 §0 F7 已验证存在, 本 Session 不新建, 仅在需要时调整 import / 文案 | 决策 #24.D | Frank 浏览器开 4 页面无 React 报错 |
| 17 | **复用 (非新建)** Frontend `frontend/src/admin/context/AdminAuthContext.jsx` — 4 状态机 (initializing/authenticated/anonymous/expired) + silent refresh 14min 定时器 (Access TTL=15min lead=60s) + `BroadcastChannel('genpano-admin-auth')` 跨 tab 同步 (login/refresh/logout/expire 4 消息); merge 仓已存在, 本 Session 不重写 4 状态机, 只 rewire fetch 路径到 Python `/admin/api/v1/auth/refresh` | 决策 #24.D | Frank 开 2 个 tab 登录 → 一个 tab 登出 → 另一个 tab 自动到 login |
| 18 | **复用 (非新建)** Frontend `frontend/src/admin/components/SessionExpiredModal.jsx` — 无 X-close / 无 ESC / 无 backdrop-click, 唯一 CTA "重新登录" → `/admin/login?reason=session_expired&redirect=<current>`; merge 仓已存在, 本 Session 不动 UI 行为 | 决策 #24.D | 模拟 token 过期 + 自动 trigger modal 实测 |
| 19 | **复用 (非新建)** Frontend `frontend/src/admin/components/AdminRouteGuard.jsx` — 决策矩阵 (initializing→spinner / anonymous→navigate login / authenticated+forceChange+非 change-password 白名单→navigate change-password / authenticated+OK→render / expired→render children 让 modal 盖顶) + 双层 force-change gating (Edge layer 1 + Context layer 2); merge 仓已存在, 本 Session 仅校验 forceChange 字段从 Python refresh response 解出无误 | 决策 #24.E | Frank 用 forcePasswordChangeAt != null 的 super_admin 登录 → 自动跳 /admin/change-password |
| 20 | **API rewire (非新建)** Frontend `frontend/src/admin/lib/adminApi.js` — `adminFetch()` wrapper + `adminAuthApi` 封装 6 端点 + `AdminApiError` class 携 `{status, body}` + `credentials: 'include'` 硬编码; **本 Session 唯一 frontend 实质工作** = 把 master 决策 #24.D 的 TS Next.js 端点路径切到 Python FastAPI 6 端点 (`/admin/api/v1/auth/login` / `/refresh` / `/logout` / `/forgot-password` / `/reset-password` / `/change-password`), 不新建文件不动调用方 | 决策 #24.D | pytest mock + manual smoke |
| 21 | Harness D8/D9/D10 Python 重写 + 3 self-seeded fixture (`backend/.harness_fixtures/D8_hardcoded_jwt_secret.py.cifixture` / `D9_bcrypt_cost_8.py.cifixture` / `D10_cookie_samesite_lax.py.cifixture`) + `python -m harness selftest` 期望 EXPECTED_POSITIVES=6 (Session 0' 的 F1+F4+D8 + 本 Session 的 D8+D9+D10 — 注: D8 在 Session 0' 已上, 本 Session 是验证可命中 admin/auth 实际代码) | 决策 #21.C + 决策 #24.F | `python -m harness selftest` 打印 `selftest: PASS (6/6 fixture expectations met)` |
| 22 | pytest 覆盖率 admin/auth 聚合 ≥ 80% (剔除 Resend/Redis 耦合的 email.py + session_repo.py + rate_limit_config.py — 改 L3 endpoint replay 覆盖) | 决策 #24.F | `pytest backend/tests/admin/auth/ --cov=backend/app/admin/auth --cov-report=term-missing --cov-fail-under=80` 全过 |
| 23 | Preview env 部署: PR comment 自动给 `https://genpano-preview-pr-<id>.vercel.app/admin/login` URL, Frank 浏览器登录 super_admin | 决策 #30 + Session 0' Step 10 | Frank 截图 OK |

### 2.2 ❌ 本 Session 不做 (推迟到对应 Session)

| # | 项 | 推迟到 | 理由 |
|---|---|--------|------|
| N1 | `ops_admin` / `viewer` 角色支持 + RBAC 矩阵 | A1' (用户管理) | 决策 #24.C2 — A0 只开 super_admin 单值 CHECK; A1' 一并扩 3 角色 + Admin 用户管理 UI |
| N2 | Admin Dashboard 真实卡片 (KG QA / Alert / System Health) | A1' | A0 只交付 stub 页 (登录后看到一个 placeholder) |
| N3 | MFA / WebAuthn / 2FA | Phase 2 | MVP 不要; 决策 #24 未提 |
| N4 | OAuth Provider (Google/Microsoft Login) | Phase 2 | MVP 用密码 |
| N5 | 邀请流 (invitation 实际 send + 接收页) | A1' | 决策 #24.C4 — purpose 列本 Session 创建但 invitation 流程 A1' 启用 |
| N6 | API token (MCP Token) 签发 | A5 (Citation Tier + MCP Token) | 决策 #21.E — A5 单独 Session |
| N7 | Citation Tier CRUD 参数管理 | A5 | 决策 #21.E |
| N8 | Admin 审计日志查询 UI | A1' | A0 只写 admin_login_attempts, 不实现查询页 |
| N9 | Admin Help Center / 文档 | Phase 2 | 不要 |
| N10 | E2E Playwright Visual 测试 | Session 6 (TEST_STRATEGY Phase 4) | A0 只 pytest |

---

## §3 STOP Triggers

任一触发立即停下, 写 `.session_a0prime_stop.md` 报告详情, 等 Frank alignment 后再续:

### Type A · 环境失败
- **A1**: Session 0' 未完成 (F4 grep 失败), 无法 import FastAPI / SQLAlchemy / Alembic
- **A2**: Supabase Preview Branch 未配置 (无法 alembic upgrade head)
- **A3**: Resend API key 缺失 + 邮件流必须的 endpoint 测试无法跑
- **A4**: Redis (rate limiter 后端) 未配置且 in-memory fallback 在 multi-worker 场景失效

### Type B · 真相源冲突
- **B1**: ADMIN_PRD §5.6.8 字段名 / CHECK 约束与 CLAUDE.md 决策 #24.A 描述冲突 (e.g. forcePasswordChangeAt 突然变 mustChangePassword)
- **B2**: REPLAN §4 line 132-152 与 CLAUDE.md 决策 #24 算法描述冲突 (e.g. Cookie SameSite 策略不一致)
- **B3**: PRD §4.1.1e (登出 6 步) 与 CLAUDE.md 决策 #24.D (BroadcastChannel 4 消息) 冲突

### Type C · 范围溢出
- **C1**: Frank 在中途追加 "顺便实现 ops_admin 角色" → 立即 STOP 走 N1 推迟到 A1'
- **C2**: 测试覆盖率 < 80% 但代码量已经远超原始计划 → STOP 重新对齐 ✅ 表 22 行
- **C3**: Frontend 4 页面 + 4 component 实现量超出 1.5 天 → STOP 评估是否拆 Session A0.1'

### STOP 报告模板

```markdown
# Session A0' STOP Report

**触发类型**: <Type A / B / C>
**编号**: <A1 / A2 / B1 / ...>
**触发时间**: <ISO timestamp>
**触发位置**: Step <N> · <子任务名>
**冲突描述**:
<具体描述>

**已完成**:
- <Step 0 ... Step N-1>

**已 commit 数**: <数量> commits 在 `session-a0prime` 分支

**建议 alignment**:
<1-2 sentence 建议>
```

---

## §4 Phase Gate (Layer 1/2/3 验收)

### G_A0.1 — `verify-session-a0prime.sh` Layer 1 自动验收

```bash
#!/bin/bash
set -e
echo "▶ G_A0.1 — Layer 1 自动验收"
cd backend

# 1. ruff + mypy
echo "▶ G_A0.1.1 ruff lint"
ruff check app/admin/auth/ app/admin/api/v1/auth/ scripts/admin-bootstrap.py app/models/admin.py
echo "▶ G_A0.1.2 mypy strict"
mypy app/admin/auth/ app/admin/api/v1/auth/ app/models/admin.py

# 2. pytest 覆盖率 ≥ 80%
echo "▶ G_A0.1.3 pytest 覆盖率"
pytest tests/admin/auth/ \
  --cov=app/admin/auth \
  --cov-report=term-missing \
  --cov-fail-under=80

# 3. Alembic 迁移
echo "▶ G_A0.1.4 alembic upgrade head 全绿"
alembic upgrade head
psql $DATABASE_URL -c "SELECT count(*) FROM admin_users;" || exit 1
psql $DATABASE_URL -c "SELECT count(*) FROM admin_sessions;" || exit 1
psql $DATABASE_URL -c "SELECT count(*) FROM admin_password_resets;" || exit 1
psql $DATABASE_URL -c "SELECT count(*) FROM admin_login_attempts;" || exit 1

# 4. CHECK 约束生效
echo "▶ G_A0.1.5 CHECK 约束实测"
psql $DATABASE_URL -c "INSERT INTO admin_users (email, password_hash, role, status) VALUES ('test@test.com', 'x', 'NOT_A_VALID_ROLE', 'active');" 2>&1 | grep "violates check" || exit 1

# 5. Harness selftest
echo "▶ G_A0.1.6 harness selftest"
python -m harness selftest || exit 1

# 6. admin-bootstrap idempotent
echo "▶ G_A0.1.7 admin-bootstrap 幂等"
python scripts/admin-bootstrap.py
ROW_COUNT_1=$(psql $DATABASE_URL -At -c "SELECT count(*) FROM admin_users WHERE role='super_admin';")
python scripts/admin-bootstrap.py
ROW_COUNT_2=$(psql $DATABASE_URL -At -c "SELECT count(*) FROM admin_users WHERE role='super_admin';")
[ "$ROW_COUNT_1" = "$ROW_COUNT_2" ] || { echo "❌ bootstrap 不幂等"; exit 1; }

echo "✅ G_A0.1 Layer 1 全部通过"
```

### G_A0.2 — Harness selftest Layer 2

```bash
python -m harness selftest
# 期望: ● selftest: PASS  (6 / 6 fixture expectations met)
# 6 = Session 0' 的 F1/F4/D8 + Session A0' 的 D8/D9/D10 (注: D8 在 Session 0' 已存, A0' 验证可命中 admin/auth 实际代码)
```

### G_A0.3 — Frank Layer 3 浏览器实测

| 编号 | 操作 | 期望结果 | 自动 / 人审 |
|------|------|---------|------------|
| G_A0.3.1 | 打开 `https://genpano-preview-pr-<id>.vercel.app/admin/login` | 看到登录页 + dev 顶条 (绿色) | 人审 |
| G_A0.3.2 | 用 super_admin 邮箱 + 错密码登录 5 次 | 第 6 次返回 429 + audit 看到 5 行 RATE_LIMITED | 人审 |
| G_A0.3.3 | 用对的密码登录 | 落到 /admin/change-password (因为 forcePasswordChangeAt 已 set) | 人审 |
| G_A0.3.4 | 改密成功 | 落到 /admin/dashboard 看到 placeholder 卡片 | 人审 |
| G_A0.3.5 | 持续浏览 30min 不刷新 | 控制台看到每 14min 一次 silent refresh + tab 不掉线 | 人审 |
| G_A0.3.6 | 开 2 个 tab 登录 → 一个 tab 点登出 | 另一个 tab 自动到 /admin/login | 人审 |
| G_A0.3.7 | 模拟 token 过期 (DB 改 admin_sessions.revoked_at) → 任意操作 | SessionExpiredModal 弹出, 唯一 CTA "重新登录" | 人审 |
| G_A0.3.8 | 调用 forgot-password endpoint 输入邮箱 | 收到 zh-CN 重置邮件 (locale=zh-CN) + 链接 24h 内有效 | 人审 |
| G_A0.3.9 | 修改 User.locale=en-US 后再请求 | 收到 en-US 重置邮件 | 人审 |

---

## §5 12 步交付顺序 (原子 commit, ≤ 5 文件 / commit)

每 commit 必须 `Session A0' Step <N>: <主题>` 格式; 不允许跨 step 混改。

### Step 0 · 分支 + Pre-flight Grep
```bash
git checkout main && git pull
git checkout -b session-a0prime
bash scripts/preflight-a0prime.sh   # 跑 §0 的 F1-F6 grep
```
Commit: `Session A0' Step 0: 分支建立 + pre-flight grep 全绿`

### Step 1 · SQLAlchemy 4 模型 + Alembic 迁移
- `backend/app/models/admin.py` (4 类)
- `backend/alembic/versions/<timestamp>_admin_auth_baseline.py`
- `alembic upgrade head` 实测
Commit: `Session A0' Step 1: Admin 4 表 + 6 CHECK 约束 + Alembic 迁移`

### Step 2 · Constants + JWT + Refresh Token + Password
- `backend/app/admin/auth/constants.py`
- `backend/app/admin/auth/jwt.py` + `tests/admin/auth/test_jwt.py` (7 例)
- `backend/app/admin/auth/refresh_token.py` + `test_refresh_token.py` (8 例)
- `backend/app/admin/auth/password.py` + `test_password.py` (8 例)
Commit: `Session A0' Step 2: JWT + RefreshToken + Password 单元测试 23 例`

### Step 3 · Cookies + ReauthGate + RateLimiter
- `backend/app/admin/auth/cookies.py` + `test_cookies.py` (11 例)
- `backend/app/admin/auth/reauth_gate.py` + `test_reauth_gate.py` (7 例)
- `backend/app/admin/auth/rate_limiter.py` + `test_rate_limiter.py` (7 例)
Commit: `Session A0' Step 3: Cookies + Reauth + RateLimiter 单元测试 25 例`

### Step 4 · Middleware + SessionRepo + Audit + Email
- `backend/app/admin/auth/middleware.py` + `test_middleware.py` (15 例)
- `backend/app/admin/auth/session_repo.py` (Prisma → SQLAlchemy 等价)
- `backend/app/admin/auth/audit.py` + `test_audit.py` (5 例)
- `backend/app/admin/auth/email.py` (Resend client + 双语模板)
Commit: `Session A0' Step 4: Middleware + SessionRepo + Audit + Email`

### Step 5 · 6 endpoint
- `backend/app/admin/api/v1/auth/login.py`
- `backend/app/admin/api/v1/auth/refresh.py`
- `backend/app/admin/api/v1/auth/logout.py`
- `backend/app/admin/api/v1/auth/forgot_password.py`
- `backend/app/admin/api/v1/auth/reset_password.py`
- `backend/app/admin/api/v1/auth/change_password.py`
Commit: `Session A0' Step 5: 6 endpoint 集成测试 18 例`

### Step 6 · Bootstrap + Harness D8/D9/D10
- `backend/scripts/admin-bootstrap.py` + idempotent 测试
- `backend/harness/rules.py` 扩 D8/D9/D10
- `backend/.harness_fixtures/D8_hardcoded_jwt_secret.py.cifixture`
- `backend/.harness_fixtures/D9_bcrypt_cost_8.py.cifixture`
- `backend/.harness_fixtures/D10_cookie_samesite_lax.py.cifixture`
- `python -m harness selftest` 实测 6/6
Commit: `Session A0' Step 6: Bootstrap + Harness D8/D9/D10 selftest 6/6`

### Step 7 · 前端 adminApi.js API rewire (复用基线, 非新建)
**前置确认**: §0 F7 已验证 `frontend/src/admin/pages/{AdminLoginPage,AdminForgotPasswordPage,AdminChangePasswordPage,AdminDashboardPage}.jsx` + `context/AdminAuthContext.jsx` + `lib/adminApi.js` 在 merge 仓全部存在 (8 个 ✅)。本 Step **不新建任何 .jsx 页面 / 不重写 4 状态机**, 唯一实质工作 = 把 `adminApi.js` 的 fetch 路径从 master 决策 #24.D 的 TS Next.js endpoint 切到 Python FastAPI 6 endpoint。
- `frontend/src/admin/lib/adminApi.js` — **rewire only**: 6 endpoint URL 字符串 (`/admin/api/v1/auth/login` 等) 与 `credentials: 'include'` + `AdminApiError` 类保持不变; 若 master 版 endpoint path 与 Python FastAPI route path 完全一致则 0 行变更, 仅 README 注释引 §1.2.5 (本 Session 修改契约文件) 标记 "切到 Python 后端"
- `frontend/src/admin/context/AdminAuthContext.jsx` — **复用**, 0 行变更 (4 状态机 + silent refresh 14min 定时器 + BroadcastChannel 跨 tab 已就位)
- `frontend/src/admin/pages/AdminLoginPage.jsx` / `AdminForgotPasswordPage.jsx` / `AdminChangePasswordPage.jsx` — **复用**, 0 行变更, 仅在 manual smoke 时若 UI 文案与 Python 后端 error code 不一致才微调
Commit: `Session A0' Step 7: adminApi.js rewire 到 Python /admin/api/v1/auth/ 6 endpoint (frontend 复用 master 基线)`

### Step 8 · AdminRouteGuard + SessionExpiredModal + Dashboard stub (复用基线, 仅校验)
**前置确认**: §0 F7 已验证 3 component + AdminDashboardPage.jsx 在 merge 仓全部存在。本 Step **不新建任何 component**, 仅校验 forcePasswordChangeAt 字段从 Python refresh response 解出后, 双层 force-change gating (Edge layer 1 + Context layer 2) 决策矩阵仍 fire 正确, 必要时调 1-2 行 fallback 处理。
- `frontend/src/admin/components/AdminRouteGuard.jsx` — **复用**, 0 行变更 (决策矩阵已就位)
- `frontend/src/admin/components/SessionExpiredModal.jsx` — **复用**, 0 行变更 (无 X-close / 无 ESC / 无 backdrop-click 已就位)
- `frontend/src/admin/components/AdminAuthShell.jsx` — **复用** (master 已交付)
- `frontend/src/admin/pages/AdminDashboardPage.jsx` — **复用**, Phase Gate stub 已就位
- `frontend/src/App.jsx` — 校验 AdminRouteGuard 集成无 React 报错; 若 master 已 wire 则 0 行变更
Commit: `Session A0' Step 8: AdminRouteGuard + ExpiredModal + Dashboard stub 校验 (frontend 复用 master 基线)`

### Step 9 · 端到端集成测试
- `backend/tests/admin/auth/test_e2e_integration.py` (登录 → 改密 → 登出 → silent refresh)
- 实测覆盖率 ≥ 80%
Commit: `Session A0' Step 9: E2E 集成测试 + 覆盖率 80%+`

### Step 10 · verify-session-a0prime.sh + Phase Gate Layer 1
- `scripts/verify-session-a0prime.sh` (按 §4.G_A0.1)
- 跑通 7 阶段
Commit: `Session A0' Step 10: Layer 1 verify-session-a0prime.sh 全绿`

### Step 11 · Preview env + Frank Layer 3
- 推到 GitHub → CI 跑通 → Preview URL 自动 PR comment
- Frank 浏览器跑 §4.G_A0.3 9 个场景, 截图回写 §6 交付报告
Commit: `Session A0' Step 11: Preview env + Frank Layer 3 9/9 通过`

### Step 12 · 文档 + 决策追溯
- `docs/CLAUDE_CODE_SESSIONS_PYTHON.md` 更新 Session A0' 状态 → 已交付
- `CLAUDE.md` 新增决策 #33 (Session A0' Python 重写交付)
- `docs/SESSION_A0PRIME_DELIVERY.md` 交付报告 (按 §6 模板)
- 重跑 §0 §7 grep 确认真相源未漂移
Commit: `Session A0' Step 12: 文档 + 决策追溯 + Closing Loop 全绿`

---

## §6 交付报告模板 (Step 12 写入 SESSION_A0PRIME_DELIVERY.md)

```markdown
# Session A0' 交付报告

## 1. Phase Gate 通过证据

### G_A0.1 Layer 1 (机器自动)
- ruff: ✅
- mypy strict: ✅
- pytest 覆盖率: <实际 %>%, 阈值 80%
- alembic upgrade head: ✅
- 4 表实测 + 6 CHECK 约束: ✅
- harness selftest: <实际 N/N>
- admin-bootstrap 幂等: ✅

### G_A0.2 Layer 2 (Harness)
- selftest: <实际 6/6 fixture expectations met>

### G_A0.3 Layer 3 (Frank 浏览器)
- 9/9 场景通过 (附截图链接)

## 2. 偏差登记 (规则 3)
<C1 / C2 / ... 列出与 ADMIN_PRD §5.6.8 / CLAUDE.md 决策 #24 的偏差>

## 3. 真相源同步 (规则 4)
<改了哪些真相源 + 同步触发的 grep>

## 4. CLAUDE.md 决策 #33 内容
<新增决策号 + 段号格式同决策 #24>

## 5. 下一 Session 依赖确认
- Session 4a' (User Auth + Onboarding) 依赖本 Session 提供的 `app.dependencies.get_db_session` 和 `app.admin.auth.constants` 全套常量复用为 user 侧 — ✅ 就绪
```

---

## §7 Closing Consistency Loop (Step 12 末尾)

**重跑 §0 grep 验证真相源未漂移**:

```bash
# 重跑 F1-F6
bash scripts/preflight-a0prime.sh
# 期望: 与 Step 0 时一致, 无 ❌
```

如发现新偏离, 回 §3 Type B 登记 + 写 STOP report (此情况下 Step 12 不能 commit, 等 alignment)。

---

## §8 Final Reminders to Claude Code

1. **真相源不重抄**: §1 列的 16 行真相源, 引用即可, 不在 Prompt 内重新写一遍 ADMIN_PRD §5.6.8 字段表 (规则 1)
2. **每 step 一个 commit**: ≤ 5 文件, 标题严格 `Session A0' Step <N>: <主题>` (规则 12 的标准, 见 `feedback_genpano_session_commit_rule.md`)
3. **bcrypt cost 12 唯一入口**: 所有 hash 调用必须 `from app.admin.auth.constants import BCRYPT_COST` 不能写死 12 (Harness D9 拦)
4. **Cookie SameSite=Strict 写 literal**: `cookies.py` 必须 mention `sameSite='strict'` 字面量, 不能写 `SAMESITE_VALUE=os.getenv('SAMESITE','strict')` (Harness D10 拦)
5. **JWT_SECRET 不硬编码**: 全部走 `os.getenv('ADMIN_JWT_SECRET')` + 启动时 `len(secret) >= 32` fast-fail (Harness D8 拦)
6. **forcePasswordChangeAt 不重命名**: 决策 #24.C1.2 已锁定, 不允许 mustChangePassword / forceChange / requirePasswordReset 等变体
7. **PRD §4.1.1e 6 步登出契约**: BroadcastChannel 'logout' 消息 → mixpanel.track('admin_logout') → mixpanel.reset() → POST /admin/api/v1/auth/logout → clear cookies → navigate /admin/login (顺序固定, mixpanel.reset() 必须在 track 之后, PII 不进 mixpanel)
8. **Resend 双语模板按 User.locale 路由**: 默认 zh-CN, locale=en-US 才发英文; 不允许两份都发
9. **每 commit 跑 ruff + mypy**: 不允许 lint 报错的 commit 存在
10. **Step 12 重跑 §0 grep 验证 closing loop**: 新偏差必须登记 STOP report 不允许偷过

---

**Session A0' 起飞条件**: §0 grep F1-F6 全绿 + Session 0' 已 merge 到 main → 立即开始 Step 0。
