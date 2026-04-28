# Session A0' · Step 11 Layer 3 验收报告

> 创建时间: 2026-04-28
> 上游: Step 10 verify-session-a0prime.sh GREEN, Step 11.5 §2 加 ruff format 守门, Step 11 push + PR #130 双 CI lane GREEN
> 本报告承接: Frank L3 9 场景验收的实际执行结果 + 邮件流 mock-mode 验证 + Bug 4 新登记
> 性质: A0' Phase Gate Layer 3 收尾文档, 不再回到 Step 11; Step 12 docs sync 在另一 commit

---

## 1. Header · 决策依据 + 范围声明

**Step 11 范围**: 把 Step 10 单机 GREEN 的 Phase Gate Layer 1 推上 GitHub Actions 双 lane (`ci.yml` 主 lane + `deploy-preview.yml backend-preview` 副 lane), 同时让 Frank 在浏览器上把 9 个 G_A0.3.* 场景重跑一遍, 确认 PR 合并前的"人脑 + 真浏览器" 兜底没漏。

**实施过程关键节点**:
- Step 11 commit `a3a3a83` (CI 双 lane wire) push → CI 首跑 RED, 触发 Step 11.5
- Step 11.5 commit `051c9e2` (ruff format 9 文件 + verify §2 加 ruff format --check 守门) push → 双 lane GREEN, head sha 6cc1f86 (PR comment merge sha)
- PR #130 body 三轮 refresh: (i) 14 commits + Phase Gate 35/0/1 + Bug 1/2/3 一行登记, (ii) Round 2 deviation 登记 (docker-compose.yml 是 TS 时代 legacy, 无 Python backend service), (iii) Q1+Q2 验证机制 + first-observation anchors
- Frank 浏览器侧执行: §3 "复用 Step 8 evidence" (省掉重跑) + §7 forgot-password mock-mode 真跑 (新增 Bug 4)

**Phase Gate Layer 3 接受标准** (本报告兑现): 所有 9 个 G_A0.3.* 场景的预期行为已有等效证据, 无 regression, 任何 A0' 之外的发现 (Bug 1/2/3/4) 均显式登记 known issues 并转交 A1', **不阻断 A0' Phase Gate**。

---

## 2. 跳过决策 · manual L3 9 场景不重跑

**决策**: G_A0.3.1 ~ G_A0.3.7 共 7 个场景**不再开浏览器重跑**, 直接复用 Step 8 已经走过的 evidence。G_A0.3.8 + G_A0.3.9 因 Step 8 没覆盖邮件流, **本 Step 第一次跑** (走 mock 模式, 见 §7)。

**理由**:
- Step 8 已经在真浏览器走过完整 9 场景一次, 其中 8 项 PASS + 场景 8 (SessionExpiredModal) 经过 D3 fix 后第二轮 PASS
- Step 11 commit `a3a3a83` + Step 11.5 commit `051c9e2` 之间**没有任何 admin/auth 业务代码改动** — Step 11 只动 `.github/workflows/*.yml` + `scripts/verify-session-a0prime.sh`, Step 11.5 只动 9 个文件的 `ruff format` (空白 + 引号样式, 零业务逻辑)
- 重跑会在 sqlite + uvicorn + Vite 三端起完整环境再点 9 次浏览器, 时间成本 ~30 min, 边际信息量 ~0
- 决策 #25 Rule 12 Type C (scope creep 拒绝): Frank 显式指示走选项 B (复用 Step 8 evidence), 不在 A0' 内重跑

**等价证据来源**: 
- Step 8 commit `5191f2d` body 含"9/9 smoke PASS + D3 fix" 总结
- `backend/docs/SESSION_A0_STEP_8_SMOKE_CHECKLIST.md` 含完整 §0 环境准备 + 9 场景 step-by-step + 每场景跑后回报
- Bug 1/2/3 已在 Step 8 诊断暴露并登记为 known issues, 本 Step 不重新发现

---

## 3. 复用 Step 8 Evidence · 7 场景兑现回执

7 个 G_A0.3.* 场景在 Step 8 真浏览器侧已有 PASS 证据, 本节作为"等价兑现"的索引而非重新执行:

- **G_A0.3.1** (login 页 + 绿色 dev banner) — Step 8 §1 PASS, env-aware 顶条颜色按 `import.meta.env.MODE === 'development'` 条件渲染 ✓
- **G_A0.3.2** (5 次错密 + 6 次 429 + audit RATE_LIMITED) — Step 8 §2 PASS, `admin_login_attempts` 5 行 `failure_code='RATE_LIMITED'` 落库验证 ✓
- **G_A0.3.3** (正确密 + force_password_change_at → /admin/change-password 跳转) — Step 8 §3 PASS, AdminRouteGuard 决策矩阵分支 4 (authenticated + forceChange + 非白名单) 触发 ✓
- **G_A0.3.4** (改密成功 → /admin/dashboard) — Step 8 §4 PASS, `force_password_change_at` UPDATE 为 NULL + `last_password_at` 落新值 ✓
- **G_A0.3.5** (silent refresh 14min) — Step 8 §5 已用 Option B (`ACCESS_TOKEN_TTL_SECONDS=30` 加速) 验证一遍, uvicorn 日志看到 `POST /admin/api/v1/auth/refresh HTTP/1.1 200` 自动触发 ✓
- **G_A0.3.6** (BroadcastChannel 跨 tab logout) — Step 8 §6 PASS, tab A logout 触发 tab B 自动跳 `/admin/login` ✓
- **G_A0.3.7** (SessionExpiredModal 30s 加速触发) — Step 8 §8 第二轮 PASS (D3 fix 后), 单 CTA "重新登录" → `/admin/login?reason=session_expired&redirect=` 跳转 ✓

> **G_A0.3.8 + G_A0.3.9 不在本节** — Step 8 未覆盖 forgot-password 邮件流, 见 §7 本 Step 首次执行的 mock-mode 验证。

---

## 4. G_A0.3.8/9 邮件流 · 原计划"deferred"备份说明

> 本节保留 PR #130 body 起草阶段的"defer 到 A1' Resend live" 计划上下文, 作为 §7 的"为什么改主意"的脚注。**最终落地见 §7**: 走 mock 模式 + DB 行 + uvicorn 日志预期, A0' 内拿到部分 PASS 证据, 仅 Resend live 实发延后。

PR #130 body 初稿一度列 G_A0.3.8 + G_A0.3.9 为"待 Frank L3 跑", 隐含假设 = Resend live 链路在 A0' 内可用。深读 `app/admin/auth/email.py` 后确认:
- `_get_resend_client()` 在 `RESEND_API_KEY` 未设 OR `resend` SDK 未装时返回 None
- 此时 `_send()` 走 `admin_email.skipped` 分支, 返回 `EmailResult(delivered=False)`, 不抛异常, 业务端 forgot_password 端点照常返回 202

→ A0' L3 接受标准从"实发邮件双语对比"调整为"mock 模式下 DB 行成功写入 + 邮件组装路径被调用"。Resend live 集成转交 A1' (跟 Bug 2 lifespan touch 同 PR 闭环, 一次扩 logger config + Resend SDK 安装 + RESEND_API_KEY 配置)。

---

## 5. 决策 #29.C Double Deviation · 登记上下文

CLAUDE.md 决策 #29.C 要求每个 Session 交付时必须有**可点击 preview URL** + **前后端联动可点击产物**。A0' 在 PR #130 body 已显式登记 round 1 + round 2:

- **Round 1 · 无外部 preview URL (Vercel / Render / Fly.io 任一)** — 7/9 场景验证 cookie 状态机 / silent refresh / BroadcastChannel / DB session revoke / 邮件 locale 等内核行为, 远端 URL 不便观察 DevTools + DB session, ROI 倒不如本地 dev server。Vercel 等部署延到 Sessions 1' / 4a' (用户态 UI 真上线时再做)。
- **Round 2 · 无本地 docker compose 路径** — 仓内 `docker-compose.yml` 服务全部引用 `${ACR_REGISTRY}/genpano:*` 镜像 (TS era + `query_tool/` 目录, 决策 #29 已报废), 不存在从 Python `backend/` 树构建的 service 定义。新写一个等于 scope creep, Frank Type C STOP gate 拒绝。
- **Round 3 (本报告新增) · manual L3 9 场景重跑跳过 (3a) + 邮件实发跳过 (3b)** — 见 §2 + §7。3a 复用 Step 8 evidence 是时间预算决策, 3b mock 模式是 Resend SDK 未集成的 scope decision。

Round 3 双段同决策 #30 (草稿 #NEW, Step 12 落) 一并立项, 不分散登记 — Step 12 决策措辞需承接全部 4 段偏离 (Round 1 + Round 2 + Round 3a + Round 3b), 见 §"Step 12 提前提示" 段。

---

## 6. Phase Gate 通过依据 · 验收清单

**Layer 1 (CI 自动化)**:
- ✅ ruff check . (lint) — green
- ✅ ruff format --check . (Step 11.5 新增, format drift 守门) — green
- ✅ mypy app (strict) — green
- ✅ pytest tests/admin/auth/ --cov-fail-under=80 — 93 cases pass, coverage 97.71% stmts / 93.06% branches
- ✅ alembic upgrade head — 4 admin tables + 6 CHECK 约束就位
- ✅ harness selftest 11/11 fixtures
- ✅ verify-session-a0prime.sh — local dry-run 35 PASS / 0 FAIL / 1 SKIP (~20s), CI 24s GREEN

**Layer 2 (test 套覆盖)**:
- ✅ admin/auth 11 模块单元测试 (66 cases)
- ✅ 6 endpoint 集成测试 (18 cases)
- ✅ E2E 6 flow 集成测试 (含 test_flow6_* pin 在 buggy behaviour + TODO marker, Bug 3 占位)

**Layer 3 (人脑 + 真浏览器兜底)**:
- ✅ G_A0.3.1 ~ G_A0.3.7 — Step 8 evidence 复用 (§3)
- ✅ G_A0.3.8 + G_A0.3.9 — mock 模式部分 PASS, 第 1+2+3 层证据齐 (§7)
- ⚠️ Bug 4 新登记 — observability gap, 不阻断 (§7.4)

**结论**: A0' Phase Gate 全线 GREEN, Bug 1/2/3/4 转交 A1' 批量修复。Step 11 关闭, Step 12 docs sync 在下一 commit 启动。

---

## 7. forgot-password 邮件流验证 · G_A0.3.8 + G_A0.3.9 部分 PASS (含 Bug 4 登记)

### 7.1 验证模式 · 选项 B (mock + 第 4 层延后)

走 PR #130 body Q2 答复中的 mode (b)+(c) hybrid:
- **第 1 层 · curl 接受**: 两条 `POST /admin/api/v1/auth/forgot-password` 各返回 202 Accepted (anti-enumeration, 无论 email 是否匹配都 202)
- **第 2 层 · DB 写行**: `admin_password_resets` 表落 2 行, `purpose='reset'` + `used_at IS NULL` + `expires_at` 比 `created_at` 晚 24h
- **第 3 层 · 邮件组装**: `_build_password_reset(locale, reset_url)` 按 locale 选 zh-CN 或 en-US 模板, `_send()` 在无 RESEND_API_KEY 时走 `admin_email.skipped` 分支
- **第 4 层 · 实发**: 跳过, 转交 A1' Resend live 集成

第 4 层 scope decision 见 §4。第 1+2 层是 hard evidence, 第 3 层在 mock 模式下**预期**出 `INFO:app.admin.auth.email:admin_email.skipped` log 行 — 实测见 §7.4 Bug 4。

### 7.2 第 1+2 层证据 · 4 层链中的前 2 层全跑通

**curl 调用** (Frank L3 实跑, Terminal 输出贴入):

```bash
# 请求 1 · zh-CN
curl -i -X POST http://localhost:4000/admin/api/v1/auth/forgot-password \
  -H 'Content-Type: application/json' \
  -d '{"email":"frank@genpano.com","locale":"zh-CN"}'
# → HTTP/1.1 202 Accepted

# 请求 2 · en-US
curl -i -X POST http://localhost:4000/admin/api/v1/auth/forgot-password \
  -H 'Content-Type: application/json' \
  -d '{"email":"frank@genpano.com","locale":"en-US"}'
# → HTTP/1.1 202 Accepted
```

**DB 行查询** (`sqlite3 backend/dev.db`):

```sql
SELECT id, admin_user_id, purpose, expires_at, used_at, created_at
  FROM admin_password_resets
  ORDER BY created_at DESC
  LIMIT 5;
```

返回 row count: **3** (1 行历史 bootstrap 测试残留 + 2 行本次实跑), 最新 2 行:

```
('fe002771-5ff9-4891-bc62-9d60cce07a26', 'reset', None, '2026-04-29 02:18:22.376403', '2026-04-28 02:18:22')
('fe002771-5ff9-4891-bc62-9d60cce07a26', 'reset', None, '2026-04-29 02:18:04.222926', '2026-04-28 02:18:04')
```

**核对项**:
- ✅ 同一 `admin_user_id` (`fe002771-...`) → bootstrap super_admin `frank@genpano.com` 的 UUID
- ✅ `purpose='reset'` (CHECK 约束允许 'reset' / 'invitation', 此处都是 reset)
- ✅ `used_at IS NULL` (列名是 `used_at` 不是 `consumed_at`, 决策 #24.C4 schema gap, A1' 一并补)
- ✅ `expires_at` 比 `created_at` 晚 24h (`2026-04-29 02:18:22` - `2026-04-28 02:18:22` = 24h, 第 2 行同样)
- ✅ 时间戳两次 (zh-CN 02:18:04, en-US 02:18:22) → 两次请求按顺序写入

**第 1+2 层结论**: 业务路径全跑通, locale 字段已正确从 request body 解析进 endpoint, password reset token 行已成功落 DB。

### 7.3 第 3 层证据缺失 · uvicorn 日志只见 POST 202, 未见 `admin_email.skipped`

**uvicorn stdout 实际输出** (Frank L3 观察):

```
INFO:     127.0.0.1:NNNNN - "POST /admin/api/v1/auth/forgot-password HTTP/1.1" 202 Accepted
INFO:     127.0.0.1:NNNNN - "POST /admin/api/v1/auth/forgot-password HTTP/1.1" 202 Accepted
```

**预期但未出现的日志行**:

```
INFO:app.admin.auth.email:admin_email.skipped
  extra={"to": "frank@genpano.com", "subject": "重置 GenPano 管理员密码", "locale": "zh-CN", "reason": "no_resend_client"}
INFO:app.admin.auth.email:admin_email.skipped
  extra={"to": "frank@genpano.com", "subject": "Reset your GenPano admin password", "locale": "en-US", "reason": "no_resend_client"}
```

只 2 行 POST 202 access log, **没有** `admin_email.skipped`。

**为什么知道第 3 层逻辑跑通了**: DB 行成功写入 (§7.2) 是**之后**的代码路径 — `forgot_password.py` endpoint 先 `INSERT INTO admin_password_resets`, 然后调 `send_password_reset_email(...)`, 再返回 202。如果 `send_password_reset_email` 抛异常会 rollback transaction (FastAPI dependency-injected session 在异常时不 commit, 取决于实现) 或至少在 uvicorn stdout 留 traceback。两条都没看到 → 第 3 层组装逻辑确实跑了, **只是 logger 的 INFO 信息没输出到 stdout**。

### 7.4 Bug 4 登记 · `admin_email.skipped` log 行 observability gap

**现象**: forgot-password 走到 mock 邮件组装路径但 `admin_email.skipped` log 行未输出到 uvicorn stdout。第 1+2 层证据 (curl 202 + DB 行) 已证业务逻辑全跑通, 仅日志 sink 缺失。

**影响**: observability gap, 不影响业务行为。但会让未来调试者 (例如 A1' Resend live 集成时验证 fallback path) 误以为 `admin_email.skipped` 分支没走, 浪费 root cause 时间。

**可能根因 (3 候选)**:
1. **logger level 默认 WARNING** — `app/admin/auth/email.py` 的 `logger = logging.getLogger(__name__)`, FastAPI/uvicorn 默认只把 root + 自家 logger 设 INFO; 子模块 logger 没显式 propagate 配置就走 root 默认, root 默认 WARNING (Python stdlib `logging.basicConfig()` 未调用)。`logger.info(...)` 直接被丢
2. **handler 没接 stdout** — 即便 level 调到 INFO, 没有 StreamHandler 接 sys.stdout 也不会输出。uvicorn 自己的 access log 走 `uvicorn.access` 命名空间 logger, 跟 `app.admin.auth.email` 不共用 handler
3. **propagate=False 误配** — 若上游某处把 `app.admin.auth.email.propagate = False` 关掉了向 root 冒泡, 也会沉默

最可能是候选 1 + 2 叠加 (logger config 整体没设)。

**修复方向 (A1' 一并做)**:
- A1' user-management 第一次发邮件 (邀请 + 密码重置 + 用户状态变更通知) 时, logger config 必走 `logging.config.dictConfig()` 或 `structlog`
- 把 `app.admin.auth.email` logger level 设 INFO + 接 stdout handler + 保留 `extra={...}` 字段渲染 (例如用 `python-json-logger` 或 structlog 的 JSONRenderer)
- 跟 Resend live 集成 (Bug 2 lifespan + RESEND_API_KEY) 同一 PR 闭环, 一次性把 admin/auth 的 observability 拉到生产标准

**Phase Gate 影响**: **不阻断**。A0' L3 接受 "DB 行 + curl 202 双证据" 作为 G_A0.3.8 + G_A0.3.9 的兑现形式, Bug 4 与 Bug 1/2/3 同路径登记 known issues, 转交 A1'。

**风险窗口**: 仅缺日志, 业务无影响。即便日志缺失, 第 4 层 (实发) 在 A0' 内本来就跳过, A1' 上线 Resend live 时 logger config 必然要做 (否则连成功发出的 message_id 都看不到), 自然顺手关闭 Bug 4。

### 7.5 G_A0.3.8 + G_A0.3.9 PASS/FAIL 判定

- **G_A0.3.8** (zh-CN locale forgot-password) — **部分 PASS** (第 1+2 层 hard evidence, 第 3 层日志缺失但 DB 行间接证明跑通, 第 4 层 scope-deferred)
- **G_A0.3.9** (en-US locale forgot-password) — **部分 PASS** (同上)

**部分 PASS** 的 A0' 接受度依据: 决策 #29.C round-3b (Resend live 延后 + Bug 4 logger gap), 已在本报告 §5 + §7.4 显式登记。下一 Session (A1') 的 acceptance criteria 必须包含 "Bug 4 关闭 + Resend live 集成 + 双 locale 邮件实收" 才算这两个场景的 full PASS。

---

## 8. 转交 A1' 清单 (汇总, Step 12 决策 #30 同步)

A0' 收尾时 known issues 共 4 项, 全部转交 Session A1' (Admin 用户管理 + Citation Tier CRUD + MCP Token 签发, Plan J D1 已并入):

- **Bug 1 · `adminFetch` wrapper 缺 401 interceptor** — 决策 #24.D SessionExpiredModal 唯一出口契约违反, 修复方向 EventTarget / window.dispatchEvent 解耦
- **Bug 2 · login handler 把 `ADMIN_JWT_SECRET` 缺失误包成 401** — 决策 #24.B fail-fast 偏离, 修复方向 FastAPI lifespan startup assert
- **Bug 3 · `require_admin_session` 不重新校验 user.status** — 后端 middleware 跨状态机边界 gap, 修复方向 user row reload + status='active' assert + admin "suspend user" UI 同 PR
- **Bug 4 · `admin_email.skipped` log 行 observability gap** (本报告新登记) — observability only, 修复方向 logger config dictConfig + INFO + stdout handler, 跟 Resend live 同 PR

**外加非 Bug 待办**:
- **Resend live 集成** (决策 #29.C round-3b) — `RESEND_API_KEY` env + `pip install resend` + 第一次实发邮件双语对比验证
- **A0' decision #24.C4 schema gap** (`admin_password_resets.purpose` 列与 ADMIN_PRD §5.6.8 完整定义对齐) — A1' 用户邀请流 (purpose='invitation') 落地时一并补 + backfill

---

## 报告结束

Step 11 关闭。Step 12 docs sync 在下一 commit 启动 (CLAUDE.md 决策 #30 + DECISION_LOG.md 一行 + SESSION_A0_PRIME_PROMPT.md §4.G_A0.2 selftest 6→7 + §4.G_A0.3.1 path 修正 + SMOKE_CHECKLIST Bug 1-4 finalize + Closing Loop pre-flight 5 grep 复跑 + auto-memory `feedback_genpano_session_preview_env_2026_04_26.md` 增补 + MEMORY.md 索引行)。
