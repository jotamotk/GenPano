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
| 数据存储 | 内存存储（dev）/ PostgreSQL（prod） |
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
