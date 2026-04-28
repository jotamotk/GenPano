# Session 4b'.1 Prompt · Frontend Foundation (横切 + App Shell + Auth/Onboarding/Landing/Settings)

**版本**: 1.0 · 创建日期 2026-04-26
**拆分自**: `docs/SESSION_4B_PRIME_PROMPT.md` (consolidated 4b' 的第 1/4 段)
**上游链**: 0' (CI/CD) → 4a' (Auth/Onboarding API) → **本 Session (4b'.1)** → 4b'.2 → 4b'.3 → 4b'.4
**下游 Session**: 4b'.2 GREEN gate = 本 Session PASS

---

## §0 · Pre-Flight Grep Contract (开工前 30min 内执行, 全部命中才能动代码)

```bash
# F1 · IA v2.0 路径锚点 (PRD §4.6-IA-v2 Brand 9 + Industry 4) - 仅核心壳层
rg -n "/brand/overview|/brand/visibility|/industry/overview|/industry/ranking" docs/PRD.md | head -20
# 期望: ≥ 4 命中 (Brand 9 + Industry 4 = 13 路径在 PRD 出现)

# F4 · 上游 GREEN gate (Sessions 0' + 4a' 必须 PASS)
rg -n "Session 0'.*GREEN|Session 4a'.*GREEN|Phase Gate.*PASS" docs/SESSIONS_PYTHON.md | head -10
# 期望: 0' GREEN + 4a' GREEN 双锚点; 任一为 ❌ 立即 STOP Type A4

# F5 · Onboarding 草稿契约 (PRD §4.1.1d.C, ?resumeStep + DraftProject 72h)
rg -n "DraftProject|resumeStep|onboarding_draft_(created|resumed|expired)" docs/PRD.md | head -10
# 期望: ≥ 4 命中 (status enum + ?resumeStep + 3 events)

# F7 · frontend/src/pages/* 空仓验证 (Python 反转后 frontend 应为空)
ls frontend/src/pages/ 2>/dev/null && echo "❌ 仓不空, 看是否需要 Plan G branch reset"
# 期望: 命令报 No such file (frontend 仓 main HEAD 干净)

# F8 · package.json 依赖锚 (Vite + React 19 + TS strict 必须未引)
rg -n '"react":\s*"\^19' frontend/package.json 2>/dev/null && echo "❌ deps 已引入, 看是否需要 Plan G branch reset"
# 期望: 命令无输出 (frontend/package.json 不存在 OR 不含 react@19, 即开工前空白)

# F9 · AuthPage Email-first 2-step (PRD §4.1.1-form, decision #29)
rg -n "AuthPage|email-first|Step 0.*identifier|Step 1.*password" docs/PRD.md | head -10
# 期望: ≥ 4 命中 (PRD §4.1.1-form 完整描述)

# F10 · i18n 覆盖矩阵 (PRD §4.10.4a + decision #11)
rg -n "i18n|next-intl|formatBrand|locale|zh-CN|en-US" docs/PRD.md | head -10
# 期望: ≥ 6 命中

# F12 · CLAUDE.md 最近 3 条决策 freshness check (规则 11)
rg -n "^[0-9]+\. \*\*" CLAUDE.md | tail -3
# 期望: 决策 #28/#29/#30 之类近期条目, 任何提及 frontend/IA/Auth 必须读全文
```

**STOP 触发对照表**:

| 命中条件 | STOP 类型 | 行动 |
| --- | --- | --- |
| F4 显示 0' / 4a' 任一未 GREEN | Type A4 | 暂停, 回追前置 Session |
| F7 显示 frontend/src/pages/ 已有内容 | Type C18 | 撤换分支, 不准 cherry-pick |
| F8 显示 react@19 已引入 | Type C18 | 同上 |
| F1/F5/F9 命中数 < 期望阈值 | Type B1 (truth source 漂移) | 回 PRD 校验, 再补 grep |
| F12 显示有未读决策提及 frontend | Type B7 | 读全文, 加入 §1 真相源索引再开工 |

---

## §1 · Truth Source Index (本 Session 引用 / 修改的所有真相源, 段号最小单元)

### Prerequisites (chain dependency, 全部 GREEN 才能开工)

| 前置 Session | GREEN 条件 | 本 Session 依赖点 | 验证命令 |
| --- | --- | --- | --- |
| **0'** | CI/CD GitHub Actions + Vercel app.preview.genpano.dev DNS 通 + main 分支可推 | Vite 构建产物部署管线 + verify_*.sh runner | `curl -I https://app.preview.genpano.dev` 返回 2xx OR 404 (DNS 已生效) |
| **4a'** | `/api/v1/auth/lookup`, `/api/v1/auth/login`, `/api/v1/auth/logout`, `/api/v1/onboarding/state`, `/api/v1/onboarding/save-step`, `/api/v1/users/me` 6 端点 OpenAPI 已发, 401 / 403 行为契约稳定 | TanStack Query 401 触发 SessionExpired / OnboardingGuard 读 state | `curl -s https://api.preview.genpano.dev/api/v1/openapi.json \| jq '.paths \| keys' \| grep -E "auth/lookup\|onboarding/state"` |

**STOP Type A4**: 上述任一前置 Session 未 GREEN, 本 Session 必须暂停 Phase Gate 任何活动, 回追前置 Session 的 Phase Gate 报告。**绝不**用 mock/stub 绕过缺失的真实端点 (msw 仅用于 Storybook + 本地 dev fallback, 绝不进 Layer 3 preview env)。

### 引用的真相源 (只读)

| 文档 / 锚点 | 引用内容 | 用途 |
| --- | --- | --- |
| `docs/PRD.md §4.1.1-gate` | Auth-Required 数据访问 (decision #9) | RouteGuard 实现依据 |
| `docs/PRD.md §4.1.1-form` | AuthPage Email-first 2-step (decision #29) | AuthPage 状态机 / lookup ≥400ms anti-enum |
| `docs/PRD.md §4.1.1d.C` | Onboarding 草稿 DraftProject 72h + ?resumeStep (decision #21 D) | OnboardingPage 4 步流 + Route Guard 续签 |
| `docs/PRD.md §4.1.1e` | 登出 6 步契约 + L1/L2/L3 三层 (decision #18) | UserMenu / SessionExpiredModal / SettingsPage L2 |
| `docs/PRD.md §4.6-IA-v2.A-F` | Brand/Industry Mode IA + Topbar pill toggle (decision #2) | AppLayout / Topbar / Sidebar URL-derived mode |
| `docs/PRD.md §4.6.0a` | UI 禁用开发约束语 (decision #19) | 文案审查锚点 |
| `docs/PRD.md §4.10.4a` | i18n 覆盖矩阵 + formatBrand 唯一入口 (decision #11) | i18n 命名空间 + Brand 名格式化 |
| `docs/PRD.md §4.11 §4.11.4` | Mixpanel 事件 #44/#45/#46/#63-#65/#70 (decision #21 D) | Mixpanel helper + Onboarding/Auth track |
| `docs/DESIGN_TOKENS.md` | Stripe 浅色 token 集 (decision #18) | LandingPage + AuthPage + 全局 CSS variables |
| `CLAUDE.md` 决策 #2 / #9 / #10 / #11 / #18 / #25 / #29 | IA / Auth-Required / Onboarding 替代 E1-E4 / i18n / 登出 / Prompt 公约 / AuthPage | 全 Session 行为依据 |

### 修改的文件 (本 Session 写入)

| 路径 | 内容 | 备注 |
| --- | --- | --- |
| `frontend/package.json` | Vite 5 + React 19 + TS 5.6 strict + TanStack Query v5 + Mixpanel + i18next + msw devDep | Y1-Y6 横切依赖 |
| `frontend/vite.config.ts` | base / proxy `/api` → `https://api.preview.genpano.dev` / build target esnext | Y1 |
| `frontend/tsconfig.json` | strict + paths `@/*` → `src/*` | Y1 |
| `frontend/index.html` | 单页 entry, `<div id="app">` | Y1 |
| `frontend/src/main.tsx` | React 19 createRoot + i18n init + Query client provider | Y1 + Y2 + Y4 |
| `frontend/src/App.tsx` | React Router v6.x routes 定义 (含 RouteGuard 包裹 / 11 Legacy 301 占位由 4b'.3 填充) | Y7 + Y9 |
| `frontend/src/lib/api.ts` | fetch wrapper + 401 interceptor + OpenAPI typed client (openapi-typescript 生成) | Y2 + Y3 |
| `frontend/src/lib/queryClient.ts` | TanStack Query v5 client (staleTime / retry / 401 默认行为) | Y2 |
| `frontend/src/lib/i18n.ts` | i18next + zh-CN/en-US namespace 加载 | Y4 |
| `frontend/src/lib/formatBrand.ts` | 唯一品牌名格式化入口 (decision #11) | Y4 |
| `frontend/src/lib/mixpanel.ts` | Mixpanel init + track helper + logoutSequence 6 步 helper (PRD §4.1.1e) | Y5 |
| `frontend/src/lib/msw/` | dev-only mock service worker handlers (auth/onboarding 兜底, 不进 preview build) | Y6 |
| `frontend/src/components/layout/AppLayout.tsx` | Shell: Topbar + Sidebar + `<Outlet />` | Y7 |
| `frontend/src/components/layout/Topbar.tsx` | Stripe-style pill `🎯 ⇌ 🌍` URL-derived (NOT localStorage) + 🔍 ⌘K + 🔔 + UserMenu | Y7 + Y10 |
| `frontend/src/components/layout/Sidebar.tsx` | URL-derived (`/brand/*` vs `/industry/*`) 两套侧栏 | Y8 |
| `frontend/src/components/layout/UserMenu.tsx` | L1 登出 trigger | Y10 |
| `frontend/src/components/layout/SessionExpiredModal.tsx` | L3 唯一出口, 无 X-close, 唯一 CTA "重新登录" + BroadcastChannel 监听 | Y10 |
| `frontend/src/components/layout/RouteGuard.tsx` | Auth-Required 包裹 (decision #9) + 401 → /login?redirect= | Y9 |
| `frontend/src/components/layout/OnboardingGuard.tsx` | 检查 `/api/v1/onboarding/state` → 草稿存在则 302 `/onboarding?resumeStep=N`; 零 Project 强制 `/onboarding` | Y9 |
| `frontend/src/pages/LandingPage.tsx` | 浅色 Stripe token, CTA 实路由 `/register` `/login` (decision #18 + memory `feedback_genpano_landing_v21`) | Y11 |
| `frontend/src/pages/AuthPage.tsx` | Email-first 2-step 状态机 (PRD §4.1.1-form), `/login` `/register` 都 mount | Y12 |
| `frontend/src/pages/OnboardingPage.tsx` | 4 步流 (行业 / 主品牌 / 竞品 / 偏好) + DraftProject 自动续签 + 事件 #70 | Y13 |
| `frontend/src/pages/SettingsPage.tsx` | L2 inline 登出 + 账号信息 / 偏好 / Locale 切换 | Y14 |
| `frontend/src/i18n/zh-CN.json` + `frontend/src/i18n/en-US.json` | 命名空间结构 (auth / onboarding / settings / common), 覆盖矩阵满足 §4.10.4a | Y4 |
| `frontend/scripts/verify_4b1.sh` | Phase Gate Layer 1 runner (见 §6) | Phase Gate |
| `frontend/scripts/ci_check.py` Group I 部分 | I6 no-empty-state-components rule + 1 cifixture | Y42 部分 |
| `frontend/scripts/ci-harness-selftest.py` | EXPECTED_POSITIVES 32 → 33 (+I6) | Y42 部分 |
| `frontend/playwright/auth.spec.ts` | Smoke: Landing → AuthPage email-first → OnboardingPage Step 1 渲染 | Y44 部分 |
| `vercel.json` (4b'.1 创建, 4b'.3 完善 11 Legacy 301) | 静态托管 + SPA fallback | Y45 部分 |

### 版本警告 (12 项, 全 Session 共用)

1. **React 19**: 必须用 `createRoot` (不用 ReactDOM.render); 注意 useTransition 行为新语义 vs React 18
2. **Vite 5**: `target: 'esnext'` + `build.rollupOptions` 切 chunks; 不引 webpack
3. **TS 5.6 strict**: `noUncheckedIndexedAccess` + `exactOptionalPropertyTypes` 必开
4. **TanStack Query v5**: `useQuery({ queryKey, queryFn })` API (非 v4 数组 args); error 类型必标 `Error`
5. **React Router v6.x**: `<Outlet />` + `useNavigate` (非 v5 history.push)
6. **i18next v23+**: `useTranslation` + `t(key, { values })` 接口 (decision #20 V2 (8))
7. **Mixpanel browser SDK**: `mixpanel.init` + `mixpanel.track` + `mixpanel.reset` (登出后) — track 必先于 reset (PRD §4.1.1e 6 步)
8. **msw v2**: `setupWorker` (browser) / `setupServer` (node, 测试用); 不混用 v1 API
9. **openapi-typescript**: 5.x+, 命令 `npx openapi-typescript ./openapi.json -o src/lib/api-types.ts`
10. **Tailwind v3.4+**: 用 JIT, 不写 deprecated `@apply` 嵌套
11. **Recharts v2.x** / **AntV G6 v5**: 在 4b'.2 / 4b'.3 才装, 本 Session 不引
12. **Playwright v1.4x**: `test.describe` + `expect(page).toHaveURL`; 1 路径 smoke 不开 visual

---

## §2 · MVP Scope-Cut Declaration (本 Session 做 / 不做)

### ✅ 做 (Y1-Y14, 14 项, ≈ 3-5 days)

**横切基础设施 Y1-Y6**:

- **Y1 · Vite 脚手架 + React 19 + TS strict**: `frontend/package.json` + `vite.config.ts` + `tsconfig.json` + `index.html` + `src/main.tsx`; `npm run dev` 启动 + `npm run build` 产物 ≤ 2MB gzipped (Phase Gate L1.4)
- **Y2 · TanStack Query v5 + 401 interceptor**: `lib/api.ts` 单 fetch wrapper + 401 → 触发 BroadcastChannel `'genpano-auth'` 'expire' 消息 → SessionExpiredModal 显; queryClient 默认 retry: 0, staleTime: 30s
- **Y3 · OpenAPI typegen pipeline**: 从 4a' 发布的 `https://api.preview.genpano.dev/api/v1/openapi.json` 拉 schema, `openapi-typescript` 生成 `src/lib/api-types.ts`; 加 `npm run typegen` script
- **Y4 · i18n + formatBrand**: i18next 加载 `src/i18n/{zh-CN,en-US}.json`; `formatBrand` 单一入口 (NOT 多处实现, decision #11) — A3 harness 锁; namespace 至少 4 (auth / onboarding / settings / common), 缺翻译报警 (Phase Gate L1.6)
- **Y5 · Mixpanel + 登出 6 步 helper**: `lib/mixpanel.ts` 提供 `track(event, props)` + `logoutSequence(reason)` (PRD §4.1.1e: 1️⃣ track logout_initiated → 2️⃣ POST /api/v1/auth/logout → 3️⃣ track logout_completed → 4️⃣ mixpanel.reset → 5️⃣ BroadcastChannel post 'logout' → 6️⃣ navigate /login); D2 harness 守 track 先于 reset
- **Y6 · msw dev-only**: `lib/msw/handlers.ts` 仅 `auth/lookup` `auth/login` `onboarding/state` 三 handler; `setupWorker` 仅在 `import.meta.env.DEV` 启用; 严禁进 vite build production bundle (Phase Gate L1.4 验产物无 msw)

**App Shell Y7-Y10**:

- **Y7 · AppLayout + Topbar URL-derived ModeToggle**: `<Topbar>` 内含 Stripe-style pill `🎯 品牌 ⇌ 🌍 行业`; 当前 mode 由 URL 推导 (`useLocation().pathname.startsWith('/brand/')` vs `/industry/`); 切换时 `navigate('/brand/overview')` 或 `'/industry/overview'`; 严禁 localStorage / sessionStorage / Cookie 存 mode (decision #2)
- **Y8 · Sidebar URL-derived 双套**: Brand Mode 9 项侧栏 + Industry Mode 4 项侧栏; 两套都本 Session 渲染骨架 (路由项 + 文案 i18n) 但具体页面 (Y15-Y33) 由 4b'.2 / 4b'.3 落; 本 Session 占位用 `<ComingSoon />` 简单组件 (不写"Empty State", 见 N13)
- **Y9 · RouteGuard + OnboardingGuard**: `<RouteGuard>` 包所有 `/brand/*` `/industry/*` `/settings/*`, 401 → `navigate('/login?redirect=' + currentPath)`; `<OnboardingGuard>` 在 RouteGuard 内层, 调 `/api/v1/onboarding/state` → 草稿存在 302 `/onboarding?resumeStep=N`; 零 Project 强制 `/onboarding`
- **Y10 · UserMenu + SessionExpiredModal + BroadcastChannel**: UserMenu (Topbar 右侧) → 下拉含 "设置" "登出"; SessionExpiredModal 是 expired 态唯一出口 (无 X-close / 无 ESC / 无 backdrop-click), 唯一 CTA "重新登录"; BroadcastChannel `'genpano-auth'` 跨 tab: login / logout / expire 三消息

**Auth + Onboarding + Landing + Settings Y11-Y14**:

- **Y11 · LandingPage 浅色 Stripe**: 用 DESIGN_TOKENS Stripe 浅色 token (NOT 自创视觉, memory `feedback_genpano_landing_v21`); CTA 4 个全部指向真路由 (`/register`, `/login`, `/industry/overview`, `/about`) + UTM 参数; 严禁 `#cta` 锚点占位
- **Y12 · AuthPage Email-first 2-step**: PRD §4.1.1-form 状态机; Step 0 = identifier (email) input → POST `/api/v1/auth/lookup` (≥400ms 强制 anti-enumeration) → 返回 `{exists: bool}` → Step 1 (exists=true 显示 password / exists=false 显示 register flow); 5 Harness (memory `project_genpano_authpage_email_first`) 内 A1/A4 由本 Session 已 wire (i18n + Mixpanel 事件 #57-#61, email_domain only NOT email)
- **Y13 · OnboardingPage 4 步**: 行业 (调 `/api/v1/industries`) → 主品牌 (调 `/api/v1/brands?industryId=`) → 竞品 (多选 ≥2) → 偏好 (locale + email subscribe boolean); 每步 POST `/api/v1/onboarding/save-step` 带 `step` + `payload`, 后端写 DraftProject 72h; URL 含 `?resumeStep=N` 自动恢复; 完成后 302 `/brand/overview`; 全 4 步埋 #70 onboarding_step_completed (props: stepNumber, durationMs)
- **Y14 · SettingsPage L2 inline 登出**: 标签页 (Tab): "账号" / "偏好" / "Locale"; "账号" Tab 底部红色 "登出" 按钮 (L2 inline) 调用 `logoutSequence('settings_inline')`; 不弹 confirm modal (PRD §4.1.1e L2 直接执行); 注销账号按钮 disabled + tooltip "Phase 2 上线" (decisions #18 N1)

### ❌ 不做 (推到下游 sub-Session, 全部带去向)

- Brand Mode 9 sub-views 实际页面 (Y15-Y29) → **4b'.2**
- Industry Mode 4 sub-views (Y30-Y33) → **4b'.3**
- CSV 导出 ExportCsvButton + 8 接入点 (Y34-Y41) → **4b'.3**
- Citation 模块 5 Tab (overview / content-gap / pr-targets / tier-coverage / domains) → **4b'.2**
- 知识图谱 AntV G6 (`/industry/knowledge-graph`) → **4b'.3**
- Group I I1-I5 chart/page harness rules + cifixture → **4b'.2**
- Vitest 80% lib coverage 完整聚合 → **4b'.4** (本 Session 只跑 lib/* 目录, 不跑 pages/* 因为 pages 还没生成)
- Playwright 完整 6 关键路径 → **4b'.4** (本 Session 只跑 1 条 auth-flow smoke)
- 11 Legacy 301 redirect 全表 + vercel.json route 配置 → **4b'.3** (本 Session 只 vercel.json 骨架)
- Citation Simulator (decision #19 v1.1 deferred) → 本 SaaS Phase 2 (N1)
- Citation Tier 编辑 CRUD UI → A5' (N2)
- MCP Token 签发 UI → A5' (N3)
- 报告 PDF 渲染 → 本 SaaS Phase 2 (N4) (本 Session SettingsPage 不暴露报告设置)
- Acquisition 事件流 (decision #19 D) → 本 SaaS v1.1 (N6)
- KOL Shannon entropy 多样性算法 → 本 SaaS v1.1 (N7)
- Phase 4 visual regression baseline (TEST_STRATEGY) → **4b'.4** + Phase 2 (N8)
- Multi-turn Query (decision #26 C2) → Phase 2 (N9)
- Mobile 响应式 (PRD MVP 桌面优先) → Phase 2 (N10)
- Custom Dashboard / 多 Project picker → Phase 2 (N11/N12)
- E1-E4 四面 Empty State 组件 (decision #10 已废) → 永不创建 (N13) — Group I I6 守
- Engine Compare Tab (decision #2 已改 segmented control) → 4b'.2 内做 segmented (N14)
- 顶层 `/diagnostics` 跨品牌聚合 (decision #2 已废) → 永不 (N15)
- OAuth 登录 → Phase 2 (N16)
- admin.genpano.internal 域 → Admin Sessions A0'-A5' (N17)
- Citation simulator Tab → A5' / Phase 2 (N18)

---

## §3 · STOP Triggers (任一触发立即停止 + 写 .blocker.md + 通知 Frank)

### Type A · 环境失败 (Environment Failures)

- **A1** `npm install` 失败 (network / lockfile drift / peer-deps)
- **A4** `npm run dev` 启动后页面白屏 + console 红错且 5min 内未自愈
- **A5** Vercel app.preview.genpano.dev DNS 不生效 (`curl -I` 超时 OR 5xx)
- **A8** GitHub Actions runner 卡住 OR `verify_4b1.sh` 任一步超时 5min

### Type B · 真相源冲突 (Truth Source Conflicts)

- **B1** PRD §4.6-IA-v2.A-F 与本 Prompt §1 引用段号语义不一致 (URL 路径 / mode 切换契约 / pill toggle 文案)
- **B6** PRD §4.1.1d.C 与 4a' API 契约 (`/api/v1/onboarding/state` 字段 / status enum) 冲突
- **B7** decision #29 AuthPage Email-first 在实施时发现 4a' 后端不支持 lookup 端点 (`POST /api/v1/auth/lookup` 返回 404)

### Type C · 范围溢出 (Scope Overflow)

- **C11** 单 TSX 文件 > 500 行 (强制拆 sub-component)
- **C13** 任何组件用 `useState('7d')` 等本地状态绕 URL (违反 IA v2.0 URL-derived 契约)
- **C15** 任何 JSX 含 CJK literal (decision #11 i18n 唯一入口) — A1 harness 应在 4b'.2 引入, 本 Session 提前手工自查
- **C18** 试图 cherry-pick `claude/*` 历史分支 (memory `feedback_genpano_branch_per_session` 禁)
- **C19** Mixpanel 事件 props 含 PII (email / 手机号 / userId 明文); D3 harness 在 4b'.2 引入, 本 Session 手工自查 (#57-#61 + #70 props 只能 email_domain / step / durationMs)

---

## §4 · 本 Session 引入的 Harness (Group I 子集 1 条)

**L3/L4 Phase Gate**: 本 sub-Session 验收追溯到 SESSION_4B_PRIME_PROMPT.md §4 L3/L4 Phase Gate 卡控 (Hard Fail), 详见 REPLAN_2026_04_26.md §5 4b' 行.

`frontend/scripts/ci_check.py` 新增 Group I 段落, 本 Session 落地 **I6** 一条:

- **I6 · `no-empty-state-components`**: 扫 `frontend/src/**/*.tsx`, 黑名单文件名 `DashboardEmptyState.tsx` / `ProjectRequiredBanner.tsx` / `LandingNavQuickCreateButton.tsx` (decision #10 已废 E1-E4); 命中即 block。fixture: `frontend/src/__ci_fixtures__/I6_dashboard_empty_state.cifixture.tsx` 自带文件名匹配黑名单 → selftest 应抓到。

`frontend/scripts/ci-harness-selftest.py` `EXPECTED_POSITIVES` 32 → **33** (新增 I6 fixture 期望命中)。

I1-I5 (chart/page rules) 由 4b'.2 引入。本 Session **不要**提前拉 I1-I5 — 它们守的是 4b'.2 才会创建的 Brand 页面 / charts。

---

## §5 · Step Delivery Order (本 Session 6 步, 顺序严格)

### Step 0 · 分支 + Vite 脚手架 (≈ 0.5 day)

```bash
# 从 main HEAD fork
git checkout main && git pull
git checkout -b session/4b1-frontend-foundation

# Vite 脚手架
cd frontend  # 若不存在则 npm create vite@latest frontend -- --template react-ts
npm install
# 装 deps (Y1 锚)
npm install react@^19 react-dom@^19 react-router-dom@^6.26
npm install -D typescript@~5.6 @types/react@^19 @types/react-dom@^19 vite@^5
# Y2 + Y3
npm install @tanstack/react-query@^5
npm install -D openapi-typescript@^7
# Y4
npm install i18next react-i18next i18next-browser-languagedetector
# Y5
npm install mixpanel-browser
npm install -D @types/mixpanel-browser
# Y6 dev only
npm install -D msw@^2
# Tailwind
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p

# tsconfig.json 打开 strict + noUncheckedIndexedAccess + exactOptionalPropertyTypes
# vite.config.ts 加 proxy: '/api' → 'https://api.preview.genpano.dev'
```

**Phase Gate Step 0**: `npm run dev` 启动 → 浏览器 `localhost:5173` 显示默认 Vite 页面 (HelloWorld); `npm run build` 通过, `dist/` 产物存在。

### Step 1 · i18n + formatBrand + Mixpanel + msw (≈ 0.5 day)

- 落 `src/lib/i18n.ts`, 加载 zh-CN / en-US 命名空间
- 落 `src/lib/formatBrand.ts` (PRD §4.10 Brand 多语种归一化)
- 落 `src/lib/mixpanel.ts` 含 `logoutSequence` 6 步 helper
- 落 `src/lib/msw/handlers.ts` (auth/lookup, auth/login, onboarding/state 3 个), `setupWorker` 仅 dev
- 落 `src/i18n/zh-CN.json` + `src/i18n/en-US.json` 命名空间骨架

**Phase Gate Step 1**: `npm run dev` console 无红错; 在 dev tools 调 `window.mixpanel.track('test')` 不抛错; msw worker 注册成功 (Network 标 `service-worker` 起来)。

### Step 2 · API client + TanStack Query + OpenAPI 类型生成 (≈ 0.5 day)

- 落 `src/lib/api.ts` 单 fetch wrapper, 401 → BroadcastChannel post 'expire'
- 落 `src/lib/queryClient.ts` 创建 QueryClient + Provider 包到 main.tsx
- 跑 `npm run typegen` (拉 https://api.preview.genpano.dev/api/v1/openapi.json), 生成 `src/lib/api-types.ts`
- 验证 typed client: 写一个测试 `useQuery` 调 `/api/v1/users/me`, dev 启动看 401 行为

**Phase Gate Step 2**: dev 调用 `/api/v1/users/me` 401 → SessionExpiredModal 还没 wire (Step 3 才装); 但 401 被 fetch wrapper catch 并 BroadcastChannel post 'expire' 这一行为可在 dev tools log 验证。

### Step 3 · App Shell + Topbar + Sidebar + ModeToggle + RouteGuard + OnboardingGuard (≈ 1 day)

- 落 `src/components/layout/AppLayout.tsx` (含 Topbar + Sidebar + Outlet)
- 落 `src/components/layout/Topbar.tsx` (含 Stripe pill `🎯 ⇌ 🌍` URL-derived) + 🔍 ⌘K (placeholder, 无后端搜索, 4b'.2 fill) + 🔔 (placeholder) + UserMenu
- 落 `src/components/layout/Sidebar.tsx` (URL-derived 双套, 路由项渲染 `<NavLink>` + i18n 文案 + `<ComingSoon />` 占位 component for 未实现页面)
- 落 `src/components/layout/UserMenu.tsx` + `src/components/layout/SessionExpiredModal.tsx`
- 落 `src/components/layout/RouteGuard.tsx` + `src/components/layout/OnboardingGuard.tsx`
- 落 `src/App.tsx` 路由表 (含所有 `/brand/*` `/industry/*` `/settings` `/onboarding` 占位 + LandingPage `/` + AuthPage `/login` `/register`)

**Phase Gate Step 3**: 浏览器访问 `/brand/overview` (匿名) → 自动 302 `/login?redirect=/brand/overview`; 登录后 (走 4a' 真后端) → 看到 AppLayout + Sidebar 9 项 + Topbar pill 高亮 "品牌"; 点 pill 切到 "行业" → URL 变 `/industry/overview` + Sidebar 切 4 项。

### Step 4 · Landing + AuthPage + OnboardingPage (≈ 1 day)

- 落 `src/pages/LandingPage.tsx` (浅色 Stripe + 4 CTA 实路由 + UTM)
- 落 `src/pages/AuthPage.tsx` (Email-first 2-step 状态机, 调 `/api/v1/auth/lookup` 强制 ≥400ms; 调用 4a' login/register 端点)
- 落 `src/pages/OnboardingPage.tsx` (4 步流, 每步调 `/api/v1/onboarding/save-step`; URL 含 `?resumeStep=N` 自动恢复; 全 4 步埋 #70 事件)

**Phase Gate Step 4**: 浏览器全流程: Landing → 点 "免费注册" → /register (AuthPage Step 0 input email) → lookup 返回 not exists → Step 1 显示注册表单 → 提交 → 302 `/onboarding` → 4 步走完 → 302 `/brand/overview`; 中途刷新 onboarding URL `?resumeStep=2`, 自动续到 Step 2。

### Step 5 · SettingsPage + L1/L2 登出 (≈ 0.5 day)

- 落 `src/pages/SettingsPage.tsx` (3 Tab: 账号 / 偏好 / Locale)
- "账号" Tab 底部 L2 inline 登出按钮调 `logoutSequence('settings_inline')`
- UserMenu 点 "登出" 调 `logoutSequence('user_menu_l1')`
- SessionExpiredModal 点 "重新登录" 触发跨 tab BroadcastChannel post 'expire' + navigate `/login?reason=session_expired&redirect=` (NOT 触发 logoutSequence — expired 态下 access token 已亡, mixpanel.reset 直接调用即可)

**Phase Gate Step 5**: 登录后访问 `/settings`, 看 3 Tab; 点 L2 登出 → 1️⃣ console log `logout_initiated` track → 2️⃣ POST /api/v1/auth/logout 200 → 3️⃣ console log `logout_completed` track → 4️⃣ mixpanel reset → 5️⃣ 同时打开第二 tab 收到 `'logout'` 消息 → 6️⃣ navigate `/login`。所有 6 步顺序按 PRD §4.1.1e。

---

## §6 · Phase Gate Acceptance (3 层独立验收, 全绿才能 merge)

### Layer 1 · `frontend/scripts/verify_4b1.sh` 12 项自动化检查

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# L1.1 · ESLint
npm run lint

# L1.2 · TS strict
npx tsc --noEmit

# L1.3 · Vitest lib/* 覆盖率 ≥ 80% (本 Session 只 lib/, pages/* 由 4b'.4 聚合)
npx vitest run --coverage --coverage.include='src/lib/**' --coverage.thresholds.lines=80 --coverage.thresholds.functions=80 --coverage.thresholds.branches=80 --coverage.thresholds.statements=80

# L1.4 · Vite build 产物 ≤ 2MB gzipped + 验产物无 msw
npm run build
test "$(du -sb dist/assets/*.js | awk '{sum+=$1} END {print sum}')" -lt 2097152
! grep -r 'msw' dist/ || (echo "❌ msw 进了 production bundle" && exit 1)

# L1.5 · OpenAPI typegen drift
npm run typegen
git diff --exit-code src/lib/api-types.ts || (echo "❌ OpenAPI types 漂移, 跑 npm run typegen 再 commit" && exit 1)

# L1.6 · i18n parity (zh-CN ↔ en-US key 数量必须一致)
node -e "const z=Object.keys(require('./src/i18n/zh-CN.json')); const e=Object.keys(require('./src/i18n/en-US.json')); if (z.length !== e.length) { console.error('❌ i18n key 数不匹配', z.length, e.length); process.exit(1) }"

# L1.7 · ci_check.py Group I I6
python3 scripts/ci_check.py --group I

# L1.8 · selftest 33/33
python3 scripts/ci-harness-selftest.py
# 期望输出: ● selftest: PASS  (33 / 33 fixture expectations met)

# L1.9 · Playwright auth-flow smoke (1 路径, NOT 6)
npx playwright test playwright/auth.spec.ts

# L1.10 · Lighthouse a11y on /, /login (本 Session 只 2 页, 4b'.4 扩 6 路径)
npx lighthouse https://app.preview.genpano.dev/ --only-categories=accessibility --quiet --chrome-flags="--headless"

# L1.11 · DESIGN_TOKENS lint (无硬编码颜色 hex / px 数字 in tsx 文件)
! grep -rE "color:\s*'#[0-9a-fA-F]{3,6}'" src/components src/pages || (echo "❌ 硬编码 hex 颜色" && exit 1)

# L1.12 · Mixpanel events 0 PII (扫 mixpanel.track 调用 不含 email / phone / userId 明文)
node scripts/check-mixpanel-pii.mjs
```

### Layer 2 · Group I selftest 单独验证 (33/33 必绿)

`python3 frontend/scripts/ci-harness-selftest.py` 必须输出:

```
● selftest: PASS  (33 / 33 fixture expectations met)
```

**EXPECTED_POSITIVES 33** = 32 (4b' baseline 的 32) + 1 (I6 新增)。如果命中数 ≠ 33, 说明 I6 fixture 没被抓 (rule 写错) OR 历史 fixture 漂移 — STOP Type B1。

### Layer 3 · Frank 浏览器自验 (preview env: app.preview.genpano.dev/4b1-frontend-foundation)

Frank 必须亲自走以下 3 段旅程, 每段产出截图归档:

- **S1 · Landing → 注册路径**:
  - 访问 `https://app.preview.genpano.dev/4b1-frontend-foundation/`
  - 看 LandingPage 浅色 Stripe + 4 CTA + UTM
  - 点 "免费注册" → /register
  - AuthPage Step 0: 输 email `frank-test@example.com` → submit → 看 lookup 调用耗时 ≥400ms (Network 标)
  - lookup 返回 `{exists: false}` → Step 1 显示注册表单 → 输密码 + submit → 跳 /onboarding

- **S2 · Onboarding 4 步 + 续签**:
  - Step 1 选行业 (美妆个护) → next
  - Step 2 主品牌 (雅诗兰黛) → next
  - Step 3 竞品 (≥2: SK-II + 兰蔻) → next
  - **此时手工刷新页面**, URL 应自动追加 `?resumeStep=3`
  - Step 4 偏好 (locale=zh-CN, email subscribe=true) → 完成 → 302 `/brand/overview`
  - Mixpanel debug 应见 4 个 `onboarding_step_completed` 事件 (#70), props 仅含 `stepNumber` + `durationMs`, NOT 含 email/userId

- **S3 · Settings + 登出 6 步**:
  - 访问 `/settings` → 看 3 Tab
  - 点 "账号" Tab 底部红 "登出" → 观察 Network + Mixpanel debug + dev tools console
  - **6 步顺序验证**: track logout_initiated → POST /api/v1/auth/logout 200 → track logout_completed → mixpanel.reset → BroadcastChannel post → navigate /login
  - 同时打开第二 tab `/brand/overview`, 应自动 302 /login (跨 tab 同步)

**S1/S2/S3 全绿 + Layer 1 / Layer 2 全绿 → Phase Gate PASS, 可 merge main**。

### Phase Gate 收尾 (merge 前)

1. **再跑 §0 Pre-Flight Grep**: 6 条全部命中, 验真相源未漂移
2. **CLAUDE.md 加决策 #N**: "Session 4b'.1 · Frontend Foundation 交付 (2026-XX-XX)" 含 A-G 段 (A 目录 / B 12 文件 / C Y1-Y14 实施 / D Group I I6 / E 偏差登记 / F Phase Gate 验收 / G 下游链)
3. **(可选) `docs/auto-memory/` 加 cross-Session pattern 文件**: 仅当本 Session 产出 cross-Session 可复用 pattern (e.g. Frontend Foundation Y1-Y14 模式 / TanStack Query setup 模式) 时, 写 `docs/auto-memory/{type}_{topic}.md` + `docs/MEMORY.md` 追加一行 index; per-session delivery (Y1-Y14 + Group I 6 条) 详情走 CLAUDE.md 决策 #N, 不单独写 archive 文件 (对齐 A0' 实际落档机制 — A0' Step 12 commit 09014b0 仅写了 cross-Session pattern, 未写 per-session delivery archive)
4. **`docs/SESSIONS_PYTHON.md` 加状态行**: `4b'.1 · Frontend Foundation · GREEN · 2026-XX-XX`
5. **git commit + push**: `git commit -F .git-msg-4b1.txt` (标题 `Session 4b'.1: Frontend Foundation - Phase Gate 3/3 PASS`, body 回引 CLAUDE.md decision #N)
6. **PR 描述含 Layer 3 截图归档链接**

---

## §7 · 下游 Session Note

**4b'.2 GREEN gate**: 本 Session (4b'.1) 必须 PASS。4b'.2 开工前 grep `docs/SESSIONS_PYTHON.md` 须见 `4b'.1.*GREEN`, 否则 STOP Type A4。

**4b'.2 涵盖**: Y15-Y29 Brand Mode 9 sub-views + Citation 5 Tab + Group I I1-I5 chart/page harness rules (selftest 33 → 38)。

**本 Session 留给 4b'.2 的接口**:

- `<ComingSoon />` 占位组件位置 (Sidebar 9 项 NavLink 跳转的目标路由)
- `lib/api.ts` typed client + queryClient 已 ready, 4b'.2 直接 `useQuery` 调 Brand API
- `lib/formatBrand` + i18n 命名空间 already exists, 4b'.2 加 `brand.*` namespace
- Mixpanel `track` helper available, 4b'.2 加 #50-#56 (Citation events)
- ci_check.py Group I 框架 already wired, 4b'.2 直接加 I1-I5 rules + 5 cifixture

---

**Decision-Freshness Final Check (开工前 30 min 内最后一次):**

- ✅ `Session 0' GREEN` ✅ in SESSIONS_PYTHON.md
- ✅ `Session 4a' GREEN` ✅ in SESSIONS_PYTHON.md
- ✅ CLAUDE.md 最近 3 条决策 (#28/#29/#30 之类) 已读, 无 frontend / IA / Auth 影响项
- ✅ PRD §4.6-IA-v2 / §4.1.1-form / §4.1.1d.C / §4.1.1e / §4.10.4a 段号语义稳定 (与本 Prompt §1 一致)
- ✅ DESIGN_TOKENS 浅色 Stripe token 表稳定
- ❌ N2 (Tier CRUD) / N3 (MCP Token) → 本 Session 不引入, 留 A5'
- ✅ Y6 msw dev-only 严格不进 build (Phase Gate L1.4 守)

如有任何 ❌ 项 (除 N2/N3 这种已声明 deferred), STOP Type B7 → 暂停, 回 Frank 对齐。
