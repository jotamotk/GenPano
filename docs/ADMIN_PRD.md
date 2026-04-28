# GENPANO Admin - Product Requirements Document (PRD)

> Version: 1.0 | Author: Frank Wang | Date: 2026-04-16
> Status: Draft → Ready for Claude Code Implementation
> **此文档与 `docs/PRD.md` (面向终端用户的产品 PRD) 并列独立**。Admin 不是 App 的某个页面，而是独立部署的内部运营控制台。

---

## 0. 关于本文档

### 0.1 为什么 Admin 要独立出 PRD

GENPANO 的核心逻辑是 **Data-First, User-Second**：平台必须先把数据采集、知识图谱、Pipeline 调度全部跑起来，用户才能在注册后立即看到"已经运转的数据"。这意味着 Admin（运营后台）不是 MVP 的"附属功能"，而是 **MVP 能否上线的前置条件**——没有 Admin，平台级采集、账号池、KG 审核、成本控制都无处落地。

把 Admin 从 `docs/PRD.md` 中独立出来，原因有三：

1. **读者不同**：App PRD 的读者是"终端用户 + 实现 App 功能的 Session"；Admin PRD 的读者是"Frank 自己 + 实现 Admin 的 Session"。职责不同的文档必须独立，否则两边都会被对方的细节淹没。
2. **节奏不同**：App 功能围绕"用户旅程"编排；Admin 围绕"运营事件（任务失败、账号被封、品牌提交待审）"编排。信息架构本质不同。
3. **安全边界不同**：Admin 处理的是 platform-scoped 的特权操作（审批图谱、重跑任务、调整预算），其权限模型、审计要求、部署域名都和 App 隔离。

### 0.2 此文档与现有文档的关系

| 文档 | 职责 | 本文档与其关系 |
|---|---|---|
| `docs/PRD.md` | App 终端功能 PRD | Admin 中的"数据管道 / KG / 用户列表"与其 §4.0–§4.3 所定义的数据模型**共享同一套表**；本文档只补充"这些数据如何被运营"。 |
| `docs/CLAUDE_CODE_SESSIONS.md` | App Session 规划 | Admin 的 Session 单列在 `docs/ADMIN_CLAUDE_CODE_SESSIONS.md`，**不穿插进 App Session 序列**。 |
| `docs/HARNESS_ENGINEERING.md` | 方法论 | 本文档每个 Admin 模块都给出可执行验收标准，符合 Harness 三层质保架构（Executable Acceptance / Adversarial / Spec Compliance）。 |
| `docs/DESIGN_TOKENS.md` | 样式真相源 | Admin 前端与 App 共用同一套 token；样式契约同时适用。 |
| `CLAUDE.md` | 项目共享大脑 | Admin 完工后，CLAUDE.md 增加 "Admin 模块" 一节，供后续 Session 引用。 |

### 0.3 设计原则

1. **Admin 服务于"运营事件"，不是"功能清单"**：每个模块的信息架构都围绕"最高频的运营动作"展开（例：品牌审核页的顶栏第一个按钮必然是批量通过 / 驳回）。
2. **Solo-first，Team-ready**：MVP 阶段只有 Frank 一个 super_admin 角色，但 schema 必须预留 `role` 枚举、`operator_id` 审计字段、`admin_audit_log` 表，保证未来加入 ops/support/data-ops/bizdev 四个角色时**不用迁移业务代码**。
3. **平台数据与用户数据的权限边界清晰**：Admin 可以改 Platform Layer（KG、调度、预算、账号池），**不允许直接改某个用户的 Project 内容**——用户数据只能"查看、冻结、导出"，不能"编辑"。编辑需要用户本人授权或工单流程。
4. **一切特权操作留痕**：任何会修改 Platform 数据（批准品牌、重跑任务、改预算、封禁用户、手动覆盖 KG 关系）的动作，全部写入 `admin_audit_log` 并可在 UI 上追溯。
5. **可观测优先于可配置**：MVP 阶段如果某个参数"看起来可能要调"，先把"当前值是多少"和"变化趋势"做出来，配置 UI 先留空（hardcode 在 env 或 config 文件）。配置 UI 是 MVP 后期 / Phase 2 才加。

---

## 1. Goals & Non-Goals

### 1.1 Goals (MVP — 4 周内必须有)

- **Frank 一个人就能运营整个平台**：用 Admin 看到当天的采集成功率、账号池水位、失败任务、成本趋势，发现问题能 1-2 次点击触发修复。
- **KG 审核闭环**：LLM 发现 + 用户提交的品牌/产品，能在 UI 上逐条 approve / reject / merge，修正别名与关系边。
- **数据管道全链路可视**：从 Topic 生成到 Response 解析的四层 Pipeline 每一步都能看到当日吞吐、失败原因、样本数据。
- **成本可控**：每日 LLM + 代理 + 爬取的花销按引擎 / 行业 / 品牌归因，超预算自动停采。
- **安全底线**：所有 Admin 登录、特权动作、数据导出都有审计；Admin 域名 / 入口与 App 完全隔离。

### 1.2 Non-Goals (MVP)

- **不做多租户组织 / 团队协作**：MVP 只有 1 个 Admin 账户，`organizations` 表先不建。
- **不做订阅 / 计费管理**：MVP 全免费，无 Stripe、无发票、无套餐升降级。`orders` / `subscriptions` 相关 UI 不做，只在 schema 预留一个 `commercial_leads` 表承接咨询线索。
- **不做复杂审批流**：所有品牌 / 产品审核都是"单人决策"，不做两级审批。
- **不做白标 / 代理商后台**：非本 MVP 范围。
- **不做 A/B 实验平台 / 用户级灰度**：MVP 的 feature flag 只到"环境级开关"（`ENABLE_CHATGPT_ADAPTER=true`），按用户比例灰度留 Phase 2。
- **不做邮件 WYSIWYG 编辑器**：MVP 邮件模板用代码定义（React Email），Admin 只能"预览 + 发测试邮件"，不能直接在 UI 上改模板 HTML。

### 1.3 MVP 成功标准（Definition of Done）

Admin 合格的标准不是"功能齐了"，而是——

- [ ] Frank 每天花在 Admin 上的平均时间 ≤ 20 分钟，能完成全部日常运维（审核 / 监控 / 异常处理）。
- [ ] 连续 7 天，通过 Admin 能发现并恢复至少 1 次真实故障（账号被封 / 代理失效 / 调度卡住 / 某引擎成功率跌落），无需看服务器日志。
- [ ] Admin 自身的所有特权动作在 `admin_audit_log` 表里可按时间 / 操作员 / 对象类型检索。

---

## 2. Users & Roles

### 2.1 MVP 角色矩阵

| 角色 | MVP 启用？ | 职责范围 | 关键权限 |
|---|---|---|---|
| `super_admin` | ✅ 启用 | Frank 本人，全权 | 所有操作 |
| `ops` | 🟡 Schema 预留 | 运维：监控 Pipeline、处理工单 | 读所有 + 重跑任务 / 冻结账户（无 KG 编辑、无预算修改） |
| `data_ops` | 🟡 Schema 预留 | 数据审核：KG / Brand Submission | 读所有 + KG 编辑 + Brand Submission 审批 |
| `support` | 🟡 Schema 预留 | 客户成功：邮件 / 工单 / 公告 | 读用户信息 + 发工单回复 + 发公告（无 Pipeline 操作） |
| `bizdev` | 🟡 Schema 预留 | 商务：行业报告 / 咨询线索 | 读用户基础信息 + 商务模块全权（无用户封禁、无 Pipeline） |

> **设计约束**: `admin_users.role` 是枚举字段；MVP 所有中间件的 RBAC 判断都走 `if (role === 'super_admin')`，但中间件形态已是"检查角色是否在允许列表内"，Phase 2 加角色只需扩列表，不改调用点。

### 2.2 典型工作场景（运营事件驱动）

这些场景驱动了 Admin 的信息架构。不是"我们有哪些功能"，而是"Frank 每天要处理哪些事"：

| 场景 | 触发来源 | Admin 入口 | 目标动作 |
|---|---|---|---|
| 某引擎昨夜失败率飙升 | Alert / Dashboard 首页红条 | `/admin/pipeline/engines/:engine` | 看失败原因分布 → 决定重试 / 切代理 / 切账号 |
| 账号池水位告警 | Alert | `/admin/accounts-pool/:engine` | 触发补充 / 手动注入 / 切换兜底账号 |
| 用户提交了一个新品牌 | Brand Submission Inbox 顶栏 badge | `/admin/kg/brand-submissions` | 预览 LLM 验证结果 → approve / reject / merge |
| LLM 发现了一批新品牌但置信度偏低 | Discovery Logs 日级生成 | `/admin/kg/discovery-logs` | 批量标注后入图谱 / 丢弃 |
| 昨日 LLM 成本超预算 | Cost 首页红色横幅 | `/admin/cost/daily` | 查看高花销引擎 / 行业 → 调整调度层级 |
| 用户报了一个数据不对 | 工单 / 邮件 | `/admin/users/:id` → `/admin/kg/search?q=...` | 查用户的 Project 配置 + 对应品牌的 mention 原始 Response |
| 有人来咨询行业报告 | Landing 表单 | `/admin/commercial/leads` | 标记为 qualified → 人工跟进 |

---

## 3. 信息架构 (Information Architecture)

### 3.1 顶层导航分组

Admin 侧栏（左侧 240px，与 App 同宽，但主题色切换为"运营主题"——见 §6.1）分为 4 个 Section：

```
┌──────────────────────────────┐
│ ADMIN · GENPANO              │
│ super_admin · Frank          │
├──────────────────────────────┤
│ ● 首页总览 (Overview)         │
│                              │
│ ▼ 1. 账号 & 用户              │
│   ├ 用户列表                 │
│   ├ 用户详情 (动态)           │
│   ├ 登录审计                 │
│   └ Admin 成员 (solo 置灰)   │
│                              │
│ ▼ 2. 数据管道 & 采集           │
│   ├ Pipeline 全景            │
│   ├ 引擎健康                 │
│   ├ 爬取任务队列             │
│   ├ 账号池水位 [●]           │
│   ├ 代理池状态               │
│   └ 失败重试中心             │
│                              │
│ ▼ 3. 知识图谱                 │
│   ├ 行业 & 品类树             │
│   ├ 品牌审核 [12]            │
│   ├ 产品审核 [3]             │
│   ├ 别名与关系               │
│   ├ Brand Submission [●2]   │
│   └ Discovery Logs           │
│                              │
│ ▼ 4. 运营 & 监控              │
│   ├ 成本看板                 │
│   ├ 告警中心 [●]             │
│   ├ 调度配置                 │
│   ├ 公告 & 邮件              │
│   ├ 商务线索                 │
│   ├ Agent/MCP 运营            │
│   └ 审计日志                 │
├──────────────────────────────┤
│ env: PROD  🟢                │
│ [切换至 STAGING]              │
└──────────────────────────────┘
```

导航上的小 badge（`[12]` / `[●]`）由服务端 `/admin/api/v1/nav-counters` 每 30 秒刷新，反映"需要 Frank 关注"的事项数量——这是 Admin 第一眼要看到的信息。

### 3.2 首页总览 (Overview) 布局

Overview 是 Frank 每天打开 Admin 看到的第一屏。设计目标：**10 秒内判断"平台今天有没有问题，要不要深入看"**。

```
┌──────────────── 告警条 ────────────────┐
│ 🔴 P0 · 豆包 成功率跌破 70% (当前 62%)    │ ← 只有有告警才显示
│ ⚠ P1 · ChatGPT 账号池水位 3/10         │
└────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ 健康 KPI 4 格                                        │
│ ┌─────────┬─────────┬─────────┬─────────────────┐   │
│ │ 爬取成功 │ 当日成本 │ 新增注册 │ 活跃 Project   │   │
│ │ 92.4%   │ ¥487    │ 12      │ 34             │   │
│ │ ↓ -3.1pp│ ↑ +8%   │ ↑ +4    │ → 持平          │   │
│ └─────────┴─────────┴─────────┴─────────────────┘   │
└─────────────────────────────────────────────────────┘

┌─────────── Pipeline 四层漏斗 ────────────┐ ┌─ 引擎健康 ─┐
│ Topic  12,400 ─ Prompt 38,100 ─          │ │ ChatGPT ▓▓▓│
│ Query  184,320 ─ Response 169,221 (成功率92%)│ │ 豆包    ▓▓░│
│ [查看详情]                                │ │ DeepSeek ▓▓│
└──────────────────────────────────────────┘ └────────────┘

┌── 待办队列 (Inbox) ──────────────────────┐
│ 🟣 2 条 Brand Submission 待审             │
│ 🟢 12 条 新品牌发现待入库                  │
│ 🟡 3 条 失败任务未分类                    │
│ 🔵 4 条 商务线索新进                       │
└──────────────────────────────────────────┘

┌── 最近 7 天趋势 (小图 × 3) ──────────────┐
│ 爬取量 | 成本 | 活跃用户                   │
└──────────────────────────────────────────┘
```

---

## 4. 模块详细设计 (Detailed Requirements)

### 4.1 Module A — 账号 & 用户运营

#### 4.1.1 用户列表 `/admin/users`

**信息密度优先**。表格字段（从左到右）：

| 字段 | 说明 | 可排序 / 筛选 |
|---|---|---|
| Email | 用户邮箱 | 搜索 |
| 注册时间 | `created_at` | 排序 |
| 最后登录 | `last_login_at` | 排序 |
| 行业 | 用户选择的行业 | 筛选 |
| Project 数 | 该用户创建的 Project 数 | 排序 |
| 活跃度等级 | `hot / warm / cold / dormant`（近 30 天登录天数自动分级） | 筛选 |
| 状态 | `active / suspended / deleted` | 筛选 |
| 操作 | 查看详情 / 冻结 / 重置密码 / 删除 |

**顶栏工具**：

- 全文搜索（邮箱 / 昵称 / Project 名称）
- 多条件筛选（行业 + 活跃度 + 状态 + 注册时间段）
- 导出 CSV（MVP 仅限 super_admin，且写入审计日志，单次限 1000 行）

**关键动作**：

- **冻结 (Suspend)**：用户登录后看到"账号被暂停，联系 support@genpano.com"；原因必填（下拉 + 自由文本），写入 `user_moderation_actions`。
- **强制密码重置**：生成一次性 token，发邮件；用户下次登录必须改密码。
- **删除 (Soft Delete)**：用户数据保留 30 天 tombstone 后物理删除；Project、API Key 立即失效。

> ⚠️ **严禁**：Admin 直接编辑用户的邮箱、密码、Project 名称、竞品列表。编辑须通过用户自助或工单 + 用户授权完成。

#### 4.1.2 用户详情 `/admin/users/:id`

四 Tab 结构：

- **Tab 1 · 概览**：基础信息、注册来源、语言偏好、所在地区、近 30 天活跃日历热力图
- **Tab 2 · Projects**：该用户的所有 Project（primaryBrand / 竞品列表 / 报告偏好），点击跳转到 Platform 层对应的品牌监测数据（**只读**）
- **Tab 3 · API 使用**：若该用户启用了开发者 API Key，显示 Key 列表、调用量、限流次数、最近错误
- **Tab 4 · 操作记录**：所有针对该用户的 Admin 动作（被谁冻结、重置密码、发过工单）

**Y1/Y2 is_frozen 状态派生公式 (round 9 PR + 决策 #30.H)**:

`users` 表 §1.1 schema 无 `status` 列 (DATA_MODEL §1.1 真相源), frozen 状态完全从 `user_moderation_actions` 派生:

```sql
SELECT
  u.*,
  EXISTS(
    SELECT 1
    FROM user_moderation_actions m
    WHERE m.user_id = u.id
      AND m.action = 'freeze'
      AND (m.expires_at IS NULL OR m.expires_at > NOW())
    ORDER BY m.created_at DESC
    LIMIT 1
  ) AS is_frozen
FROM users u;
```

软删除状态走 `users.deletion_requested_at IS NOT NULL` 直接判定 (跟 §1.1 "30 天 grace window" 语义一致, Session 4a' cron job 在 grace 过期后清除 + 级联到 projects/brands/responses)。

#### 4.1.3 登录审计 `/admin/users/login-audit`

- 字段：时间 / user_id / email / IP / UA / 结果 (`success / failed / locked`) / 失败原因
- 筛选：user + IP + 时间段
- 警戒规则（MVP 只做显示，不做自动阻断）：
  - 同一 IP 1 小时内 10 次失败 → UI 标记红
  - 同一账号跨地理位置跳变 → UI 标记橙

#### 4.1.4 数据模型

> ⚠️ **真相源说明 (2026-04-21)**: `admin_users` 字段完整定义以 [§5.6.8 新增表汇总](#568-新增表汇总) 为唯一真相源。本段只列 Module A 特有的 3 张表 (`admin_audit_log` / `user_moderation_actions` / `user_activity_stats`)，`admin_users` 在此不复述，避免两处维护造成 drift (Session A0 曾发生 Q2 字段命名偏离, 根因即是此类重复)。

```sql
-- Module A 特有新增表 (admin_users 见 §5.6.8)
admin_audit_log      (id, operator_id, action, target_type, target_id, diff_json, reason, ip, ua, created_at)

-- user_moderation_actions: A1' round 8 决议字段
--   id (PK, UUID)
--   user_id (FK users.id, NOT NULL) — 被操作的用户
--   action (String, NOT NULL, CHECK IN ('freeze','unfreeze','force_password_reset','soft_delete'))
--   operator_id (FK admin_users.id, NOT NULL) — 操作的管理员
--   reason (Text, NULL)
--   expires_at (Timestamp, NULL) — 自动解除时间 (e.g. 临时冻结)
--   created_at (Timestamp, NOT NULL, DEFAULT NOW)
user_moderation_actions (id, user_id, operator_id, action, reason, expires_at, created_at)

-- user_activity_stats: A1' round 8 决议字段
--   user_id (PK, FK users.id)
--   last_login_at (Timestamp, NULL)
--   login_count_30d (Integer, NOT NULL, DEFAULT 0)
--   query_count_30d (Integer, NOT NULL, DEFAULT 0) — 30d 窗对运营更有用
--   last_active_at (Timestamp, NULL)
--   updated_at (Timestamp, NOT NULL)
user_activity_stats  (user_id, last_login_at, login_count_30d, query_count_30d, last_active_at, updated_at)
```

> **A1' round 8 schema alignment (2026-04-28)**: `user_activity_stats` 字段集由 `(project_count, api_call_count_7d)` 改为 `(query_count_30d, last_active_at)`, 30 天窗对运营页面更有信号; `user_moderation_actions` CHECK 4 值 + `expires_at` 落定。详见 CLAUDE.md 决策 #30.G。

---

### 4.2 Module B — 数据管道 & 采集健康

> 这一组模块是 MVP **每天使用频率最高** 的部分。所有页面都以"故障发现 → 定位 → 处置"为动线。
>
> **⚠️ §4.2 为摘要 (6 子页)。完整实现 (10 子页 · 含 Prompt 模板管理 / Response 质检 / Trace & Lineage / 变更审批 4 个延伸)、失败场景 F1-F10、以及新增 8 张数据表，见 [`ADMIN_PRD_B_PIPELINE.md`](./ADMIN_PRD_B_PIPELINE.md)。本摘要与深化文档出现冲突时，以深化文档为准。**
>
> **📌 Adapter 行为真相源**: 引擎健康 / 账号池 / 代理池 / 失败重试分组的底层数据模型、错误码定义、状态机、自动化动作的副作用边界, 全部以 [`docs/ADAPTER_CONTRACT.md`](./ADAPTER_CONTRACT.md) 为准。Admin 这层只是 **把 Adapter 已暴露的能力可视化** — 任何想新加的监控字段或告警规则, 必须先落在 ADAPTER_CONTRACT, 再接入 Admin 看板。

#### 4.2.1 Pipeline 全景 `/admin/pipeline/overview`

四层漏斗可视化（Topic → Prompt → Query → Response），每层显示：

- 总数（累计 / 当日新增）
- 活跃数（`status = active`）
- 当日生成 / 执行 / 成功 / 失败分布
- 点击下钻到该层列表

**顶部 KPI**：
- 当日 Response 成功率（引擎平均）
- 当日 Query 总执行数 / 目标数（完成率）
- 当日 Topic / Prompt 增量（判断 Planner 是否正常）

**趋势图**：近 14 天堆叠柱状图（各引擎成功 / 失败 Response 数）。

#### 4.2.2 引擎健康 `/admin/pipeline/engines`

每个引擎（ChatGPT / 豆包 / DeepSeek）一张卡：

```
┌─────────────────────── ChatGPT ────────┐
│ 🟢 正常                   今日成功率 94.2% │
│ ────────────────────────────────────── │
│ 近 24h 样本:  12,340                    │
│ P50 延迟:     8.2s                      │
│ P95 延迟:     22.1s                     │
│ 错误分布:                               │
│   - CAPTCHA:       42%                  │
│   - TIMEOUT:       28%                  │
│   - PARSER_FAIL:   18%                  │
│   - PROXY_BLOCK:    8%                  │
│   - OTHER:          4%                  │
│ ────────────────────────────────────── │
│ [查看失败样本] [切换降级API] [停采]       │
└────────────────────────────────────────┘
```

**关键动作**：
- **切换降级 API**：将该引擎的 adapter 从 Web 切到 API，立即生效（写入 `engine_runtime_config.adapter_mode = 'api'`），所有新入队的 Query 走 API 路径
- **停采**：立即暂停该引擎所有新任务入队；running 任务跑完后停止

**数据源真相**：

- 5 个 KPI (成功率 / P50 / P95 / 错误分布 / 样本数) 全部来自物化视图 `engine_health_5min` (SQL 定义见 [`ADAPTER_CONTRACT.md §10.4`](./ADAPTER_CONTRACT.md#104-metrics-推给-admin-admin_prd-42))，每 5 分钟刷新。
- **成功率分母的关键口径**: 自动剔除 `NO_ACCOUNT_AVAILABLE` 与 `COOKIE_EXPIRED` (账号池 / Cookie 侧问题, 非引擎故障) — 与 PRD §4.6 引擎可用性定义一致, 见 [`ADAPTER_CONTRACT.md §6.1`](./ADAPTER_CONTRACT.md#61-错误码表-权威)。
- **错误分布饼图的 8 个错误码** (CF_BLOCKED / COOKIE_EXPIRED / CAPTCHA_REQUIRED / PAGE_CRASHED / PROXY_DEAD / NO_ACCOUNT_AVAILABLE / EXTRACT_EMPTY / TIMEOUT) 来自 `AdapterError.code` 枚举, 不得自造, 不得合并显示 (合并会丢失诊断信号)。
- **"查看失败样本"** 抽屉: 直接读取 `ai_responses.harUrl + screenshotUrl + rawHtmlUrl` 三件套 (每次 attempt 独立留档, ADAPTER_CONTRACT §10.1), 点击"重放到本地" 走 `page.routeFromHAR()` 在 admin debugger 内回放。

**DOM 变更告警规则** (ADAPTER_CONTRACT §6.1 的"告警级别"列落地):

- 同一 Adapter 同一 selector 连续 3 条 `EXTRACT_EMPTY` 失败 → 自动发 **P1 告警 "DOM 变更疑似"**, 在本页该引擎卡片顶部标红 + 插入一行 "近 24h 新 selector failure: xxx" + 跳转至 [`ADAPTER_CONTRACT.md §8.3`](./ADAPTER_CONTRACT.md#83-引擎特异-quirks) 对应引擎的 selector 章节便于修订。

#### 4.2.3 爬取任务队列 `/admin/pipeline/queue`

- Tab 切换：`Pending / Running / Failed / Completed (近 24h)`
- 列表字段：task_id / engine / profile / prompt 摘要 / 进入队列时间 / 尝试次数 / 状态 / 原因
- 行内操作：重试 / kill / 复制载荷
- 批量：多选 → 批量重试 / 批量标记忽略
- 失败重试的重试次数上限硬编码（`MAX_RETRY=3`），超过后进入"需人工分类"（走 §4.2.6）

#### 4.2.4 账号池水位 `/admin/accounts-pool`

> **架构边界** (2026-04-23, CLAUDE.md 决策 #28.A): 本页的数据与业务逻辑 (`accounts` / `account_states` / `account_registration_logs` 表读写, Luban SMS live client, auto-register orchestrator, cookie bundle 读写) 全部由 **Platform Layer** (`backend/src/accounts/**`) 提供, 契约真相源为 [`ADAPTER_CONTRACT.md §5.3 状态机 / §5.4 自动注册`](./ADAPTER_CONTRACT.md)。本页 (Session A2 交付) 仅是 **HTTP wrapper + 可视化**, admin API handler 必须 `import { ... } from '@/accounts/**'`, **严禁** 重写 Luban / auto-register / crypto 业务逻辑, 避免双轨代码。Platform Layer 已由 App Session 1.2 交付。

每个引擎一屏，内容：

- 水位柱状图（`active / cooldown / frozen / pending_register` 四状态）
- 预警阈值：`active_count < 水位下限` → 首页红条告警
- 账户列表：用户名（遮盖）/ 状态 / 上次使用 / 连续失败数 / 标签
- 自动注册历史（近 7 天）：时间 / 接码平台 / 成本 / 结果
- 手动操作：冻结 / 解冻 / 强制下线 / 添加账号（粘贴 cookie）

**阈值配置**（MVP hardcode，Phase 2 迁到 UI）：`config/account-pool.yaml`。

**账号状态机 & Cookie 粘贴规范真相源**:

- 4 状态机 (ACTIVE ↔ COOLDOWN 12h ↔ FROZEN ↔ BANNED) 及触发条件见 [`ADAPTER_CONTRACT.md §5.1`](./ADAPTER_CONTRACT.md#51-账号状态机)。本页按钮"冻结/解冻/强制下线"的跳转规则必须与契约一致, 禁止自造新状态转移。
- **Cookie 粘贴表单只接受两种格式**: EditThisCookie JSON 数组 或 浏览器"Copy as HAR"的 `request.cookies[]`; 其它格式拒绝, 前端自动检测并转换为 Playwright `BrowserContext.addCookies()` 格式 (ADAPTER_CONTRACT §5.3)。
- **DeepSeek 特例**: 表单必须同时有 `userToken` 输入框 (DeepSeek 用 localStorage, 只传 Cookie 无效); 该字段随账号一起加密存储。
- **存储要求** (2026-04-23 更新, CLAUDE.md #28.C1): `encryptedCookies: Bytes` 字段 **MVP 阶段存明文 UTF-8 JSON** (`JSON.stringify({cookies, localStorage, userToken?})` 的 UTF-8 bytes), 字段名与 Bytes 类型保留作为日后 AES-256-GCM + KMS 升级的预留点, 不改 schema。UI 仍遵守"回显永远 `***` / 审计日志不记明文" 两条行为纪律 (避免 operator 手动 psql 查表和 UI 显示耦合, 减少未来加密时 UI 迁移成本); 审计日志仅记"粘贴 cookie" 动作名 + 时间 + operator, **严禁** 记录 JSON 内容本身。升级加密时机: 付费版本 / B2B 客户合规要求触发时, 走标准 migration + codec 替换, 无需改 Prisma schema 字段名。
- **并发锁**: 两个 scheduler worker 取账号必须走 `SELECT ... FOR UPDATE SKIP LOCKED` (SQL 见 ADAPTER_CONTRACT §7.2), 否则会选到同一账号造成状态污染 — Admin 本页的"当前使用中"状态依赖这个锁保证准确。

**自动注册** (`pending_register` 状态对应的流程):

- MVP 仅豆包 / DeepSeek 自动注册 (CN 引擎, 鲁班SMS 接码), ChatGPT / Gemini 半自动 (脚本 + CAPTCHA 失败告警)。完整流程见 [`ADAPTER_CONTRACT.md §5.4`](./ADAPTER_CONTRACT.md#54-自动注册-cn-引擎)。
- "自动注册历史" 表的 `cost` 列从 `AccountRegistrationLog` 表读取, 单号成本 ¥0.5-2, 累计展示月消耗。
- 触发条件: `account_pool.active_count < 3` 且该引擎未在 `pending_register` 状态中 (避免重复触发)。

#### 4.2.5 代理池状态 `/admin/pipeline/proxies`

- 每个区域（overseas / cn）代理池的 IP 列表
- 字段：IP / Provider / 可用性 / 近 1h 请求数 / 失败率 / 最后使用
- 操作：拉黑 / 重新启用 / 补充（触发代理供应商 API）

**MVP 代理调度规则** (Ninja Clash 订阅方案真相源见 [`ADAPTER_CONTRACT.md §7.1`](./ADAPTER_CONTRACT.md#71-代理调度) 及 memory `project_genpano_proxy_architecture.md`):

- **Solo 阶段不做 IP 池 CRUD**: Admin 只看订阅源健康度 + 当前可用节点列表 (从订阅链接自动刷新, 每 6h 一次), 不提供"手动添加 IP"表单 (避免过度工程化)。
- **失败率阈值**: 节点近 1h 失败率 > 30% 自动 `status='probing'` 降级; Admin 页显示红标。
- **IP 粘性**: 同一账号在 `cooldown_until` 前优先复用上次成功代理 (不是"先到先得"), 本页"最后使用"字段体现这个关系。
- **CN 引擎无代理**: 豆包/DeepSeek 国内直连, 本页 cn Tab 只显示"直连, 无代理" 占位, 不是空态。

#### 4.2.6 失败重试中心 `/admin/pipeline/retry-center`

"所有重试上限后仍失败的任务"集中地。按失败原因分组：

- `CAPTCHA_UNSOLVED` → 批量丢给新 profile 重跑
- `PARSER_FAIL` → 丢给 Parser 新版本测试 + 报告 bug
- `PROXY_BLOCK` → 换代理池重跑
- `OTHER` → 人工判断

每组支持批量操作；每个任务可查看原始 HTML / 截图。

**分组映射真相源** (与 ADAPTER_CONTRACT §6.1 错误码表对齐):

| 本页分组 | 对应 AdapterError.code | 上游处置已做 | 人工层要做 |
|---------|-----------------------|-------------|-----------|
| `CAPTCHA_UNSOLVED` | `CAPTCHA_REQUIRED` (三级全失败后) | Adapter 已走 CapSolver → 视觉 → 滑块轨迹三级 (ADAPTER_CONTRACT §9) | 人工过一次 Cookie, 或标记该 profile 废弃 |
| `PARSER_FAIL` | `EXTRACT_EMPTY` | 不自动重试 (selector 过期大概率重试无效) | 对比 fixture + ADAPTER_CONTRACT §8.3 quirks, 修 selector 后跑 HAR 回放 |
| `PROXY_BLOCK` | `CF_BLOCKED` / `PROXY_DEAD` | 代理已加黑 1h / 24h | 确认 Ninja Clash 订阅是否健康, 触发换组 |
| `OTHER` | `PAGE_CRASHED` / `TIMEOUT` (3 次后) / 其它未归类 | 已尝试重启 Browser Context | 看 HAR + 截图定位 |

**不进入本页的失败**:

- `NO_ACCOUNT_AVAILABLE` → 对应 Query 已置 PENDING, 等账号补充后重入; 在 §4.2.4 账号池页处置, 不污染重试中心。
- `COOKIE_EXPIRED` → 账号已 COOLDOWN 12h, 自动 warmup 探测; 在 §4.2.4 账号池页处置。

**HAR 复现按钮**:

- 每条任务详情支持"下载 HAR" (已脱敏) + "在 admin sandbox 回放" (启动内置 Playwright headless + routeFromHAR), 便于在不触碰真实账号/代理的前提下反复验证解析器修改效果。
- 脱敏规则见 [`ADAPTER_CONTRACT.md §10.2`](./ADAPTER_CONTRACT.md#102-har-录制约束); **禁止** Admin 提供"查看原始 cookie" 按钮 (合规红线)。

#### 4.2.7 数据模型

```sql
engine_runtime_config  (engine, adapter_mode, is_paused, updated_at, updated_by)
proxy_ips              (id, region, provider, address, status, last_used_at, failure_count)
scrape_account_pool    (id, engine, username_masked, encrypted_cookies, status,
                        segment_group, cooldown_until, consecutive_failures,
                        last_used_at, last_health_check_at, registered_at, created_by,
                        tags JSONB)
account_registration_log (id, engine, sms_provider, phone_masked, success, duration_ms,
                          cost_cny, failure_reason, created_at)
-- 物化视图 (Adapter 层观测数据源, 每 5 分钟刷新 by cron `refresh_engine_health`):
engine_health_5min     (engine, window_start, sample_count, success_rate,
                        p50_latency_ms, p95_latency_ms, error_breakdown JSONB)
-- 复用 App 侧: query_executions, ai_responses (含 harUrl / screenshotUrl / rawHtmlUrl / attempts)
```

**模型定义真相源**: 以上表结构与字段语义由 [`ADAPTER_CONTRACT.md §5.1 / §10.1 / §10.4`](./ADAPTER_CONTRACT.md) 权威定义; Admin 这层只是消费。任何新字段需求必须先在 ADAPTER_CONTRACT 落地, 再通过迁移进入本表。

---

### 4.3 Module C — 知识图谱运营

> **⚠️ §4.3 为摘要 (6 子页)。完整实现 (9 子页 · 含实体合并/拆分 / KG Diff Viewer / KG 质量监控 3 个延伸)、K1-K12 工作流场景、实体状态机 (`discovered → submitted → approved → active`)、以及新增 10 张数据表 (含 `submission_trust_score` 四档信任体系 + `daily_kg_llm_budget` LLM 成本闸门)，见 [`ADMIN_PRD_C_KG.md`](./ADMIN_PRD_C_KG.md)。本摘要与深化文档出现冲突时，以深化文档为准。**

#### 4.3.1 行业 & 品类树 `/admin/kg/industries`

- 左侧：4 个 MVP 行业列表，点击展开品类树
- 右侧：选中品类的详情（含品牌数 / 产品数 / 近 7 天 Topic 生成量）
- 品类树支持：新建子品类 / 改名 / 移动 / 标记 deprecated（不删除，避免级联）
- LLM 生成新品类：选中节点 → "用 LLM 补全子品类" → 预览 → 入库

#### 4.3.2 品牌审核 `/admin/kg/brands`

表格 + 筛选（状态 / 行业 / 来源 / 置信度）。状态枚举：

- `pending` — LLM 刚发现，待审
- `approved` — 审核通过，进入采集
- `rejected` — 驳回（写原因）
- `merged` — 合并到另一品牌（alias 追加）
- `inactive` — 下线

**详情抽屉**：

- 所有别名（按语言 + 来源分类）
- 所有关系边（COMPETES_WITH / SAME_GROUP）+ 置信度
- 近 14 天 mention 样本（随机抽 10 条）
- Discovery source（LLM 原始输出引用）

**批量动作**：approve / reject / merge 支持多选，reason 必填。

#### 4.3.3 产品审核 `/admin/kg/products`

结构同品牌，字段额外有：关联品牌 / 关联品类 / keyFeatures。

#### 4.3.4 别名与关系 `/admin/kg/aliases-relations`

聚焦"别名消歧" + "关系置信度清理"两类常见运营动作：

- **别名冲突**：列出"同一别名被多个品牌 / 产品认领"的冲突，运营决定归属
- **关系边清理**：列出 `confidence < 0.3` 的边、`confidence > 0.9` 但类型可能矛盾的边（如既是 COMPETES_WITH 又是 SAME_GROUP）
- 支持批量调整置信度 / 删除边

#### 4.3.5 Brand Submission 审核 `/admin/kg/brand-submissions`

用户通过 App 提交"我的品牌不在你们图谱里"后，进入此队列：

- Inbox 风格的列表
- 每条：用户 email / 提交时间 / 行业 / 品牌名 / 用户补充信息 / LLM 预验证结果
- **LLM 预验证**：系统在用户提交后立即调 LLM：`是否存在？行业归属？可能的官方名称？` → 输出填充到详情抽屉
- 动作：approve（触发 KG 入库 + 首次产品发现）/ reject（写原因并回邮）/ merge（合并到已有品牌）
- SLA：MVP 承诺用户 24 小时内审核完成，首页告警提示"超 24h 未处理的 submission"

#### 4.3.6 Discovery Logs `/admin/kg/discovery-logs`

LLM 每次发现调用的原始输出 + 入库结果。用于：

- 回溯"某品牌为什么被入库"
- 审计 LLM 幻觉（发现的品牌在现实中不存在）
- 质量评估（计算近 30 天 LLM 发现品牌的 approved 比率）

#### 4.3.7 数据模型

```sql
-- 大部分复用 App 侧: kg_industries, kg_categories, kg_brands, kg_products,
-- kg_brand_relations, kg_product_relations, discovery_logs

-- kg_review_queue: A1' round 8 决议字段 (PRD 命名 + status 加 merged 4 值)
--   id (PK, UUID)
--   target_type (String, NOT NULL, CHECK IN ('brand','product','category'))
--   target_id (UUID, NOT NULL)
--   status (String, NOT NULL, CHECK IN ('pending','approved','rejected','merged'))
--   submitted_by (FK admin_users.id, NOT NULL)
--   submitted_at (Timestamp, NOT NULL, DEFAULT NOW)
--   reviewer_id (FK admin_users.id, NULL)
--   reason (Text, NULL)
--   reviewed_at (Timestamp, NULL)
kg_review_queue   (id, target_type, target_id, status, submitted_by, submitted_at, reviewer_id, reason, reviewed_at)

-- alias_conflicts: A1' round 8 决议字段 (PRD N-候选 JSONB 设计胜出)
--   id (PK, UUID)
--   alias_value (String, NOT NULL)
--   language (String, NOT NULL) — e.g. 'zh-CN', 'en'
--   candidate_ids (JSONB, NOT NULL) — N 个候选 entity id 列表
--   resolved_to_id (UUID, NULL) — 最终选定的 entity id
--   resolved_admin_id (FK admin_users.id, NULL)
--   resolved_at (Timestamp, NULL)
alias_conflicts   (id, alias_value, language, candidate_ids JSONB, resolved_to_id, resolved_admin_id, resolved_at)

-- brand_submissions: A1' round 8 首次落定义 (PRD 原留白 "复用 App 侧, 不列字段")
--   id (PK, UUID)
--   submitter_user_id (FK users.id, NOT NULL)
--   brand_name_zh (String, NULL)
--   brand_name_en (String, NULL)
--   aliases (JSONB, NULL)
--   trust_score (Numeric, NULL)
--   status (String, NOT NULL, CHECK IN ('pending','approved','rejected'))
--   sla_started_at (Timestamp, NOT NULL, DEFAULT NOW)
--   resolved_at (Timestamp, NULL)
--   resolved_admin_id (FK admin_users.id, NULL)
brand_submissions (id, submitter_user_id, brand_name_zh, brand_name_en, aliases JSONB, trust_score, status, sla_started_at, resolved_at, resolved_admin_id)
```

> **A1' round 8 schema alignment (2026-04-28)**: `alias_conflicts` 走 PRD N-候选 JSONB 设计 (现实别名冲突常 ≥3 候选, 强于 spec 2-候选状态机); `kg_review_queue` status 加 `merged` 第 4 值支持实体合并 use case; `brand_submissions` 首次落完整字段定义 (含 SLA 时间戳)。详见 CLAUDE.md 决策 #30.G。

---

### 4.4 Module D — 运营 & 监控

#### 4.4.1 成本看板 `/admin/cost/daily`

**顶部 KPI**：当日总成本 / 本月累计 / 预算余额 / 预估月度支出。

**归因视图**（三级下钻）：

1. **按引擎** 堆叠面积图（ChatGPT / 豆包 / DeepSeek × LLM API / 代理 / 爬取工时）
2. **按行业** 饼图
3. **按品牌 Top 10** 水平条形图

**预算控制**：
- 每日硬上限（`daily_budget_cny`）
- 当天成本达到 80% → 首页黄色告警
- 达到 100% → 自动停止新任务入队（running 不受影响）
- **紧急提高预算**入口（MVP 超简陋：一个 input + 二次确认 dialog，写审计日志）

#### 4.4.2 告警中心 `/admin/alerts`

所有自动告警的统一 Inbox。告警来源：

- Pipeline 成功率跌破阈值
- 账号池 / 代理池水位低
- 成本超预算
- Brand Submission 超 SLA
- 系统错误日志聚合（Sentry-like，MVP 用 pino + 聚合到 DB 即可）

每条告警：严重度 / 模块 / 首次出现时间 / 最后出现时间 / 发生次数 / 认领人 / 状态（new / acknowledged / resolved）。

#### 4.4.3 调度配置 `/admin/schedule`

MVP 最小化的调度配置：

- **平台调度开关**（总 kill switch）
- **每日开始时间**（UTC 偏移 + 小时）
- **分层频率**（high / medium / low 三档的间隔天数）—— MVP 显示只读，Phase 2 可编辑
- **单次采集预算**（每日 Query 上限数）

**手动触发区**（这个在 MVP 最有用）：
- "立即对某品牌跑一次全量采集"表单（选品牌 + 选引擎 + 确认）
- "补采某 Topic"

#### 4.4.4 公告 & 邮件 `/admin/comms`

**公告**：
- 站内 Banner 管理（title + body + link + 启用 / 停用 + 目标受众：all / 某行业）
- 最多 1 条同时显示（多条按 priority）

**邮件模板**：
- 模板列表（验证 / 欢迎 / 密码重置 / Brand Submission 批复 / 周报）
- 每个模板：预览（zh-CN / en-US 切换）+ 发测试邮件到指定地址
- **不提供在 UI 改模板内容**；模板源码在 `packages/emails`

#### 4.4.5 商务线索 `/admin/commercial/leads`

未来数据变现入口。MVP 只做接收 + 跟进标记：

- 字段：来源（行业报告 CTA / 咨询表单 / 其他）/ 公司 / 联系人 / 行业 / 需求描述 / 提交时间
- 状态：`new / contacted / qualified / won / lost`
- 动作：更改状态 / 加备注 / 标记跟进日期
- 导出 CSV（限 super_admin + bizdev）

**Phase 2 预留**：订单、发票、合同、Stripe 支付、交付工作流。

#### 4.4.6 Agent/MCP 运营 `/admin/mcp-ops`

GENPANO 是 Agent-native 产品，必须监控谁在"程序化访问"平台：

- **API Key 列表**：用户 / Key 名称 / 创建时间 / 最近调用 / 调用量（24h / 7d / 30d）/ 限流命中次数 / 状态
- **MCP 调用趋势**：每个 tool（`genpano_get_brand_visibility` 等）的日调用数 + P95 延迟 + 错误率
- **抽样查询**：随机抽 20 条 MCP 请求的 payload，用于"用户 Agent 在问什么"研究
- **限流 / 封禁**：单个 key 可调整 rate limit 或标记 suspend

#### 4.4.7 审计日志 `/admin/audit-log`

所有 Admin 特权动作的全局视图。字段：

- 时间 / 操作员 / 动作 / 对象类型 / 对象 ID / 修改前 → 修改后 diff / 理由 / IP / UA

支持：时间筛选 / 操作员筛选 / 动作筛选 / 对象类型筛选 / 关键字搜索。

**导出**：super_admin 可导出 CSV，导出行为**自身也写入 audit_log**（防止"清除痕迹"）。

#### 4.4.8 数据模型

```sql
-- cost_daily: A1' round 8 决议字段 (合并 PRD + spec)
--   id (PK, UUID)
--   date (Date, NOT NULL)
--   engine_id (String, NOT NULL) — chatgpt / doubao / deepseek-CN
--   category (String, NULL) — 品类聚合维度
--   industry_id (UUID, NULL)
--   brand_id (UUID, NULL)
--   amount_cny (Numeric, NOT NULL, DEFAULT 0)
--   amount_usd (Numeric, NOT NULL, DEFAULT 0) — 多币种支持
--   token_count (Integer, NOT NULL, DEFAULT 0)
--   query_count (Integer, NOT NULL, DEFAULT 0)
--   aggregated_from (Timestamp, NOT NULL)
--   aggregated_to (Timestamp, NOT NULL)
--   UNIQUE (date, engine_id, industry_id, brand_id, category)
cost_daily              (id, date, engine_id, category, industry_id, brand_id, amount_cny, amount_usd, token_count, query_count, aggregated_from, aggregated_to)

-- budget_config: A1' round 8 决议字段 (spec 强 schema 取代 PRD key-value)
--   id (PK, UUID)
--   scope (String, NOT NULL, CHECK IN ('global','engine','industry','brand'))
--   scope_id (UUID, NULL) — global 时 NULL
--   monthly_budget_usd (Numeric, NOT NULL)
--   warning_threshold_pct (Integer, NOT NULL, CHECK BETWEEN 0 AND 100, DEFAULT 80)
--   hard_threshold_pct (Integer, NOT NULL, CHECK BETWEEN 0 AND 200, DEFAULT 100)
--   updated_at (Timestamp, NOT NULL)
--   updated_admin_id (FK admin_users.id, NOT NULL)
budget_config           (id, scope, scope_id, monthly_budget_usd, warning_threshold_pct, hard_threshold_pct, updated_at, updated_admin_id)

-- alerts: A1' round 8 决议字段 (合并 PRD 聚合 + spec 工作流)
--   id (PK, UUID)
--   alert_type (String, NOT NULL) — e.g. 'cost_spike', 'dom_change', 'proxy_dead', 'kg_quality_drop'
--   severity (String, NOT NULL, CHECK IN ('P0','P1','P2'))
--   state (String, NOT NULL, CHECK IN ('open','acknowledged','resolved'))
--   module (String, NULL) — 来源模块
--   title (String, NOT NULL)
--   detail (Text, NULL)
--   payload (JSONB, NULL)
--   first_seen_at (Timestamp, NOT NULL, DEFAULT NOW)
--   last_seen_at (Timestamp, NOT NULL, DEFAULT NOW)
--   count (Integer, NOT NULL, DEFAULT 1)
--   ack_admin_id (FK admin_users.id, NULL)
--   ack_at (Timestamp, NULL)
--   resolved_admin_id (FK admin_users.id, NULL)
--   resolved_at (Timestamp, NULL)
alerts                  (id, alert_type, severity, state, module, title, detail, payload JSONB, first_seen_at, last_seen_at, count, ack_admin_id, ack_at, resolved_admin_id, resolved_at)

commercial_leads        (id, source, company, contact_name, email, phone, industry, note, status, assigned_to, followup_at)
announcements           (id, title, body, link, audience, priority, starts_at, ends_at, enabled)
mcp_request_samples     (id, api_key_id, tool, payload_redacted, latency_ms, status, created_at)
```

> **A1' round 8 schema alignment (2026-04-28)**: `alerts` 合并 PRD 聚合设计 (`first_seen_at` / `last_seen_at` / `count` 去重) + spec 工作流设计 (`state` open/acknowledged/resolved + `ack_admin_id`/`ack_at` + `resolved_admin_id`/`resolved_at` 双 admin 分离); `cost_daily` 合并 PRD (engine/category/CNY/token) + spec (USD 多币种 + aggregated_from/to 时间窗); `budget_config` 走 spec 强 schema 取代 PRD key-value JSONB (预算配置项有限, 强类型对前端友好)。详见 CLAUDE.md 决策 #30.G。

---

## 5. 跨模块设计 (Cross-Cutting)

### 5.1 权限模型

```
admin_users.role 最终取值域 (Phase 2 目标): {super_admin, ops, data_ops, support, bizdev}

每个 API endpoint 声明所需角色:
  middleware: requireRole(['super_admin', 'data_ops'])

MVP (Session A0-A5): 所有 endpoint 只允许 super_admin
  数据层: CHECK (role IN ('super_admin')) —— DB 层收紧, 防 SQL 直写绕过 (defense in depth)
  应用层: requireRole(['super_admin']) 显式列表, 便于 Phase 2 扩展

Phase 2 RBAC 落地时 (后续 Session):
  ALTER TABLE admin_users DROP CONSTRAINT admin_users_role_chk;
  ALTER TABLE admin_users ADD CONSTRAINT admin_users_role_chk
    CHECK (role IN ('super_admin','ops','data_ops','support','bizdev'));
  扩展各 endpoint 的 requireRole() allow-list, 无需改 endpoint 代码逻辑
```

**⚠️ 实施约束 (2026-04-21 Session A0 对齐)**: MVP 阶段 `role` 字段**禁止**用 Prisma enum 实现, 必须用 `String + CHECK constraint`。理由: enum 的 migration (ALTER TYPE ADD VALUE) 在 Postgres 里有事务限制, CHECK 扩值只是 DROP/ADD CONSTRAINT 一行 SQL, migration 更灵活。

**前端侧**：路由 guard + 按钮级 guard，非授权角色看不到入口；后端仍然做最终校验。

### 5.2 审计日志规范

所有下列动作 **必须** 写入 `admin_audit_log`：

- 任何对 `kg_*` / `scrape_account_pool` / `engine_runtime_config` / `budget_config` 的写操作
- 任何对 `users` 表的 moderation 动作
- 任何数据导出
- 任何手动触发爬取 / 重跑任务
- 任何角色 / 权限变更

写入内容：`operator_id, action, target_type, target_id, diff_json, reason, ip, ua, created_at`。

**不可删除 / 不可修改**：`admin_audit_log` 表在迁移里明确只允许 INSERT。审计导出也是 INSERT。

### 5.3 部署与访问控制

- Admin 走独立子域名：`admin.genpano.internal`（MVP 阶段仅限 Frank 本机 + 固定 IP 白名单）
- 强制 HTTPS + HSTS
- 基础认证层：`admin.genpano.internal` 前面加一层 Cloudflare Access (或 Tailscale)，应用层 session 是第二层
- MVP 暂不上 2FA，但 schema 预留 `admin_users.totp_secret`

### 5.4 与 App 数据层的关系

Admin **不建自己的数据副本**。它直接读 App 的 Postgres（同一套表）+ 一些 Admin 专属的小表（`admin_*`）。原则：

- **Read**：Admin 能读所有表
- **Write to KG / Pipeline / Config**：允许，写入同一张表，额外写审计
- **Write to User data**：禁止（只允许 `status` 字段的 moderation 操作）
- **Aggregations**：Admin 有自己的物化视图 / 定时任务生成（`user_activity_stats`, `cost_daily`）

### 5.5 Admin 后端 API 前缀

```
/admin/api/v1/*
```

与 App 的 `/api/v1/*` 完全隔离。MVP 前后端放在同一个 Next.js 项目（不同 `app/admin/**` 路由组），Phase 2 可分离到独立服务。

### 5.6 Admin 认证 & 登录页

Admin 用户的身份认证是平台安全的第一道防线。MVP 采用"应用层 Email + Password"方案，配合 Cloudflare Access 或 Tailscale 的网络层隔离。

#### 5.6.1 登录页 UI (`/admin/login`)

- **页面结构**：左侧 240px 为品牌标识 + 环境色带（将 §6.1 的 4px 色带展开为 8px，更醒目），右侧 form 区
- **表单字段**：Email + Password 两个输入框，"登录"按钮（青绿色，`--color-accent`）
- **失败提示**：
  - 前 5 次错误：显示"邮箱或密码错误"（不区分是哪个，防止邮箱枚举）
  - 第 6 次及以后（15 分钟内）：显示"账户已锁定，请在 15 分钟后重试"，同时发送 P1 告警给 Frank（防暴力破解）
  - 15 分钟后自动解锁（`admin_login_attempts` 表通过 cron 清理过期记录）
- **"忘记密码"链接**：跳转 `/admin/password-reset`（见 §5.6.5）
- **登录后重定向**：跳到 `/admin`（首页总览），无特殊历史记录恢复（Admin 操作严肃，不走默认 redirect）
- **MVP 无注册页**：super_admin 通过 seed script 或 CLI 命令创建（见 §5.6.4）

#### 5.6.2 Token 策略

Admin 采用短生命周期 Token + Silent Refresh 机制，比 App 的标准认证更严格（安全优先）。

**Cookie 配置**（HttpOnly + Secure 三件套，无异议）：
```javascript
// 设置 access_token cookie
res.setHeader('Set-Cookie', [
  `access_token=${token}; HttpOnly; Secure; SameSite=Strict; Path=/admin; Max-Age=900; Domain=admin.genpano.internal`
])
```

**Token 生命周期**：
- **Access Token**：15 分钟有效期，用于所有 API 请求
- **Refresh Token**：7 天有效期（比 App 的 30 天短），存放在另一个 HttpOnly cookie，仅用于 silent refresh endpoint
- **Silent Refresh**：前端 (`/admin` 路由加载后) 无感知地在 `token_expires_in - 5min` 时触发 `POST /admin/api/v1/auth/refresh`，刷新 access token。若 refresh token 也过期，重定向到 `/admin/login`

**特权操作 Re-Auth**（关键）：
- 执行"修改预算、审批品牌入库、重跑爬取任务、冻结用户"等特权动作时，如果距上次密码认证已超过 **30 分钟**，触发 Modal 要求 Admin 重新输入密码
- 流程：Modal 显示"此操作需要身份确认" → 输入密码 → 调 `POST /admin/api/v1/auth/re-auth { password }` → 验证通过后刷新"最后认证时间"戳 → 继续原操作
- 目的：防止 Admin 账户被 XSS / 会话劫持 + 物理离开电脑时的风险

#### 5.6.3 会话管理

**单设备活跃 Session**（防多处登录滥用）：
- Admin 新登录时，旧 session 自动失效（`admin_sessions` 表中旧 token 设 `revoked_at = now()`）
- 旧 session 的任何后续 API 调用返回 `401 Unauthorized`，前端弹"您在其他地点登录，请重新登录"的 Modal（无刷新，直接跳 `/admin/login`）

**会话表结构**（`admin_sessions`）：
```sql
CREATE TABLE admin_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  admin_user_id UUID NOT NULL REFERENCES admin_users(id),
  token_hash VARCHAR(255) NOT NULL UNIQUE,  -- bcrypt(token), 用于快速查询
  ip_address INET,                           -- 登录来源 IP
  user_agent TEXT,                           -- User-Agent（用于设备识别）
  last_activity_at TIMESTAMP DEFAULT now(),  -- 最后活动时间（用于超时检测）
  created_at TIMESTAMP DEFAULT now(),
  expires_at TIMESTAMP NOT NULL,             -- 7 天后
  revoked_at TIMESTAMP,                      -- 手动撤销或新登录踢出时刻
  UNIQUE(admin_user_id, revoked_at IS NULL)  -- 同一用户最多 1 个活跃 session
);
CREATE INDEX idx_token_hash ON admin_sessions(token_hash);
CREATE INDEX idx_admin_user_active ON admin_sessions(admin_user_id) WHERE revoked_at IS NULL;
```

**登录审计**（`admin_login_attempts`）：
```sql
CREATE TABLE admin_login_attempts (
  id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  ip_address INET NOT NULL,
  email VARCHAR(255),  -- 可能是未知邮箱
  success BOOLEAN,
  failure_reason VARCHAR(50),  -- 'invalid_credentials' | 'account_locked' | 'account_suspended'
  created_at TIMESTAMP DEFAULT now()
);
CREATE INDEX idx_ip_created ON admin_login_attempts(ip_address, created_at);
CREATE INDEX idx_email_created ON admin_login_attempts(email, created_at);
```

**过期策略**：
- 若 `admin_sessions.expires_at < now()`，API 返回 `401 Unauthorized` + response body: `{ error: "session_expired" }`
- 前端拦截 `error === "session_expired"` 后弹 Modal："您的会话已过期，请重新登录"，按钮点击跳 `/admin/login`

#### 5.6.4 首个 Admin 引导 (Bootstrap)

MVP 只有 Frank 一个 super_admin，创建流程通过 CLI 完成，**不开放 UI 注册**。

**方案 A：`prisma db seed` (推荐)**

在 `prisma/seed.ts` 中定义：

```typescript
async function main() {
  // Seed Admin User
  const existingAdmin = await prisma.admin_users.findUnique({
    where: { email: 'frank@genpano.com' }
  });

  if (!existingAdmin) {
    const hashedPassword = await bcrypt.hash(process.env.INITIAL_ADMIN_PASSWORD || 'ChangeMe123!', 12);
    await prisma.admin_users.create({
      data: {
        email: 'frank@genpano.com',
        password_hash: hashedPassword,
        role: 'super_admin',
        status: 'active',
        force_password_change_at: new Date() // 首次登录强制改密码
      }
    });
    console.log('✓ Admin user created: frank@genpano.com');
  } else {
    console.log('ℹ Admin user already exists');
  }
}
```

运行 `npx prisma db seed`，自动创建或跳过（幂等）。

**方案 B：手写 CLI 命令**（若需更多交互）

`scripts/admin-bootstrap.mjs`：

```bash
npm run admin:bootstrap -- --email frank@genpano.com --password "临时密码"
```

输出：
```
✓ Admin user created
  Email: frank@genpano.com
  Role: super_admin
  First login: Change your password immediately
```

**首次登录强制改密码**：
- 登录成功后检查 `admin_users.force_password_change_at` 是否 `<= now()`
- 若是，弹 Modal："首次登录，请修改密码"，跳转 `/admin/settings/password`
- 输入新密码 → 调 `POST /admin/api/v1/auth/change-password { old_password, new_password }` → 清除 `force_password_change_at` → 重定向 `/admin`

#### 5.6.5 密码规则 & 重置

**密码强度规则**（应用层 + 前端实时校验）：
- 最少 12 字符（比 App 的 8 字符严格）
- 必须包含：大写字母 + 小写字母 + 数字
- 禁止：常见弱密码（`password123`、`admin`、`genpano` 等），前端用 zxcvbn 库评分 >= 3（中强度）

**密码哈希**：
- 算法：bcrypt，cost factor = 12（默认较慢，每次验证约 200ms，可接受）
- 存储：`admin_users.password_hash`

**密码重置流程**（MVP 仅 CLI，无自助 UI）：

CLI 命令：
```bash
npm run admin:reset-password -- --email frank@genpano.com
```

后端行为：
1. 查找 `admin_users` 记录
2. 生成一个 32 字节的随机 token（base64 编码）
3. 存入 `admin_password_resets` 表：`{ email, token_hash, expires_at = now() + 24h }`
4. 输出一次性重置链接（CLI 直接显示，不发邮件）：`https://admin.genpano.internal/admin/password-reset?token=...`
5. Frank 手工复制链接到浏览器，打开 `/admin/password-reset?token=xxx` 页面
6. 输入新密码 → `POST /admin/api/v1/auth/reset-password { token, new_password }` → 验证 token、更新密码、删除重置记录
7. 成功后重定向 `/admin/login`

> **为什么 MVP 不做邮件重置？** 因为 Frank 是唯一 Admin，若忘记密码，直接改数据库或 Tailscale 拿到服务器重跑 seed 即可。等未来加了 ops / data_ops 才需要自助邮件重置。

#### 5.6.6 API Endpoints（认证层）

```
POST   /admin/api/v1/auth/login
       { email, password }
       → 200: { access_token, refresh_token_in_cookie, expires_in }
          或 429: { error: "account_locked", retry_after_seconds }

POST   /admin/api/v1/auth/refresh
       (Cookie 含 refresh_token)
       → 200: { access_token, expires_in }
          或 401: { error: "refresh_token_expired", redirect_to: "/admin/login" }

POST   /admin/api/v1/auth/logout
       (Cookie 含 access_token)
       → 200: { message: "logged_out" }
       副作用: 设置 revoked_at, 清空 cookie

POST   /admin/api/v1/auth/re-auth
       { password }
       (Cookie 含 access_token，需有效)
       → 200: { reauthenticated_until }  // UNIX timestamp + 30min
          或 401: { error: "invalid_password" }

POST   /admin/api/v1/auth/change-password
       { old_password, new_password }
       → 200: { message: "password_changed" }
          或 401: { error: "invalid_old_password" }
```

所有 endpoint 都写入 `admin_login_attempts` 或 `admin_audit_log` 记录。

#### 5.6.7 前端防御

- **XSS 防守**：所有用户输入通过 React 自动 escape，不拼 innerHTML
- **CSRF 防守**：`SameSite=Strict` cookie 已防，无需额外 CSRF token
- **内存安全**：密码输入框使用 `type="password"`，提交后立即清空
- **Token 存储**：Token 仅存 HttpOnly cookie，**禁止** localStorage / sessionStorage
- **自动登出**：浏览器标签页 focus 回来时，若 `now() > session.expires_at`，自动触发 logout（BroadcastChannel + 防多标签页竞态）

#### 5.6.8 新增表汇总

> 🎯 **本段为 `admin_*` 表字段的唯一真相源**。§4.1.4 / Session A0-A5 Prompt / schema.prisma 均应反查本段, 不得独立重复定义。任何字段增删必须同步更新本段 + schema.prisma + CLAUDE.md 决策链 (参考决策 #24 "C. 偏离说明" 模式)。

| 表名 | 职责 | 关键字段 |
|---|---|---|
| `admin_users` | Admin 账户存储 | id (UUID), email (unique), password_hash, role (String + CHECK, MVP 仅 `super_admin`, Phase 2 扩展见 §5.1), status (String + CHECK, `active`/`suspended`), totp_secret (预留 Phase 2 2FA), force_password_change_at (DateTime?, null=不强制, `<=now()`=强制跳改密页), **last_password_at (DateTime?, re-auth gate 判据, 距 now > 30min 触发密码二次确认)**, last_login_at (DateTime?), created_at, **updated_at** |
| `admin_sessions` | 活跃会话追踪 | id (UUID), admin_user_id (FK), access_token_jti (unique, 用于撤销), refresh_token_hash (unique, sha256), ip_address, user_agent, issued_at, access_expires_at (+15min), refresh_expires_at (+7d), revoked_at |
| `admin_login_attempts` | 登录失败审计 | id (UUID), email, ip_address, success (bool), failure_code (`WRONG_PASSWORD`/`USER_SUSPENDED`/`RATE_LIMITED`/`UNKNOWN_EMAIL`), created_at |
| `admin_password_resets` | 密码重置链接 | id (UUID), admin_user_id (FK), token_hash (unique), expires_at (+24h), used_at, created_at |

**CHECK constraint (MVP 初始值)**:
```sql
ALTER TABLE admin_users ADD CONSTRAINT admin_users_role_chk
  CHECK (role IN ('super_admin'));                              -- Phase 2 RBAC ALTER 放宽, 见 §5.1
ALTER TABLE admin_users ADD CONSTRAINT admin_users_status_chk
  CHECK (status IN ('active', 'suspended'));
```

**字段语义补注**:
- `force_password_change_at`: bootstrap seed 写入 `now()`, 登录后判 `value && value <= new Date()` 跳改密页, 改密成功置 `null`
- `last_password_at`: 成功登录/改密时更新为 `now()`, re-auth gate 判 `now - lastPasswordAt > 30min` 则弹密码确认

**语义补注 (Session A0, 2026-04-21)**:
- `force_password_change_at`: `DateTime?` 替代原 PRD 可能的 `must_change_passwd Boolean` 写法。`null`=正常登录, 非 `null`=首登或被 reset 后必须改密才能进 Admin。Session A0 bootstrap 脚本 seed super_admin 时会写入当前时间触发首登改密。
- Rate limiter: 按原 Prompt §5 in-memory `Map<string, Bucket>` sliding-window 落地 (见 `backend/src/admin/auth/rate-limiter.ts`), **不**走 DB 持久化, 因此 `admin_users` 表不扩任何登录失败计数 / 锁定时间字段。DB 持久化方案 (如需服务重启后保留退避状态) 推到 Session A1 评估再说。

> 2026-04-21 · Session A0 落地扩 3 字段 (`force_password_change_at` / `last_password_at` / `last_login_at`), 与 CLAUDE.md #24 C1.2 偏差记录双向同步。(Step 11.5 误报 "DB 持久化 rate limiter" 偏差已在 Step 11.6 回滚; rate limiter 按原 Prompt §5 in-memory Map + TTL 方案落地, 无偏差。存档见 `docs/SESSION_A0_STEP_11_6.md`。)

#### 5.6.9 验收标准（Harness Layer 1）

- [ ] 错误密码 5 次后第 6 次返回 `HTTP 429` + "account_locked" error，同时生成 P1 告警 Slack 消息
- [ ] 冻结 15 分钟后自动解锁，无需手工操作
- [ ] 登录成功的 access_token cookie 验证：`HttpOnly=true`, `Secure=true`, `SameSite=Strict`
- [ ] 新标签页打开 `admin.genpano.internal` 时，若 token 有效，无感知 silent refresh 后显示仪表板；若过期，自动跳 `/admin/login`
- [ ] 执行"批准品牌入库"等特权操作，若距上次密码认证 > 30 分钟，弹 re-auth Modal；输入正确密码通过，操作继续
- [ ] `npm run admin:bootstrap` 可重复执行，第二次运行输出"admin user already exists"，无报错
- [ ] 所有登录 / 登出 / 密码操作均写入 `admin_audit_log` 或 `admin_login_attempts`

---

## 6. UI 设计原则

### 6.1 与 App UI 的区分

Admin **不能和 App 长得一样**——否则 Frank 在两者间切换时容易误操作。区分手段：

- **顶部色带**：Admin 最上方加一条 4px 的环境色带（prod 红 / staging 橙 / dev 绿），App 无
- **Header 标识**：左上角 Logo 旁加 `ADMIN` 色块徽标
- **色彩偏严肃**：主色仍用 `--color-accent`（保持品牌）但次要用 `--color-text-primary` 的深色背景块作为"严肃操作区"，而不是 App 常用的白底

所有颜色 / 圆角 / 字体 **仍然消费** `docs/DESIGN_TOKENS.md`，不另立 token。

### 6.2 高密度表格 & 行内操作

Admin 页面 90% 是"表格 + 详情抽屉"模式：

- 表格必须用 **TanStack Table**（见 CLAUDE.md 依赖规则）
- 行 hover 出现 `[...]` 下拉，展开快捷操作
- 点击行 → 右侧抽屉（不离开列表），大型详情才走路由
- 分页 + 排序 + 筛选状态同步到 URL Query（便于分享 / 书签 / 刷新）

### 6.3 危险操作的二次确认

以下操作**必须**弹二次确认，且确认框要求用户输入"目标名称"：

- 删除用户
- 驳回 Brand Submission
- 停采某引擎
- 清除代理
- 紧急提高预算
- 导出 CSV > 500 行

### 6.4 空状态 / 加载态 / 错误态

- 空状态：不要"一片空白"——给出"还没有 X，因为 Y，下一步可以 Z"
- 加载态：skeleton > spinner（仅在操作级 spinner）
- 错误态：展示原因 + 重试 + "复制错误到剪贴板"（便于 Frank 转交给 AI 诊断）

### 6.5 结构锚点 (预告)

Admin 落盘后，以下文件将成为 Admin 的结构锚点（未来 Session **在这些上演进**）：

| 文件 | 职责 |
|---|---|
| `frontend-admin/src/layouts/AdminLayout.jsx` | 侧栏 + 环境色带 + 顶部 nav |
| `frontend-admin/src/pages/AdminOverviewPage.jsx` | 首页总览（告警条 + KPI + Pipeline 漏斗 + 待办） |
| `frontend-admin/src/pages/PipelineOverviewPage.jsx` | Pipeline 四层漏斗 + 引擎健康 |
| `frontend-admin/src/pages/KgBrandReviewPage.jsx` | 品牌审核表 + 详情抽屉 |
| `frontend-admin/src/pages/CostDashboardPage.jsx` | 成本归因看板 |

> **UI Session 约束**：落盘后，后续 Admin UI Session 必须在这些锚点上**演进**，不得新开 `*V2.jsx`。新增页面先找同类锚点参照。

---

## 7. 技术栈

### 7.1 与 App 的关系

**共用 App 的技术栈**（Next.js + Prisma + Postgres + Tailwind + Recharts + TanStack Table + React Hook Form + Radix），避免双技术栈维护。部署形态：

- **MVP**：同一个 Next.js 仓库，`app/admin/*` 路由组 + 独立 middleware，通过 hostname（`admin.genpano.internal`）路由
- **Phase 2**：按需拆分独立服务

### 7.2 新增依赖（Admin 专属）

| 领域 | 依赖 | 理由 |
|---|---|---|
| 表格 | `@tanstack/react-table` | 排序 / 筛选 / 分页 / 虚拟滚动 |
| 命令面板（Cmd+K） | `cmdk` | Admin 频繁跳转，命令面板大幅提速 |
| JSON 展示 | `react-json-view-lite` | Discovery Logs / Audit diff 展示 |
| 日期范围 | `react-day-picker` | 筛选器标配（date-fns 已装） |
| 异常捕获 | `@sentry/nextjs`（Phase 2 接入） | MVP 先留 hook |

**严禁** 引入独立的 Admin UI 框架（AntD Pro / Refine 等）——会打破 Design Tokens 契约。

### 7.3 数据模型变更概述

新增表：

```
admin_users
admin_audit_log
user_moderation_actions
user_activity_stats           (materialized)
engine_runtime_config
proxy_ips
scrape_account_pool
kg_review_queue
alias_conflicts
cost_daily                    (materialized)
budget_config
alerts
commercial_leads
announcements
mcp_request_samples
```

所有表必须有 `created_at` + `updated_at`。所有可 soft delete 的实体必须有 `deleted_at`。`admin_audit_log` 表迁移里显式 `REVOKE UPDATE, DELETE`。

---

## 8. MVP 实施范围 & 验收标准

### 8.1 Must-Have (MVP Week 1-4 内必须完成)

| # | 模块 | 关键交付 |
|---|---|---|
| M1 | 账号 & 身份 | 用户列表 / 详情 / 冻结 / 登录审计；admin_users 表 + RBAC 中间件 |
| M2 | Pipeline 全景 | 四层漏斗 + 引擎健康卡 + 爬取任务队列（基础版） |
| M3 | 账号池 & 代理池 | 水位看板 + 基础告警 |
| M4 | KG 审核 | 品牌审核 / 产品审核 / Brand Submission Inbox |
| M5 | 成本看板 | 日成本归因（按引擎 + 行业）+ 预算上限 |
| M6 | 告警中心 | 最小化告警聚合 + 认领流程 |
| M7 | 审计日志 | 全局审计视图 + 所有写操作接入 |
| M8 | Admin 脚手架 | AdminLayout + 环境色带 + Cmd+K + 权限 guard |

### 8.2 Should-Have (MVP 末期或 Week 5)

| # | 模块 | 关键交付 |
|---|---|---|
| S1 | 别名与关系编辑器 | 冲突列表 + 批量调整 |
| S2 | Discovery Logs | LLM 调用原始输出审计 |
| S3 | 失败重试中心 | 按原因分组 + 批量重试 |
| S4 | 调度配置（只读） | 展示当前配置 + 手动触发 |
| S5 | 公告管理 | Banner CRUD + 邮件模板预览 |
| S6 | 商务线索 | 线索接收 + 状态跟进 |
| S7 | Agent/MCP 运营 | API Key 列表 + 调用趋势 |

### 8.3 Could-Have (Phase 2 起步点)

- 多角色 RBAC 启用
- 团队 / 组织管理
- 订阅 / 计费 / 发票
- 邮件模板 WYSIWYG 编辑
- 用户级 Feature Flag / 灰度
- 2FA
- Sentry 集成
- 完整的数据导出 / 删除请求流程（GDPR / 个保法）

### 8.4 Phase Gate 人类 Review 节点

| Gate | 时机 | 人类审查内容 | 预计耗时 |
|---|---|---|---|
| A-Gate 1 | M1 + M8 完成后 | Admin 脚手架稳固？RBAC 正确？审计日志接入全面？ | 30min |
| A-Gate 2 | M2 + M3 完成后 | 你能在 Admin 上发现并修复一次模拟的"引擎挂了"吗？ | 60min |
| A-Gate 3 | M4 完成后 | 跑 20 条 Brand Submission，测试审核体验？ | 45min |
| A-Gate 4 | M5 + M6 + M7 完成后 | 一整天使用 Admin 做运维，记录体感问题 | 1 day |

### 8.5 每个 Session 的验收脚本模板

遵循 HARNESS_ENGINEERING.md Layer 1（可执行验收），每个 Admin Session 必须附带 `verify-admin-session-X.sh`：

```bash
#!/bin/bash
set -e
# 1. 结构检查（关键文件存在）
# 2. 数据库迁移已执行（检查表 / 列）
# 3. 接口合规（OpenAPI 快照 diff）
# 4. 关键 API 烟测（curl + expected status）
# 5. 权限检查（未授权用户访问受保护 endpoint 必须 401）
# 6. 审计完整性（任何写操作后 admin_audit_log 有记录）
# 7. 无硬编码密钥 / 无 console.log 泄露 PII
```

---

## 9. 成功指标（上线后 30 天追踪）

| 指标 | 目标值 | 测量方式 |
|---|---|---|
| Admin 日均会话时长 | ≤ 20min | 用户活动统计 |
| 平台故障 MTTR（通过 Admin 发现 + 恢复） | ≤ 15min | 事件 + 审计交叉 |
| Brand Submission 审核 SLA 达标率（24h 内） | ≥ 90% | brand_submissions 时间戳 |
| KG 审核通过率（approved / total） | 60-80% | 合理区间，低说明 LLM 发现质量差 |
| 成本超预算触发次数 | ≤ 1 次 / 月 | alerts 表 |
| Admin 特权动作有审计记录 | 100% | 全量审计 |

---

## 10. Open Questions & 决策记录

### 10.1 已决策

- ✅ **独立 PRD 而非并入 PRD.md**：读者与节奏不同，独立更清晰。
- ✅ **共用 App 技术栈 + 同仓库 admin 路由组**：Solo 维护成本最低。
- ✅ **MVP 只有 super_admin 一个真实角色，其他 schema 预留**：避免未来迁移。
- ✅ **不自己建数据副本**：避免与 App 数据漂移，Admin 只读 + 少量 Admin 专属小表。
- ✅ **审计日志不可更新 / 删除**：数据库层面 REVOKE UPDATE, DELETE。

### 10.2 待讨论（不阻塞 MVP）

- ❓ **是否在 MVP 加 Cloudflare Access 作为入口层**：Nice-to-have，看时间决定。
- ❓ **MCP 调用采样比例**：1% / 10% / 100%？成本与 debug 能力的权衡，先 10% 试试。
- ❓ **Brand Submission 是否引入"社区投票"**：Phase 2 考虑，MVP 仅 Admin 审。
- ❓ **成本超限时的自动行为**：停采 还是 降级采集频率？先停采（保守），观察反馈。

---

## 附录 A — 与 App PRD 数据模型的边界

| 表 | App PRD 定义？ | Admin PRD 使用？ | Admin 写权限？ |
|---|---|---|---|
| `users` | ✅ | 读 + moderation | 只写 `status` 字段 |
| `projects` | ✅ | 读 | 禁写 |
| `kg_industries` | ✅ | 读 + 写 | 允许（审计） |
| `kg_categories` | ✅ | 读 + 写 | 允许（审计） |
| `kg_brands` / `kg_products` | ✅ | 读 + 写（审核流程） | 允许（审计） |
| `kg_*_relations` | ✅ | 读 + 写 | 允许（审计） |
| `platform_topics/prompts` | ✅ | 读 | 禁写（由 Planner 生成） |
| `query_executions` | ✅ | 读 + 重试 | 允许 `status` 改为 retry |
| `ai_responses` | ✅ | 读 | 禁写 |
| `brand_submissions` | ✅ | 读 + 写 | 允许（审核动作） |
| `discovery_logs` | ✅ | 只读 | 禁写 |
| `admin_*` | ❌ 本 PRD 新增 | 读 + 写 | 允许 |

---

## 附录 B — 术语一致性

| 术语 | 定义（沿用 App PRD） |
|---|---|
| Platform Layer | 唯一数据源，所有用户共享的监测数据 |
| User View Layer | 用户的 Project 视角过滤器，不存储监测数据 |
| Knowledge Graph (KG) | 行业→品类→品牌→产品 + 关系边 |
| Pipeline | Topic → Prompt → Query → Response 四层 |
| PANO Score | 综合评分（品牌 / 产品 / 行业三级） |
| Brand Submission | 用户提交的未入库品牌，待 Admin 审核 |
| Discovery Logs | LLM 发现调用的原始输出审计 |
| Profile | Agent 画像（用于 Query 组装） |
| MCP Server | Model Context Protocol 服务端（Agent 消费数据的入口） |

---

**End of Admin PRD v1.0**

下一步：阅读 `docs/ADMIN_CLAUDE_CODE_SESSIONS.md` 查看如何将本 PRD 拆分为 4 个可执行 Session。
