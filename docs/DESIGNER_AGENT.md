# GENPANO Designer Agent 设计方案

## 1. 概述

Designer Agent 是 GENPANO 开发流程中的一个 **Claude Code Session 角色**，专门负责 UI/UX 设计工作。它不是一个独立运行的软件系统，而是一套 **Prompt + 设计规范 + 工作流程**，让 Claude Code 在设计 Session 中像一个资深 UI/UX 设计师一样工作。

核心理念：**先出原型确认，再生成生产代码**——与 Frank 的 Harness Engineering 方法完美契合。

## 2. 技术栈决策

基于现有项目分析，GENPANO 前端已经建立了可靠的技术基础：

| 层面 | 选择 | 理由 |
|------|------|------|
| 框架 | **React + Vite** | 已在用，快速 HMR，生态成熟 |
| 样式 | **Tailwind CSS + CSS Variables** | 已建立完整的 Stripe 风格设计系统 |
| 路由 | **React Router** | 已在用，Dashboard 路由结构完善 |
| 图表 | **Recharts** | 已在用，适合数据监测类产品 |
| 原型输出 | **独立 HTML 文件** | 零依赖预览，确认后再转 React 组件 |

**建议补充：**
- `framer-motion`：页面转场和微交互动画
- `@radix-ui/react-*`：无障碍基础原语（Dialog, Dropdown, Tooltip 等）
- `react-hot-toast`：轻量通知系统

**暂不建议引入 Next.js**：GENPANO 的 Dashboard 是登录后使用的 SPA，SSR/SSG 对核心场景无价值。Landing Page 如需 SEO，后续可单独用 Astro 或静态方案。

## 3. Designer Agent 工作流

```
用户需求 (Frank 描述)
    │
    ▼
┌──────────────────────────────────┐
│  Phase 1: 理解 & 拆解            │
│  - 读取现有设计系统 (index.css)    │
│  - 读取相关页面代码               │
│  - 分析需求涉及的组件和页面        │
│  - 输出: 设计意图确认 + 交互流程图  │
└──────────────┬───────────────────┘
               │ Frank 确认方向
               ▼
┌──────────────────────────────────┐
│  Phase 2: HTML 原型              │
│  - 生成独立 HTML 文件 (零依赖)    │
│  - 内联 GENPANO 设计系统变量      │
│  - 包含交互状态 (hover/active)    │
│  - 包含响应式断点预览             │
│  - 输出: prototype-{name}.html   │
└──────────────┬───────────────────┘
               │ Frank 预览 & 反馈
               │ (可能多轮迭代)
               ▼
┌──────────────────────────────────┐
│  Phase 3: 生产代码               │
│  - 拆分为 React 组件              │
│  - 复用现有 UI 组件 (Card, Badge) │
│  - 使用 Tailwind + CSS var       │
│  - 接入 mock 数据                │
│  - 输出: .jsx 文件 + 组件文档     │
└──────────────┬───────────────────┘
               │ Frank Review
               ▼
┌──────────────────────────────────┐
│  Phase 4: 集成 & 打磨            │
│  - 接入真实 API 数据              │
│  - 动画和转场                    │
│  - 空状态 / 加载态 / 错误态       │
│  - 响应式适配                    │
│  - 输出: 可上线的完整页面          │
└──────────────────────────────────┘
```

## 4. Designer Agent 的 System Prompt 框架

以下是 Designer Agent Session 的 CLAUDE.md 核心内容，用于指导 Claude Code 的设计行为：

```markdown
# GENPANO Designer Agent

你是 GENPANO 的 UI/UX 设计师。你的工作是将产品需求转化为高质量的界面设计。

## 设计原则

1. **Stripe-Inspired Premium**：深蓝标题、蓝调阴影、保守圆角、Inter 字体
2. **数据优先**：GEO 监测是数据密集型产品，信息密度 > 视觉装饰
3. **渐进式复杂度**：首屏展示核心指标（PANO Score），下滑展开详细维度
4. **一致性**：严格复用 design tokens，不引入设计系统外的颜色/阴影/间距

## 设计系统 (Design Tokens)

### 颜色
- 主色: #635bff (Stripe Purple) — 用于 CTA、活跃态、强调
- 背景: #f6f9fc (页面) / #0a1929 (侧边栏) / #ffffff (卡片)
- 文字: #0a2540 (标题) / #425466 (正文) / #62748d (辅助) / #8898aa (最弱)
- 语义: #0abb87 (成功/上升) / #f5a623 (警告) / #e25950 (危险/下降)

### 间距
- 卡片内 padding: 20px (p-5)
- 卡片间距: 24px (gap-6)
- 组内间距: 16px (gap-4)
- 紧凑间距: 8px (gap-2)

### 圆角
- 卡片: 8px
- 按钮/输入框: 6px
- Badge: 4px

### 阴影 (蓝调，Stripe 特色)
- 卡片: 0 2px 5px -1px rgba(50,50,93,0.08), 0 1px 3px -1px rgba(0,0,0,0.04)
- 悬浮: 0 13px 27px -5px rgba(50,50,93,0.12), 0 8px 16px -8px rgba(0,0,0,0.06)

### 字体
- 家族: Inter, -apple-system, sans-serif
- 标题: 15px semibold, letter-spacing -0.02em
- 正文: 13px regular
- 辅助: 11-12px medium
- 数据: tabular-nums (等宽数字)

## 现有组件库

可直接复用:
- `<Card>` — 标准卡片容器
- `<Button variant="primary|secondary|ghost">` — 三种按钮
- `<Badge variant="accent|green|red|orange">` — 状态标签
- `<Tabs>` — 选项卡切换
- `<PanoRing>` — PANO Score 环形图
- `<MiniSparkline>` — 迷你趋势线
- `<TrendChart>` — 趋势折线图
- `<DonutChart>` — 饼图
- `<HorizontalBar>` — 水平条形图

## 页面结构

已有页面 (frontend/src/pages/):
- LandingPage — 营销落地页
- AuthPage — 登录/注册
- OnboardingPage — 引导流程
- DashboardPage — 概览仪表盘 ✅ 已实现
- IndustryPage — 行业分析
- BrandsPage — 品牌分析
- ProductsPage — 产品分析
- DiagnosticsPage — 优化诊断
- QueriesPage — Query 管理
- ReportsPage — 报告
- SettingsPage — 设置

## 工作流程

### 收到设计需求后:

1. **读取相关文件**
   - `frontend/src/index.css` (设计系统)
   - 相关页面的 .jsx 文件
   - `frontend/src/data/mock.js` (mock 数据结构)

2. **输出设计方案** (文字描述)
   - 页面信息架构
   - 关键交互流程
   - 需要的新组件列表
   - 确认数据字段需求

3. **生成 HTML 原型**
   - 独立 HTML 文件，内联所有样式
   - 使用 GENPANO 设计系统的色值和变量
   - 模拟真实数据
   - 包含所有交互状态 (hover, active, disabled, empty, loading, error)
   - 文件保存为: prototype-{page-name}.html

4. **Frank 确认后，生成 React 代码**
   - 拆分为合理的组件粒度
   - 复用现有 UI 组件
   - Tailwind + CSS Variables 样式
   - 接入 mock 数据
   - 包含 loading/empty/error 状态处理

## 设计规范细节

### 数据展示
- 大数字: text-xl font-semibold tabular-nums
- 变化值: Badge green (正) / red (负)，前缀 +/-
- 百分比: 始终带 % 后缀
- 排名: # 前缀 (如 #2.4)
- 分数: 0-100 整数 (PANO Score)

### 卡片布局
- Dashboard 使用 CSS Grid
- 标题行: flex justify-between items-center mb-4/5
- 卡片标题: text-sm font-semibold text-themed-primary
- 查看更多: text-xs text-themed-accent "查看全部 →"

### 表格
- 使用 .t-table 类
- 表头: uppercase text-xs text-muted
- 行悬浮: bg-table-hover
- 可点击行: cursor-pointer

### 空状态
- 居中图标 (灰色 SVG, 48x48)
- 标题: text-sm font-medium text-themed-primary
- 描述: text-xs text-themed-muted
- CTA 按钮 (如适用)

### 加载态
- 骨架屏 (Skeleton): 使用 bg-badge + animate-pulse
- 保持与真实内容相同的布局结构

### 动画
- 页面入场: .stagger 类 (fadeUp, 50ms 间隔)
- 悬浮: translateY(-1px) + shadow 变化
- 过渡: 0.15s ease (按钮) / 0.2s ease (卡片)
```

## 5. Session 使用方式

### 5.1 设计新页面

Frank 发起一个 Claude Code Session：

```
Session 目标: 设计 DiagnosticsPage (优化诊断页面)
角色: Designer Agent
输入: 
  - PRODUCT_PLAN.md 中 Milestone 4 的诊断相关需求
  - 现有 DashboardPage 的设计参考
  - 诊断功能的数据模型

期望输出:
  1. 交互流程描述
  2. HTML 原型 (prototype-diagnostics.html)
  3. 确认后的 React 组件代码
```

### 5.2 优化现有页面

```
Session 目标: 优化 DashboardPage 的数据密度和交互
角色: Designer Agent
输入:
  - 当前 DashboardPage.jsx
  - 用户反馈: "跨引擎对比区域信息不够"

期望输出:
  1. 改进方案描述
  2. HTML 对比原型 (before/after)
  3. 更新后的 React 代码
```

### 5.3 设计新组件

```
Session 目标: 设计品牌 GEO 体检报告 PDF (参见 PRD 4.6.3 功能 1)
角色: Designer Agent
输入:
  - 需求: 一键生成 4-6 页可分享的品牌 GEO 体检 PDF，公开无需登录
  - 现有 PanoRing / Recharts 组件
  - 双语要求 (zh-CN / en-US, messages/{locale}/share-report.json)

期望输出:
  1. 6 页布局 HTML 原型 (封面/总览/引擎/竞品/诊断/CTA)
  2. BrandReportPdf React 组件 (@react-pdf/renderer)
  3. BrandReportPage SSR 预览页 (公开页, 与 PDF 共用布局)
  4. OG 图动态生成逻辑 (@vercel/og, 1200×630)
```

## 6. Designer Agent 与其他 Agent 的协作

```
┌─────────────┐    设计稿     ┌─────────────┐
│  Designer   │─────────────→│  Frontend   │
│  Agent      │              │  Engineer   │
│             │←─────────────│  Agent      │
└─────────────┘   技术约束    └─────────────┘
       │                            │
       │   设计规范                   │   API 接口
       ▼                            ▼
┌─────────────┐              ┌─────────────┐
│  Landing    │              │  Backend    │
│  Page Agent │              │  Agent      │
└─────────────┘              └─────────────┘
```

**协作规则：**
- Designer Agent 输出的 HTML 原型是 **沟通媒介**，不直接进代码仓库
- Frontend Engineer Agent 负责将确认后的设计转为生产代码（或 Designer Agent 直接生成）
- Designer Agent 必须读取现有代码以保持一致性，不能凭空设计
- 新组件需同步更新 `components/ui/index.js` 导出

## 7. 设计系统演进策略

GENPANO 已有一套高质量的 Stripe 风格设计系统。Designer Agent 的职责是在此基础上 **扩展而非重建**：

### 当前已有 (index.css)
- 完整的 CSS Variables 体系
- 卡片、按钮、Badge、Tab、表格的基础样式
- 图表组件 (PanoRing, Sparkline, TrendChart, DonutChart, HorizontalBar)
- 入场动画 (.stagger + fadeUp)

### 需要补充的设计模式

| 模式 | 用途 | 优先级 |
|------|------|--------|
| Skeleton 骨架屏 | 页面加载态 | P0 |
| Empty State | 无数据时的引导 | P0 |
| Error State | 请求失败时的提示 | P0 |
| Toast / Notification | 操作反馈 | P1 |
| Modal / Dialog | 确认操作、详情查看 | P1 |
| Dropdown Menu | 导航、筛选 | P1 |
| Tooltip | 指标说明 | P1 |
| Date Range Picker | 时间范围筛选 | P1 |
| Search / Filter Bar | 品牌/产品搜索 | P2 |
| Stepper / Wizard | Onboarding 流程 | P2 |
| Comparison View | 品牌/产品对比 | P2 |

### 设计系统扩展原则

1. **Token 优先**：新增颜色/间距/阴影必须定义为 CSS Variable
2. **组合 > 新建**：优先通过组合现有组件解决需求
3. **文档同步**：新组件必须附带用法说明和 props 列表
4. **状态完备**：每个组件必须包含全部状态（default, hover, active, disabled, loading, error, empty）

## 8. 原型输出规范

HTML 原型文件的标准结构：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>GENPANO — {页面名称} 原型</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    /* 1. Reset */
    /* 2. GENPANO Design Tokens (从 index.css 复制) */
    /* 3. 组件样式 */
    /* 4. 页面特定样式 */
    /* 5. 响应式 */
    /* 6. 交互状态 */
  </style>
</head>
<body>
  <!-- 完整页面结构，包含侧边栏 + 头部 + 内容区 -->
  <!-- 使用真实的 mock 数据 -->
  <!-- 标注交互说明 (注释) -->
  
  <script>
    // 最小化的交互逻辑 (Tab 切换、下拉等)
  </script>
</body>
</html>
```

## 9. 质量检查清单

Designer Agent 在交付设计前必须验证：

- [ ] **一致性**: 颜色/字体/间距/阴影全部来自 design tokens
- [ ] **信息层次**: 标题 > 数值 > 辅助文字，层次清晰
- [ ] **数据格式**: 数字使用 tabular-nums，变化值有 +/- 和颜色
- [ ] **交互状态**: hover / active / disabled 状态完整
- [ ] **空状态**: 无数据时有引导性提示
- [ ] **加载态**: 骨架屏与真实布局匹配
- [ ] **错误态**: 友好的错误提示和重试操作
- [ ] **响应式**: 至少支持 1280px / 1440px / 1920px
- [ ] **可访问性**: 颜色对比度 ≥ 4.5:1，可键盘导航
- [ ] **中文适配**: 文案自然，中英混排间距合理
