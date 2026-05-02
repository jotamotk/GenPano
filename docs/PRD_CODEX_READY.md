# GENPANO Codex 可执行 PRD
> 2026-05-02 override: the orange `admin_console` Admin is the only Admin system.
> The legacy FastAPI Admin auth/API package has been removed. Historical
> references in this file to a separate FastAPI Admin backend are superseded.
> Do not restore a second Admin frontend or backend.

> 日期：2026-04-30
> 目标读者：Codex / 后续研发 Session
> 原型来源：
> - 产品主 App：`http://localhost:3000/`
> - Admin 原型：`http://localhost:5000/admin`
> 相关文档：
> - `docs/PRD.md`
> - `docs/ADMIN_PRD.md`
> - `docs/ADMIN_PRD_B_PIPELINE.md`
> - `docs/ADMIN_PRD_C_KG.md`
> - `docs/DATA_MODEL.md`
> - `docs/ADAPTER_CONTRACT.md`
> - `docs/PRD_ADMIN_IMPLEMENTATION_PLAN.md`

## 1. 本文档的作用

这份 PRD 是给 Codex 用的“可执行版 PRD”。它不替代所有历史 PRD 的细节，但它定义当前研发应遵守的最新产品形态、技术边界和验收口径。

当前两个 localhost 原型具有产品优先级：

- `http://localhost:3000/` 是产品主 App 的前端原型。它满足当前产品体验方向。
- `http://localhost:5000/admin` 是 Admin 的原型图和运营控制台方向。

Codex 后续研发时，应先读本文档，再按需查更长的 PRD / Admin PRD / DATA_MODEL / ADAPTER_CONTRACT。

## 2. 最新不可变决策

### 2.1 Admin 决策

- 唯一 Admin 是 `admin_console` Admin。
- Admin 入口是 `admin_console/app.py` + `admin_console/templates/admin.html`。
- `http://localhost:5000/admin` 可视为 Admin 高保真原型。
- 不再建设独立 `frontend/src/admin` React Admin。
- Legacy FastAPI Admin backend has been removed; do not recreate a second Admin backend.
- 未来 Admin 的页面、交互和接口优先在 `admin_console` 中演进。

### 2.2 产品 App 决策

- 产品主 App 是 `frontend` 下的 React + Vite App。
- 当前浏览器入口为 `frontend/index.html -> frontend/src/main.jsx -> frontend/src/App.jsx`。
- `frontend/src/App.tsx` / `frontend/src/main.tsx` 是另一条轻量 auth 原型路径，不能默认视为当前产品主入口。
- 产品前端原型可以作为用户侧体验的验收基准。

### 2.3 Adapter 决策

- `geo_tracker` 中已有跑通的 3 个 LLM adapter，是核心资产。
- 不允许 Codex 因为 PRD 文案不同而盲目重写 adapter。
- 任何涉及 adapter 的修改必须先对照 `docs/ADAPTER_CONTRACT.md` 做差异审计。
- 如果 PRD 与已验证代码冲突，应输出“代码事实 / PRD 要求 / 风险 / 建议”，而不是直接改代码。

## 3. 产品定位

GENPANO 是一个 GEO（Generative Engine Optimization）监测平台。

核心逻辑是 **Data-first, User-second**：

- 平台先通过 LLM adapter、账号池、代理池、Profile、Topic / Prompt / Query 生成和采集任务，构建平台级 GEO 数据。
- 用户注册后，不等待首次采集，而是通过 Project 视角读取已经存在的平台数据。
- Admin 负责让这套平台级采集和分析系统持续可运营。

## 4. 系统边界

### 4.1 产品主 App

职责：

- 用户注册 / 登录 / 邮箱验证 / 密码重置 / onboarding。
- 用户选择或创建 Project。
- 用户查看品牌视角、行业视角、报告、诊断、设置。
- 所有数据页面必须经过用户认证。

技术路径：

- 前端：`frontend/src/main.jsx`、`frontend/src/App.jsx`、`frontend/src/pages/**`、`frontend/src/components/**`。
- 用户认证 API：`backend/app/api/v1/auth/router.py`，前缀为 `/api/auth`。
- 产品数据 API：后续在 FastAPI `/api/v1/*` 或现有 `/api/*` 约定下补齐，但必须与前端 central API client 对齐。

### 4.2 Query Admin

职责：

- 平台运营首页。
- Pipeline / Attempts / Account Pool / Analyzer / KG / Cost / Alerts / Audit。
- 运行、重试、排错、查看 artifact、管理账号资源。

技术路径：

- 后端 + 页面：`admin_console/app.py`
- 模板：`admin_console/templates/admin.html`
- 密码重置脚本：`admin_console/scripts/admin_reset_password.py`
- 正式入口：`/admin`
- Admin Console API：`/api/*`，在正式 Admin mount 下应通过 `/admin/api/*` 代理到 admin_console。

### 4.3 Worker / Adapter

职责：

- 3 个 MVP LLM adapter 的采集执行。
- 账号池、Cookie 生命周期、自动登录、SMS 注册。
- Query 执行、Response 提取、Artifact 保存。
- Analyzer 解析品牌、情感、引用、指标。

技术路径：

- `geo_tracker/agent/**`
- `geo_tracker/tasks/**`
- `geo_tracker/pool/**`
- `geo_tracker/analyzer/**`
- `geo_tracker/db/**`

## 5. 产品主 App 信息架构

当前产品 App 应以 `App.jsx` 为准。

### 5.1 匿名可访问路由

| 路由 | 页面 | 说明 |
|---|---|---|
| `/` | LandingPage | 公开落地页 |
| `/login` | AuthPage login | 登录入口 |
| `/auth` | AuthPage login | 登录兼容入口 |
| `/register` | AuthPage register | 注册入口 |
| `/forgot` | AuthPage forgot | 忘记密码兼容入口 |
| `/forgot-password` | AuthPage forgot | 忘记密码入口 |
| `/email-sent` | EmailSentPage | 验证邮件已发送 |
| `/setup` | SetupPage | 邮箱验证或 OAuth setup 后补充资料 |
| `/reset-password` | ResetPasswordPage | 重置密码 |
| `/reset-password-success` | ResetPasswordSuccessPage | 重置成功 |
| `/auth/callback` | AuthCallback | OAuth callback |

要求：

- 匿名页面不能请求品牌、行业、监测、报告等受保护数据。
- 已登录用户访问 public-only 页面，应跳到 `redirect` / `return_to` 或默认 `/brand/overview`。
- Auth 表单继续采用 email-first 两步体验，不退回到 email + password 同屏大表单。

### 5.2 登录后基础路由

| 路由 | 页面 | 说明 |
|---|---|---|
| `/onboarding` | OnboardingPage | 新用户引导 |
| `/settings` | SettingsPage | 用户设置 |
| `/project-settings` | ProjectSettingsPage | 项目设置 |
| `/brands` | BrandsPage | 品牌集市 / 项目品牌列表 |

要求：

- 受保护路由必须通过 `RequireAuth`。
- 未登录访问受保护路由，跳 `/register?redirect=...`。
- `redirect` 只允许站内路径，不能开放跳转。

### 5.3 Brand Mode

Brand Mode 是用户查看“我的品牌”的核心模式。

| 路由 | 页面 | 核心能力 |
|---|---|---|
| `/brand/overview` | DashboardPage | 品牌总览，PANO、SoV、竞品、趋势、诊断入口 |
| `/brand/visibility` | BrandVisibilityPage | 提及率、排名、引擎对比、Topic 可见性 |
| `/brand/topics` | TopicsPage | Topic 覆盖、Topic 意图、Prompt / Query 线索 |
| `/brand/sentiment` | BrandSentimentPage | 情感分布、情感趋势、Topic 归因、原始 Response 样本 |
| `/brand/citations` | BrandCitationsPage | 引用份额、权威来源、内容缺口、PR 目标 |
| `/brand/products` | BrandProductsPage | 产品组合、产品 PANO、产品矩阵 |
| `/brand/products/:productId` | BrandProductDetailPage | 单产品详情 |
| `/brand/competitors` | BrandCompetitorsPage | 竞品威胁、四象限、雷达、同集团关系 |
| `/brand/diagnostics` | DiagnosticsPage | GEO 诊断建议 |
| `/brand/reports` | ReportsPage | 报告列表、报告生成、导出 |

Brand Mode 验收：

- 所有页面必须显示同一个 Project / primary brand 视角。
- Brand picker / query string 中的 `brandId` 必须在子页面切换时保留。
- 页面不能直接读取 mock 作为生产真相；真实 API 未就绪时要显示明确空状态。
- Brand Mode 不暴露“Brand Mode”这类开发术语给最终用户，用户侧文案用“品牌”等自然语言。

### 5.4 Industry Mode

Industry Mode 是行业全景视角。

| 路由 | 页面 | 核心能力 |
|---|---|---|
| `/industry/overview` | IndustryOverviewPage | 行业总览、5 KPI IQR、SoV、趋势、集团版图 |
| `/industry/ranking` | IndustryRankingPage | 多口径排行、矩阵、Top 引用源 |
| `/industry/topics` | IndustryTopicsPage | 行业 Topic 格局、热度、覆盖与机会 |
| `/industry/knowledge-graph` | KnowledgeGraphPage | 行业 KG 可视化、品牌 / 品类 / 关系 |

Industry Mode 验收：

- Mode 由 URL 决定，不存 localStorage。
- `/industry/*` 页面不新增独立 mock truth，优先从平台品牌 / topic / response 数据派生。
- Industry picker / `industryId` 在子页面切换时保留。
- 行业页的“我的品牌”标记只有在当前用户有 primary brand 时展示。

### 5.5 Legacy 路由

保留现有 SPA 内的兼容重定向：

- `/dashboard` -> `/brand/overview`
- `/topics` -> `/brand/topics`
- `/industry`、`/industries` -> `/industry/overview`
- `/knowledge-graph` -> `/industry/knowledge-graph`
- `/diagnostics` -> `/brand/diagnostics`
- `/reports` -> `/brand/reports`
- `/brands/:id` -> `/brand/overview?brandId=:id`
- `/brands/:id/products/:productId` -> `/brand/products/:productId?brandId=:id`

Codex 修改路由时不能破坏这些兼容入口。

## 6. 产品主 App 数据要求

### 6.1 Project 视角

Project 是用户视角层，不复制平台监测数据。

Project 至少需要：

- `id`
- `user_id`
- `industry_id`
- `primary_brand_id`
- `competitor_brand_ids`
- `preferences`
- `created_at`
- `updated_at`

产品页面的数据读取应遵守：

- 先确定当前 Project。
- 通过 Project 的 primary brand、competitor brands、industry 过滤平台数据。
- 不在用户表或 Project 表里复制 response / metric 明细。

### 6.2 核心指标

用户侧至少展示：

- PANO Score
- Mention Rate / Visibility
- Average Rank / Position
- Sentiment
- Citation Share
- Authority / PANO A
- Competitor Gap
- Trend

指标口径应从 `docs/PRD.md`、`docs/DATA_MODEL.md`、`docs/ADAPTER_CONTRACT.md` 继承。若已有运行代码和 PRD 口径冲突，先写差异说明。

### 6.3 API 要求

后续产品数据 API 至少覆盖：

- current user / session
- projects
- brands
- industries
- topics
- prompts / queries
- responses
- metrics
- citations
- diagnostics
- reports
- commercial leads

要求：

- 所有数据 API 必须认证。
- 前端不得在组件里散落裸 `fetch` 调 protected data。
- API client 应集中处理 base URL、token、错误结构、401。
- 真实 API 未就绪时，前端显示空状态或“数据接入中”，不能继续扩散 mock。

## 7. Query Admin 信息架构

Admin 原型以 `admin_console/templates/admin.html` 的 navigation 为准。

### 7.1 顶层分组

| 分组 | 页面 key | 说明 |
|---|---|---|
| 概览 | `overview` | 仪表板 |
| 账号 & 用户 | `users-list`、`users-login`、`users-audit`、`users-feedback` | 用户、登录、审计、反馈 |
| 管道总览 | `pipeline-dashboard` | Planner / Tracker / Analyzer 一屏 |
| Planner · 规划 | `planner-scheduler`、`planner-generation`、`planner-prompts`、`planner-profiles`、`planner-resources` | 采什么、怎么采、用什么资源 |
| Tracker · 执行 | `tracker-attempts`、`tracker-engines`、`tracker-trace` | 每次执行、引擎健康、链路追溯 |
| Analyzer · 分析 | `analyzer-quality`、`analyzer-qa` | 结果分析、人工质检 |
| 横切 | `pipeline-changes` | 变更审批 |
| 知识图谱 | `kg-tree`、`kg-brand-review`、`kg-product-review`、`kg-aliases`、`kg-inbox`、`kg-discovery`、`kg-entity-ops`、`kg-diff`、`kg-quality` | KG 治理 |
| 运营 & 监控 | `ops-cost`、`ops-alerts`、`ops-schedule`、`ops-announce`、`ops-email`、`ops-leads`、`ops-mcp` | 成本、告警、公告、邮件、线索、MCP |

### 7.2 Admin 登录与访问控制

要求：

- 正式 `/admin` 必须要求 Admin 登录。
- `/api/admin-auth/session` 返回当前登录态。
- `/api/admin-auth/login` 支持 rate limit、bcrypt 校验。
- `/api/admin-auth/logout` 清理 session。
- `/api/admin-auth/change-password` 修改当前 Admin 密码。
- `ADMIN_SESSION_SECRET` 生产环境必须配置。
- session cookie path 为 `/admin`，生产环境应开启 secure。

临时 `/query/admin` 的访问策略可以与正式 `/admin` 不同，但必须在文档或代码注释中写清楚。

### 7.3 用户管理

用户管理是 Query Admin 的 MVP 能力，PRD 支持从 App 端注册登录闭环后开始实现。

页面：

- `users-list`：用户列表
- `users-login`：用户登录审计
- `users-audit`：管理员操作审计
- `users-feedback`：用户反馈，可后置

用户列表必须支持：

- 邮箱搜索
- 注册时间排序 / 筛选
- 最后登录排序
- 行业筛选
- Project 数排序
- 活跃度等级筛选：`hot / warm / cold / dormant`
- 状态筛选：`active / frozen / deleted`
- 查看详情
- 冻结 / 解冻
- 强制密码重置
- CSV 导出，MVP 仅 `super_admin`，单次上限 1000 行，并写 audit

用户详情必须支持：

- 概览：邮箱、姓名、公司、注册来源、语言偏好、注册时间、最后登录
- Projects：该用户的所有 Project，只读展示 primary brand、竞品、报告偏好
- API 使用：若用户有 API Key，展示 key 列表、调用量、限流、最近错误
- 操作记录：所有针对该用户的 Admin 动作

用户登录审计必须支持：

- 时间
- user_id
- email
- IP
- User-Agent
- 结果：`success / failed / locked`
- 失败原因
- user / IP / 时间段筛选
- 同一 IP 1 小时 10 次失败时 UI 标红
- 同一账号地理位置跳变时 UI 标橙

用户 moderation 规则：

- `users` 表不新增粗暴 `status` 真相字段。
- 冻结状态从 `user_moderation_actions` 派生。
- soft delete 状态从 `users.deletion_requested_at IS NOT NULL` 派生。
- `user_moderation_actions.action` 至少支持：
  - `freeze`
  - `unfreeze`
  - `force_password_reset`
  - `soft_delete`
- 冻结 / 解冻 / 强制重置 / soft delete 必须填写 reason，并写 audit。
- Admin 不允许直接编辑用户邮箱、密码、Project 名称、竞品列表。此类修改必须通过用户自助或工单 + 用户授权。

Query Admin API 建议：

- `GET /api/users`
- `GET /api/users/<user_id>`
- `GET /api/users/<user_id>/actions`
- `GET /api/users/login-audit`
- `POST /api/users/<user_id>/freeze`
- `POST /api/users/<user_id>/unfreeze`
- `POST /api/users/<user_id>/force-password-reset`
- `POST /api/users/<user_id>/soft-delete`
- `GET /api/users/export`

正式 `/admin` mount 下，这些 API 应通过 `/admin/api/users...` 访问并被 Admin session 保护。

最低实现顺序：

1. 用户列表 read-only
2. 用户详情 read-only
3. 登录审计 read-only
4. moderation 表与 audit helper
5. freeze / unfreeze
6. force password reset
7. CSV export
8. soft delete，最后实现

### 7.4 Admin Overview

Overview 必须回答：“今天平台有没有问题？”

必须展示：

- P0 / P1 告警条或明确空状态
- 爬取成功率
- 今日成本
- 新增注册
- 活跃 Project
- Topic → Prompt → Query → Response 四层漏斗
- 引擎健康：ChatGPT、豆包、DeepSeek
- 待办 inbox：品牌审核、失败任务、告警、商务线索
- 近 7 天趋势

数据优先级：

1. admin_console 已有 API 的真实数据
2. 明确空状态
3. 临时 demo 数据，仅可在代码里标注为 prototype，不可伪装成真实状态

### 7.5 Pipeline / Attempts

必须支持：

- `/api/queries` 列表
- 分页
- 按 status / engine / brand / topic / prompt 过滤
- 展示 query text、engine、profile、account、latency、retry reason、created / updated time
- 单条 retry：`/api/queries/<id>/retry`
- 批量 trigger：`/api/queries/batch_trigger`
- mark failed：`/api/queries/<id>/mark_failed`
- artifact 查看：HTML / screenshot / JSON debug 文件

写操作要求：

- retry、batch trigger、mark failed 必须有 reason。
- 正式 Admin 下必须写 audit，或在 P0 明确列为待补风险。

### 7.6 Account Pool

必须支持：

- `/api/accounts` 列表
- 账号按 engine 分组
- status：active / banned / cooldown 等
- cookies 导入：`/api/accounts/import_cookies`
- status 修改：`/api/accounts/<id>/status`
- reset：`/api/accounts/<id>/reset`
- delete：`/api/accounts/<id>`
- auto login：`/api/accounts/<id>/auto_login`
- SMS 注册：`/api/sms_register`

安全要求：

- cookie / localStorage 输入属于敏感凭据材料，正式使用时必须限制访问、避免日志泄露完整内容。
- 删除账号必须二次确认。
- 高风险操作必须写 audit。

### 7.7 Analyzer

必须支持：

- `/api/analyzer/stats`
- `/api/analyzer/brands`
- `/api/analyzer/llms`
- `/api/analyzer/responses`
- `/api/analyzer/response/<id>`
- `/api/analyzer/daily`
- `/api/analyzer/trigger`
- `/api/analyzer/rerun/<response_id>`
- `/api/topics`
- `/api/prompts`

Analyzer 页面必须能回答：

- 哪些品牌 / Topic / Prompt 表现异常？
- Response 原文、引用、情感、品牌检测结果是什么？
- 哪些结果需要重新分析？

### 7.8 KG 治理

KG 页面当前可先按原型补齐 read / empty state，写操作分阶段做。

MVP 必须逐步实现：

- 行业 & 品类树
- 品牌审核
- 产品审核
- 别名 & 关系
- 品牌征集
- 发现日志

进阶页面：

- 实体合并 / 拆分
- KG Diff
- KG Quality

要求：

- 如果当前页面仍是 mock，必须标记并改为真实 API 或明确空状态。
- approve / reject / merge 这类写操作必须审计。
- LLM 发现实体不能自动 active，必须先进 pending。

### 7.9 Cost / Alerts / Audit

必须逐步实现：

- 成本面板：按 engine / model / topic / date 聚合
- 告警中心：open / acknowledged / resolved
- 定时任务：cron / 手动触发 / 只读状态
- 系统公告
- 邮件模板预览
- 商务线索
- MCP 运维
- 操作审计

最低验收：

- Admin 写操作能在 audit 中追踪。
- Alert 没有真实表时显示空状态。
- Cost 没有真实聚合时显示“待接入”，不展示随机图表冒充真实成本。

## 8. Adapter / Pipeline 要求

MVP 引擎：

- ChatGPT
- 豆包
- DeepSeek

必须保护现有已跑通 adapter。

Codex 涉及 adapter 前，必须先审计：

| 契约项 | 要求 |
|---|---|
| response_source | 每条 response 应标记来源，如 web / api / fallback |
| error code | 对齐 `ADAPTER_CONTRACT.md`，不自造散乱错误码 |
| NO_ACCOUNT_AVAILABLE / COOKIE_EXPIRED | 不应简单算作引擎失败 |
| retry | 有最大次数、原因、状态迁移 |
| account / cookie 生命周期 | 能观察、冷却、重置、重新登录 |
| proxy / CAPTCHA / timeout | 分类明确，能被 Admin 诊断 |
| artifact | 保存或暴露 HTML / screenshot / raw debug 信息 |
| attempt 粒度 | 每次执行可追踪 |
| analyzer | 能从 response 回溯 query / prompt / topic / brand |

## 9. 研发验收总规则

Codex 每次改动必须遵守：

- 先看 `git status`，保护 dirty worktree。
- 不回滚用户或其他 session 的改动。
- 不重建已废弃 Admin 技术栈。
- 不重写已跑通 adapter。
- 新 Admin 写操作必须审计。
- 新产品数据 API 必须认证。
- 原型已有体验不能被无意降级。
- 如果真实数据未接入，显示空状态，不扩散 mock truth。
- 改路由必须保留 legacy redirect。
- 改 API 必须同步考虑 `docs/openapi.yaml` 或在 final 明确说明未同步原因。

## 10. Codex 开发入口建议

后续 session 开始时应按顺序读取：

1. `docs/PRD_CODEX_READY.md`
2. `docs/DEVELOPMENT_PLAN.md`
3. 与任务相关的原型源码：
   - 产品 App：`frontend/src/App.jsx`、对应 page/component
   - Admin：`admin_console/app.py`、`admin_console/templates/admin.html`
4. 与任务相关的权威文档：
   - `docs/DATA_MODEL.md`
   - `docs/ADAPTER_CONTRACT.md`
   - Admin B / C 深化文档

不要从历史 session prompt、旧 Admin 文件、或已废弃实现中推断当前产品方向。
