# Session A0' · Step 8 Browser Smoke Checklist (9 场景)

> Frank 在 Windows 浏览器 (Chrome / Edge 任一) 亲跑, 现象记到本文件 §"跑后回报",
> CC 整合进 Step 8 commit body 后才 commit。**不点头不写历史**。
>
> 本 Checklist 验证目标: 前端 (jotamotk 仓 frontend/src/admin/) 与 Step 7 收敛后
> 的 Python wire format (camelCase forcePasswordChangeAt / accessExpiresAt /
> Set-Cookie HttpOnly+SameSite=strict+Path=/admin) 整合握手. AdminRouteGuard 决策矩阵
> + SessionExpiredModal 唯一出口契约 + AdminAuthContext 4 状态机 + BroadcastChannel
> 跨 tab 同步全部走真人浏览器路径过一遍, 把任何残留的 snake_case 假设 / 时态漂移 /
> 决策矩阵分支错位暴露出来。

---

## 0. 环境准备

### 0.1 Terminal A · uvicorn (backend)

```bash
cd C:/Users/frank.wang/genpano/backend
ADMIN_JWT_SECRET='test-secret-32-bytes-minimum-len-ok' \
  .venv/Scripts/uvicorn.exe app.main:app --reload --port 4000
```

确认: `http://127.0.0.1:4000/healthz` 返回 `{"status":"ok"}`。

### 0.2 Terminal B · Vite dev (frontend)

```bash
cd C:/Users/frank.wang/genpano/frontend
npm run dev
```

确认 console 提示 `Local: http://localhost:5173/`。

### 0.3 Seed super_admin

```bash
cd C:/Users/frank.wang/genpano/backend
ADMIN_BOOTSTRAP_EMAIL=frank@genpano.com \
ADMIN_BOOTSTRAP_PASSWORD='SmokeTestPwd_2026!' \
  .venv/Scripts/python.exe scripts/admin-bootstrap.py
```

期望输出: `OK: super_admin 'frank@genpano.com' seeded (force_password_change_at set; first login must rotate)`。

> 重跑此命令需先 `DELETE FROM admin_users` (sqlite3 dev.db), 否则会得 `(no-op)` 提示 — bootstrap 是幂等的。

### 0.4 浏览器 + DevTools

- 浏览器: Chrome / Edge 任一
- 起点 URL: `http://localhost:5173/admin/login`
- DevTools: F12
  - **Network** tab (preserve log 勾上)
  - **Console** tab (warnings/errors 过滤都开)
  - **Application** tab → Storage → Cookies → `http://localhost:5173`
    - 关注 `admin_access_token` + `admin_refresh_token`
    - 三件套: HttpOnly ✓ / SameSite=Strict ✓ / Path=/admin ✓

### 0.5 Vite dev proxy 检查

`frontend/vite.config.js` 必须把 `/admin/api/*` 反代到 `http://localhost:4000` 才能保 cookie 的 `Path=/admin` 作用域。若浏览器 Console 看到 CORS / 404 / `localhost:5173/admin/api/v1/auth/login` 直接打到 Vite 而非后端, **场景 1 之前停下检查 vite proxy 配置**。

---

## 跑场景规则

- 严格按场景 1 → 9 顺序跑, 不跳序
- 每个场景跑完立刻在 §"跑后回报" 表格填 PASS / FAIL + 现象
- 任一 FAIL 立刻停下 + 抓 DevTools Network 一条 (status / response body / Set-Cookie 三段) + Console 一段, **不要继续往后跑** (前置失败的场景会污染后续场景的状态前提)

---

## 场景 1 · login 成功

**触发动作**:
1. 起点 `http://localhost:5173/admin/login`
2. 表单输入 `frank@genpano.com` / `SmokeTestPwd_2026!`
3. 点 "登录"

**期望现象**:
- HTTP: Network 抓到 `POST /admin/api/v1/auth/login` 200
- Response body 含 4 个 camelCase key: `forcePasswordChangeAt` (非 null, ISO 时间戳) + `lastPasswordAt` + `lastLoginAt` + `accessExpiresAt`
- Set-Cookie 三件套: `admin_access_token` + `admin_refresh_token` 都带 `HttpOnly; Path=/admin; SameSite=Strict`
- UI: **不卡白屏**, **不停在 login page**, 因 `forcePasswordChangeAt` 非 null, AdminRouteGuard 决策跳到 `/admin/change-password`
- Console: 无 `KeyError` / `undefined` / React error boundary trigger

**失败信号 (任一即停)**:
- Response 含 snake_case `force_password_change_at` 等 (Step 7 alias 没生效)
- UI 停在 `/admin/login` 不动 (AdminAuthContext setStatus 没切 'authenticated')
- UI 跳 `/admin/dashboard` 而不是 `/admin/change-password` (RouteGuard 没读 `forcePasswordChangeAt`, D1 偏离影响真实)
- Console `Cannot read properties of undefined (reading 'forcePasswordChangeAt')` (frontend 读 user 对象时键名错)

---

## 场景 2 · forcePasswordChangeAt 触发跳转 (RouteGuard 决策矩阵 b 分支)

**触发动作**:
- 场景 1 跳到 `/admin/change-password` 后, **不要改密**, 在 URL bar 手动跳 `http://localhost:5173/admin/dashboard`

**期望现象**:
- AdminRouteGuard.jsx lines 73-74 `if (status === 'authenticated' && forceChange && !onChangePasswordPage) → navigate('/admin/change-password', { replace: true })` 触发
- URL 立即弹回 `/admin/change-password` (replace, 不留 history)
- UI 不闪 dashboard 内容

**失败信号 (任一即停)**:
- 浏览器停在 `/admin/dashboard` (RouteGuard force-change 分支没生效)
- URL 历史里有 `/admin/dashboard` (用了 push 不是 replace)
- 闪一下 dashboard 内容再跳走 (Placeholder 兜底失效, line 80-82 `return <Placeholder />`)

---

## 场景 3 · 改密成功

**触发动作**:
1. 在 `/admin/change-password` 表单输入:
   - 当前密码: `SmokeTestPwd_2026!`
   - 新密码: `NewPwd_StrongChange_2026!` (≥12 字符 + zxcvbn ≥3)
   - 确认新密码: 同上
2. 提交

**期望现象**:
- HTTP: `POST /admin/api/v1/auth/change-password` 200
- Response: `forcePasswordChangeAt` = `null`
- Set-Cookie: 一对**新**的 `admin_access_token` + `admin_refresh_token` (cookie value 与场景 1 不同)
- 前端: `forcePasswordChangeAt` 既然 null, RouteGuard 不再回弹, navigate 到 `/admin/dashboard`
- 看到 Dashboard 内容 (即使是 stub 也算 PASS, Step 8 不验 Dashboard 业务)

**失败信号 (任一即停)**:
- Response 仍然 `forcePasswordChangeAt` 非 null (后端 commit 漏写 None)
- 跳回 `/admin/login` (后端误把 change-password 当登出处理)
- HTTP 200 但 UI 卡 change-password 页 (前端没消费 forcePasswordChangeAt 清空状态)

---

## 场景 4 · 重登验证 (forcePasswordChangeAt 清空持久化)

**触发动作**:
1. 在 dashboard 点 logout (UserMenu / 顶栏退出按钮 — jotamotk 仓 AdminAuthShell 提供; 若没有可手动跑 `await fetch('/admin/api/v1/auth/logout', {method:'POST', credentials:'include'})` from console)
2. 跳到 `/admin/login` 后, 用新密码 `NewPwd_StrongChange_2026!` 重登

**期望现象**:
- HTTP: `POST /admin/api/v1/auth/login` 200
- Response: `forcePasswordChangeAt` = `null` (改密后第二次登录, 字段已清, AdminRouteGuard 决策走 d 分支 `authenticated + OK`)
- UI: **直接进 `/admin/dashboard`**, 不绕 `/admin/change-password`

**失败信号 (任一即停)**:
- Response 仍非 null (backend `force_password_change_at` 列没 UPDATE 干净)
- UI 又跳 change-password (RouteGuard 误判)

---

## 场景 5 · silent refresh 静默续约

**触发动作 (两选一)**:
- **选项 A · 真等 14min**: 登录后停在 dashboard 不操作, 等 ≥14min, 看 Network 是否有自动 `POST /admin/api/v1/auth/refresh`
- **选项 B · 加速验证 (推荐)**: 临时改 `frontend/src/admin/context/AdminAuthContext.jsx` line 41 `const ACCESS_TOKEN_TTL_SECONDS = 15 * 60;` 为 `30` (30 秒), 重启 Vite, 登录后等 ~30 秒看 refresh 是否自动触发. **验证完务必改回 `15 * 60` + 重启 Vite, 再跑场景 6+**

**期望现象 (两个选项通用)**:
- 用户无任何操作, Network 自动出现 `POST /admin/api/v1/auth/refresh` 200
- Response body: 新的 `accessExpiresAt` 戳
- Set-Cookie: 一对新 cookie 值 (rotation), 旧 refresh token 在 backend `admin_sessions` 表标 `revoked_at` (这个看不到 UI 现象, 但 Network response 200 即证明 backend 接受了 rotation)
- UI: **完全无感**, 用户停在 dashboard 不被打扰
- Console: 不出现 `[admin-auth] silent refresh failed (network?)` 警告

**失败信号 (任一即停)**:
- 没看到自动 `POST /refresh` 请求 (setTimeout 没起, line 83-86 出问题)
- Refresh 请求 401 (refresh token cookie 没带过去 — 检查 cookie Path=/admin 是否生效, vite proxy 是否保 cookie)
- 用户被踢登出 (refresh 失败 → setStatus('expired') → 看到 SessionExpiredModal)
- Console 警告: `silent refresh failed`

> 加速验证完成后**必须**把 line 41 改回 `15 * 60`, 否则后续场景的 token TTL 不准。

---

## 场景 6 · BroadcastChannel 跨 tab 同步

**触发动作**:
1. Tab A: `http://localhost:5173/admin/dashboard` (从场景 4 状态延续)
2. 复制当前 URL, 在 **新 Tab B** 打开同样 URL — 应该已登录直接进 dashboard (cookie 共享)
3. 在 Tab A 点 logout

**期望现象**:
- Tab A: navigate `/admin/login`, cookie 清空
- **Tab B: 5 秒内自动跳 `/admin/login`** (`AdminAuthContext.jsx` BroadcastChannel listener line 174-176 收到 logout 消息 → `setStatus('anonymous')` → AdminRouteGuard navigate)
- Tab B 不应继续显示 dashboard 数据 (即使没刷新)

**失败信号 (任一即停)**:
- Tab B 仍然停在 dashboard, 直到刷新才跳 (BroadcastChannel listener 失活 / channel name 错)
- Tab A 跳 login 后, Tab B 显示 modal "session expired" 而不是直接跳 login (logout 消息被误识别为 expire)

---

## 场景 7 · manual logout (UserMenu)

**触发动作**:
1. 重新登录 (Tab A 用新密码)
2. 找 UserMenu (jotamotk 仓 AdminAuthShell 顶栏右上角) → 点 logout

**期望现象 (6 步契约, 决策 #21.D D2)**:
- (1) Network: `POST /admin/api/v1/auth/logout` 200
- (2) Set-Cookie: 两个 cookie 都 `Max-Age=0` (clearAuthCookies 生效)
- (3) Application → Cookies: `admin_access_token` + `admin_refresh_token` 都消失
- (4) AdminAuthContext: status 切 `anonymous` (DevTools React Devtools 可看 Provider state)
- (5) URL navigate `/admin/login`
- (6) BroadcastChannel: 跨 tab 已在场景 6 验证, 本场景不重复

> 注: jotamotk 仓的 mixpanel.reset 调用 (决策 #21.D D2) 是 TS 时代 user-side 埋点, Admin 侧 MVP 没接入; 若 console 没 mixpanel-related 报错即 PASS。

**失败信号 (任一即停)**:
- HTTP 200 但 cookie 没清 (后端 logout 路径漏 clearAuthCookies)
- HTTP 200 + cookie 清 但 UI 不动 (前端 logout handler 漏 navigate)
- Console mixpanel 错误 (本场景免责, 但记录现象)

---

## 场景 8 · SessionExpiredModal 触发

> **诊断 2026-04-27 (Step 8 实施过程产物 — 替换原触发法)**: 之前的"删 access cookie + 手动 fetch"触发法**不会进** expired 分支。
> AdminAuthContext `setStatus('expired')` 只在两条路径触发:
>   - **(1) silentRefresh callback 通过 setTimeout 自动 tick + 拿到 401** (catch 块, lines 118-119)
>   - **(2) BroadcastChannel 收到来自其他 tab 的 'expire' 消息** (lines 199-200)
>
> **Known gotcha (绕开 expired 的常见误触发, 不要这么做)**:
>   - DevTools Console 手动 `fetch('/refresh')` 是裸 fetch, **不走** silentRefresh callback, state 完全不动
>   - 页面 F5 / 任何导航 → 触发 AdminAuthContext mount probe (lines 217-229) → 401 → 设 `'anonymous'` (不是 `'expired'`); 这是**故意设计**: 冷启动 401 走 anonymous 直跳登录, modal 只伺候"用户活跃中途 session 死亡"
>   - 只删 `admin_access_token` 一个 cookie, 保留 `admin_refresh_token` → silent refresh 仍能用 refresh cookie 续上, 不进 catch
>
> **正确触发: 必须走后台 setTimeout tick 才能命中 catch 块。**

**触发动作 (两选一)**:

### 路径 (a) · 单 tab 加速验证 (推荐)

1. 临时改 `frontend/src/admin/context/AdminAuthContext.jsx` lines 45-46:
   ```diff
   - const SILENT_REFRESH_INTERVAL_MS =
   -   (ACCESS_TOKEN_TTL_SECONDS - SILENT_REFRESH_LEAD_SECONDS) * 1000;
   + const SILENT_REFRESH_INTERVAL_MS = 30000;  // 30s 临时, 测完务必改回
   ```
2. **重启 Vite** (Ctrl-C 后 `npm run dev`; HMR 对 module-level const 不一定切干净)
3. 浏览器登录 (用 `NewPwd_StrongChange_2026!`), 停在 `/admin/dashboard`
4. ⚠️ **不要 F5 / 不要点任何菜单 / 不要在 Console 里手动跑 fetch** — 任一动作都会绕开 expired 进 anonymous 或不动 state
5. 在终端跑 SQL 撤所有 active session:
   ```bash
   sqlite3 backend/dev.db \
     "UPDATE admin_sessions SET revoked_at = datetime('now') WHERE revoked_at IS NULL"
   ```
   (期望返回 `revoked N` 且 N ≥ 1)
6. ⚠️ **手不要碰键盘鼠标**, 浏览器枯坐 **~30 秒**
7. 等 Network 里自动出现 `POST /admin/api/v1/auth/refresh` 401 (后台 tick 触发)
8. 看 modal 是否弹出 + 验契约

### 路径 (b) · 双 tab BroadcastChannel 验证 (兜底)

1. Tab A: 已登录在 `/admin/dashboard` (路径 a 的 30s 间隔仍开着)
2. 新 Tab B 打开同 URL `http://localhost:5173/admin/dashboard` (cookie 共享, 直接进 dashboard)
3. SQL 撤 session (同上 step 5)
4. **任一 tab** 等 30s tick 自动触发 → 那个 tab 进 expired → 通过 BroadcastChannel 广播 `'expire'`
5. **另一个 tab** 应在收到 broadcast 后立即弹 modal (lines 196-201 处理 expire 消息)

**期望现象 (两路径通用)**:
- `setStatus('expired')` + `setSessionExpired(true)` 触发
- UI: SessionExpiredModal 出现, **覆盖** dashboard (overlay, 不替换路由)
- Modal 契约 (决策 #24.D):
  - **无** X / close 按钮
  - **无** ESC 关闭
  - **无** backdrop click 关闭
  - **唯一 CTA**: "重新登录"
- 点 "重新登录" → navigate `/admin/login?reason=session_expired&redirect=<原 URL>`

**测后清理 (强制)**:
1. 改回 lines 45-46 原公式 `(ACCESS_TOKEN_TTL_SECONDS - SILENT_REFRESH_LEAD_SECONDS) * 1000`
2. 重启 Vite
3. session 已撤, 用 `NewPwd_StrongChange_2026!` 重登才能跑场景 9

**失败信号 (任一即停)**:
- Modal 有 X / ESC / backdrop click 能关 (违反唯一出口)
- Modal 多于 1 个 CTA (违反契约)
- 点 CTA 跳 `/admin/login` 但缺 `?reason=session_expired` query (登录页无法识别"用户被踢"上下文)
- Modal 在 `/admin/login` 自身路径上也显示 (login page 本身不该看到 modal — 决策 #24.D 明确)
- 走完路径 (a) 但 30 秒后 Network 没自动出现 `/refresh` 请求 (Vite restart 没生效 / SILENT_REFRESH_INTERVAL_MS 改写失败 / setTimeout 在 mount 时没起)

---

## 场景 9 · unauthorized 路由

**触发动作**:
1. 场景 8 后已 logout, 应在 `/admin/login`
2. 直接在 URL bar 手动跳 `http://localhost:5173/admin/dashboard`

**期望现象**:
- AdminRouteGuard.jsx line 64-71: `if (status === 'anonymous')` 触发, navigate `/admin/login?redirect=/admin/dashboard`
- URL 落到 `/admin/login?redirect=%2Fadmin%2Fdashboard`
- UI 显示 login form, **不闪 dashboard 内容**
- 登录成功后 (用 `NewPwd_StrongChange_2026!`) → AdminLoginPage 读 `redirect` query → navigate `/admin/dashboard`

**失败信号 (任一即停)**:
- 直接看到 dashboard 内容 (RouteGuard anonymous 分支失效)
- URL 落 `/admin/login` 但缺 `?redirect=...` (登录后无法回到原页)
- 登录后跳到 default 路径而不是 dashboard (AdminLoginPage 没消费 redirect query)

---

## 跑后回报 (Frank 填)

跑完所有 9 场景后, 复制下面表格填到 CC 回报里:

| # | 场景 | PASS/FAIL | 现象 / 异常 |
|---|---|---|---|
| 1 | login 成功 | | |
| 2 | forcePasswordChangeAt 触发跳转 | | |
| 3 | 改密成功 | | |
| 4 | 重登验证 | | |
| 5 | silent refresh 静默续约 (选项 A 或 B) | | |
| 6 | BroadcastChannel 跨 tab 同步 | | |
| 7 | manual logout | | |
| 8 | SessionExpiredModal 触发 | | |
| 9 | unauthorized 路由 | | |

**整体结论**: PASS / FAIL / PARTIAL — 第一行写最终判断

**未跑或跳过场景**: 列编号 + 原因

**FAIL 详情** (有 FAIL 才填):
- 场景编号:
- DevTools Network 一条: status / URL / response body / Set-Cookie
- Console 错误段:
- 推测原因:

---

## 失败应急

任一 FAIL 立刻停 — **不连环修, 不"顺手"试别的**, 把现象贴 CC 等决策。常见根因猜测 (供 Frank 自查 / CC 排障):

- **场景 1 失败 + Response snake_case**: Step 7 alias 配置漏到某 DTO. 跑 `grep -rn "model_config" backend/app/admin/api/v1/auth/_dto.py` 看是否有子类自带 model_config 漂移.
- **场景 2 失败 + 卡 dashboard**: AdminRouteGuard 没读 `forcePasswordChangeAt`. 跑 `grep -n "forceChange\|forcePasswordChangeAt" frontend/src/admin/components/AdminRouteGuard.jsx` 看 line 57-59 决策点是否正常.
- **场景 5 失败 + 没看到 refresh**: setTimeout 没起 / vite 重启没生效 / 改 line 41 后忘记重启. 在 Console 跑 `console.log(window.__refreshTimerSet)` (若 Provider 暴露 debug hook 则可见).
- **场景 6 失败 + Tab B 不动**: BroadcastChannel name 不一致 / 浏览器隔离不同源 (Vite dev port 必须一致, 不要 Tab A/B 用不同端口).
- **场景 8 失败 + Modal 可关**: SessionExpiredModal.jsx 是否绑了 ESC/backdrop click — 决策 #24.D 明确禁止, 是 jotamotk 仓代码 regression 信号.

---

## 完成回报后

CC 整合 9 场景结果到 Step 8 commit body, 然后 commit:
- 标题: `Session A0' Step 8: AdminRouteGuard + SessionExpiredModal 9 场景 smoke + D3 注释 fix`
- Body 含: 9 场景 PASS/FAIL 表 + D3 替换前后对比 + 决策依据引用 (#24.D + #25 Rule 3)

**本 Step 8 commit 落定后**, 单独跑 cleanup commit 收 line 13 + lines 33-35 文档 drift, message: `docs(admin-auth): fix TS-era step references and tense drift in AdminAuthContext`.

---

## A0' Phase Gate 后 known issues (Step 8 诊断产物)

Step 8 场景 8 实施过程诊断暴露的 2 条**独立** follow-up bug, **不在 Step 8 修**, 进 A0' Phase Gate 后的 known issues 列表, **不阻断 Phase Gate**。Session A1' 或单独批次再修。

### Bug 1 · adminFetch wrapper 缺 401 interceptor

**现象**: `frontend/src/admin/lib/adminApi.js` 的 `adminFetch` 收到非 `/auth/login` 路径的 401 时, 只 throw `AdminApiError`, **不会** 触发 AdminAuthContext 切 expired 态。

**影响**: 用户主动操作 (点菜单 / 提交表单 / 在 SPA 里任何 admin 端调用) 中途被踢, 表现为 alert 弹错或静默吞掉, 而不是统一的 SessionExpiredModal。违反 SessionExpiredModal 唯一出口契约 (决策 #24.D — 所有 expired 信号汇聚到 modal)。

**当前唯一 expired 触发路径**: 后台 setTimeout silentRefresh tick 401 (lines 118-119) + BroadcastChannel `'expire'` 消息 (lines 199-200)。覆盖面不全。

**修复方向**: `adminFetch` 收到 401 (排除 `/auth/login` 自己) 时, 应通知 AdminAuthProvider 切 expired 态。建议走 `EventTarget` / `window.dispatchEvent` 解耦, 避免 adminApi.js → AdminAuthContext 反向 import。

**留待**: A0' 后批次或 Session A1'。

### Bug 2 · login handler 把 ADMIN_JWT_SECRET 缺失误包成 401

**现象**: 后端启动若 `ADMIN_JWT_SECRET` 环境变量未设, `app/admin/api/v1/auth/login.py` 对每次登录请求都尝试 `sign_access_token` → 抛 `AdminJwtSecretMissingError` → 被 try/except 当 generic auth failure 包成 401 返回前端。

**影响**: 部署配置错误 (env 漏写) 表现成"frank@genpano.com 登不上去", root cause (env 缺失) 隐藏在通用 401 里, 调试昂贵。决策 #24.B 明确说 "JWT secret boot-time fast-fail" 是设计目标, 但 login handler 实施漂离了。

**当前缓解**: §0.1 uvicorn 启动命令显式 `ADMIN_JWT_SECRET='test-secret-32-bytes-minimum-len-ok'` 绕过, 此 bug 在 smoke 流程不会重现。

**修复方向**: FastAPI `lifespan` / `app.main` import time 检查 `ADMIN_JWT_SECRET` 长度 ≥ 32, 否则 raise 不让进程起 (mirror Session A0 TS 时代决策 #24.B 的 boot-time fail-fast 实现)。

**留待**: A0' 后批次或 Session A1'。

### Bug 3 · `require_admin_session` 不重新校验 user.status

**现象**: `app/admin/auth/middleware.py:147-171` 的 `require_admin_session` 只过 `verify_access_token` (签名/过期/claims), 拿到 payload 直接返回, 不做 DB user row 查找, 也不 assert `status='active'`。`/refresh` 同 gap — 找到 session row 后 mint 新 access token 之前从不查 user.status, 因此被 suspend 的用户还能拿现有 refresh cookie 给自己续命。

**后果**: admin 把某 user `status` 改成 `suspended` 后, 该 user 已发的 access cookie 仍可继续打受保护端点 (`/change-password` / 未来 admin API) 直到 access TTL 到期, 最长 15 分钟。`/refresh` 路径还能进一步 self-extend, 直到对应 admin_sessions 行被显式 revoke。

**触发**: `tests/admin/auth/test_e2e_integration.py::test_flow6_suspended_user_cannot_login_or_use_existing_cookie` Step 4。当前 assertion **pin 在 buggy behaviour (200)** + TODO marker 保留期望行为 (401/403), 等 A1' 修复后翻转。

**修复方向**: A1' Session admin "suspend user" UI 一起做 — middleware 扩展加 user row load + `status='active'` assert + `revoke_all_sessions_for_user` 在 suspend admin action 触发, 单一 PR 闭环。Decision #24.D 中跨状态机边界 gap, 在 A0' scope 之外。

**风险窗口**: TTL=15 min, 需 admin 已发起 suspend (privileged action 链), MVP super_admin 仅 Frank 一人, 不构成 hostile actor 场景。Phase Gate 不阻断。

**留待**: Session A1' (admin 用户管理 + suspend 流) 一并修复, 决策依据 #25 Rule 12 Type C (scope creep 拒绝)。
