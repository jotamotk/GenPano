# Session A1' Phase Gate · Layer 3 (Frank 浏览器实操验收清单)

> 本文档是 **A1' Phase Gate Layer 3** 的真相源。依据 `SESSION_A1_PRIME_PROMPT.md §4 Layer 3` 推到 6 步可执行 (S1-S6), 每步含 (a) 入口路径 / (b) 操作 / (c) 期望 UI / (d) 期望审计 / (e) 红时回滚锚点。**Layer 1 (`scripts/verify-session-a1prime.sh`) + Layer 2 (`scripts/smoke_admin_a1.sh`) 全绿后, Frank 才走 Layer 3。任一 S 步红, A1' Phase Gate 不绿, 回 §5 修后再来。**Frank 不接受截图替代浏览器实操 (`feedback_genpano_session_preview_env_2026_04_26.md`)。**

## 前置 (一次性)

- A1' 分支已 push 到 `origin/feature/session-a1prime`
- Vercel preview deploy GREEN (frontend admin shell)
- Render preview deploy GREEN (`genpano-admin-backend` web service: alembic upgrade head + uvicorn `app.main:app`)
- Render dashboard 已配置 secret (sync=false 项): `ADMIN_JWT_SECRET` (≥32 bytes) / `RESEND_API_KEY` (mock mode 接受空) / `GENPANO_DATABASE_URL` / `GENPANO_REDIS_URL`
- Render 启动后跑过一次 `python scripts/admin-bootstrap.py`, super_admin 入库, Frank 邮箱 + 强密码已记录 (force_password_change_at=NOW, 首登强改密)
- 测试用户已通过 4a' 注册接口或 SQL fixture 入库 (Frank 在 Render shell `psql $GENPANO_DATABASE_URL` 直接 INSERT 1 行, 用于 S3 操作)
- 已造一条 `alias_conflicts` (`candidate_ids` 含 ≥ 2 个元素) + 一条 `brand_submissions` (`status='pending'`, `sla_started_at=NOW()-2h`) 用于 S4

## S1 · 登录 + Dashboard 真实当日成本

- **路径**: `https://<vercel-preview>.vercel.app/admin/login`
- **操作**:
  1. 输入 super_admin 邮箱 + 强密码 → 提交
  2. 若是首登, 跳 `/admin/change-password`, 填新密 (≥12 chars + zxcvbn ≥3) → 提交
  3. 跳 `/admin/dashboard`
- **期望 UI**:
  - URL 落 `/admin/dashboard` (不是 `/admin/login?reason=session_expired`)
  - 顶部 KPI 卡: 当日成本 (USD / CNY 双单位) + 今日 Query 数 + Pipeline 健康度三色灯
  - 当日成本 KPI **非 0** (Render preview env 已跑过至少 1 条 mock query → cost_daily 表非空) — 若 0, 跳到 S1.degraded
  - 不出现 503 / 401 / mock 字样
  - cookie `admin_access_token` + `admin_refresh_token` 都 HttpOnly + Path=/admin
- **期望审计**: `admin_login_attempts` 表新增 1 行 `success=true`, `failure_code=NULL`
- **S1.degraded** (cost_daily 空可接受场景): 若 1.2'/3' 还没真实 query 入库, KPI 显示 `--` 而不是 mock 数字, 接受为 GREEN; 但若显示 mock literal (如 "1234.56") 直接 RED, 走 §5 Step 6 调查 cost_daily 数据源
- **红时回滚**: 检查 (a) Render `/healthz` 是否 200 (b) `ADMIN_JWT_SECRET` 是否 ≥32 字节 (c) Vercel rewrite `/admin/*` → Render 是否生效 (DevTools Network panel 看 `/admin/api/v1/auth/login` 落到 onrender.com)

## S2 · 资源页 — 账号池水位

- **路径**: `/admin/pipeline/planner/resources/accounts`
- **操作**: 直接进入页面, 不操作
- **期望 UI**:
  - 三引擎列 (chatgpt / doubao / deepseek-CN), 每列显示 ACTIVE / COOLDOWN / FROZEN / BANNED 4 状态计数
  - **A1' 实测预期**: 1.2' 还没接, 三列全 0 — Frank 接受 0 作为 GREEN, 因为本 Session 只交付 Module B 资源页**界面**, 真实账号注入要等 1.2'
  - 表格行级 cookie / userToken 字段必显示 `***` (J4 mask_secret), 鼠标 hover 不展开
  - 不出现 "未实现" / "TODO" 字样
- **期望审计**: 仅 GET 操作, 无 audit 行 (Y9-Y12 是只读)
- **S2.degraded**: 1.2' 跑过后 Frank 重跑 S2, 此时 doubao 应有 ACTIVE ≥1, COOLDOWN 字段呈倒计时格式 (mm:ss). 当下 A1' 验收, 0 即绿
- **红时回滚**: 若页面 500 或 RBAC 401, 检查 (a) Render env `ADMIN_BASE_URL` 是否设 (b) `app/services/account_pool_admin.py` 是否走 `from app.accounts.pool` (J2 grep 拦截误手写实现)

## S3 · Module A · 冻结测试用户 + Audit 闭环

- **路径**: `/admin/users`
- **操作**:
  1. 列表里找到测试用户 (邮箱 `smoke-user@example.com` 或前置 SQL 注入的那行) → 点击行 → 抽屉打开
  2. 抽屉 "管理动作" 段 → 点 "冻结" 按钮 → 弹 ConfirmModal
  3. ConfirmModal 输入 `Reason = "test freeze"` + `Expires = (留空, 永久冻结)` → 提交
  4. 弹窗关闭, 1s 内列表行的 `is_frozen` 列变 ✓ (绿勾 → 红盾) + 抽屉 Moderation Action 历史段最上方新增一行 `freeze · ops@<...> · just now · test freeze`
  5. 新开标签页 `/admin/audit-log` (S5 用) 此时**先不查**, 留 S5 验
- **期望 UI**:
  - 列表行 `is_frozen` 状态标记由 ✗ 变 ✓ (派生于 `user_moderation_actions WHERE action='freeze' AND (expires_at IS NULL OR expires_at > NOW())`)
  - **users 表 `status` 列不变** (#30.H Path B Variant 2 — 决策强调状态走派生不走列)
  - 抽屉 Moderation Action 列表按 `created_at DESC` 排, freeze 行在最上
- **期望审计**: `admin_audit_log` (Session 3' 真实表 / A1' caplog 捕获 stub) 新增 1 行 `action='user.freeze'`, `target_id=<user_id>`, `actor_id=<super_admin_id>`, `metadata={reason: 'test freeze', expires_at: null}`
- **红时回滚**: 若行内 status 变 "frozen" (literal column update), 立刻回 §5 Step 3 检查 `app/admin/api/v1/users.py:freeze_user` 是否误 UPDATE users — J5 grep 已防御, 但 freeze 端点除外路径需手验

## S4 · Module C · 品牌建议 24h SLA + Approve

- **路径**: `/admin/kg/brand-submissions`
- **操作**:
  1. 进入页面 → 看 inbox 列表, 默认按 `sla_started_at ASC` 排 (越久越靠前)
  2. 找到 `brand_name_zh="花西子"` 那条 → `hours_since_submission` 列显示 ≥ 2h (前置时刻 -2h 注入)
  3. 点击行 → 抽屉打开, 显示 brand_name_zh / brand_name_en / aliases / 提交者 / SLA timer
  4. 点 "Approve" 按钮 → 弹 ConfirmModal → Reason 留空 (approve 是可选的) → 提交
  5. 1s 内列表里花西子状态由 `pending` → `approved`
- **期望 UI**:
  - 列表 `sla_overdue` 列对 sla_started_at > 24h 的行显示红色 24h 标志, 否则灰色 (本测试用例 2h, 灰色)
  - approve 后行高亮短暂闪烁 (visual ack), 状态列从 "pending" 标签变 "approved" 标签
  - **#30.J Option Z** — A1' 不交付 `/admin/kg/brands` 主表页, S4 不要求验证 "1s 内出现在 /admin/kg/brands" (那是 1.5' 的活); 接受 status 字段更新 + 抽屉关闭即绿
- **期望审计**: `admin_audit_log` 新增 1 行 `action='kg.submission.approve'`, `target_id=<submission_id>`, `metadata={reason: null}`
- **红时回滚**: 若 422, 检查 ApproveSubmissionRequest 是否在前端发了非法字段; 若 409, 检查行是否已被同事 race condition approve, 应换一条新 pending submission 重测

## S5 · Audit Log 导出 CSV 闭环

- **路径**: `/admin/audit-log`
- **操作**:
  1. 进入页面 → 列表显示 S1 (login) + S3 (user.freeze) + S4 (kg.submission.approve) 至少 3 行 — Frank **每条都要看见** (按 created_at DESC, 最近的在最上)
  2. 点 "导出 CSV" 按钮 → 浏览器下载 `audit-log-<YYYYMMDD-HHMMSS>.csv`
  3. 打开下载文件 (Excel 或 VS Code) → UTF-8 BOM 头 + 表头 (`id,actor_id,action,target_type,target_id,metadata,created_at`) + ≥3 数据行
  4. 回页面 **刷新**列表 → 应**多出 1 行** `action='audit.export.csv'`, `metadata={row_count: <N>, format: 'csv'}` (闭环验证, decision §5 Step 7 hard requirement)
- **期望 UI**:
  - CSV 下载完成后页面无错误 toast
  - 刷新后 audit list **N+1 行 (export 自身入 audit)**
  - rate limit: 1 分钟内连点 6 次导出, 第 6 次 429 (slowapi 5/min)
- **期望审计**: 导出本身入审计 (闭环) — 这是 S5 的核心验证点
- **红时回滚**: 若文件无 BOM (Excel 中文乱码), 检查 `csv` 模块 writer 是否经 `utf-8-sig` encoding 写; 若导出 N 行但 audit log 没 +1, 立回 §5 Step 7 修 `app/admin/api/v1/audit.py:export_csv` 闭环写入

## S6 · API Token 直调 (curl) + JSON 字段对应 PRD §1.1

- **路径**: 终端 / Postman / Insomnia
- **操作**:
  1. 在浏览器 DevTools Application → Cookies → 复制 `admin_access_token` 值 (HttpOnly cookie 必须开 DevTools 复制, 命令行 curl 拿不到)
  2. 终端 `curl -H "Cookie: admin_access_token=<value>" "https://<render-preview>.onrender.com/admin/api/v1/pipeline/dashboard"` (注意是 Render 直连 URL, 不走 Vercel rewrite, 因为 Vercel rewrite 不带 cookie 跨域)
  3. 看返回
- **期望 UI / JSON**:
  - HTTP 200
  - JSON 返回 (不是 `{"detail": "Not Found"}` / `{"detail": "Unauthorized"}`)
  - 字段对应 PRD §1.1 IA 描述: `total_queries_today` / `cost_today_usd` / `cost_today_cny` / `engines: [{id, healthy_count, cooldown_count, frozen_count}]`
  - 数字非 mock literal — Frank 用 SQL `SELECT COUNT(*) FROM query_executions WHERE date(created_at) = current_date;` 对一下应一致
- **期望审计**: API 调用本身**不入** audit (audit 只对写操作 + sensitive read 触发, dashboard 是普通 read)
- **红时回滚**:
  - 401 → access cookie 已过期 (15min), 重新走 S1 登录拿新 cookie
  - 503 → Render 服务 cold start, 等 30s 重试一次
  - 字段缺失 → 回 §5 Step 6 修 `app/admin/api/v1/pipeline.py:get_dashboard` 字段映射

## 验收闭环

- **6 步全绿** → A1' Phase Gate Layer 3 GREEN → 同步给 Frank → Frank 打 OK 后我写 CLAUDE.md 决策 #32 (A1' 交付 + 偏差登记) + (可选) `docs/auto-memory/{type}_{topic}.md` cross-Session pattern + push squash merge 到 main
- **任一 S 红** → 复制对应步骤的"红时回滚"段 + 当时浏览器 DevTools Console / Network 截图给我 → 回 §5 修 → 重跑该 S 步 + 后续步 (因为前置依赖)
- **Layer 1 红 / Layer 2 红 都不能进 Layer 3** — 接受标准是逐层往上 (规则 7 一致性回路)

## 决策引用

- 决策 #29.C — preview env + 浏览器联动 + 点击产物 (横切要求, 本清单是兑现)
- 决策 #30.H — Path B Variant 2 (Y3 / Y5 写 moderation_actions / deletion_requested_at, 不动 users.status)
- 决策 #30.J — Option Z (Module C admin 侧 3 表 endpoints, 不含 KG 主表)
- 决策 #28.G C3 — NO SCHEMA DEFAULT (S1 不会因 admin_password_resets.purpose default 路径漂移)
- ADMIN_PRD §4.1 / §4.3 / §4.4 — 6 步操作的 endpoint 真相源
- `feedback_genpano_session_preview_env_2026_04_26.md` — Frank 不接受截图替代实操
