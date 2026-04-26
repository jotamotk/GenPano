# PRD ↔ Session ↔ Frontend 一致性 Review

> **目的**：在把 Session Prompt 喂给 Claude Code 之前，确保 PRD / Session / Design Tokens / Harness / Adapter Contract 描述的是同一个产品，避免产出偏离 PRD、出现运行期错误或视觉碎裂。
>
> **审阅文档**（共 17 份，约 1.3MB）：
> `PRD.md` · `CLAUDE_CODE_SESSIONS.md` · `ADMIN_PRD.md` · `ADMIN_PRD_B_PIPELINE.md` · `ADMIN_PRD_C_KG.md` · `ADMIN_CLAUDE_CODE_SESSIONS.md` · `HARNESS_ENGINEERING.md` · `ADAPTER_CONTRACT.md` · `DESIGN_TOKENS.md` · `DASHBOARD_REDESIGN_PROPOSAL.md` · `LANDING_REDESIGN.md` · `DESIGNER_AGENT.md` · `DESIGNER_AGENT_CAPABILITIES.md` · `GROWTH_PLAN.md` · `PRODUCT_PLAN.md` · `PRD_TEST_DATA_V1.md` · `TEST_STRATEGY.md`
>
> **Review 日期**：2026-04-20
> **状态**：初稿，待 Frank 逐项确认后再触发修订

---

## 0. Elevator Summary（读前摘要）

**整体判断：产品结构健壮，可在 1–2 天内达到"可直接喂 Session 给 Claude Code 编码"的状态。**

- **五条审阅轴**：
  - (A) Consumer PRD ↔ Consumer Session：**覆盖面完整**，有 2 个路由/组件级 P0（`/dashboard` 去留矛盾）。
  - (B) Admin PRD ↔ Admin Session：**零 P0、零 Scope Creep**，覆盖率 100%，P1 偏"澄清"而非"修复"。
  - (C) Design Tokens 覆盖：**5 个 P0**（引用但未定义的 token）是最容易引发编码期静默 Bug 的类别。
  - (D) Harness / Adapter Contract：**4 个 P0**（字段/端点不存在或命名冲突），会直接导致运行期报错。
  - (E) 前端功能 ↔ 后端数据设计支撑度（新增）：**4 个 P0** —— KPI 快照表、Citation 归因表、Heatmap 聚合视图、Response 去规范化索引全部缺失，Dashboard / Topics / Drilldown 三大核心页跑不起来或会超时。

- **总计**：**15 P0**（必须修）· **21 P1**（建议修）· **19 P2**（可延后）。
- **预估修订工时**：P0 全修 ≈ 6–8 小时（含 E 区的 DDL 和 rollup 设计）；P0+P1 全修 ≈ 14–16 小时。
- **建议先修顺序**：**E 区（后端数据模型）** → D 区（Harness/Adapter）→ C 区（Design Tokens）→ A 区（路由/组件）→ B 区（澄清文案）。
- **关键点**：E 区的 P0 不修，就算 A/C/D 全部对齐，前端跑起来也会是空白或超时；E 区必须**最先**解决。

### 严重度定义

| 级别 | 含义 | 对 Session → Claude Code 的影响 |
|---|---|---|
| **P0** | 直接导致编译/运行期错误或前后端 Schema 不一致 | 必须在投喂 Session 前修复；否则 Claude Code 产出必然失败或功能错位 |
| **P1** | 歧义、潜在 Bug、行为不确定 | 建议修复；否则 Claude Code 会做出一个合理但不一定符合 PRD 的选择 |
| **P2** | 命名、风格、冗余、可维护性 | 不修也能跑；但将来扩展/回归测试会变累 |

---

## 1. 如何使用这份 Review（给 Frank）

1. **逐条阅读**每一项 Finding，在 `[ ] 同意 / [ ] 不同意` 处打勾。
2. **同意的**：我将按"建议修复"里的 diff 直接改到各源文件。
3. **不同意的**：请在条目下简短写明你想怎么处理（保留现状 / 走另一种方案 / 延到 v1.1 等）。
4. 第 7 章有一张"Ready-to-Session Gate"表，全部 P0 勾选为"已修复"之前，**不建议**把任何 Session 投给 Claude Code。
5. Review 一旦定稿，我会根据确认清单批量修订原文档，然后再出一份"修订 diff 摘要"给你做最终复核。

---

## 2. A 区：Consumer PRD ↔ Consumer Session

审阅文件：`PRD.md`（~6900 行）· `CLAUDE_CODE_SESSIONS.md`（~4950 行）。

### A-P0-1 · 登录后默认路由矛盾（`/dashboard` 已被废除 vs Session 仍跳回）

- **PRD 定义**（PRD.md §4.6.1-0 / §4.6-IA-v2 路由总表）：
  > `/dashboard` 路由被整个废除, 登录后直接进 `/brand/overview`；`/dashboard → 301 /brand/overview`。
- **Session 现状**（CLAUDE_CODE_SESSIONS.md §2b.4 "LandingPage 快速创建项目按钮"）：
  > `navigate('/dashboard')` when `projects.length > 0`
- **影响**：登录后被导向已废弃路由。
- **建议修复**：Session 里 `navigate('/dashboard')` → `navigate('/brand/overview')`；同时在 Harness 加 grep 规则，禁止 `navigate('/dashboard')` 再出现。
- **Frank 确认**：`[ ] 同意 / [ ] 不同意`，批注：_______________

### A-P0-2 · `/dashboard` 到底存不存在（Session T1 的 Daily Digest Spike 和 PRD 直接冲突）

- **PRD 定义**：§4.6.1-0 明确标记 "⛔ SUPERSEDED — `/dashboard` 路由废除"。
- **Session 现状**：Session T1 (Spike S1) 仍在实现 `/dashboard` 的两种布局（Daily Digest + Action Center）、含 `?layout=` 切换器与 DevMenu。
- **影响**：MVP 产出一个 PRD 里已经死掉的页面。
- **建议修复**（二选一）：
  - **(A) 推荐**：删除 Session T1，页面仅保留 `/dashboard → 301 /brand/overview`。
  - **(B)** 如果你想保留 Daily Digest 做 Spike，把它明确标注为 v1.1、并且**不在 MVP Session 序列里**。
- **Frank 确认**：`[ ] A（删除） / [ ] B（延到 v1.1） / [ ] 其他：___________`

### A-P1-1 · Topic 更新端点 HTTP 方法不一致（PUT vs PATCH）

- **PRD**（§4.5.1）：`PUT /api/v1/projects/:id/topics/:topicId`
- **Session**（Session 2, Task 4）：`PATCH /api/v1/projects/:id/topics/:tid`
- **影响**：前端发 PATCH 时后端可能只接受 PUT，返回 405；或相反。
- **建议修复**：统一为 **PATCH**（"标记为关键/忽略"本质是部分字段更新，语义更贴 PATCH）。同步改 PRD §4.5.1。
- **Frank 确认**：`[ ] 用 PATCH（推荐） / [ ] 用 PUT / [ ] 其他`

### A-P1-2 · Profile Group 端到端覆盖"被打散"，缺 Harness 强制校验

- **PRD**：§4.2.3a 和 §4.6.1a 把 Profile Group 定为"一等公民维度"，要求所有 Brand 详情 / Diagnostics / Topics 页都有 `<ProfileGroupFilter>`。
- **Session**：`profile_groups` 表建表在 Session 2，API 在 Session 3，组件规格在 Session 4b——**没有单独的 Harness 规则**去保证"三个目标页都接入了 filter"。
- **影响**：可能只有一个页面真的挂上了 ProfileGroupFilter，另外两个静默漏装。
- **建议修复**：在 Session 4b 的"验收标准"里加 grep 断言：
  ```bash
  grep -l '<ProfileGroupFilter' src/pages/BrandDetailPage.jsx src/pages/TopicsPage.jsx src/pages/DiagnosticsPage.jsx | wc -l  # 必须 = 3
  ```
- **Frank 确认**：`[ ] 同意 / [ ] 不同意`

### A-P1-3 · 如 A-P0-2 选"保留 Daily Digest"，则缺验收规则

- 若选择保留 Session T1，则 Daily Digest / Action Center 的 Harness 规则缺失：没有断言 Delta Cards KPI 数量、没有断言 Action Queue 与 Diagnostics 的数据一致性。
- **建议修复**：加 Harness 规则到 `scripts/ci-check.mjs`；或者一开始就按 A-P0-2 (A) 方案删掉 Spike。
- **Frank 确认**：_由 A-P0-2 决议驱动_

### A-P2-1 · "Spike" 和 "Session T" 命名混用

- 文档里既有 `Session T3 (triad-S3)` 又有 `Session T1 (Spike S1)`，定义不统一。
- **建议修复**：在文档开头加一行术语表，统一为"Session Tn = Spike Sn"，或只保留一种。
- **Frank 确认**：`[ ] 同意`

### A-P2-2 · `/dashboard` 301 跳转缺 CI 校验

- 建议加 CI 检查：`curl -I /dashboard | grep -q '301\|Location.*brand/overview'`。
- **Frank 确认**：`[ ] 同意`

### A-P2-3 · Drilldown Drawer 未明确引用 Design Tokens

- Session T3 里 `KpiDrilldownDrawer.jsx` 没有显式强调"必须用 `--color-*` token"，容易被硬编码。
- **建议修复**：在 Session T3 加一句：Drawer 左色条、sentiment chips、badge 颜色必须来自 DESIGN_TOKENS.md，不得硬编码 hex/rgba。
- **Frank 确认**：`[ ] 同意`

### A-P2-4 · Auth 端点在 Session 里没有汇总表

- 7 个端点（lookup/register/verify-email/forgot-password/reset-password/logout/refresh）目前散落在 Session 4a 各处，建议在 §4a 开头加一张汇总表。
- **Frank 确认**：`[ ] 同意 / [ ] 可延后`

---

## 3. B 区：Admin PRD ↔ Admin Session

审阅文件：`ADMIN_PRD.md` · `ADMIN_PRD_B_PIPELINE.md` · `ADMIN_PRD_C_KG.md` · `ADMIN_CLAUDE_CODE_SESSIONS.md`（共 10 个 Session：A0–A4）。

### 总体评价（好消息）

- **PRD 覆盖率 100%**：基础 PRD、Pipeline 子 PRD、KG 子 PRD 的每一章都能在 Session 里找到对应任务。
- **反向覆盖率 100%**：每个 Session 都能回指 PRD 某节，**无 Scope Creep**。
- **数据契约健康**：15+ 张表在三个文档（ADMIN_PRD、ADAPTER_CONTRACT、Session）中定义一致。
- **权限矩阵一致**：`super_admin / analyst / kg_reviewer / cost_admin` 四种角色配合 `requireRole + withAudit` 中间件。
- **KG 9 类实体 + 属性**（brands / products / aliases / trust scores / merge logs 等）Session 全部实现。
- **Pipeline 失败模式 F1–F12** 全部有 "模块 → 动作" 映射（如 F1 COOKIE_EXPIRED → Tracker 告警 → Planner 账号池调整）。

**→ 结论：Admin 侧目前没有 P0，可以直接投 Session。**

### B-P1-1 · `PARSER_FAIL` 归属分类不明

- ADAPTER_CONTRACT 定义 8 种错误码，其中 `PARSER_FAIL` 在 ADMIN_PRD_B 的"重试规则表"里缺失。
- 隐含由 Analyzer 的 `parse_status` 处理，不走 Tracker。
- **建议修复**：在 ADMIN_PRD_B 的重试规则表里显式写"PARSER_FAIL: 不进 Tracker 重试池，由 Analyzer `parse_status` 单独兜底"。
- **Frank 确认**：`[ ] 同意`

### B-P1-2 · 测试数据 Seeding 策略未指定

- Session A2 / A2.1 引用了具体量级（128K Attempts、1560 Topics），但没说"这些数据**怎么来**"。候选方案：
  - (a) 用 `PRD_TEST_DATA_V1.md` 里的 fixtures；
  - (b) 写 seed migration；
  - (c) HAR replay 回放真实数据。
- **建议修复**：在 Session A2 Prompt 第一段明确写："Seeding 使用 `PRD_TEST_DATA_V1.md` §X 的 fixtures，通过 `npm run seed:admin` 注入 SQLite dev DB"。
- **Frank 确认**：`[ ] 用 (a) / [ ] 用 (b) / [ ] 用 (c)`

### B-P1-3 · KG LLM 预算没和 Pipeline 成本系统对齐

- ADMIN_PRD_C §4.1 定义了 KG 单独的 LLM 预算门控；ADMIN_PRD §4.4 的整体成本追踪没有明确把 KG 预算计入。
- **建议修复**：在 A4 Prompt 补一句"KG 预算和 Pipeline 预算各自独立硬约束，但都上报到 `/admin/cost-dashboard` 的同一张表，仅 `budget_scope` 字段区分"。
- **Frank 确认**：`[ ] 同意`

### B-P2-1 · "生成管线" 侧边栏文案歧义

- 侧边栏 label 容易被读成"3 个独立页面"，实际是"1 页 3 Tab"。
- **建议修复**：ADMIN_PRD_B §1.2 的标题加注 "（单页，三层 Tab）"。
- **Frank 确认**：`[ ] 同意`

### B-P2-2 · Admin 侧未强制引用 Design Tokens

- Admin Session 指定了 Recharts / Monaco / AntV G6 组件库，但**没有强调**颜色/间距/字体必须来自 `src/theme/tokens.ts`。
- **建议修复**：在每个 Admin Session Prompt 末尾加一行："所有颜色/间距/字体必须来自 `src/theme/tokens.ts`，禁止硬编码 hex/px/font-family"。
- **Frank 确认**：`[ ] 同意`

---

## 4. C 区：Design Tokens 覆盖

审阅文件：`DESIGN_TOKENS.md` vs 全部 PRD / Session 里出现的视觉引用。

### Token 清单（现状）

| 类别 | 数量 |
|---|---|
| Color | 53 |
| Typography | 13 |
| Radius | 8 |
| Shadow | 5 |
| Gradient | 3 |

结构完整，但**几个被 Session 主动引用的 token 没在 DESIGN_TOKENS.md 里定义**——这是最会让 Claude Code 静默出 Bug 的类别。

### C-P0-1 · `--color-overlay-drawer` 定义缺失（P0）

- DESIGN_TOKENS.md §C8（第 208 行）引用："Drawer overlay backdrop: `rgba(28,29,34,0.42)`, token `--color-overlay-drawer`"。
- 但**颜色表里根本没有这个 token**。
- **建议修复**：在 DESIGN_TOKENS.md 颜色表加入 `--color-overlay-drawer: rgba(28, 29, 34, 0.42);`
- **Frank 确认**：`[ ] 同意`

### C-P0-2 · `--drawer-width-desktop / --drawer-width-tablet-max` 缺失（P0）

- §C8 规定 desktop 560px / tablet `min(560px, 80vw)` / mobile 100vw；C8-1 grep 规则禁止 `w-[620px]` 硬编码——但**这些尺寸本身没变成 token**。
- **建议修复**：在 DESIGN_TOKENS.md 加"Drawer Dimensions"段：
  ```css
  --drawer-width-desktop: 560px;
  --drawer-width-tablet: min(560px, 80vw);
  --drawer-width-mobile: 100vw;
  --drawer-animation-duration: 220ms;
  ```
- **Frank 确认**：`[ ] 同意`

### C-P0-3 · `--color-danger` 未定义但已被 Session 引用（P0）

- Session 第 1863 行提示："若 token 不存在, 先... 补 `--color-danger: #DC2626`"；第 2095 行 logout 按钮 `color: var(--color-danger)` 直接用了它。
- **建议修复**：加 `--color-danger: #DC2626;` 到语义色段。
- **Frank 确认**：`[ ] 同意`

### C-P0-4 · `--color-scrim` 未定义（P0）

- Session 第 2184 行："如果本 Session 要加弹窗, 顺手在 DESIGN_TOKENS 里补 `--color-scrim`"。
- **建议修复**：加 `--color-scrim: rgba(0, 0, 0, 0.4);`
- **Frank 确认**：`[ ] 同意`

### C-P0-5 · `--color-text-on-accent` 未定义（P0）

- Session 第 1738 行按钮样式 `color: 'var(--color-text-on-accent)'` 被引用。
- **建议修复**：加 `--color-text-on-accent: #FFFFFF;`
- **Frank 确认**：`[ ] 同意`

### C-P1-1 · Heatmap token 和 Dashboard Redesign 的 chart token 可能冲突

- 当前：`--color-heatmap-seq-0..5` + `-div-neg-2..pos-2`（11 个 token）。
- 提案（DASHBOARD_REDESIGN_PROPOSAL §4.2）：`chart-primary / chart-neutral-* / chart-positive / chart-negative`。
- **风险**：Session 在实现时可能挑错 token 家族。
- **建议修复**：在 DESIGN_TOKENS 明确："`BrandTopicHeatmap` 只使用 `--color-heatmap-*`，其他图表使用 `--color-chart-*`"；加 C9 grep 规则。
- **Frank 确认**：`[ ] 同意 / [ ] 不同意（保留灵活性）`

### C-P1-2 · Accent 主色"未锁定"

- 当前生产值：`--color-accent: #605BFF`。
- DASHBOARD_REDESIGN_PROPOSAL 提了 3 个替代色（Ink Navy / Claret / Electric Blue），但状态是"提案阶段"。
- **风险**：Claude Code 不知道该为换主题留接口还是就用 #605BFF。
- **建议修复**：在 DESIGN_TOKENS.md 加一段"Current production: #605BFF（唯一生效）。Future candidates listed in DASHBOARD_REDESIGN_PROPOSAL, 不在 MVP 开关。"
- **Frank 确认**：`[ ] 同意（锁 #605BFF） / [ ] 要留换主题能力`

### C-P1-3 · Landing 的 inline rgba 应 token 化

- LANDING_REDESIGN §1.6：dot pattern `rgba(96,91,255,0.05)`、glow `rgba(96,91,255,0.10) + rgba(139,92,246,0.06)`——全部 inline。
- 风险：主色一变，glow 效果自己会脱钩。
- **建议修复**：新增 token `--color-accent-alpha-05 / -10`、`--color-accent-2-alpha-06`。
- **Frank 确认**：`[ ] 同意`

### C-P2 (合并)：命名与覆盖细节

- Sentiment token `sentiment.positive` 和 `--color-chart-2` 用途边界模糊 → 建议加用法注释。
- 缺 `--color-success-hover / --color-danger-hover` → 会强制 Claude Code 硬编码；建议按各自 base +10% Shade 定义。
- Spacing 目前依赖 Tailwind 的 `p-1/p-2`，和 color/radius 的"显式 token"路径不一致 → 建议至少在 DESIGN_TOKENS 里列出映射。
- `--color-engine-*` 定义了但 Session 从未引用 → 保留做未来 engine switcher，可接受。
- **Frank 确认**：`[ ] 一揽子同意 / [ ] 逐条审（告诉我逐条做）`

---

## 5. D 区：Harness Engineering + Adapter Contract

审阅文件：`HARNESS_ENGINEERING.md` · `ADAPTER_CONTRACT.md` · 两份 PRD · 两份 Session · `TEST_STRATEGY.md`。

> 这一区是**最容易在 Claude Code 编码时炸的**——字段名不一致、端点没定义、响应 Schema 缺失，都会在跑起来那一刻才暴露。

### D-P0-1 · `profileGroupId` vs `profileGroupIds` 命名冲突（严重）

- ADAPTER_CONTRACT §2.1 第 100 行：`profileGroupId: string | null`（单数、可空）。
- Session 第 895 行："`profileGroupIds[]` 冗余存储"（复数、数组）。
- PRD §4.2.3a 第 1958 行：`profileGroupIds: string[]`。
- **后果**：Session 1.2 的 `adapter.execute(query, ctx)` 里 `query.profileGroupId` 为 `undefined`，要么 NullPointerException，要么埋下静默错误。
- **建议修复**：统一为**复数数组** `profileGroupIds: string[]`；
  - 改 ADAPTER_CONTRACT §2.1、§3.3（sampling 签名）、§3.4、§6.2、§10.1 全部引用；
  - 单数语义（"指定单一 group"）用数组长度 =1 表达；
  - `null` → 改为空数组 `[]` 代表"任意"。
- **Frank 确认**：`[ ] 统一 plural（推荐） / [ ] 统一 singular / [ ] 其他`

### D-P0-2 · Topic 更新端点方法不统一（与 A-P1-1 同条）

- 见 §2 A-P1-1。跨文档一致修。

### D-P0-3 · `POST /api/auth/logout` 响应 status 未定义

- PRD 第 1269 行："返回 204 No Content (无 body)"。
- ADAPTER_CONTRACT / openapi.yaml 未定义。
- **风险**：前端 `resp.json()` 在 204 上会抛错；登出后本地状态清理链路断。
- **建议修复**：
  1. openapi.yaml 加 `/auth/logout: post: responses: 204/401`；
  2. Session 4a Prompt 补："前端收到 204 **不得**调 `.json()`，直接清 local state"；
  3. TEST_STRATEGY §2.1 加 grep：`grep -n "response.json()" src/auth/*.ts | grep -E "logout" && exit 1`。
- **Frank 确认**：`[ ] 同意`

### D-P0-4 · `DELETE /api/users/me` 端点只在 PRD 里提过，从未被定义

- PRD 第 1326 行："调 `DELETE /api/users/me` + 强制登出"；第 1343 行 `user_deletion_requested` event 引用。
- ADAPTER_CONTRACT / Session 4a / openapi.yaml 全没定义 → 请求体、响应码、副作用（立即删除 vs 30 天窗口）全未知。
- **建议修复**：
  - 在 openapi.yaml 里加：`DELETE /users/me`, request `{ reason?: string }`, response `204`；
  - Session 4a 补充"Side effect: `User.deletion_requested_at = now()`, revoke all sessions；30 天撤回窗口"；
  - TEST_STRATEGY Phase 3 加 E3 回归：已删除账号走 forgot-password 必须得到"账号已删除"而不是"重置链接"。
- **Frank 确认**：立即删除 / 30 天窗口？**需要你定一下**：`[ ] 立即硬删 / [ ] 30 天窗口 / [ ] 其他`

### D-P1-1 · `profileGroupId = null` 的调度语义未定义

- 当 `ExecutableQuery.profileGroupId = null`、`Profile.segmentGroup = luxury_collector`、`Account.segmentGroup = beauty_daily` 三者冲突时，scheduler 应该：(A) 拒绝 NO_ACCOUNT_AVAILABLE / (B) 重新采样一个匹配的 Profile / (C) 忽略约束？
- **建议修复**：ADAPTER_CONTRACT §3.3 明确："null = 采样任意 Profile；但采样后 Profile.segmentGroup **必须**与 SelectAccount().segmentGroup 匹配；若无匹配账号则返 NO_ACCOUNT_AVAILABLE、不重试、Query 置 PENDING。"
- **Frank 确认**：`[ ] 同意 / [ ] 用 (B) / [ ] 用 (C)`

### D-P1-2 · `BrowserProfile.profileId` vs `ExecutableQuery.profileGroupId` 概念冲突

- `profileId` = 单个 Profile 实例 ID；`profileGroupId` = Group 成员身份 → 两个正交概念但命名相似，Analytics join 时极易把 "1 profile = 1 group" 误当。
- **建议修复**：把 `BrowserProfile.profileId` 重命名为 `instanceId`；加 grep 规则禁止 `profileId.*profileGroup` 同行出现。
- **Frank 确认**：`[ ] 同意重命名 / [ ] 不改（加注释足够）`

### D-P1-3 · `AIResponse.profile` snapshot 语义未定义

- AIResponse 里带了一份 profile 副本，但没说是引用还是 deep-copy；如果 adapter 内部 mutate 了 `ctx.profile`，后续分析会读到被改过的值。
- **建议修复**：在 ADAPTER_CONTRACT §2.2 明确 "AIResponse.profile 是 execute() 返回时对 ctx.profile 的不可变深拷贝；adapter 禁止 mutate ctx.profile"。实现层用 `Object.freeze({...ctx.profile})`。
- **Frank 确认**：`[ ] 同意`

### D-P1-4 · 重试次数文案歧义

- ADAPTER_CONTRACT §6.1 "最多 3 次" 在 §6.2 的代码里是 `while (attempt < 3)` → 实际 "1 原始 + 2 重试 = 3 total attempts"。
- **建议修复**：改文案为 "最多 3 次 attempt（1 原始 + 2 重试），指数退避 2s/4s"；ADMIN_PRD 查询详情页显示 "Failed after 2 retries (3 attempts total)"。
- **Frank 确认**：`[ ] 同意`

### D-P1-5 · `ExecutableQuery` 字段 required / optional 未显式标注

- 10 个字段没有"必填 / 可选 / 默认值"的表格；openapi.yaml 自动生成时极易错。
- **建议修复**：在 ADAPTER_CONTRACT §2.1 加显式字段表（见"Contract Audit"附录），并同步 openapi.yaml。
- **Frank 确认**：`[ ] 同意`

### D-P1-6 · `GET /api/v1/profile-groups` 响应 Schema 未定义

- Session 提"返回 6–10 个预置 group"，但没有 interface / 字段清单 → 前端猜响应形状必然和后端不一致。
- **建议修复**：在 ADAPTER_CONTRACT 新开 §2.3（API Data Shapes），或在 Session 3 Prompt 里加：
  ```ts
  interface ProfileGroupResponse {
    id: string;          // 'pg_young_female_tier1'
    nameZh: string; nameEn: string;
    description: string;
    industryScope?: string[];
    isDefault: boolean;
  }
  // GET /api/v1/profile-groups → ProfileGroupResponse[]
  ```
- **Frank 确认**：`[ ] 同意`

### D-P2 合集

- **D-P2-1**：API 路径参数风格混用（`:id` 与 `{id}` 同文档里都出现）→ 统一 `:id`，加 grep 规则。
- **D-P2-2**：`ExecutableQuery`（DTO）vs `platform_queries`（表）vs "Query"（泛指）命名冲突 → 建议表改名 `query_executions`，代码注释里严格区分。
- **D-P2-3**：`intent` enum 存储类型未声明（VARCHAR vs INT），跨服务传输可能出现 "1" vs "informational"。建议在 ADAPTER_CONTRACT §2.1 明示 "字符串传输、VARCHAR(50) 存储、禁止数字编码"。
- **D-P2-4**：`ParsedCitation.extractedBy` 只列了 4 个值（footnote / reference_card / citation_tooltip / inline_link），Gemini / Perplexity / Kimi 等后续引擎可能需要 `api_structured / hover_card / unknown`，Phase 2 会被迫回改。建议现在就加上。
- **Frank 确认**：`[ ] 一揽子同意 / [ ] 逐条审`

---

## 6. E 区：前端功能 ↔ 后端数据设计支撑度（新增）

> 这一区回答 Frank 明确追加的问题："前端的功能，后端的数据设计是可以支持的吗？"
>
> 审阅方法：逐个过 Consumer PRD / Admin PRD 里的**每个核心页面组件**（Dashboard KPI 卡、Heatmap、Drilldown Drawer、Topics 列表、Brand 提交、报告订阅等），反查后端是否有**对应的表 / 索引 / 预聚合视图 / 端点 / 权限 / 批量接口**。
>
> **结论：这是全项目最危险的一区——4 个 P0 都会让前端在生产数据量下直接"渲染空白"或"请求超时"，而且 PRD 与 Session 里没有任何 Schema 定义。**

### E-P0-1 · KPI 快照表 / Rollup 策略完全缺失（严重）

- **前端位置**：PRD §4.6.1a（Dashboard 5 张 KPI 卡）+ §4.6.1b-C.2.2a（Brand Mode KPI 卡）。每 30s 刷新一次，显示大数字 + 变动箭头 + 7 日 sparkline。
- **后端缺口**：
  - PRD §4.0 提到 `MetricSnapshot (平台级)` 但 **schema 从未物化**；
  - Session 0 建表脚本里只写了 `metric_snapshots` 这个名字，**字段、更新频率、聚合规则全缺**；
  - 若按当前写法直接跑，每次刷新会对 `ai_responses` 做全表扫描 → 数据量上百万后秒级超时。
- **建议修复**：在 Session 2 任务里新增"计算层"子任务，落地：
  ```sql
  CREATE TABLE metric_snapshots (
    id UUID PRIMARY KEY,
    brand_id UUID NOT NULL,
    project_id UUID NOT NULL,
    engine_id VARCHAR,           -- NULL = 全引擎聚合
    profile_group_id VARCHAR,    -- NULL = 全 Profile 聚合
    period_start TIMESTAMPTZ,
    period_end TIMESTAMPTZ,
    mention_rate  DECIMAL(5,3),  -- 0..1
    sentiment_score DECIMAL(3,2),-- -1..+1
    ranking INT,
    sov DECIMAL(5,3),
    citation_share DECIMAL(5,3),
    sample_count INT,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
  );
  CREATE INDEX idx_ms_brand_period ON metric_snapshots(brand_id, period_start, period_end);
  CREATE INDEX idx_ms_proj_period  ON metric_snapshots(project_id, period_start, period_end);
  -- 批处理：每日 02:00 UTC 重算昨日；当日数据小时级 cache。
  ```
- **Frank 确认**：`[ ] 同意上述 schema / [ ] 先简化到只 mention_rate+sentiment / [ ] 其他`

### E-P0-2 · Citation 归因表缺失 + 品牌域名匹配规则未定义（严重）

- **前端位置**：PRD §4.2.6（Citation extraction）+ §4.6.1a（`citation_share` KPI 卡）+ Admin §4.2.1–4.2.6（Admin 监控 `PARSER_FAIL`）。
- **后端缺口**：
  - ADAPTER_CONTRACT §2.1 有 `ParsedCitation` TS 接口，但**没有持久化表**；
  - §4.2.6.E 公式 C（`brandsAttributed`）依赖"citation 域名 = brand 域名"的**匹配规则从未写过**（eTLD+1？alias 处理？lookalike？）；
  - 结果：`citation_share` KPI 永远返回 `null` 或 `0`。
- **建议修复**：
  ```sql
  CREATE TABLE ai_response_citations (
    id UUID PRIMARY KEY,
    response_id UUID NOT NULL REFERENCES ai_responses(id),
    url VARCHAR NOT NULL,
    domain VARCHAR NOT NULL,        -- eTLD+1 归一化
    brand_id UUID,                   -- NULL = 未归因
    confidence DECIMAL(3,2),
    extraction_method VARCHAR,       -- footnote/inline/card/...
    created_at TIMESTAMPTZ
  );
  CREATE INDEX idx_citation_response_brand ON ai_response_citations(response_id, brand_id);
  CREATE INDEX idx_citation_domain_brand   ON ai_response_citations(domain, brand_id);
  ```
  且 ADAPTER_CONTRACT §2.6（新节）要写清匹配算法：先 eTLD+1 精确；再走 `kg_brand_domains` 别名映射；最后 fuzzy（Levenshtein ≤ 2）兜底，置信度 < 0.6 记 `candidate`。
- **Frank 确认**：`[ ] 同意 / [ ] 只做精确匹配、不做 fuzzy`

### E-P0-3 · Heatmap 二维聚合没有物化视图 / 索引策略（严重）

- **前端位置**：PRD §4.6.1b-C（Brand Mode Sentiment / Visibility Heatmap）、Admin §4.3（KG 监控 Heatmap）。20×10 到 50×10 的网格，每格 `COUNT(*)` + `AVG(sentiment)`，可按日期 / profile_group / engine 筛。
- **后端缺口**：
  - `brand_mentions` / `product_mentions` 表在 Session 0 提了名字，**无外键、无索引、无聚合视图**；
  - 前端要求 < 2s 渲染；无索引时单格 > 100ms，50×10 网格并行请求也要 > 5s。
- **建议修复**：
  ```sql
  CREATE MATERIALIZED VIEW heatmap_mention_agg AS
  SELECT
    topic_id, brand_id, engine_id, DATE(created_at) AS date,
    COUNT(*)        AS mention_count,
    AVG(sentiment)  AS avg_sentiment,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY sentiment) AS median_sentiment
  FROM brand_mentions
  GROUP BY topic_id, brand_id, engine_id, DATE(created_at);
  CREATE INDEX idx_heatmap_topic_date  ON heatmap_mention_agg(topic_id, date);
  CREATE INDEX idx_heatmap_brand_date  ON heatmap_mention_agg(brand_id, date);
  CREATE INDEX idx_heatmap_engine_date ON heatmap_mention_agg(engine_id, date);
  -- 每小时 REFRESH MATERIALIZED VIEW CONCURRENTLY；日切后全量重算一次。
  ```
- **Frank 确认**：`[ ] 同意物化视图方案 / [ ] 改用 ClickHouse / 列存 / [ ] 先用 app 层 in-memory cache`

### E-P0-4 · Response 去规范化缺失，Drilldown Drawer 必超时

- **前端位置**：PRD §4.6.1a-drilldown（Topics 页 Top Prompts / Top Topics / Sentiment / Citations 列表）；Admin §4.2.6（重试中心"Top 10 未配对 Prompts"）。
- **后端缺口**：
  - `ai_responses` 存 `rawText`，**没有 `detected_brand_ids[]` / `detected_topic_ids[]` 两个 GIN 可索引数组**；
  - "列出包含 Brand X、Topic Y、sentiment > 0.5 的 Responses"只能 JOIN + LIKE，百万行量级下秒级不返。
- **建议修复**：
  ```sql
  ALTER TABLE ai_responses ADD COLUMN detected_brand_ids UUID[];
  ALTER TABLE ai_responses ADD COLUMN detected_topic_ids UUID[];
  CREATE INDEX idx_response_brands_gin ON ai_responses USING GIN (detected_brand_ids);
  CREATE INDEX idx_response_topics_gin ON ai_responses USING GIN (detected_topic_ids);
  -- 解析 Hook：adapter 解析完 rawText 之后，调用 EntityExtractor 同步填入两列。
  ```
- **Frank 确认**：`[ ] 同意 / [ ] 改走倒排搜索引擎（Meilisearch/Elastic）`

### E-P1-1 · `projectId` scope 过滤在 API 层没兜底

- **前端位置**：PRD §4.1.1-gate C（Access matrix）、§4.6（SoV 计算按当前 project 的 competitors 作分母）。
- **后端缺口**：`GET /api/brands/:id` 没强制 `projectId` 校验；若 brand 不在 project scope 内后端依然返回 200。
- **建议修复**：改为 `GET /api/v1/projects/:projectId/brands/:brandId`；越界返 403；SoV 分母按 `primaryBrandId + competitorBrandIds` 汇总。
- **Frank 确认**：`[ ] 同意`

### E-P1-2 · Brand Ranking（SoV 排名）无物化，标记会漂移

- **前端位置**：PRD §4.6 brand 卡 "排名 #4" badge + DESIGN_TOKENS C7（`ranking === sort_index + 1`）。
- **后端缺口**：ranking 当前是 mock 里的字段，DB 无对应视图；实时算只能 window function 全扫。
- **建议修复**：
  ```sql
  CREATE MATERIALIZED VIEW brand_rankings AS
  SELECT project_id, date, engine_id, brand_id,
         ROW_NUMBER() OVER (PARTITION BY project_id, date, engine_id
                            ORDER BY mention_count DESC) AS ranking
  FROM brand_mention_daily_agg;
  CREATE INDEX idx_brank_proj_date ON brand_rankings(project_id, date);
  ```
- **Frank 确认**：`[ ] 同意 / [ ] 只在 Dashboard 首屏预聚合`

### E-P1-3 · `platform_topics` 表只在 Session 0 留了名字，字段全缺

- **前端位置**：PRD §4.2 Planner 生成 Topic；§4.6 Dashboard 显示"监控 47 Topics"。
- **后端缺口**：`text_zh / text_en / dimension / intent / confidence / source / status` 全未定义；"获取 Topic 列表"的端点也没有。
- **建议修复**：
  ```sql
  CREATE TABLE platform_topics (
    id UUID PRIMARY KEY,
    brand_id UUID NOT NULL REFERENCES kg_brands(id),
    product_id UUID, category_id UUID,
    dimension VARCHAR CHECK (dimension IN ('品类','品牌','产品')),
    text_zh TEXT NOT NULL, text_en TEXT NOT NULL,
    intent VARCHAR,           -- informational|commercial|transactional|navigational
    status VARCHAR DEFAULT 'active', -- active|archived|deprecated
    confidence DECIMAL(3,2),
    source VARCHAR,           -- planner_generated|user_submitted
    created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ
  );
  CREATE INDEX idx_topic_brand_status ON platform_topics(brand_id, status);
  CREATE INDEX idx_topic_dimension    ON platform_topics(dimension);
  ```
  并在 ADAPTER_CONTRACT §2.3 补 `GET /api/v1/projects/:projectId/topics?status=active`。
- **Frank 确认**：`[ ] 同意`

### E-P1-4 · ProfileGroup 没持久化，Admin 无法管控

- **前端位置**：Admin 各页显示 `Profile Group: beauty_daily (14 queries today)`。
- **后端缺口**：没有 `profile_groups` / `browser_profiles` 两张表；当前靠 seed 脚本硬编码 6–10 个 group，Admin 无增删改能力。
- **建议修复**：建 `profile_groups (id PK, name_zh, name_en, filter_rules JSONB)` + `browser_profiles (id, profile_group_id FK, locale, timezone, user_agent, platform)`；Admin Session A3 新增 `GET/POST/PATCH /admin/profile-groups`。
- **Frank 确认**：`[ ] 同意 / [ ] MVP 先保持硬编码`

### E-P1-5 · Brand 提交 / 自动发现 没有落表、没有状态机

- **前端位置**：PRD §4.1.2 Brand Submission Modal；Admin §4.3.2 Brand Audit；ADAPTER_CONTRACT §KG "候选节点"。
- **后端缺口**：没有 `brand_submissions`（user 提交流）、没有 `brand_discovery_logs`（LLM 自动发现流）、没有 state machine（pending→verified→approved / rejected / merged）、没有"品牌通过后触发 Planner 首日采集"的 hook。
- **建议修复**：建两张表（略见下）+ 在 Admin Session A3 / A4 里补 "approve 时 enqueue planner.bootstrap(brandId)"。
  ```sql
  CREATE TABLE brand_submissions (
    id UUID PRIMARY KEY, user_id UUID REFERENCES users(id),
    brand_name_zh TEXT NOT NULL, brand_name_en TEXT,
    industry_id UUID REFERENCES kg_industries(id),
    status VARCHAR DEFAULT 'pending',
    llm_verification_result JSONB,
    admin_operator_id UUID, rejection_reason TEXT,
    merged_into_brand_id UUID,
    created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ
  );
  CREATE TABLE brand_discovery_logs (
    id UUID PRIMARY KEY,
    source_response_id UUID REFERENCES ai_responses(id),
    discovered_brand_name TEXT,
    confidence DECIMAL(3,2),
    llm_context JSONB,
    status VARCHAR DEFAULT 'candidate',
    created_at TIMESTAMPTZ
  );
  ```
- **Frank 确认**：`[ ] 同意`

### E-P2 合集（Polish / Phase 2）

- **E-P2-1 品牌 Mention 别名去重**：`kg_brands.aliases` 的匹配规则（exact / case-insensitive / fuzzy）未定；建议 `ai_responses.matched_aliases JSONB` + Postgres GIN `to_tsvector`。
- **E-P2-2 情感分析落地**：Session 1 Prompt 说"先规则、TODO 后 LLM"——没写规则表也没写 fallback；建议 `ai_responses.sentiment / sentiment_source / sentiment_confidence` 三列 + 失败告警表。
- **E-P2-3 周报 / 月报调度**：PRD 说"周报/月报 [ON]"但无 `report_schedules` / `generated_reports` 表、无邮件模板、无 cron runner。
- **E-P2-4 CSV 导出异步作业**：无 `export_jobs` 表、无速率限制、无"就绪邮件"通知；MVP 大表导出（> 10K 行）必炸。
- **E-P2-5 MCP 端点**：openapi.yaml 只有骨架，`genpano_get_brand_metrics` 等 Agent 工具端点未声明；Phase 2 再补可接受。
- **Frank 确认**：`[ ] 一揽子同意（P2 延后） / [ ] 指定哪些要并入 MVP`

### E 区小结

| 编号 | 类别 | 关键缺口 | 不修的直接后果 |
|---|---|---|---|
| E-P0-1 | 预聚合 | `metric_snapshots` schema 未定 | Dashboard 每次刷新全表扫、秒级超时 |
| E-P0-2 | Citation 归因 | 表 + 域名匹配算法缺 | `citation_share` KPI 永远 null |
| E-P0-3 | Heatmap 聚合 | 物化视图 + 索引缺 | 50×10 网格 > 5s |
| E-P0-4 | Response 倒排 | `detected_brand_ids[] / detected_topic_ids[]` + GIN | Drilldown Drawer 超时 |
| E-P1-1..5 | Scope / Ranking / Topics / Profile / Brand Audit | 表 / 索引 / 状态机缺 | 显示错数据 / 列表空 / 管控失效 |
| E-P2-1..5 | Alias / Sentiment / Report / Export / MCP | Pipeline 或异步作业缺 | 体验毛刺；Phase 2 可延 |

---

## 7. 跨区共性问题（Cross-Cutting Themes）

以下几个问题**跨多个审阅轴重复出现**，一次性改效率最高：

1. **`profileGroupId` 单复数**：在 A / D 两区都出现（见 D-P0-1）。修改 ADAPTER_CONTRACT 一处后需同步 PRD § 4.2.3a、Session 895 / 1128、Admin PRD 的相关段落。
2. **`/dashboard` 的去留**：在 A 区两个 finding 都指向同一个决策（A-P0-1, A-P0-2）。决策一次、五个地方联动改（PRD §4.6.1-0, §4.6-IA-v2；Session §2b.4, §T1；routing table）。
3. **Design Tokens 的"引用先行于定义"**：C-P0-1..5 全部是 Session 在引用一个尚未定义的 token。根源是 Session 作者"先写业务、再补 token"；建议把 `scripts/ci-check.mjs` 加一条规则：发现 `var(--color-*)` / `var(--drawer-*)` 未在 DESIGN_TOKENS.md 表格内的，fail 整个 pre-commit。
4. **Auth / User 生命周期端点不完整**：`logout` 的 204、`DELETE /users/me` 的 schema 都缺。建议在 Session 4a 开头做一张"7 个端点一览表"，同时驱动 openapi.yaml。
5. **Admin vs Consumer 共用的字段 / 枚举**：`intent`、`extractedBy`、`profileGroupIds` 这些在 Admin Session 和 Consumer Session 都出现，目前没有一个"共享契约"文件。建议新建 `src/types/shared.ts`（或 openapi.yaml 的 `components.schemas.*`）作为单一真相来源，PRD/Session 都从它引用。
6. **"数据模型只留了表名"**（E 区共性）：`metric_snapshots / platform_topics / brand_mentions / product_mentions / profile_groups / browser_profiles` 等关键表在 Session 0 的建表脚本里只出现了名字，字段、索引、外键全缺。需要在 Session 2 之前补一份 **完整 DDL 文档**（建议独立文件 `DATA_MODEL.md`），并在 Session Prompt 里强制引用它。

---

## 8. Ready-to-Session Gate（投喂 Session 前必须过的闸）

> 在下表所有 P0 都勾上"已修复"之前，**不建议**把任何 Session 投给 Claude Code——否则产出必然偏离 PRD 或运行期报错。

| # | 所属区 | 编号 | 简述 | 状态 |
|---|---|---|---|---|
| 1 | E | E-P0-1 | `metric_snapshots` 表 + 日/时 rollup 策略落地 | `[ ]` |
| 2 | E | E-P0-2 | `ai_response_citations` 表 + 域名归因算法 | `[ ]` |
| 3 | E | E-P0-3 | `heatmap_mention_agg` 物化视图 + 索引 | `[ ]` |
| 4 | E | E-P0-4 | `ai_responses.detected_brand_ids[] / detected_topic_ids[]` + GIN 索引 | `[ ]` |
| 5 | A | A-P0-1 | 登录后默认路由改回 `/brand/overview` | `[ ]` |
| 6 | A | A-P0-2 | 决定 `/dashboard` 是删 Spike 还是延到 v1.1 | `[ ]` |
| 7 | C | C-P0-1 | 定义 `--color-overlay-drawer` | `[ ]` |
| 8 | C | C-P0-2 | 定义 drawer-width / drawer-animation token 组 | `[ ]` |
| 9 | C | C-P0-3 | 定义 `--color-danger` | `[ ]` |
| 10 | C | C-P0-4 | 定义 `--color-scrim` | `[ ]` |
| 11 | C | C-P0-5 | 定义 `--color-text-on-accent` | `[ ]` |
| 12 | D | D-P0-1 | 统一 `profileGroupIds: string[]` | `[ ]` |
| 13 | D | D-P0-2 | 统一 Topic 更新 HTTP 方法 | `[ ]` |
| 14 | D | D-P0-3 | `POST /api/auth/logout` 明确 204 + 前端处理 | `[ ]` |
| 15 | D | D-P0-4 | 定义 `DELETE /api/users/me`（含 30 天窗口决策） | `[ ]` |

**预估修 P0 全部**：6–8 小时（E 区 4 条是 DDL + rollup 设计 + 归因算法，需要你确认；其余 11 条多是文档同步改写）。
**P1 建议在 Session 2 跑起来之前修完**：再 6–8 小时（含 E-P1-1..5）。
**P2 可以在 Session 3 / Admin A2 之前择机修**。

> ⚠️ **顺序提醒**：**E 区的 4 条 P0 务必最先完成**。如果先修了 A/C/D 却没修 E，即使前端跑起来，Dashboard / Topics / Drilldown 也会是空白 / 超时——等于 Session 白跑。

---

## 9. 下一步（等你勾完这份 Review 之后我会做的事）

1. 按你勾选的决议，批量修订：`PRD.md` · `CLAUDE_CODE_SESSIONS.md` · `ADAPTER_CONTRACT.md` · `DESIGN_TOKENS.md` · `TEST_STRATEGY.md` · 必要时 `ADMIN_PRD_B / C`。
2. **新建 `DATA_MODEL.md`**：把 E 区所有 DDL（`metric_snapshots`、`ai_response_citations`、`heatmap_mention_agg` 物化视图、`ai_responses` 倒排列、`platform_topics`、`profile_groups`、`browser_profiles`、`brand_submissions`、`brand_discovery_logs`、`brand_rankings` 等）统一收敛进去，做为 Session 2 的 Prompt 强制引用对象。
3. 生成 `openapi.yaml` 骨架（把 D 区所有新增/修正的端点 + E 区需要的查询端点都落地）。
4. 产出一份 **REVISION_DIFF.md**——列出每处改动的 before/after，你做最终复核。
5. 补齐 Harness 的新 grep / CI 规则（`scripts/ci-check.mjs`），含"token 引用必须先在 DESIGN_TOKENS 表里"、"DDL 必须在 DATA_MODEL.md 里"两条。
6. 最终跑一遍自查：重新审阅 PRD ↔ Session ↔ DESIGN_TOKENS ↔ ADAPTER_CONTRACT ↔ DATA_MODEL 的 cross-reference matrix，确认全部 P0 被关掉。
7. **到那一步你就可以直接把 Session Prompt 投给 Claude Code**，产出就既对齐 PRD、又有后端数据支撑、视觉也会走 token。

---

## 附录 A · Cross-Reference Matrix（精简版）

| 规约项 | HARNESS | ADAPTER | PRD | SESSION | TEST | 状态 |
|---|---|---|---|---|---|---|
| Adapter interface（execute/warmup/dispose） | — | §2 | §4.3 | S1 | — | ✓ |
| ExecutableQuery 字段 | — | §2.1 | — | S2 Prompt | — | ⚠ D-P0-1 |
| ExecutionContext 构建 | — | §3 | — | S1 | — | ✓ |
| 错误码 + 重试 | — | §6 | §4.3 | S1.2 | — | ⚠ D-P1-4 |
| Profile-group 绑定 | — | §3.3 | §4.2.3a | S2 | — | ⚠ D-P1-2 |
| GET /profile-groups schema | — | **未定义** | — | S3 | — | ✗ D-P1-6 |
| DELETE /users/me | — | — | §4.1.1e | — | — | ✗ D-P0-4 |
| POST /auth/logout 204 | — | — | §4.1.1e | S4a | — | ⚠ D-P0-3 |
| Topic update PUT vs PATCH | — | — | §4.5.1 | S2/913 | — | ⚠ A-P1-1 |
| `/dashboard` 路由 | — | — | §4.6.1-0 | S T1 / §2b.4 | — | ✗ A-P0-1/2 |
| ProfileGroupFilter 组件覆盖 | — | — | §4.6.1a | S4b | **缺** | ⚠ A-P1-2 |
| Drawer token（overlay/width） | — | — | — | — | — | ✗ C-P0-1/2 |
| `--color-danger / scrim / text-on-accent` | — | — | — | S | — | ✗ C-P0-3/4/5 |
| **`metric_snapshots` KPI 快照表** | — | — | §4.0（仅名字） | S0 / S2（**schema 缺**） | — | ✗ **E-P0-1** |
| **`ai_response_citations` 归因表 + 匹配算法** | — | §2.1 TS 有 | §4.2.6 公式有 | **缺** | — | ✗ **E-P0-2** |
| **`heatmap_mention_agg` 物化视图** | — | — | §4.6.1b-C | **缺** | — | ✗ **E-P0-3** |
| **`ai_responses.detected_*_ids[]` 倒排** | — | — | §4.6.1a-drilldown | **缺** | — | ✗ **E-P0-4** |
| `brand_rankings` 物化视图 | — | — | §4.6 badge | **缺** | — | ⚠ E-P1-2 |
| `platform_topics` 表结构 | — | — | §4.2 | S0 仅名字 | — | ⚠ E-P1-3 |
| `profile_groups / browser_profiles` 表 | — | §3 TS 有 | — | **缺** | — | ⚠ E-P1-4 |
| `brand_submissions / discovery_logs` | — | — | §4.1.2 | **缺** | — | ⚠ E-P1-5 |
| HAR 采样 + sanitize | — | §10 | — | S1.2 | Phase 1 | ✓ |
| 验收标准 | §4.4 | §11.2 | — | — | Phase 3 | ✓ |

---

## 附录 B · 修订预估工时

| 级别 | 条数 | 累计工时估算 |
|---|---|---|
| P0 | 15（含 E 区 4 条 DDL） | 6–8 h |
| P1 | 21 | +6–8 h |
| P2 | 19 | +2 h |
| **总计** | **55** | **≈ 14–18 h** |

---

**End of Review. 请在上文 Frank 确认: 行勾选或批注，完成后告诉我"Review 完成"，我就开始批量改文档并出 REVISION_DIFF.md。**
