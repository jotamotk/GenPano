# GenPano PRD — 产品需求文档

**产品名称**: GenPano
**版本**: v1.2
**日期**: 2026-03-24
**状态**: In Review

---

## 目录

1. [产品概述](#1-产品概述)
2. [目标用户](#2-目标用户)
3. [登录注册模块 PRD](#3-登录注册模块-prd)
4. [用户流程](#4-用户流程)
5. [数据系统架构](#5-数据系统架构)
6. [技术要求](#6-技术要求)
7. [非功能性需求](#7-非功能性需求)

---

## 1. 产品概述

### 1.1 背景

随着 AI 生成内容（AIGC）的普及，用户越来越多地通过 ChatGPT、Perplexity、Gemini、Claude 等大语言模型获取信息。传统的 SEO 监测工具无法追踪品牌和内容在 AI 回答中的曝光情况，GEO（Generative Engine Optimization）成为新的营销战场。

### 1.2 产品定义

**GenPano** 是一款 **GEO（Generative Engine Optimization）监测工具**，通过 AI Agent + 浏览器自动化技术，实时采集品牌在主流 AI 引擎（ChatGPT、Perplexity、Gemini、Claude 等）中的引用情况，并对数据进行汇总分析，帮助企业量化 GEO 表现、优化内容策略。

### 1.3 核心功能概览

| 功能模块 | 描述 |
|---------|------|
| AI 曝光监测 | Agent 自动采集品牌在各 AI 平台中的被引用次数与位置 |
| 关键词追踪 | 自定义监测关键词，查看 AI 对相关话题的回答中是否提及品牌 |
| 竞品对比 | 与竞品在 AI 引用中的曝光量对比分析 |
| 情感分析 | 分析 AI 引用中对品牌的正/负/中性描述 |
| 报告导出 | 生成周期性 PDF/CSV 报告 |
| 用户管理 | 企业账户、成员邀请、权限管理 |

### 1.4 产品目标

- **短期（Q1-Q2）**: 上线 MVP，覆盖登录/注册、基础监测仪表盘
- **中期（Q3-Q4）**: 支持多用户企业账户，API 接入，多平台覆盖
- **长期**: 成为 GEO 领域标杆工具，服务 500+ 企业客户

---

## 2. 目标用户

### 2.1 主要用户画像

#### 用户类型 A：企业市场营销团队
- **角色**: Marketing Manager / CMO
- **痛点**: 无法衡量品牌在 AI 平台的曝光效果，缺乏数据支撑 AI 营销决策
- **目标**: 了解品牌在 AI 引擎中的知名度，优化内容策略
- **使用频率**: 每周查看报告，每月深度分析

#### 用户类型 B：品牌管理人员
- **角色**: Brand Manager / Brand Strategist
- **痛点**: 担心 AI 生成内容对品牌形象造成负面影响
- **目标**: 监控 AI 对品牌的描述是否准确、正面
- **使用频率**: 实时告警 + 每日简报

#### 用户类型 C：SEO/GEO 专员
- **角色**: SEO Specialist / Content Strategist
- **痛点**: 传统 SEO 工具无法覆盖 AI 渠道，需要专门的 GEO 数据
- **目标**: 优化内容被 AI 引用的概率，提升 GEO 排名
- **使用频率**: 每日操作，深度使用

### 2.2 用户规模预估

| 阶段 | 目标用户数 | 主要来源 |
|------|-----------|---------|
| MVP 期 (0-6个月) | 500 企业用户 | 内测邀请 + 自然增长 |
| 成长期 (6-18个月) | 5,000 企业用户 | 付费推广 + 口碑 |
| 成熟期 (18个月+) | 50,000 企业用户 | 渠道合作 + 品牌效应 |

---

## 3. 登录注册模块 PRD

### 3.1 页面结构

所有认证页面采用**左右分栏布局**：

```
┌──────────────────────────────────────────────────────────────┐
│  左侧面板 (40%)                │  右侧面板 (60%)              │
│  背景色: #F5EDE5               │  背景色: #FFFFFF             │
│  3D 粒子艺术装饰（CSS 动画）    │                              │
│                                │  [右上角语言切换 EN/中文]    │
│   [金铜色几何粒子雕塑]          │                              │
│                                │  页面标题                    │
│                                │  副标题 / 跳转链接            │
│                                │                              │
│                                │  表单内容                    │
│                                │                              │
│                                │  ────── Or ──────            │
│                                │  [Google 登录/注册按钮]      │
└──────────────────────────────────────────────────────────────┘
```

**成功状态页（邮件发送成功、密码重置成功）** 使用卡片布局：
- 右侧面板背景：`#F9FAFB`（浅灰）
- 内容区域：白色卡片，`border border-gray-200 rounded-2xl`，居中

### 3.2 完整页面清单

| 路由 | 页面名称 | 说明 |
|------|---------|------|
| `/login` | 登录（2步） | Step1 输入邮箱；Step2 输入密码 |
| `/register` | 注册 | 输入企业邮箱，发送验证邮件 |
| `/email-sent?type=verify` | 邮件发送成功（注册） | 绿色✓，引导查收邮件 |
| `/email-sent?type=reset` | 邮件发送成功（重置） | 绿色✓，引导查收邮件 |
| `/setup?token=...` | 设置账户 | 验证邮件点击后，填写密码/姓名/公司 |
| `/forgot-password` | 忘记密码 | 输入邮箱，发送重置链接 |
| `/reset-password?token=...` | 重置密码 | 输入新密码+确认密码 |
| `/reset-password-success` | 密码重置成功 | 绿色✓，返回登录 |

### 3.3 登录页面（2步流程）

#### Step 1 — 邮箱验证

| 元素 | 规格 |
|------|------|
| 标题 | "登录" / "Login" |
| 副标题 | "没有账号？**注册**" |
| 工作邮箱输入框 | placeholder: `你的工作邮箱，例如：Email@company.com` |
| 继续按钮 | "继续" / "Continue"，全宽，indigo |
| 忘记密码 | "忘记密码？"链接 |
| 提示文字 | "如果点击继续，账号未注册则会跳转注册" |
| 分隔符 + Google 按钮 | "Or" / "使用 Google 账号继续" |

**Step 1 交互逻辑：**
```
输入邮箱 → 前端校验（格式 + 域名黑名单）
    ↓ 通过
点击"继续"→ GET /api/auth/check-email?email=...
    ↓
邮箱已注册 → 进入 Step 2（展示密码框）
邮箱未注册 → 跳转 /register?email=...（邮箱预填）
```

#### Step 2 — 密码输入

| 元素 | 规格 |
|------|------|
| 邮箱（只读） | 显示 Step1 输入的邮箱，右侧铅笔图标可返回修改 |
| 密码输入框 | label: "密码"，带眼睛图标（显示/隐藏密码） |
| 错误 - 密码为空 | "密码为空：请输入密码" |
| 错误 - 凭证错误 | "用户名或密码不正确" |
| 继续按钮 | "继续"，全宽，indigo |
| 忘记密码 | "忘记密码？"链接 |
| 分隔符 + Google 按钮 | "Or" / "使用 Google 账号登录" |

### 3.4 注册页面

| 元素 | 规格 |
|------|------|
| 标题 | "创建免费账户" / "Create Free Account" |
| 副标题 | "已经有账户了？**登录**" |
| 工作邮箱输入框 | 支持从 `/register?email=...` 预填 |
| 注册按钮 | "注册" / "Register" |
| 隐私政策 | "注册表示我同意 GenPano 隐私政策和条款"（纯文本） |
| 分隔符 + Google 按钮 | "Or" / "使用 Google 继续" |

**注册交互逻辑：**
```
输入邮箱 → 前端校验
    ↓ 通过
POST /api/auth/register
    ↓
成功 → 跳转 /email-sent?email=...&type=verify
邮箱已注册 → 提示"该邮箱已注册"，引导登录
```

### 3.5 邮件发送成功页（通用）

适用于「注册验证邮件」和「密码重置邮件」两种场景，通过 `?type=verify|reset` 区分文案。

| 元素 | 规格 |
|------|------|
| 图标 | 绿色 SVG 圆形✓，`w-16 h-16` |
| 标题 | verify: "邮件发送成功！" / reset: "邮件已成功发送！" |
| 副标题 | 不同场景对应不同文案 |
| 已发送至邮箱 | 灰色背景卡片，邮件图标 + 邮箱地址 + 铅笔图标（返回修改） |
| 步骤引导 | 编号圆圈（indigo）+ 操作说明，共 2 步 |
| 重新发送按钮 | "重新发送邮件"，全宽，indigo，调用 POST /api/auth/resend-verification |
| 底部提示 | "没有收到邮件？请检查你的垃圾邮件文件夹" |
| 查看邮件链接 | "查看邮件👉" |

### 3.6 设置账户页（/setup）

通过邮件中的验证链接 `/setup?token=...` 进入，完成账户信息填写。

| 字段 | 图标 | 校验规则 |
|------|------|---------|
| 公司邮箱 ★ | 邮件图标 | 必填，企业邮箱格式 |
| 密码 ★ | 锁图标 + 信息图标 + 眼睛切换 | 必填，≥8位 |
| 全名 ★ | 人像图标 | 必填 |
| 公司名称 ★ | 楼房图标 | 必填 |
| 订阅新闻邮件 | Checkbox | 默认勾选，可选 |

提交调用 `POST /api/auth/setup`，成功后返回 JWT，自动登录跳转仪表盘。

### 3.7 忘记密码页

| 元素 | 规格 |
|------|------|
| 标题 | "忘记密码？" |
| 副标题 | "没有账号？**注册**" |
| 输入框 Label | "将重置密码链接发送至：" |
| 发送按钮 | "发送" |

提交后跳转 `/email-sent?email=...&type=reset`

### 3.8 重置密码页（/reset-password?token=...）

| 字段 | 说明 |
|------|------|
| 新密码 ★ | 信息图标 + 眼睛切换，≥8位 |
| 确认密码 ★ | 眼睛切换，两次密码必须一致 |
| 错误：密码无效 | "请输入有效密码" |
| 错误：密码不匹配 | "密码不匹配，请重试。" |
| 提交按钮 | "Reset" |

提交成功后跳转 `/reset-password-success`

### 3.9 字段校验规则（企业邮箱）

**拦截以下个人邮箱域名（前后端双重校验）：**

```
gmail.com, googlemail.com, hotmail.com, hotmail.cn, outlook.com, outlook.cn,
yahoo.com, yahoo.cn, qq.com, foxmail.com, 163.com, 126.com, 139.com,
sina.com, sina.cn, sohu.com, icloud.com, me.com, mac.com, live.com, msn.com,
protonmail.com, proton.me, yandex.com, aliyun.com, 21cn.com, tom.com
```

- 校验时机：`onBlur` + 提交时
- 错误提示：`"请输入有效的公司邮箱"` / `"Please enter a valid work email"`

### 3.10 Google OAuth 流程

```
点击"使用 Google 账号继续"
    ↓
GET /api/auth/google → 重定向 Google 授权页
    ↓
用户授权 → 回调 /api/auth/google/callback
    ↓
个人邮箱 → 拒绝，跳转 /login?error=personal_email
工作邮箱（已注册）→ 直接登录，JWT → /dashboard
工作邮箱（未注册）→ 自动建账号，JWT → /dashboard
```

### 3.11 错误状态汇总

| 场景 | 错误信息（中文） | 显示位置 |
|------|----------------|---------|
| 邮箱格式错误 | 请输入有效的邮箱地址 | 输入框下方红色文字 |
| 个人邮箱域名 | 请输入有效的公司邮箱 | 输入框下方红色文字 |
| 密码为空 | 密码为空：请输入密码 | 输入框下方红色文字 |
| 凭证错误 | 用户名或密码不正确 | 输入框下方红色文字 |
| 密码不匹配 | 密码不匹配，请重试。 | 输入框下方红色文字 |
| Token 过期 | 链接已失效或过期 | Toast 提示 |
| 邮箱已注册 | 该邮箱已注册 | Toast 提示 |
| 服务器错误 | 服务器异常，请联系支持 | Toast 提示 |

---

## 4. 用户流程

### 4.1 新用户注册完整流程

```
访问 /register
    ↓
输入企业邮箱 → 前端校验
    ↓ POST /api/auth/register
邮件发送成功页 /email-sent?type=verify
    ↓
用户收到验证邮件，点击 [验证邮箱] 按钮
    ↓
设置账户页 /setup?token=<token>
    ↓
填写：密码 / 全名 / 公司名称 / 订阅选项
    ↓ POST /api/auth/setup → 返回 JWT
自动登录 → 仪表盘 /dashboard ✓
```

### 4.2 已有用户登录流程（2步）

```
访问 /login
    ↓
Step 1: 输入企业邮箱
    ↓ GET /api/auth/check-email
邮箱已注册 → Step 2: 输入密码
邮箱未注册 → 跳转 /register?email=...
    ↓ POST /api/auth/login → 返回 JWT
仪表盘 /dashboard ✓
```

### 4.3 忘记密码流程

```
/login → 点击"忘记密码？" → /forgot-password
    ↓
输入企业邮箱 → POST /api/auth/forgot-password
    ↓
/email-sent?type=reset
    ↓
用户收到邮件，点击 [重置密码]
    ↓
/reset-password?token=<token>
    ↓
输入新密码 + 确认密码 → POST /api/auth/reset-password
    ↓
/reset-password-success → 点击[返回] → /login ✓
```

### 4.4 会话管理

- JWT 有效期：7 天
- Token 存储：`localStorage`（`genpano_token`）
- 页面刷新：自动调用 `GET /api/auth/me` 恢复用户状态
- 登出：清除 localStorage token，跳转 /login

---
### 4.7 报告系统

> 本节为 **运营模块** 的报告子系统的目标规格，binding spec 适用于 `backend/app/reports/**`、`frontend/src/pages/reports/**` 以及导出渲染器。
> 本节中所有数值阈值、字段名、状态机均为**可被测断言的契约**；当代码与本节不一致时以本节为准（参见 §4.7.10）。
> 与本节冲突的实现缺陷已在 `#1044` 审计中列出，本节在涉及处用 `[audit #1044 ...]` 引用其条款。

#### 4.7.0 总览

报告系统的产品定位是 **"AI 引擎中的品牌健康简报"**。它把后端持续采集的 mention / citation / sentiment / SoV 数据，按周期或按需聚合成可邮件投递 / 可分享 / 可下载的多格式 deliverable。每份报告必须服务 **三类读者** 之一作为 primary reader，并通过 **Insight Stack 三层模型** 控制每个 section 的洞察深度。

**报告类型（4 种 ReportType）**：

| ReportType | 调度 | 主受众 | 长度 | 核心承诺 |
|---|---|---|---|---|
| `weekly` | 每周一 08:00 自动生成上周（Mon-Sun）数据 | Manager 主 + Operator 副 | ~2000 字 | 周环比变化 + P0/P1 诊断速览 + 周度 Top 3 行动锚点 |
| `monthly` | 每月 1 号 08:00 自动生成上月（1 号-月末）数据 | Manager 主 + Branding 副 | ~4000 字 | 月环比 + 月同比 + 完整 10 section + Branding 叙事弧 |
| `on_demand` | 用户在 GenerateModal / API / MCP 触发 | 由调用方指定 | ~1500 字 | 用户指定 `from_date / to_date` 区间数据复盘 |
| `lead_diagnostic` | 用户提交咨询线索（commercial_lead）时由后端自动生成 + 邮件至 BD 收件箱 | BD / 销售 + 客户决策者 | ~1500 字 | 4 层架构（Quick Wins / Strategic Bets / Branding Risks / Consulting Accelerators） + 付费咨询 CTA |

**三读者视角（Primary Reader, PRD §4.7.0-a）**：

| Reader | 中文标签 | 关心什么 | 看 section 重点 |
|---|---|---|---|
| `operator` | 执行 | 可执行的锚点问题 + 数据真伪 + Pipeline 健康 | brand_performance / anchor_actions / diagnostic_summary |
| `manager` | 经营 | KPI 走向 + 资源决策 + 行业地位 | executive_summary / pano_score / industry_landscape / competitor_comparison / cta |
| `branding` | 品牌 | 心智 / 叙事 / 人设走向 | branding_narrative + sentiment / narrative_drift 类诊断 |

**Insight Stack 三层（L1 / L2 / L3）**：

- **L1 观察 (Observation)**: 客观数据点 + 时间窗口 + delta。例: "Estée Lauder PANO Score 从 79 → 82, +3 pts"
- **L2 解释 (Explanation)**: 因果链假设 + 替代假设 + 置信度。例: "ChatGPT 引用份额 +8pt 是主因, 但需 2-4 周观察是否模型版本影响"
- **L3 方向 (Direction)**: 焦点区 + 锚点问题。**绝不能渲染具体执行剧本**（"发 X 篇文章" / "签 Y 个 KOL"），剧本属付费咨询业务边界（见 §4.7.6）。

每个 section 的 `insight_stack_layers` 字段是 `[1,2,3]` 的子集，决定该 section 在该 ReportType 下渲染哪几层。

---

#### 4.7.1 报告类型差异表

| 维度 | weekly | monthly | on_demand | lead_diagnostic |
|---|---|---|---|---|
| 默认数据窗口 | 上一个完整周（Mon 00:00 → Sun 23:59 brand-local TZ） | 上一个完整月 | 调用方指定 `from_date / to_date` | 触发时间往前 30 天 |
| 自动生成节奏 | 每周一 08:00（cron `0 8 * * 1`） | 每月 1 号 08:00（cron `0 8 1 * *`） | 否（仅手动 / API / MCP） | 提交 commercial_lead 后 < 5 分钟 |
| 内容颗粒度 | 日级趋势 + 周环比 | 周级趋势 + 月环比 + 月同比 | 调用方指定 | 现状速览 + Top 3 P0/P1 + 方向句 + CTA |
| Primary reader | manager | manager | 调用方指定（默认 manager） | lead（合并 manager + branding 关切） |
| 默认输出格式 | Markdown + PDF + 邮件正文摘要 | Markdown + PDF + 邮件正文摘要 | Markdown / PDF / JSON / CSV（用户选） | PDF（邮件附件） + 站内 HTML |
| LLM 叙述 | 必带（fallback 见 §4.7.3） | 必带 | 必带 | 仅 Layer 3 一句话方向用 LLM |
| 邮件投递 | 项目所有者 + 通知偏好里 `weekly_report=true` 的成员 | 同 weekly + `monthly_report=true` | 仅请求方 | BD 收件箱 + 客户邮箱（双发） |
| 重新生成（idempotent） | 同一周不重复发送（idempotency_key = `weekly:{project_id}:{iso_week}`） | 同一月不重复 | 不去重（用户显式动作） | 同一 lead 不重复 |
| 删除 / 归档 | 90 天后自动归档至冷存储 | 180 天后归档 | 30 天后归档 | 永久保留（合规审计） |

> **`[audit #1044 B2-1]` 强制项**：`ReportJob.scope` 必须包含 `from_date` / `to_date` / `report_type` / `locale` / `reader_perspective` 字段；`get_job_with_payload` 和 `read_public_report` 重建 payload 时必须从 `scope` 读取这些字段，**不得回退到 `_default_window(today)`**。否则 3 月生成的报告在 5 月查看会变成当前数据（公开分享链漂移）。建议同时落 `payload_snapshot: JSON`（写完即冻结）作为可选优化。

---

#### 4.7.2 SECTION_MATRIX — 10 种 Section × 4 种 ReportType

报告由有序的 section 组合而成。每个 section 在 SECTION_MATRIX 中由一个三元组定义：

```
{ variant, primary_reader, insight_stack_layers }
```

`null` 表示该 ReportType 不含该 section。`variant` 枚举值见 §4.7.2.1。

##### 4.7.2.1 Variant 枚举

| variant | 含义 |
|---|---|
| `full` | 完整版（所有数据 + LLM 叙述 + 图表） |
| `simple` | 简版（仅 KPI 数字 + 一句话叙述, 不含图表） |
| `focus` | 聚焦本品牌（剥离竞品维度） |
| `optional` | 该 ReportType 默认不渲染，但调用方可显式启用 |
| `p01_only` | 仅渲染 severity ∈ {P0, P1} 的内容 |
| `all` | 渲染全部 severity（含 P2 / P3） |
| `top3` | 仅 Top 3 竞品 |
| `strengthened` | 强化版（额外加入 4 层架构、付费 CTA） |
| `all_highlight` | 全部 + 关键项视觉强调 |

##### 4.7.2.2 主矩阵

> 此矩阵是 `frontend/src/pages/reports/lib/data.ts: SECTION_MATRIX` 的 binding spec；当前后端 `app/reports/builder.py: SECTION_MATRIX` 只实现了 4 个 section，**审计要求补齐至 10 个** `[audit #1044 B2-5]`。

| Section ↓ \ Type → | weekly | monthly | on_demand | lead_diagnostic |
|---|---|---|---|---|
| `executive_summary` | full / manager / L1+L2 | full / manager / L1+L2 | full / manager / L1+L2 | (走 lead 4 层视图, 不用本矩阵) |
| `pano_score` | simple / operator / L1 | full / operator / L1+L2 | full / operator / L1+L2 | — |
| `industry_landscape` | full / manager / L1+L2 | full / manager / L1+L2 | full / manager / L1+L2 | — |
| `brand_performance` | full / operator / L1+L2 | full / operator / L1+L2+L3 | full / operator / L1+L2+L3 | — |
| `product_competitiveness` | null | full / operator / L1+L2 | optional / operator / L1+L2 | — |
| `competitor_comparison` | simple / manager / L1+L2 | full / manager / L1+L2 | full / manager / L1+L2 | — |
| `diagnostic_summary` | p01_only / operator / L1+L2+L3 | all / operator / L1+L2+L3 | full / operator / L1+L2+L3 | (lead 视图自带) |
| `anchor_actions` | p01_only / operator / L3 | all / operator / L3 | full / operator / L3 | — |
| `branding_narrative` | null | full / branding / L2+L3 | null | (lead 视图自带 Branding Risks 层) |
| `cta` | full / manager / L3 | full / manager / L3 | full / manager / L3 | strengthened / manager / L3 |

**lead_diagnostic 独立 4 层视图**（详 §4.7.4a）：
- Quick Wins · operator · L3
- Strategic Bets · manager · L2+L3
- Branding Risks · branding · L2+L3
- Consulting Accelerators · manager+branding · L3 + 付费 CTA

##### 4.7.2.3 渲染顺序（SECTION_ORDER）

```
1. executive_summary
2. pano_score
3. industry_landscape
4. brand_performance
5. product_competitiveness
6. competitor_comparison
7. diagnostic_summary
8. anchor_actions
9. branding_narrative
10. cta
```

> 渲染时 `null` cell 直接跳过；`optional` cell 仅当 `ReportCreateIn.include_optional_sections: list[str]` 显式列出时渲染。

##### 4.7.2.4 Variant 必须真正影响输出

`[audit #1044 B2-10]` — 当前仅 `diagnostic_summary` 真正按 `variant` 分支，其他 section 接到 `variant` 但忽略。本节要求：

- `simple` 变体输出 ≤ 50% 的字段数 vs `full`（仅 KPI + 单句叙述）
- `p01_only` 变体 SELECT 时强制 `severity IN ('P0','P1')`
- `top3` 变体 ORDER BY metric DESC LIMIT 3
- `focus` 变体 WHERE `brand_id = primary_brand_id`（剥离 competitor JOIN）

---

#### 4.7.3 报告生成 Pipeline — 5 步

```
┌──────────────────────────────────────────────────────────────────┐
│ Step 1. 数据聚合 (Aggregation)                                    │
│   - 从 geo_score_daily / brand_mention / citation_source /        │
│     sentiment_driver / industry_benchmark_daily 等聚合表读取      │
│   - 必须分窗：current_window (报告期) + prior_window (等长前一期) │
│   - 多引擎权重: 每条数据按 (engine, intent, language) 加权,      │
│     权重见 §4.7.4 [audit #1044 B1-6]                              │
└──────────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────────┐
│ Step 2. 诊断关联 (Diagnostic Linkage)                             │
│   - 拉取报告期内 `detected_at ∈ [from_date, to_date)` 的 open      │
│     diagnostics, 按 severity 排序 [audit #1044 B2-6]              │
│   - 把 P0/P1 的 anchor_questions / causal_chain / industry_       │
│     benchmark 嵌入对应 section 的 evidence                        │
│   - 不得泄漏当前时间的诊断到历史报告                              │
└──────────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────────┐
│ Step 3. LLM 叙述 (Narrative Generation)                           │
│   - 每个 section.summary 走一次 LLM 调用 (model: 豆包 / DeepSeek) │
│   - 输入: { section_type, locale, reader_perspective, metrics,    │
│     prior_metrics, top_diagnostics, brand_context }               │
│   - 输出: 1-3 句 plain text, ≤ 200 字符                            │
│   - Fallback: LLM 不可用 / 超时 → 走 deterministic template       │
│     (现有 buildNarratives, 见 frontend exporters.ts 等价物)        │
│   - LLM 调用结果按 (project_id, section_type, content_hash, day)   │
│     缓存 24h                                                       │
└──────────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────────┐
│ Step 4. 渲染 (Rendering)                                          │
│   - 4 个 renderer: markdown / json / csv / pdf                    │
│   - 同一 payload 喂给所有 renderer (一致性保证)                   │
│   - 关键: variant / insightStackLayers / primaryReader 必须落     │
│     在每个 section 的 metadata 中, 让前端可重绘 ReaderBadge /      │
│     StackLayerBadges                                              │
└──────────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────────┐
│ Step 5. 持久化 + 投递 (Persist & Deliver)                         │
│   - ReportJob.status: queued → running → done | failed            │
│   - ReportJob.scope 持久化 from_date / to_date / locale / ...      │
│     ([audit #1044 B2-1] 强制)                                     │
│   - 投递: 邮件 (PDF 附件 + 邮件正文摘要)、写入 user-scope alert    │
│     提醒 "本周报告已生成"                                          │
└──────────────────────────────────────────────────────────────────┘
```

##### 4.7.3.1 LLM Prompt Skeleton

> 必须 token-budget 安全（< 4k input tokens / call），不携带 PII，所有数字进 prompt 前先按 locale `Intl.NumberFormat` 渲染。

```
SYSTEM:
You are GenPano's report narrator. Generate {1-3} sentences for section
"{section_type}", in {locale}, addressed to "{primary_reader}".
Allowed depth: L1 (observation), L2 (explanation), L3 (direction).
Forbidden:
  - 具体执行剧本 (e.g. "发布 X 篇文章" / "签约 Y 个 KOL")
  - PII (邮箱 / 手机 / IP)
  - 无依据的猜测 (不在 evidence 中的数字 / 品牌名)

USER:
Period: {from_date} → {to_date}
Brand: {brand_name}
Metrics: {metrics_json}
Prior metrics: {prior_metrics_json}
Open P0/P1 diagnostics (top 3): {top_diag_json}
Insight layers required: {insight_stack_layers}

Output: a single string, no markdown, no code blocks.
```

##### 4.7.3.2 LLM Fallback Policy

| 触发条件 | Fallback 行为 |
|---|---|
| LLM API 5xx / timeout > 8s | 走 deterministic template（i18n 模板字符串 + 数字插值），输出格式与 LLM 路径一致 |
| LLM 返回包含 forbidden patterns（执行剧本动词 "发布/签约/投放" 后跟具体数字） | 走 template，记录 `llm_rejected_count` 指标 |
| LLM 配额耗尽 | 走 template，发 P2 alert 给 operator |
| 用户 explicitly 关闭 `prefs.llm_narrative=false` | 永远走 template |

Fallback 不应让用户察觉报告"降级"—— 模板叙述与 LLM 叙述在 KPI 内容上等价，只是叙事流畅度差异。

---

#### 4.7.4 PANO Score 公式 — V/S/R/A 加权 + Waterfall

> `[audit #1044 B2-2]` 强制项：当前 `app/reports/sections/pano_score.py` 实现是 `geo_score / mention_rate / sov / sentiment` 的算术平均，**不是** PANO Score。本节是正式公式定义。

##### 4.7.4.1 Sub-dimension 定义（V / S / R / A）

| 维度 | 全称 | 计算口径 | 数据源 |
|---|---|---|---|
| **V** Visibility | 可见度 | `0.5 * normalized(mention_rate) + 0.3 * normalized(avg_sov) + 0.2 * normalized(first_place_count / total_mentions)` | `geo_score_daily.mention_rate / avg_sov / first_place_count` |
| **S** Sentiment | 情感 | `clamp((avg_sentiment_score + 1) / 2 * 100, 0, 100)` | `brand_mention.sentiment_score` 加权平均 |
| **R** Reputation (Citation) | 引用 | `0.6 * normalized(citation_count) + 0.4 * normalized(unique_citation_domains_30d)` | `citation_source` |
| **A** Authority | 权威 | `0.5 * authority_citation_ratio + 0.3 * wiki_presence_score + 0.2 * official_attribution_pct` | `citation_source.authority_confidence`, wiki domains, `source_type='official_%'` |

每个 sub-score 落在 `[0, 100]`，按 `normalize(x) = clamp(x / industry_p95 * 100, 0, 100)` 把绝对量纲映到分数。`industry_p95` 来自 `industry_benchmark_daily`。

##### 4.7.4.2 加权公式

```
PANO Score = 0.30 * V + 0.20 * S + 0.25 * R + 0.25 * A
```

**权重决策依据**（必须固化在 PRD 不可工程改）：

- V (0.30): 最高权重 —— 可见度是 GEO 的前提，没有曝光其他维度无意义
- R + A (0.25 + 0.25 = 0.50): 中长期心智资产的对称承担，引用量和权威性同等重要
- S (0.20): 最低权重 —— 情感本身波动大、单事件易扭曲，不应主导总分

> 权重锁定为产品决策，**不接受工程团队"按数据调参"**。如果未来要按行业差异化权重（如美妆 vs 医疗），必须以行业级 override 方式（`industry_pano_weights`）落 schema，而非修改默认值。

##### 4.7.4.3 等级换算（PRD §4.6.3 色码）

| Score 区间 | Grade | Tone |
|---|---|---|
| [90, 100] | S | accent |
| [80, 90) | A | accent |
| [70, 80) | B | primary |
| [60, 70) | C | body |
| [0, 60) | D | body |

##### 4.7.4.4 Waterfall 渲染

`pano_score` section 在 `full` variant 下必须输出 V/S/R/A waterfall 表：

```
Period total PANO = 82 (Grade A)
   V  85  ─ +4 vs prev
   S  78  ─ +2 vs prev
   R  80  ─ +1 vs prev
   A  84  ─ +5 vs prev
WoW delta = +3 pts
   ├─ V 贡献 +1.2 pts (0.30 × +4)
   ├─ S 贡献 +0.4 pts (0.20 × +2)
   ├─ R 贡献 +0.25 pts (0.25 × +1)
   └─ A 贡献 +1.25 pts (0.25 × +5)
```

##### 4.7.4.5 PANO 因果链

`pano_score` section 必须输出 `causalChain.dominantSubdim`，标识本期最大贡献子维度（+ 或 -），及关联诊断 ID。例：

```json
{
  "dominantSubdim": "A",
  "deltaContribution": 1.25,
  "relatedDiagnostics": ["diag-005"]  // citation_source_loss
}
```

##### 4.7.4.6 周期环比（WoW / MoM / 自定义）

`[audit #1044 B2-3]` 强制：所有 metric 必须带 prior-period delta。

| ReportType | 环比对照窗口 |
|---|---|
| weekly | 上一周（同长度 7d） |
| monthly | 上一月（同长度，按当月天数对齐） |
| on_demand | 与请求期等长的紧邻前一期 |
| lead_diagnostic | 30 天前对照（同长度） |

环比缺失（prior 无数据）时输出 `delta: null`，前端渲染 `—`，**绝不输出 0** 误导。

---

#### 4.7.4a Lead Diagnostic 报告专属 4 层架构

> `lead_diagnostic` ReportType **不走 SECTION_MATRIX**，而走 4 层独立渲染（见 `frontend/src/pages/reports/components/LeadDiagnosticView.tsx`）。

| Layer | 中文标签 | Primary reader | Insight Layer | 包含诊断 |
|---|---|---|---|---|
| **Quick Wins** | 立刻能做的小事 | operator | L3 | `ease >= 7` 且 `impact >= 5` |
| **Strategic Bets** | 跨季度决策项 | manager | L2+L3 | `impact >= 7` 且不是 branding |
| **Branding Risks** | 叙事 / 人设级风险 | branding | L2+L3 | `(reader_hints includes 'branding') OR category=='narrative_drift'`, P0/P1 |
| **Consulting Accelerators** | 适合付费咨询的复杂场景 | manager + branding | L3 + paid CTA | P0/P1 + `(causalChain.confidenceLevel=='low' OR alternativeHypotheses.length > 0)` 且 `impact >= 7` |

**分层算法**（与 `classifyDiagnosticsForLead` 同语义，需后端原样实现）：

```
For each diagnostic:
  if isBranding(d) and isHighSev(d): → Branding Risks
  elif isHighSev(d) and isComplex(d) and impact >= 7: → Consulting Accelerators
  elif ease >= 7 and impact >= 5: → Quick Wins
  elif impact >= 7 or isHighSev(d): → Strategic Bets
  else: → Quick Wins (默认)
```

每层卡片仅渲染：焦点区（`focus_area`）+ 锚点问题（`anchor_questions`，≤ 3 条预览）+ 建议参与团队（`reader_hints`）+ 评估窗口（`time_series.ageInDays`）。**绝不渲染具体动作清单 / 投放数字 / 内容标题**。

Consulting Accelerators 层独有 **Paid CTA Block**:

```
本层诊断涉及多团队协作 / 内容生态重塑 / 跨季度策略, 建议预约 1 对 1 咨询
[预约咨询]
```

---

#### 4.7.5 输出格式与邮件投递契约

##### 4.7.5.1 4 种格式

| 格式 | 用途 | 渲染器 | 备注 |
|---|---|---|---|
| Markdown | Agent / MCP 消费, 复制粘贴友好 | `render_markdown(payload)` | 必须保留 `metrics` 和 `charts` 字段（charts 以 ASCII 表格 / 链接形式渲染）`[audit #1044 B2-11]` |
| JSON | API / 二次集成 | `render_json(payload)` | Schema 见 §4.7.7.2 |
| CSV | Excel / 数据团队 | `render_csv(payload)` | 仅含 `metrics` 字段的 section **也必须渲染** `[audit #1044 B2-11]` —— 当前 `if not tables: continue` 必须去掉 |
| PDF | 邮件附件 / 客户分享 | `render_pdf(payload)` (`@react-pdf/renderer` 服务端) | PDF 在 Sprint 3 前若未上线, API 必须返回 **501 Not Implemented** 而非 422 `[audit #1044 B2-12]`, 前端按钮显示 "PDF 即将推出" 并禁用 |

##### 4.7.5.2 邮件投递契约

| 字段 | 值 |
|---|---|
| From | `reports@genpano.ai` |
| To | 项目 owner + `UserNotificationPreferences.weekly_report=true` 的成员 |
| Subject (locale=zh-CN) | `{brand_name} · {type_label}（{period}）` |
| Subject (locale=en-US) | `{brand_name} · {type_label} ({period})` |
| 正文 | Executive Summary 段（≤ 200 字符）+ 4 个 KPI 卡 + "查看完整报告 →" CTA |
| 附件 | PDF（≤ 5 MB），失败则附 Markdown |
| 投递时机 | ReportJob.status 变为 `done` 后 30 秒内 |
| 失败重试 | 3 次指数退避（1min → 5min → 15min），仍失败则写 P1 alert |
| 退订 | 邮件底部 "调整通知偏好 →" 跳 `/settings/notifications` |

---

#### 4.7.6 商业衔接 — 报告 / 诊断 / 咨询的边界

GenPano 报告系统的商业角色有两个：

1. **保留型**：让付费客户每周/每月看到价值，降低流失率
2. **转化型**：通过 `lead_diagnostic` 把潜在客户引导到付费咨询

**严格禁止的内容混淆**（违者审计每次拒收报告）：

| 允许在报告中出现 | 严禁在报告中出现 |
|---|---|
| L1: 数据点 + 时间窗 + delta | 具体执行步骤（"发布 3 篇文章" / "投 5 个 KOL"） |
| L2: 因果假设 + 替代假设 + 置信度 | 具体预算 / 排期 / 物料清单 |
| L3: 焦点区 + 锚点问题（探查型） | 渠道选型 / 媒介采购建议 |
| L3: 方向性建议（"补强权威引用"） | 标题党式承诺（"7 天提升 30%"） |
| Paid CTA（lead_diagnostic 专属） | 直接植入第三方服务 |

**`cta` section 内容契约**：

- `weekly` / `monthly` / `on_demand`: 文案中性 —— `"需要专业 GEO 优化方案? 预约 30 分钟免费诊断咨询"`
- `lead_diagnostic`: 文案强化 —— `"{p0_count} 条 P0 紧急诊断 + {p1_count} 条 P1 重要诊断. 预约资深顾问 30 分钟一对一沟通."`
- 任何 CTA 不得自动跳转 / popunder，必须是用户点击才进入 lead form

> 报告的产品价值在 **"问题画像"** 而非 **"执行剧本"**。执行剧本是付费咨询业务的护城河 —— 一旦报告渲染剧本，咨询业务的差异化就被免费替代了。

---

#### 4.7.7 API 契约

##### 4.7.7.1 Endpoints

| Method | Path | 说明 |
|---|---|---|
| `GET` | `/v1/projects/{project_id}/reports` | 列出该项目的 ReportJob（含状态） |
| `POST` | `/v1/projects/{project_id}/reports` | 创建新 ReportJob，body 见 §4.7.7.2 |
| `GET` | `/v1/projects/{project_id}/reports/{report_id}` | 取详情 + payload |
| `GET` | `/v1/projects/{project_id}/reports/{report_id}/download?format=markdown|json|csv|pdf` | 下载（401 不允许跨用户） |
| `POST` | `/v1/projects/{project_id}/reports/{report_id}/share` | 创建公开分享 token（72h 默认，最长 720h） |
| `DELETE` | `/v1/projects/{project_id}/reports/{report_id}/share/{token}` | 撤销分享 |
| `GET` | `/reports/public/{token}` | 无鉴权访问已分享报告（必须 hits++ 计数，过期返回 410） |

##### 4.7.7.2 DTO

**`ReportCreateIn`**:

```typescript
{
  report_type: 'weekly' | 'monthly' | 'on_demand' | 'lead_diagnostic',
  locale: 'zh-CN' | 'en-US',
  reader_perspective: 'operator' | 'manager' | 'branding',
  from_date: date | null,         // on_demand 必填
  to_date: date | null,           // on_demand 必填
  include_optional_sections: string[] | null,
  output_formats: ('markdown' | 'pdf' | 'json' | 'csv')[]
}
```

**`ReportJobOut`**:

```typescript
{
  id: string,
  project_id: string,
  type: ReportType,
  status: 'queued' | 'running' | 'done' | 'failed',
  created_at: ISO8601,
  finished_at: ISO8601 | null,
  output_url: string | null,
  error: string | null,
  scope: {                         // [audit #1044 B2-1] 必填
    from_date: date,
    to_date: date,
    locale: string,
    reader_perspective: string,
    report_type: ReportType
  }
}
```

**`ReportDetailOut.payload`** Schema:

```typescript
{
  report_type: ReportType,
  locale: string,
  reader_perspective: string,
  period: { from: date, to: date },
  prior_period: { from: date, to: date },   // [audit #1044 B2-3]
  project_id: string,
  brand_ids: number[],
  pano: {
    current: { V: number, S: number, R: number, A: number, total: number, grade: string },
    prior:   { V: number, S: number, R: number, A: number, total: number, grade: string } | null,
    waterfall: { dim: 'V'|'S'|'R'|'A', delta: number, contribution: number }[],
    causalChain: { dominantSubdim: string, deltaContribution: number, relatedDiagnostics: string[] }
  },
  sections: {
    section_type: string,
    title: string,
    summary: string,                 // LLM 或 fallback 模板叙述
    metrics: object,
    tables: { name: string, rows: object[] }[],
    charts: { name: string, type: string, data: any }[],
    variant: string,
    primary_reader: 'operator'|'manager'|'branding',
    insight_stack_layers: number[]   // [1] / [1,2] / [1,2,3] / [2,3] / [3] 等
  }[]
}
```

##### 4.7.7.3 状态机

```
queued → running → done
                ↘ failed (error 字段填异常摘要)
```

- 从 `queued` 到 `running` 必须 < 5 秒（非高峰）/ < 30 秒（高峰）
- 从 `running` 到 `done` ≤ 60 秒（PRD §7.2 性能上限）
- `failed` 状态下 `output_url` 必须为 null，`error` 必须有人类可读摘要（不暴露 stack trace）
- 失败重试：3 次（指数退避），仍失败则写 P1 alert 给 owner

---

#### 4.7.8 数据持久化

##### 4.7.8.1 `report_jobs.scope` JSON Schema

```json
{
  "report_type": "weekly",
  "locale": "zh-CN",
  "reader_perspective": "manager",
  "from_date": "2026-04-07",
  "to_date":   "2026-04-13",
  "include_optional_sections": [],
  "output_formats": ["markdown", "pdf"],
  "trigger": "cron" | "user" | "api" | "mcp" | "lead_submit",
  "trigger_user_id": "uuid" | null,
  "idempotency_key": "weekly:{project_id}:2026W15"
}
```

`scope` 必须保证：

1. 幂等重建：给定相同 `scope` 重跑必须产出相同 payload（数据库 snapshot 之外的变化除外）
2. 公开分享一致：`/reports/public/{token}` 永远以 `scope.from_date / to_date` 为窗口，**不允许漂移**
3. 重运算可追溯：`scope.trigger` + `trigger_user_id` 写审计日志

##### 4.7.8.2 Payload Snapshot（推荐落地）

为避免上游数据修订改变历史报告，建议增列：

```sql
ALTER TABLE report_jobs ADD COLUMN payload_snapshot JSONB;
```

`done` 状态写入时持久化最终 payload；后续 GET 优先返回 snapshot，无 snapshot 时按 scope 重建（向后兼容）。

##### 4.7.8.3 ReportSchedule

cron 任务的元数据存在 `report_schedules` 表。`cron` 字段使用标准 cron 表达式。`recipients` JSON array 存收件邮箱（明文，可逆解密非必需）。

---

#### 4.7.9 国际化与时区

##### 4.7.9.1 Locale 注入

- `ReportCreateIn.locale` 决定：
  - LLM prompt 的语言（`zh-CN` → 中文输出 / `en-US` → 英文输出）
  - 邮件主题、正文、CTA 文案的 i18n key 解析
  - 日期 / 数字格式（`Intl.DateTimeFormat` / `Intl.NumberFormat`）
  - 品牌名（`brand.nameZh` vs `brand.nameEn`）
- 报告中**不允许中英混排**（`[audit #1044 B2-13]` —— 当前 zh-CN 报告可能渲染英文 fallback 文案）

##### 4.7.9.2 时区

- 报告生成的 `from_date / to_date` 解析按 **项目所在 TZ**（`projects.timezone`，默认 `Asia/Shanghai`）
- 数据库 `created_at` 一律 UTC，比较时统一转 UTC `[audit #1044 B1-4]` 同源问题
- 邮件时间戳按 **收件人 TZ**（`user.timezone`）渲染
- 周报"上一周"按 ISO 8601 周（Mon 00:00 → Sun 23:59:59.999 项目 TZ）

##### 4.7.9.3 数字 / 百分比

| 类型 | zh-CN 格式 | en-US 格式 |
|---|---|---|
| 整数 | `1,850` | `1,850` |
| 百分比 | `34.1%` | `34.1%` |
| PANO Score | `82` (无千分位) | `82` |
| 日期范围 | `2026-04-07 至 2026-04-13` | `Apr 7–13, 2026` |

---

#### 4.7.10 验收标准（每项必须可被单元 / e2e 测试断言）

| ID | 断言 |
|---|---|
| AC-4.7-1 | `report_type='monthly'` 的报告 `payload.sections` 长度 ≥ 7（10 个 section 矩阵中除 null 外）  |
| AC-4.7-2 | `report_type='weekly'` 的 `payload.sections` 不包含 `branding_narrative` 且不包含 `product_competitiveness`  |
| AC-4.7-3 | `report_type='lead_diagnostic'` 的 payload 顶层包含 `layers` 数组长度 = 4，依次为 quick_wins / strategic_bets / branding_risks / consulting_accelerators  |
| AC-4.7-4 | PANO Score 字段 `payload.pano.total` 等于 `round(0.30*V + 0.20*S + 0.25*R + 0.25*A, 2)`，权重不可在运行时被覆盖（除非 `industry_pano_weights` override 显式存在） |
| AC-4.7-5 | 所有 numeric metric 字段都伴随 `_prev` 字段（环比对照值），prev 缺失时为 `null` 而非 `0` `[audit #1044 B2-3]` |
| AC-4.7-6 | 同一 `ReportJob.id` 在生成后立即 GET 与 30 天后 GET 的 payload 完全相同（hash 比对，时区一致前提下） `[audit #1044 B2-1]` |
| AC-4.7-7 | `diagnostic_summary` section 仅包含 `detected_at ∈ [from_date, to_date)` 的诊断 `[audit #1044 B2-6]` |
| AC-4.7-8 | `competitor_comparison` section 中无数据的竞品（`samples == 0`）必须出现在 `skipped_no_data_brand_ids` 数组里，**不得**以 `geo_score: 0` 入榜 `[audit #1044 B2-9]` |
| AC-4.7-9 | LLM 不可用时 fallback 必须 200 OK 返回报告，且每个 section.summary 非空 |
| AC-4.7-10 | `format=pdf` 在 PDF renderer 未上线前必须返回 HTTP 501，**不是** 422 `[audit #1044 B2-12]` |
| AC-4.7-11 | CSV 导出包含所有 section（含仅有 metrics 的 `executive_summary`） `[audit #1044 B2-11]` |
| AC-4.7-12 | Markdown 导出保留 `charts` 元数据（至少 chart name + data summary） `[audit #1044 B2-11]` |
| AC-4.7-13 | `locale='en-US'` 报告中 **0** 个中文字符；`locale='zh-CN'` 报告中除品牌专有名词外 **0** 个英文整句  |
| AC-4.7-14 | 公开分享 token 过期后访问返回 HTTP 410 Gone 且 `view_count` 不增 |
| AC-4.7-15 | `lead_diagnostic` 报告的 Consulting Accelerators 层必须含一个有效 `cta_link`（含 `project_id` query param），**绝不**含任何具体执行剧本字符串（regex: `/发(布|送)|签约|投放\s?\d+/`） |

---

### 4.8 诊断与告警

> 本节为 **诊断规则引擎** 与 **告警分发系统** 的目标规格，binding spec 适用于 `backend/app/diagnostics/**`、`backend/app/alerts/**`、`backend/app/api/v1/{diagnostics,alerts}/**`、`frontend/src/pages/{DiagnosticsPage,AlertsPage}.tsx`。

#### 4.8.0 总览

##### 4.8.0.1 诊断与告警的关系

```
┌────────────────────┐    eval()    ┌────────────────────┐
│  规则引擎 27 条规则  │ ───────────→ │  Diagnostic 行 (DB) │
│  (PRD §4.8.1)      │              │  status=open       │
└────────────────────┘              └────────────────────┘
                                              │
                                              │ severity ∈ {P0, P1}
                                              ↓
                                    ┌────────────────────┐
                                    │  Alert 行 (DB)      │
                                    │  source='diagnostic'│
                                    │  (PRD §4.8.7)      │
                                    └────────────────────┘
                                              │
                                              │ delivery channels
                                              ↓
                                    ┌────────────────────┐
                                    │  email / 站内 bell  │
                                    │  / (未来) webhook   │
                                    │  (PRD §4.8.9)      │
                                    └────────────────────┘
```

- **诊断 (Diagnostic)**：规则引擎检测出的"应被解读"的数据现象，承载洞察 stack 三层结构。属 *业务事件*。
- **告警 (Alert)**：当诊断严重度 ≥ P1 时自动派生的"应被推送"的提醒，目的是分发到用户视野。属 *通知载体*。
- 一条 P0/P1 诊断 ⇒ 恰好一条 Alert（去重见 §4.8.8）；P2/P3 诊断不派生 Alert，仅在 DiagnosticsPage 列表中展示。
- 诊断从 `open → resolved` 时，对应 Alert 自动 `→ resolved`（已实现于 `resolve_alert_for_diagnostic`）。

##### 4.8.0.2 三读者视角映射

| Reader | Diagnostics 页关心 | Alert 渠道 |
|---|---|---|
| operator | P0 / P1 pipeline / engine / citation 类 | 站内 bell + email（紧急时） |
| manager | competitor / industry / pano_score 类 | 周报摘要 + email |
| branding | narrative_drift / sentiment / persona 类 | 月报摘要 + email |

##### 4.8.0.3 Insight Stack L1/L2/L3 与诊断字段的映射

| Stack Layer | 诊断字段 |
|---|---|
| L1 观察 | `evidence` (含 metric / current_value / previous_value / change_percent / time_range / affected_queries / affected_engines) + `responseSamples` (LLM 引用片段) |
| L2 解释 | `causal_chain.hypothesizedMechanism / alternativeHypotheses / supportingEvidence / confidenceLevel` + `industry_benchmark.gapAnalysis` |
| L3 方向 | `focus_area` + `direction`（方向性建议，禁剧本）+ `anchor_questions`（按 reader 分组）+ `if_untreated`（不干预后果） |

> **禁字段** `[audit #1044 §0]`：诊断卡片不得有 `optimization_steps` / `playbook` / `actions[]` 或任何"按 1, 2, 3, 4 步执行"型字段。剧本属付费咨询业务边界（§4.8.6）。

---

#### 4.8.1 诊断规则分类 — 8 categories × 27 rules

##### 4.8.1.1 Category 总表

| Category | 规则数 | 主要 reader | 业务含义 |
|---|---|---|---|
| `visibility` | 4 | operator + manager | 提及率 / SoV / 位置排名相关 |
| `sentiment` | 3 | operator + branding | 情感分 / 负面比例 / 情感扩散相关 |
| `sov` (Share-of-Voice) | 3 | manager + branding | 竞品反超 / 行业 lag / SoV 绝对量 |
| `citation` | 6 | operator + branding | 引用量 / 多样性 / 权威性 / wiki / anchor |
| `pipeline` | 2 | operator | 监测中断 / 引擎异常（仅 operator） |
| `product` | 3 | operator | 产品功能层负面 / 沉默 / 类目识别 |
| `persona` (Narrative / Persona) | 3 | branding | 关键词漂移 / 叙事分散 / 人设固化 |
| `narrative` (Industry / Entrant) | 3 | manager + branding | 新入场 / 行业 lag / 跨引擎差异 |

合计 27 条（与 `rules.py: REGISTRY` 一致）。

##### 4.8.1.2 完整规则清单

| rule_id | category | type | 严重度阈值 | Time window | Cooldown |
|---|---|---|---|---|---|
| `visibility_decline_v1` | visibility | brand | P1 ≤ -30% / P2 ≤ -15% (30d vs prior 30d mention_rate) | 30d | 7d |
| `topic_loss_v1` | visibility | brand | P1: cur < 1% AND prior ≥ 5% | 30d | 7d |
| `first_place_loss_v1` | visibility | brand | P1 ≥ 60% drop / P2 ≥ 30% drop, prior ≥ 10 | 30d | 7d |
| `category_rank_drop_v1` | visibility | brand | P1 ≥ +4 rank / P2 ≥ +2 rank | 30d | 7d |
| `negative_sentiment_growth_v1` | sentiment | brand | P1 ≥ 40% / P2 ≥ 25% negative ratio | 30d | 7d |
| `sentiment_drop_v1` | sentiment | brand | P1 ≤ -0.25 / P2 ≤ -0.10 (Δ score) | 30d | 7d |
| `product_feature_negative_v1` | sentiment | product | P0 ≥ 60% / P1 ≥ 30% feature negative, ≥ 10 samples | 30d | 7d |
| `share_of_voice_minor_v1` | sov | brand | P2 if avg_sov < 5% sustained | 30d | 14d |
| `industry_lag_top10_v1` | sov | brand | P1 ≥ 20 pts lag / P2 ≥ 10 pts lag | 30d | 14d |
| `competitor_overtake_v1` | sov | brand | P1 ≥ 5 pts gap / P2 ≥ 1 pt gap | 30d | 7d |
| `competitor_radical_growth_v1` | sov | brand | P1 ≥ 40% / P2 ≥ 25% growth | 30d | 7d |
| `geo_score_drop_v1` | pano_score | brand | P0 ≤ -30% / P1 ≤ -15% | 30d | 7d |
| `geo_score_drop_severe_v1` | pano_score | brand | **P0 if Δ ≤ -20 in 7d** ⚠ 须修复时间窗等长 `[audit #1044 B1-5]` | 7d | 3d |
| `citation_volume_drop_v1` | citation | brand | P1 ≤ -50% / P2 ≤ -30% | 30d | 7d |
| `citation_diversity_low_v1` | citation | brand | P2 if unique_domains < 5 | 30d | 14d |
| `citation_attribution_mismatch_v1` | citation | brand | P1 < 10% / P2 < 20% official attribution, total ≥ 10 | 30d | 14d |
| `wiki_missing_v1` | citation | brand | P2 if 0 wiki citations | 30d | 30d (gate: project age ≥ 30d `[audit #1044 B1-13]`) |
| `citation_growth_surge_v1` | citation | brand | P3 if growth ≥ 100% (positive signal) | 30d | 14d, **floor prior ≥ 20** `[audit #1044 B1-12]` |
| `attribution_anchor_low_v1` | citation | brand | P2 if citations < 5 AND mentions ≥ 10 | 30d | 14d (gate: project age ≥ 30d) |
| `monitoring_outage_v1` | pipeline | brand | P0 if 0 mentions in 24h AND prior 14d 非空 | 24h | 1d |
| `llm_engine_anomaly_v1` | pipeline | brand | P1 if any engine 0 mentions vs others active | 7d | 3d, **单引擎项目也须可触发** `[audit #1044 B1-9]` |
| `product_missing_v1` (= 现 ProductRemissionRule + category-scope 扩展) | product | product | P2 / P3 视场景 | 30d | 14d |
| `product_remission_v1` | product | product | P3 if feature mention 5+ → 0 | 30d | 30d |
| `persona_keyword_change_v1` | persona | brand | P2 if churn ≥ 70% (Jaccard) `[audit #1044 B1-10]` | 30d MoM | 30d |
| `narrative_drift_v1` | persona | brand | P1 / P2: 相对阈值（vs industry p75）`[audit #1044 B1-11]` | 30d | 30d |
| `topic_emerging_missed_v1` | narrative | brand | P2 if missed on engines where competitors ≥ 5 mentions | 7d | 7d |
| `same_group_share_low_v1` | narrative | brand | P3 if < 3 group-shared domain citations | 30d | 30d |

##### 4.8.1.3 多引擎权重（修复 `[audit #1044 B1-6]`）

所有规则在 `func.avg(GeoScoreDaily.*)` 之前必须按 `(engine, intent, language)` 分组归一化：

```python
# 伪代码 (替代当前 avg)
per_engine_avg = SELECT engine, AVG(metric) GROUP BY engine
weighted_metric = sum(engine_weight[e] * per_engine_avg[e] for e in engines)
```

`engine_weight` 默认值（可被 `projects.engine_weights` 覆盖）：

| Engine | Default Weight |
|---|---|
| ChatGPT | 0.35 |
| 豆包 (Doubao) | 0.25 |
| DeepSeek | 0.15 |
| Gemini | 0.10 |
| Claude | 0.10 |
| 其他 | 0.05 |

权重和不为 1 时按比例归一化。

##### 4.8.1.4 行业过滤（修复 `[audit #1044 B1-3]`）

`industry_lag_top10_v1` 的 "Top 10" 必须 JOIN `kg_brand.industry_id = project.industry_id`，**不允许全表 top 10**。

##### 4.8.1.5 brand_id JOIN（修复 `[audit #1044 B1-8]`）

`product_feature_negative_v1` / `product_remission_v1` 现以 `brand_name` 字符串 JOIN，必须改为 `brand_id`（"OpenAI" vs "Open AI" 不应漏 JOIN 也不应笛卡尔积放大）。

##### 4.8.1.6 阈值配置化（修复 `[audit #1044 B1-16]`）

所有上述阈值不得是 magic number。需引入 `diagnostics_config` 表或 YAML，按 `(rule_id, project_id | industry_id | global)` 三级 fallback 解析。前端 SettingsPage 提供管理员视图调阈。

---

#### 4.8.2 诊断卡片字段契约

> 所有字段名 **snake_case**（一致性已在 `[audit #1044 B1-1 / B1-2]` 修复后强制：旧 camelCase 占位符全部失效）。前端读取时统一 snake_case，序列化为 JSON 时也保留 snake_case。

```typescript
type Diagnostic = {
  id: string,                       // UUID
  project_id: string,
  brand_id: number | null,
  product_id: number | null,
  industry_id: number | null,

  rule_id: string,                  // 见 §4.8.1.2
  rule_version: string,             // e.g. 'v1'
  category: string,                 // 见 §4.8.1.1
  severity: 'P0' | 'P1' | 'P2' | 'P3',
  type: 'brand' | 'product' | 'industry',

  title: string,                    // 一句话标题, ≤ 80 字符
  description: string | null,       // 1-3 句话, ≤ 300 字符
  focus_area: string,               // L3, 焦点区, ≤ 60 字符
  direction: string | null,         // L3, 方向性建议 (禁剧本)
  reader_hints: ('operator' | 'manager' | 'branding')[],
  decision_prompt: string | null,   // 给 manager 的 1 句决策提示

  // L1: 观察
  evidence: {
    metric: string,
    current_value: number,
    previous_value: number | null,
    change_percent: number | null,
    time_range: string,
    affected_queries: string[],
    affected_engines: string[],
    [extras: string]: any           // rule-specific evidence (e.g. citation_source_loss)
  },

  // L2: 解释
  causal_chain: {
    hypothesized_mechanism: string,
    alternative_hypotheses: string[],
    supporting_evidence: string[],  // ID list pointing to evidence keys
    confidence_level: 'high' | 'medium' | 'low',
    source: 'deterministic_v1' | 'llm_v1'
  } | null,

  industry_benchmark: {
    metric: string,
    my_value: number | null,
    industry_median: number | null,
    industry_top10_avg: number | null,
    top_competitor: {
      brand_id: number,
      brand_name: string,
      value: number,
      key_characteristics: string[]
    } | null,
    gap_analysis: {
      gap_to_median: number | null,
      gap_to_top: number | null,
      percentile_rank: number | null
    },
    window_days: number,
    window_from: date,
    window_to: date
  } | null,

  // L3: 方向
  anchor_questions: {
    operator?: string[],            // 3-5 条
    manager?: string[],
    branding?: string[]
  },
  if_untreated: string | null,      // 不干预后果, ≤ 200 字符

  // 元数据
  time_series: {
    first_observed_at: date,
    last_updated_at: date,
    trend_status: 'new' | 'growing' | 'persisting' | 'fading',
    age_in_days: number,
    severity_history: { date: date, severity: string }[]
  } | null,
  priority_score: {
    impact: number,                 // 1-10
    ease: number,                   // 1-10
    urgency: number,                // 1-10
    composite: number,              // weighted: 0.4*impact + 0.3*urgency + 0.3*ease
    rank_within_period: number
  } | null,
  related_diagnostics: {
    derived_from: string[],
    child_diagnostics: string[],
    historical_similar: string[]
  } | null,
  response_samples: {
    engine: string,
    prompt_id: string,
    response_id: string,
    snippet: string,
    captured_at: date
  }[],

  // 生命周期
  status: 'open' | 'acknowledged' | 'ignored' | 'resolved',
  detected_at: ISO8601,
  acknowledged_at: ISO8601 | null,
  acknowledged_by: string | null,
  resolved_at: ISO8601 | null,
  resolved_by: string | null,
  alert_id: string | null
}
```

##### 4.8.2.1 字段必填矩阵

| 字段 | P0 | P1 | P2 | P3 |
|---|---|---|---|---|
| `evidence` | 必填 | 必填 | 必填 | 必填 |
| `causal_chain` | 必填 | 必填 | 必填 | 推荐 |
| `industry_benchmark` | 必填 | 必填 | 推荐 | 可选 |
| `anchor_questions` | 必填 ≥3 条 | 必填 ≥2 条 | 推荐 | 可选 |
| `if_untreated` | 必填 | 必填 | 推荐 | 可选 |
| `response_samples` | 推荐 ≥1 条 | 推荐 | 可选 | 可选 |

---

#### 4.8.3 因果链 (causal_chain) — Schema + 模板 + LLM 升级

##### 4.8.3.1 Schema（snake_case binding）

```json
{
  "hypothesized_mechanism": "...",
  "alternative_hypotheses": ["...", "..."],
  "supporting_evidence": ["resp-2011-a", "..."],
  "confidence_level": "high" | "medium" | "low",
  "source": "deterministic_v1" | "llm_v1"
}
```

##### 4.8.3.2 模板替换变量（修复 `[audit #1044 B1-1]`）

| 占位符 | 来源（evidence 字段） |
|---|---|
| `{brand}` | 项目主品牌名 |
| `{value}` | `evidence.current_value` |
| `{prev_value}` | `evidence.previous_value` |
| `{pct}` | `evidence.change_percent`（百分比，保留 1 位小数） |
| `{category}` | `evidence.metric` |
| `{top_competitor}` | `industry_benchmark.top_competitor.brand_name` |

> ⚠️ 单元测试断言：所有模板填充后**不得**含 `—` 或 `?` 字符（除非该字段在 evidence 中确为 null）。

##### 4.8.3.3 LLM 升级路径

当 `confidence_level == 'low'` 或 `alternative_hypotheses.length > 0` 时，可调用 LLM 重写 mechanism（model: 豆包 / DeepSeek）。LLM 输出存入 `causal_chain` 并将 `source` 改为 `llm_v1`。缓存策略与 §4.7.3 一致（24h per `(project_id, rule_id, brand_id, day)`）。

---

#### 4.8.4 锚点问题 (anchor_questions)

##### 4.8.4.1 Schema

```json
{
  "operator": ["...", "..."],
  "manager":  ["...", "..."],
  "branding": ["...", "..."]
}
```

仅含 `reader_hints` 数组中列出的 reader key。每个 reader 数组长度 3-5。

##### 4.8.4.2 模板原则

- **探查型 不是 指令型**：句式以"是否 / 多少 / 谁 / 是不是"开头，**不允许**"应该 / 必须 / 推荐"等指令动词
- **事实驱动**：每个问题应指向一个可在 GenPano 内查到答案的数据点或可用 API 查证的外部事实
- **可分配**：每个问题暗示 1 个负责团队（PR / 内容 / 工程 / 客服）

示例（来自 `visibility_decline` × `manager`）：

```
1. {brand} 在 {category} 主题的 SoV 下滑 {pct}%, 是否需要重新分配 PR 预算?
2. 竞品 {top_competitor} 抢占了哪些 query? 是否有针对性反制内容?
3. 本季度品牌曝光预算结构是否要调整?
```

##### 4.8.4.3 替换变量（修复 `[audit #1044 B1-2]`）

来源同 §4.8.3.2，必须读 snake_case key。

---

#### 4.8.5 行业基准 (industry_benchmark)

##### 4.8.5.1 Schema

```json
{
  "metric": "mention_rate" | "geo_score" | "sentiment" | "sov" | "...",
  "my_value": 12.0,
  "industry_median": 18.0,
  "industry_top10_avg": 21.0,
  "top_competitor": {
    "brand_id": 42,
    "brand_name": "兰蔻",
    "value": 30,
    "key_characteristics": ["近 30 天该主题内容输出 8 篇", "..."]
  },
  "gap_analysis": {
    "gap_to_median": -6,
    "gap_to_top": -18,
    "percentile_rank": 35
  },
  "window_days": 30,
  "window_from": "2026-03-14",
  "window_to": "2026-04-13"
}
```

##### 4.8.5.2 数据源

| 字段 | SQL |
|---|---|
| `my_value` | `AVG(geo_score_daily.{metric_col})` WHERE `brand_id = primary_brand_id` AND `date >= cutoff` |
| `industry_median` | `AVG(industry_benchmark_daily.{metric_col})` WHERE `date >= cutoff` AND `industry_id = project.industry_id` |
| `industry_top10_avg` | Top-10 per industry, AVG of top 10 brand averages（同样要求 industry 过滤 `[audit #1044 B1-3]`） |
| `top_competitor` | `project_competitor` JOIN `geo_score_daily`, ORDER BY metric DESC LIMIT 1 |
| `gap_analysis.percentile_rank` | `PERCENT_RANK()` over all brands in industry |

##### 4.8.5.3 行业 ID 缺失

`project.industry_id IS NULL` 时返回空对象 `{}`，前端隐藏 industry_benchmark 卡片，**不渲染 "0 / 行业 0"**。

---

#### 4.8.6 业务边界 — 诊断只给方向，不给剧本

与 §4.7.6 同源。诊断卡片：

- ✅ 允许：focus_area / direction（方向性，1 句话）/ anchor_questions（探查型）/ if_untreated（不干预后果）
- ❌ 严禁：execution_steps / playbook / actions / kpi_targets / channels[] / budget[]

> 当某条诊断对应的策略涉及跨季度 / 多团队 / 不确定路径，应在 lead_diagnostic 报告中分到 **Consulting Accelerators** 层，通过 paid CTA 引导付费咨询，而不是在诊断卡片里渲染剧本（§4.7.4a）。

---

#### 4.8.7 告警生命周期

##### 4.8.7.1 状态机（含新增 snoozed）

```
              ┌────────┐
              │ unread │ ◄── 初始（diagnostic→alert 派生时）
              └───┬────┘
        read    ├────────┐  ignore
                ↓        ↓
           ┌────────┐ ┌─────────┐
           │  read  │ │ ignored │
           └───┬────┘ └─────────┘
       resolve │           │ (终态)
               ↓           
       ┌──────────┐
       │ resolved │  ── (终态, 由 diagnostic resolve 触发或用户手动)
       └──────────┘
               ↑
        snooze │ snooze_expires
               │
       ┌──────────┐
       │ snoozed  │ ── 临时静默, snoozed_until 到期自动回 unread
       └──────────┘
```

`[audit #1044 B3-3]` 强制新增：

- 新增 `Alert.snoozed_until: DateTime | null` 列
- 新增 `Alert.status` 枚举值 `'snoozed'`，CHECK constraint 必须放开
- 默认 snooze 时长：**24 小时**（用户可选 1h / 4h / 24h / 7d）
- snoozed 状态下 bell badge **不计数**；`snoozed_until` 到期后定时任务自动改回 `unread`
- snoozed 期间 **不再发送任何 channel**（email / inapp）

##### 4.8.7.2 状态转换权限

| 当前态 → 目标态 | 谁可操作 |
|---|---|
| `unread` → `read` | 项目所有者 + 协作成员 |
| `unread` → `ignored` | 同上 |
| `unread` → `snoozed` | 同上 |
| `read` → `resolved` | 同上 |
| `read` → `snoozed` | 同上 |
| `snoozed` → `unread` | 系统 cron（到期）/ 用户手动唤回 |
| `*` → `resolved` | 链接的 diagnostic resolve 时由系统触发（已实现 `resolve_alert_for_diagnostic`） |

`patch_alert_status` 必须用 Pydantic `Literal['unread','read','ignored','resolved','snoozed']` 校验入参 `[audit #1044 B3-4]`，**不接受任意字符串**。

##### 4.8.7.3 与诊断生命周期联动

| Diagnostic.status | Alert.status |
|---|---|
| `open` | `unread` 或 `read` 或 `snoozed` |
| `acknowledged` | `read` |
| `ignored` | `ignored` |
| `resolved` | `resolved` |

---

#### 4.8.8 告警触发与去重

##### 4.8.8.1 触发条件

```
Diagnostic.severity ∈ {P0, P1}    ──► create Alert
Diagnostic.severity ∈ {P2, P3}    ──► no Alert (仅 DiagnosticsPage 展示)
```

Alert 字段映射：

| Alert 字段 | 来源 |
|---|---|
| `source` | 固定 `'diagnostic'` |
| `source_ref_id` | `Diagnostic.id` |
| `scope` | `'user'`（FE bell） |
| `severity` | 复制 `Diagnostic.severity` |
| `title` | 复制 `Diagnostic.title` |
| `body` | 复制 `Diagnostic.description` |
| `triggered_at` | `now()` |

##### 4.8.8.2 去重 — `(source, source_ref_id)` UNIQUE

`[audit #1044 B3-2]` 强制：

1. 数据库层增加约束：

```sql
ALTER TABLE alerts ADD CONSTRAINT uq_alerts_source_ref
  UNIQUE (source, source_ref_id);
```

2. 应用层在 `create_alert_from_diagnostic` 内 SELECT 校验（现有），抛 IntegrityError 时静默 return None（幂等）
3. 同一诊断重新 evaluate 不允许产生第 2 条 Alert

##### 4.8.8.3 Cooldown × 严重度交互

诊断引擎的 cooldown（§4.8.1.2 每条规则） 在 evaluator 中按 `category + brand_id` 去重 `[audit #1044 B1-15]` 需扩展为 **`category + brand_id + severity`**，让 P0 不被 P2 cooldown 压制（典型场景：同一 category 上周 P2 → 本周升级 P0，应允许新 Alert）。

---

#### 4.8.9 告警投递 — 邮件 + 站内 + 未来 webhook

##### 4.8.9.1 渠道

| Channel | 状态 | Default for severity | 备注 |
|---|---|---|---|
| `inapp` | 必须实现 | P0 / P1 / P2 / P3（所有） | 站内 bell + AlertsPage |
| `email` | **必须实现** `[audit #1044 B3-1]` 当前 0 发送 | P0 / P1（默认） | `app/user_auth/email.py` 现有能力, alerts 模块须 import |
| `webhook` | 未来 | 用户配置 | `alert_rules.channels` 已支持 schema |
| `slack` | 未来 | 用户配置 | 同上 |

##### 4.8.9.2 邮件投递契约

| 字段 | 值 |
|---|---|
| From | `alerts@genpano.ai` |
| Subject (P0) | `[紧急] {brand} · {title}` / `[Urgent] {brand} · {title}` |
| Subject (P1) | `[重要] {brand} · {title}` / `[Important] {brand} · {title}` |
| 正文 | title + description + L1 evidence 摘要 + "查看完整诊断 →" CTA |
| 投递时机 | Alert created 后 60 秒内（best-effort），quiet hours 内排队到下次窗口 |
| 失败重试 | 3 次指数退避；仍失败则不再尝试（避免风暴），写运维日志 |
| 退订 | 邮件底部 "调整通知偏好 →" |

##### 4.8.9.3 用户通知偏好

`user_notification_preferences` 字段：

| 字段 | 类型 | 默认 | 含义 |
|---|---|---|---|
| `p0p1_alerts` | bool | true | P0/P1 是否走 email |
| `weekly_report` | bool | true | 周报是否走 email |
| `competitor_alert` | bool | false | competitor_overtake / competitor_radical_growth 等竞品类告警是否单独 push |
| `email_locale` | enum | 'zh-CN' | 邮件文案语言 |
| `quiet_hours` | JSON | null | 例 `{"timezone":"Asia/Shanghai","from":"22:00","to":"08:00"}`；该时段内不发 email，inapp 不影响 |
| `channels` | JSON | `["email","inapp"]` | 启用渠道列表 |

##### 4.8.9.4 Quiet Hours 语义

- Quiet hours 期间 P0 告警**仍可立即发送**（紧急覆盖）—— 用户可在偏好里关闭 `p0_override_quiet=false`，默认 true
- P1 告警在 quiet hours 内排队到下次窗口开启时合并发送（最多合并 24h）
- inapp bell 不受 quiet hours 影响

##### 4.8.9.5 内部错误不静默吞（修复 `[audit #1044 B1-14]`）

evaluator → trigger → email 三链中任意一步失败必须：

1. 写结构化日志（含 `project_id / diagnostic_id / step / error`）
2. emit Prometheus counter `genpano_alerts_failed_total{step="..."}`
3. 不阻塞 diagnostic 插入

---

#### 4.8.10 API 契约

##### 4.8.10.1 Diagnostics Endpoints

| Method | Path | 说明 |
|---|---|---|
| `GET` | `/v1/projects/{project_id}/diagnostics` | 列表（filter: status / severity / category / type / limit） |
| `GET` | `/v1/projects/{project_id}/diagnostics/counts` | 聚合计数（total / by_status / by_severity_open） |
| `GET` | `/v1/projects/{project_id}/diagnostics/{diag_id}` | 详情 |
| `PATCH` | `/v1/projects/{project_id}/diagnostics/{diag_id}` | 状态转换（acknowledged / ignored / resolved / open） |
| `POST` | `/v1/projects/{project_id}/diagnostics/refresh` | 按需 evaluator 重跑，返回新增条数 |

##### 4.8.10.2 Alerts Endpoints

| Method | Path | 说明 |
|---|---|---|
| `GET` | `/v1/alerts/` | 列表（filter: status / severity / project_id） |
| `GET` | `/v1/alerts/unread-count` | bell badge counter |
| `PATCH` | `/v1/alerts/{alert_id}` | 状态转换（unread / read / ignored / resolved / **snoozed**） |
| `POST` | `/v1/alerts/{alert_id}/snooze` | **新增**：参数 `until: ISO8601` 或 `duration_hours: int`，将 status 改 `snoozed` 并写 `snoozed_until` |
| `POST` | `/v1/alerts/mark-all-read` | 批量标已读 |
| `GET` | `/v1/users/me/notifications` | 取通知偏好 |
| `PATCH` | `/v1/users/me/notifications` | 改通知偏好 |
| `GET/POST/DELETE` | `/v1/users/me/alert-rules` | 自定义告警规则 CRUD |

##### 4.8.10.3 DTOs

**`AlertOut`**（在现有基础上加 `snoozed_until`）:

```typescript
{
  id: string,
  project_id: string | null,
  brand_id: number | null,
  source: 'diagnostic' | 'monitoring' | 'system',
  source_ref_id: string | null,
  severity: 'P0' | 'P1' | 'P2' | 'P3',
  scope: 'user' | 'operator',
  title: string,
  body: string | null,
  status: 'unread' | 'read' | 'ignored' | 'resolved' | 'snoozed',
  triggered_at: ISO8601,
  read_at: ISO8601 | null,
  resolved_at: ISO8601 | null,
  snoozed_until: ISO8601 | null   // 新增
}
```

**`AlertSnoozeIn`**:

```typescript
{
  duration_hours: 1 | 4 | 24 | 168,   // preset, 默认 24
  // OR
  until: ISO8601                       // 自定义时间
}
```

##### 4.8.10.4 状态转换权限矩阵

| 角色 \ 资源 | 自己项目的 Alert | 他人项目的 Alert |
|---|---|---|
| 项目所有者 | 任意 PATCH | 403 |
| 项目协作者（成员） | PATCH 状态 | 403 |
| 平台管理员 | PATCH 任意 | PATCH 任意（含 scope='operator'） |

`patch_alert_status` 必须用 Literal 类型校验 status 入参，**不接受任意字符串** `[audit #1044 B3-4]`。

---

#### 4.8.11 验收标准（每项必须可被单元 / e2e 测试断言）

| ID | 断言 |
|---|---|
| AC-4.8-1 | P0 诊断在 `evaluate_project()` 后必须存在**恰好一条** Alert，重复运行不增 `[audit #1044 B3-2]` |
| AC-4.8-2 | P2 / P3 诊断 evaluate 后必须 **0 条** Alert |
| AC-4.8-3 | `causal_chain.hypothesized_mechanism` 在所有 27 条规则的样例 fixture 下渲染后**不含字符** `—` 或 `?` `[audit #1044 B1-1]` |
| AC-4.8-4 | `anchor_questions.manager[*]` 中模板占位符 `{pct}` / `{brand}` / `{top_competitor}` 全部被填充 `[audit #1044 B1-2]` |
| AC-4.8-5 | `IndustryLagTop10Rule` 在 industry_id A 的项目里，对照集仅包含 `kg_brand.industry_id = A` 的 brand（SQL EXPLAIN 含 industry JOIN） `[audit #1044 B1-3]` |
| AC-4.8-6 | `MonitoringOutageRule` 在 UTC+8 服务器跑、UTC 服务器跑结果一致（fixture: 24h 前最后一条 mention） `[audit #1044 B1-4]` |
| AC-4.8-7 | `GeoScoreDropSevereRule` current / prior 窗口必须都是 7 天等长 `[audit #1044 B1-5]` |
| AC-4.8-8 | `LlmEngineAnomalyRule` 在仅有 ChatGPT 一个引擎的项目里 24h 无数据时**必须**触发（当前不触发） `[audit #1044 B1-9]` |
| AC-4.8-9 | `PersonaKeywordChangeRule` 使用 Jaccard `1 - |A∩B|/|A∪B|`，非现有非对称公式 `[audit #1044 B1-10]` |
| AC-4.8-10 | `CitationGrowthSurgeRule` `prior < 20` 时不触发 `[audit #1044 B1-12]` |
| AC-4.8-11 | 缺位类规则（Wiki / Attribution Anchor / SameGroup）在 `project.created_at > today-30d` 时不触发 `[audit #1044 B1-13]` |
| AC-4.8-12 | Evaluator → Alert 失败时写日志 + 指标，**不静默** `[audit #1044 B1-14]` |
| AC-4.8-13 | Cooldown 去重按 `(category, brand_id, severity)` 三元组，P0 不被 P2 的 cooldown 压制 `[audit #1044 B1-15]` |
| AC-4.8-14 | `Diagnostic.status='resolved'` 触发后，对应 Alert.status 必须变为 `resolved` 且 `resolved_at` 已设置（已实现 `resolve_alert_for_diagnostic`） |
| AC-4.8-15 | 用户 PATCH `Alert.status='snoozed'` + `snoozed_until=now+24h` 后，bell badge `unread_count` **不计入**该 Alert；24h 到期后自动回 unread |
| AC-4.8-16 | 邮件投递端到端：fixture 创建一条 P0 Diagnostic → ≤ 60s 内触发邮件 SMTP send call 且 subject 含品牌名 + "[紧急]" 前缀 `[audit #1044 B3-1]` |
| AC-4.8-17 | quiet_hours `{"from":"22:00","to":"08:00"}` 在 23:30 触发的 P1 告警必须排队到次日 08:00，**而非立即发送** |
| AC-4.8-18 | quiet_hours 期间 P0 告警 默认仍立即发送（`p0_override_quiet=true`） |
| AC-4.8-19 | `patch_alert_status` 收到 `status='invalid_value'` 返回 HTTP 422，而非依赖 DB CHECK 兜底 `[audit #1044 B3-4]` |
| AC-4.8-20 | 多引擎权重生效：fixture 单一引擎 50 行 + 另一引擎 5 行，加权 mean 与算术 mean 数值不同 `[audit #1044 B1-6]` |
| AC-4.8-21 | `product_feature_negative_v1` 的 JOIN 走 `brand_id` 不走 `brand_name`（SQL EXPLAIN 含 `brand_mentions.brand_id = ...`） `[audit #1044 B1-8]` |
| AC-4.8-22 | 所有阈值（27 条规则）可从 `diagnostics_config` 表读取 override，且 admin 可在 UI 改阈值生效 `[audit #1044 B1-16]` |
| AC-4.8-23 | DiagnosticsPage 在真实项目（liveProjectId 有效）且无诊断时显示真实空态，**不**渲染 mock 假数据 `[audit #1044 F4-2]` |

---

> 本节（§4.7 + §4.8）形成 #1044 审计 46 项缺陷的验收源。任何 PR 修复审计条目时，提交说明必须引用对应 AC- ID + audit 编号（如 `closes B1-1 / asserts AC-4.8-3`）。

---


## 5. 数据系统架构

> GenPano 的核心能力：通过 **AI Agent + Browser Use** 自动化采集各大 AI 平台数据，经过清洗、分析、存储后，在仪表盘呈现 GEO 洞察。

### 5.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户配置层                                │
│  品牌名称 / 监测关键词 / 竞品列表 / 采集频率 / 目标平台          │
└───────────────────────┬─────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────────┐
│                       任务调度层                                 │
│  Scheduler（Cron / 触发式）                                      │
│  └── 生成采集任务 Task → 推入任务队列（Redis / BullMQ）          │
└───────────────────────┬─────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Agent 采集层（核心）                           │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ ChatGPT Agent│  │Perplexity    │  │ Gemini Agent │  ...      │
│  │ (browseruse) │  │Agent         │  │ (browseruse) │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│         │                 │                  │                   │
│  每个 Agent：                                                    │
│  1. 启动无头浏览器（Playwright）                                 │
│  2. 登录/访问 AI 平台                                            │
│  3. 输入预设 Prompt（包含品牌关键词）                            │
│  4. 采集 AI 回答原文                                             │
│  5. 提取：是否提及品牌、出现位置、上下文片段                     │
└───────────────────────┬─────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────────┐
│                       数据处理层                                 │
│                                                                  │
│  Raw Response → 清洗去噪                                         │
│      ↓                                                           │
│  NLP 分析（调用 LLM API）：                                      │
│  · 品牌提及检测（是/否 + 次数）                                  │
│  · 提及位置（第几句、排名第几）                                   │
│  · 情感分析（正面/负面/中性 + 置信度）                           │
│  · 上下文摘要（品牌被如何描述）                                  │
│  · 竞品共现分析（同一回答中出现的竞品）                          │
│      ↓                                                           │
│  结构化数据写入存储层                                            │
└───────────────────────┬─────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────────┐
│                        存储层                                    │
│                                                                  │
│  PostgreSQL                                                      │
│  ├── brands（品牌配置）                                          │
│  ├── keywords（监测关键词）                                      │
│  ├── crawl_tasks（采集任务记录）                                 │
│  ├── raw_responses（原始 AI 回答，含 prompt + response）         │
│  ├── mentions（品牌提及记录，含位置/情感/上下文）                │
│  └── daily_stats（每日聚合统计，用于趋势图）                     │
│                                                                  │
│  Redis                                                           │
│  ├── 任务队列（BullMQ）                                          │
│  └── 热数据缓存（最新统计、排行榜）                              │
└───────────────────────┬─────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────────┐
│                        分析 API 层                               │
│  REST API / GraphQL                                              │
│  ├── GET /stats/overview       — 总览（提及率、趋势）           │
│  ├── GET /stats/platforms      — 各平台分布                     │
│  ├── GET /stats/sentiment      — 情感趋势                       │
│  ├── GET /stats/competitors    — 竞品对比                       │
│  └── GET /mentions/timeline    — 提及时间线                     │
└───────────────────────┬─────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────────┐
│                      前端仪表盘层                                │
│  React + ECharts/Recharts                                        │
│  ├── GEO 总览卡片（提及率、排名、情感分）                        │
│  ├── 平台对比图（各 AI 平台曝光量）                              │
│  ├── 情感趋势折线图                                              │
│  ├── 关键词热力图                                                │
│  ├── 竞品雷达图                                                  │
│  └── 原始回答浏览器（可查看具体 AI 回答）                       │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 Agent 采集层详细设计

#### 5.2.1 Browser Use 集成

```python
# 伪代码示例
from browser_use import Agent, Browser

async def collect_brand_mention(brand: str, keyword: str, platform: str):
    browser = Browser()
    agent = Agent(
        task=f"访问 {platform_url}，搜索或提问：'{keyword}'，返回完整回答",
        browser=browser,
        llm=llm  # 用于解析页面、提取内容
    )
    result = await agent.run()
    return {
        "platform": platform,
        "keyword": keyword,
        "raw_response": result.text,
        "collected_at": datetime.now()
    }
```

#### 5.2.2 采集目标平台

| 平台 | 采集方式 | 频率 | 备注 |
|------|---------|------|------|
| ChatGPT | Browser Use（web） | 每日 | 需账号登录 |
| Perplexity | Browser Use（web）/ API | 每日 | 优先使用 API |
| Gemini | Browser Use（web） | 每日 | 需 Google 账号 |
| Claude | Browser Use / API | 每日 | Anthropic API 可用 |
| 文心一言 | Browser Use（web） | 每日 | 中文市场重点 |
| Kimi | Browser Use（web） | 每日 | 中文市场重点 |

#### 5.2.3 Prompt 模板设计

```
系统 Prompt 策略：
1. 行业问题型："{行业}领域最好的{产品类别}有哪些？"
2. 品牌直询型："你了解{品牌名}吗？请介绍一下"
3. 推荐型："如果我要选择{使用场景}，你会推荐什么工具？"
4. 对比型："{品牌A}和{品牌B}哪个更好？"

→ 每个关键词生成多种 Prompt 变体，避免单一问法偏差
```

### 5.3 数据模型设计

```sql
-- 采集任务
CREATE TABLE crawl_tasks (
  id            UUID PRIMARY KEY,
  brand_id      UUID REFERENCES brands(id),
  keyword_id    UUID REFERENCES keywords(id),
  platform      VARCHAR(50),      -- chatgpt | perplexity | gemini ...
  prompt        TEXT,
  status        VARCHAR(20),      -- pending | running | done | failed
  scheduled_at  TIMESTAMP,
  started_at    TIMESTAMP,
  finished_at   TIMESTAMP
);

-- 原始回答
CREATE TABLE raw_responses (
  id            UUID PRIMARY KEY,
  task_id       UUID REFERENCES crawl_tasks(id),
  response_text TEXT,
  response_html TEXT,
  collected_at  TIMESTAMP,
  INDEX (task_id)
);

-- 品牌提及记录
CREATE TABLE mentions (
  id              UUID PRIMARY KEY,
  response_id     UUID REFERENCES raw_responses(id),
  brand_id        UUID REFERENCES brands(id),
  platform        VARCHAR(50),
  mentioned       BOOLEAN,
  mention_count   INT DEFAULT 0,
  position_rank   INT,            -- 品牌在回答中出现的排名
  sentiment       VARCHAR(20),    -- positive | negative | neutral
  sentiment_score FLOAT,          -- -1.0 ~ 1.0
  context_snippet TEXT,           -- 品牌被提及的上下文片段
  collected_at    TIMESTAMP,
  INDEX (brand_id, platform, collected_at)
);

-- 每日聚合统计
CREATE TABLE daily_stats (
  id                UUID PRIMARY KEY,
  brand_id          UUID REFERENCES brands(id),
  platform          VARCHAR(50),
  stat_date         DATE,
  mention_rate      FLOAT,         -- 提及率（提及次数/总查询次数）
  avg_position      FLOAT,         -- 平均排名
  sentiment_score   FLOAT,         -- 平均情感分
  positive_count    INT,
  negative_count    INT,
  neutral_count     INT,
  total_queries     INT,
  UNIQUE (brand_id, platform, stat_date)
);
```

### 5.4 任务调度策略

```
默认采集频率：每日 1 次（凌晨低峰期执行）
自定义频率：用户可设置 每小时 / 每日 / 每周
触发式采集：用户手动触发"立即采集"

任务优先级队列：
  HIGH   — 用户手动触发
  NORMAL — 定时任务
  LOW    — 历史数据补采

失败重试策略：
  最多重试 3 次，指数退避（1min → 5min → 15min）
  超过重试次数 → 标记 failed，告警通知
```

### 5.5 反反爬策略

| 策略 | 说明 |
|------|------|
| IP 轮换 | 使用代理池，每次采集随机切换 IP |
| User-Agent 随机化 | 模拟真实浏览器 UA |
| 采集间隔随机化 | 请求间隔 2~8 秒随机抖动 |
| 账号池 | 多账号轮换使用，避免单账号触发限流 |
| 浏览器指纹随机化 | Browser Use 支持配置 |
| 优先使用官方 API | 有 API 的平台优先 API 采集（Perplexity、Claude） |

---

## 6. 技术要求

### 6.1 前端架构

| 技术 | 选型 |
|------|------|
| 框架 | React 18 + TypeScript |
| 构建工具 | Vite |
| 样式 | Tailwind CSS |
| 路由 | React Router v6 |
| 国际化 | 自定义 i18n hook（zh/en） |
| HTTP | Axios（含 interceptor 错误处理） |
| 图表 | ECharts / Recharts（仪表盘阶段引入） |

### 6.2 后端架构（认证服务，已实现）

| 技术 | 选型 |
|------|------|
| 运行时 | Node.js 20 LTS |
| 框架 | Express + TypeScript |
| 数据存储 | 内存存储（dev）/ PostgreSQL（live test 环境） |
| 认证 | JWT（jsonwebtoken）|
| OAuth | Passport.js + passport-google-oauth20 |
| 邮件 | Nodemailer + Ethereal（dev） |
| 密码加密 | bcryptjs（cost=12） |
| 限流 | express-rate-limit |

### 6.3 数据采集服务（规划中）

| 技术 | 选型 | 说明 |
|------|------|------|
| 语言 | Python 3.11+ | Browser Use 生态 |
| 浏览器自动化 | Browser Use + Playwright | 核心采集引擎 |
| 任务队列 | BullMQ（Redis） | 任务调度与重试 |
| NLP 分析 | OpenAI API / Claude API | 情感分析、提及检测 |
| 数据库 | PostgreSQL + TimescaleDB | 时序数据优化 |
| 缓存 | Redis | 热数据、队列 |
| 容器化 | Docker + Docker Compose | 服务编排 |

### 6.4 API 接口规范（认证模块，已实现）

| Method | Endpoint | 说明 |
|--------|---------|------|
| GET | `/api/auth/check-email?email=` | 检查邮箱是否已注册 |
| POST | `/api/auth/register` | 注册，发送验证邮件 |
| POST | `/api/auth/resend-verification` | 重新发送验证邮件 |
| POST | `/api/auth/setup` | 完成账户设置（含密码/姓名/公司） |
| POST | `/api/auth/login` | 登录，返回 JWT |
| POST | `/api/auth/forgot-password` | 发送密码重置邮件 |
| POST | `/api/auth/reset-password` | 重置密码 |
| GET | `/api/auth/me` | 获取当前用户信息（需 Bearer Token） |
| GET | `/api/auth/google` | Google OAuth 入口 |
| GET | `/api/auth/google/callback` | Google OAuth 回调 |
| POST | `/api/auth/dev-seed` | **仅 dev 环境**：快速创建测试账号 |

---

## 7. 非功能性需求

### 7.1 安全需求

| 需求 | 规格 |
|------|------|
| 密码存储 | bcrypt，cost factor = 12 |
| JWT | HS256 + 强密钥（256-bit+），有效期 7 天 |
| HTTPS | 生产环境强制 HTTPS |
| CORS | 仅允许白名单域名 |
| Rate Limiting | 登录/注册：10次/分钟/IP；通用：20次/分钟/IP |
| 邮箱枚举防护 | 忘记密码接口无论邮箱是否存在均返回相同响应 |
| 采集数据安全 | 原始 AI 回答加密存储，访问需鉴权 |

### 7.2 性能需求

| 指标 | 目标 |
|------|------|
| 首次加载 (FCP) | < 1.5 秒 |
| API 响应时间 | < 200ms (p95) |
| 采集任务延迟 | < 5 分钟（从调度到开始执行） |
| 单次采集耗时 | < 60 秒/平台 |
| 数据新鲜度 | 每日更新，支持手动触发即时采集 |

### 7.3 可访问性

- 符合 WCAG 2.1 AA 标准
- 键盘导航：所有交互元素可 Tab 访问
- 响应式设计：支持 375px+（移动）、768px+（平板）、1280px+（桌面）
- 颜色对比度：文本与背景 ≥ 4.5:1

### 7.4 国际化

- 默认语言：中文（zh-CN）
- 支持语言：英文（en）
- 切换方式：右上角语言切换器，偏好存 localStorage
- 扩展性：i18n 结构支持后续添加日语、韩语等

---

## 附录

### A. 竞品分析

| 产品 | 定位 | 差异 |
|------|------|------|
| BrandMentions | 品牌监测（传统渠道） | 不支持 AI 渠道 |
| Mention | 社交媒体监测 | 不支持 AI 引擎 |
| Profound | GEO 分析（美国市场） | 无中文支持，无自动化采集 |
| **GenPano** | **GEO 监测（中英双语）** | **Agent 自动化采集 + 中文市场** |

### B. 版本历史

| 版本 | 日期 | 变更说明 |
|------|------|---------|
| v0.1 | 2026-03-24 | 初稿，登录注册模块 PRD |
| v1.0 | 2026-03-24 | 实现认证系统前后端代码 |
| v1.2 | 2026-03-24 | 更新为 2步登录流程；新增邮件验证、账户设置、重置密码流程；新增数据系统架构设计 |

---

*文档维护人：GenPano 产品团队*
*下次评审日期：2026-04-07*
