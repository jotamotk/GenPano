# GENPANO Designer Agent — 能力规划

## 现状诊断

### 问题 1: Emoji 代替图标，显得廉价

**位置**: `frontend/src/data/mock.js` → INDUSTRIES 数据
```
icon: '💄'  // 美妆个护
icon: '👑'  // 奢侈品
icon: '🍽️' // 食品饮料
icon: '👗'  // 服装时尚
```
用在 OnboardingPage 的行业选择卡片中，`<div className="text-5xl">{industry.icon}</div>`。
AuthPage 中也有 `🔵` 作为 Logo 占位。

**根因**: 快速原型期没有引入图标系统，用 emoji 占位后没有替换。

### 问题 2: 设计像开源模板，没有产品个性

**具体表现**:
- **两套设计语言并存**: LandingPage 用 Builderflow 风格 (`#476AFF`蓝 + `#030B1D`黑 + 60px大圆角)，Dashboard 用 Stripe 风格 (`#635bff`紫 + `#0a2540`深蓝 + 8px小圆角)，视觉断裂
- **缺少品牌视觉资产**: 无 Logo 图形、无 illustration、无自定义图形语言
- **组件过于基础**: Card/Button/Badge 都是最简形态，缺少细节打磨 (微动画、渐变、光影)
- **空间利用单调**: 纯白卡片 + 灰色背景，缺少视觉层次和节奏变化
- **无 onboarding 引导插图**: 行业选择页应该有精美的行业 illustration，而不是 emoji

---

## Designer Agent 需要的资源 & 能力

### 一、图标系统 (解决 Emoji 问题)

| 资源 | 方案 | 落地方式 |
|------|------|---------|
| **通用图标库** | Lucide Icons (已在 DashboardLayout 中手动用 SVG 实现了部分) | 安装 `lucide-react` npm 包，统一替换 |
| **行业图标** | 自定义 SVG 图标组件 | Designer Agent 为每个行业设计专属 SVG 图标 |
| **品牌 Logo** | 品牌官方 Logo 或首字母 + 品牌色 | 用 SVG 绘制品牌首字母头像，配合品牌主色 |
| **状态图标** | Lucide 子集 (check, alert, info, x) | 语义化封装为 `<StatusIcon type="success">` |

**Agent 需要的 Skill**:
- 能生成高质量 SVG 图标代码（路径优化、一致的视觉重量）
- 理解图标设计原则：统一的 stroke width、圆角、视觉重量

**落地动作**:
```bash
npm install lucide-react
```
```jsx
// 替换前
<div className="text-5xl">{industry.icon}</div>  // 💄

// 替换后
import { Sparkles, Crown, UtensilsCrossed, Shirt } from 'lucide-react';
const INDUSTRY_ICONS = {
  beauty: Sparkles,
  luxury: Crown,
  food: UtensilsCrossed,
  fashion: Shirt,
};
<div className="w-12 h-12 rounded-xl bg-accent-subtle flex items-center justify-center">
  <IndustryIcon className="w-6 h-6 text-accent" />
</div>
```

### 二、Illustration 系统 (解决"开源感"问题)

| 资源 | 用途 | 方案 |
|------|------|------|
| **行业 Illustration** | Onboarding 行业选择卡片 | AI 生成 → SVG 转换，或用几何图形组合 |
| **空状态插图** | 无数据、加载失败 | 简约线条插画，内联 SVG |
| **Hero 图形** | Landing Page 头图 | 抽象数据可视化图形 |
| **Onboarding 步骤图** | 引导流程 | 场景化小插画 |

**Agent 需要的 Tools**:

1. **AI 图像生成 → SVG 转换 Pipeline**:
   - 用 AI (DALL-E / Midjourney) 生成插画参考
   - 提取视觉元素，用纯 SVG/CSS 重新实现（保证矢量清晰 + 体积小）
   - 或者：用代码直接生成几何化抽象插画（更 SaaS 风格）

2. **SVG 优化工具**:
   - SVGO 优化输出体积
   - 确保 viewBox 统一、颜色使用 CSS 变量

**推荐方案**: 代码生成的几何插画 > AI 生成的位图插画。原因：
- 矢量可缩放，适配任何尺寸
- 体积极小 (< 2KB per illustration)
- 可用 CSS 变量适配深色/浅色主题
- 与 Stripe/Linear 等顶级 SaaS 的设计风格一致

### 三、视觉设计提升 (从"开源"到"Premium SaaS")

#### 3.1 统一设计语言

**当前问题**: Landing Page 和 Dashboard 是两套设计系统。

**解决方案**:

| 维度 | Landing Page (当前) | Dashboard (当前) | 统一后 |
|------|-------------------|-----------------|--------|
| 主色 | #476AFF (蓝) | #635bff (紫) | **#635bff** (紫，更独特) |
| 文字 | #030B1D | #0a2540 | **#0a2540** |
| 圆角 | 60px (过大) | 8px | Landing 32px / Dashboard 8px (有区分但统一族) |
| 字体 | Figtree | Inter | **Inter** (全局统一) |
| 按钮 | 全黑 #030303 | 紫色 #635bff | 紫色主按钮 + 白色次按钮 |

#### 3.2 视觉细节打磨清单

| 提升项 | 当前状态 | 目标状态 | 感知影响 |
|--------|---------|---------|---------|
| **微渐变背景** | 纯色 #f6f9fc | 微妙径向渐变 (中心微亮) | 高 — 立即脱离"开源感" |
| **卡片光影** | 单层 box-shadow | 双层 Stripe 蓝调阴影 (已有，需更强化) | 中 |
| **数据卡片背景** | 纯白 | 微妙渐变底色 (如指标正向绿渐变) | 高 |
| **表格行分隔** | 1px border | 交替行底色 + hover 渐变 | 中 |
| **按钮微交互** | translateY(-1px) | + scale(1.02) + 阴影扩散 + 按下回弹 | 中 |
| **数字动画** | 静态显示 | 入场时数字滚动 (countUp) | 高 — 数据产品必备 |
| **PanoRing 动画** | 静态 | 入场时弧线从0绘制到目标值 | 高 — 核心视觉记忆点 |
| **加载骨架屏** | 无 | 与真实布局匹配的 shimmer 动画 | 高 |
| **页面转场** | 无 | Fade + slide 过渡 (framer-motion) | 中 |
| **Logo 图形** | 纯文字 GENPANO | 文字 + 几何标记 (如全景视角的抽象图形) | 高 — 品牌识别 |

#### 3.3 需要补充的组件

**优先级排序** (P0 = MVP 必需):

| 组件 | 优先级 | Agent 需要的能力 |
|------|--------|----------------|
| `<IndustryIcon>` — 行业 SVG 图标 | P0 | SVG 绘制 |
| `<Skeleton>` — 骨架屏 | P0 | CSS 动画 |
| `<EmptyState>` — 空状态 + 引导插画 | P0 | SVG 插画 + 文案 |
| `<CountUp>` — 数字滚动动画 | P0 | JS 动画 |
| `<AnimatedPanoRing>` — 带入场动画的评分环 | P0 | SVG + CSS animation |
| `<Toast>` — 操作反馈通知 | P1 | react-hot-toast 或自建 |
| `<Dialog>` — 模态框 | P1 | @radix-ui/react-dialog |
| `<Tooltip>` — 指标说明 | P1 | @radix-ui/react-tooltip |
| `<DropdownMenu>` — 筛选/操作 | P1 | @radix-ui/react-dropdown-menu |
| `<DateRangePicker>` — 时间筛选 | P1 | 自建或 react-day-picker |
| `<BrandAvatar>` — 品牌首字母头像 | P1 | SVG + 品牌色算法 |
| `<BrandReportPdf>` — 品牌 GEO 体检报告 PDF (6 页双语) | P2 | @react-pdf/renderer |
| `<BrandReportPage>` — 体检报告公开预览页 (SSR, 与 PDF 共用布局) | P2 | Next.js + Tailwind |
| `<OgImage>` — 体检报告 OG 社交预览图 (1200×630 动态生成) | P2 | @vercel/og 或 satori |

### 四、Designer Agent 的 Tools 和依赖

#### npm 依赖 (需要安装)

```json
{
  "dependencies": {
    "lucide-react": "^0.460.0",       // 图标库
    "framer-motion": "^11.0.0",       // 动画
    "@radix-ui/react-dialog": "^1.1.0",    // 模态框
    "@radix-ui/react-tooltip": "^1.1.0",   // 提示
    "@radix-ui/react-dropdown-menu": "^2.1.0", // 下拉菜单
    "react-hot-toast": "^2.4.0"       // Toast 通知
  }
}
```

#### Agent 工作时需要读取的文件

```
必读 (每次设计 Session):
├── frontend/src/index.css          # 设计系统 tokens
├── frontend/src/components/ui/     # 现有组件库
├── frontend/src/data/mock.js       # 数据结构
└── DESIGNER_AGENT.md               # 设计规范

按需读取:
├── frontend/src/pages/{Target}.jsx # 要修改的页面
├── frontend/src/layouts/           # 布局组件
└── frontend/src/components/charts/ # 图表组件
```

#### Agent 工作时需要使用的 Tools

| Tool | 用途 | 在 Claude Code 中的实现 |
|------|------|----------------------|
| **HTML 原型生成** | 输出独立 HTML 预览文件 | Write tool → .html 文件 |
| **React 组件生成** | 输出生产级 .jsx 代码 | Write tool → .jsx 文件 |
| **SVG 图标绘制** | 生成图标和插画 | 直接在代码中写 SVG path |
| **CSS 变量扩展** | 新增 design tokens | Edit tool → index.css |
| **截图对比** | 验证设计效果 | 浏览器截图 (如有) |
| **npm 安装** | 安装新依赖 | Bash → npm install |

### 五、Agent Session 规划

按优先级分成 3 个 Session，每个 Session 约 1-2 小时：

#### Session 1: 基础视觉系统升级 (P0)

**目标**: 消灭 emoji，统一设计语言，添加核心动画

**任务**:
1. 安装 `lucide-react` + `framer-motion`
2. 创建 `<IndustryIcon>` 组件 (4 个行业的 SVG 图标)
3. 替换 mock.js 中 emoji icon 为组件引用
4. 统一 Landing Page 设计语言 (颜色 → 紫色系，字体 → Inter)
5. 为 PanoRing 添加入场弧线动画
6. 为数字指标添加 CountUp 效果
7. 创建 `<Skeleton>` 骨架屏组件
8. 微调背景 (添加径向渐变)
9. 设计 GENPANO Logo 图形标记

**产出**: 原型 HTML (确认) → React 代码 → 可运行的升级版前端

#### Session 2: 组件库扩展 (P1)

**目标**: 补全交互组件，提升专业感

**任务**:
1. 安装 Radix UI 基础原语
2. 创建 `<Dialog>` `<Tooltip>` `<DropdownMenu>` 组件 (基于 Radix + GENPANO 样式)
3. 创建 `<Toast>` 通知系统
4. 创建 `<EmptyState>` 组件 + 几何插画
5. 创建 `<BrandAvatar>` 品牌头像组件
6. 添加页面转场动画 (framer-motion)
7. 重新设计 Onboarding 页面 (行业卡片用 illustration 替代 emoji)

#### Session 3: 高级视觉打磨 (P2)

**目标**: 从"好用"到"想截图分享"

**任务**:
1. 创建 `<BrandReportPdf>` 品牌 GEO 体检报告 PDF (6 页双语, `@react-pdf/renderer`, 详见 PRD 4.6.3)
2. 设计 Landing Page Hero 区域的数据可视化图形
3. 设计诊断卡片的视觉层次 (P0 红→P3 灰的渐变系统)
4. 添加微交互: 按钮 ripple、卡片 hover 光效、列表排序动画
5. 深色模式基础支持 (CSS 变量切换)
6. 行业排行榜嵌入代码的样式优化

---

## 六、Figma MCP 集成 (Path C 完整工作流)

### 已创建的 Figma 资产

**Figma 文件**: [GENPANO Design System](https://www.figma.com/design/pLgS03URIRedRzkPIbCPkB)
**Team**: AI_Lab (Pro plan, Full seat)

| 页面 | 内容 | 状态 |
|------|------|------|
| 🎨 Design Tokens | 22 个 Color Variables + 色板网格 | ✅ |
| 🖼 Icons & Illustrations | 4 个行业图标组件 (Beauty/Luxury/Food/Fashion) | ✅ |
| 🧩 Components | Card, Button×3, Badge×5, Tabs, RankBadge×3 | ✅ |
| 📄 Pages - Dashboard | 待设计 | 🔜 |
| 📄 Pages - Industry | 待设计 | 🔜 |

### Path C: AI 图像生成 + Figma + 代码 完整工作流

```
Step 1: Figma 设计 (use_figma API)
  ├── 用代码在 Figma 中创建/更新设计
  ├── 创建 Components (可复用组件)
  ├── 设置 Variables (设计 Token)
  └── 产出: Figma 中的高保真设计稿

Step 2: 截图审查 (get_screenshot)
  ├── 获取任意节点的截图
  ├── 直接在对话中预览确认
  └── 产出: Frank 确认 / 反馈修改

Step 3: 提取代码 (get_design_context)
  ├── 从 Figma 节点提取参考代码
  ├── 包含截图 + 元数据 + 代码
  └── 产出: 可直接适配的代码参考

Step 4: 生产代码 (Claude Code)
  ├── 基于 Figma 代码参考 → React 组件
  ├── 适配现有设计系统 (CSS Variables)
  └── 产出: 可运行的 React 代码

Step 5: 双向映射 (Code Connect)
  ├── add_code_connect_map 绑定 Figma ↔ React
  ├── 设计师/开发者可在 Figma 中看到代码
  └── 产出: Design ↔ Code 双向同步
```

### Figma MCP 可用工具

| 工具 | 用途 | 关键场景 |
|------|------|---------|
| `use_figma` | 在 Figma 中执行 JS 代码 | 创建/修改设计、组件、样式 |
| `get_screenshot` | 获取节点截图 | 预览确认、对比 before/after |
| `get_design_context` | 提取设计 → 代码 | 从 Figma 生成 React 代码 |
| `search_design_system` | 搜索设计系统组件 | 复用已有组件避免重复创建 |
| `get_variable_defs` | 获取变量定义 | 同步 Design Tokens |
| `add_code_connect_map` | 绑定 Figma ↔ 代码 | 双向映射组件 |
| `create_new_file` | 创建新 Figma 文件 | 新项目/新模块 |
| `generate_diagram` | 生成流程图 | 交互流程、架构图 |

### AI 图像生成集成方案

对于复杂插画 (Landing Page Hero、行业配图等):

1. **在对话中描述需求** → Claude 生成描述 prompt
2. **用 DALL-E/Midjourney 生成参考图**
3. **用 `use_figma` 将图片导入 Figma** → 在 Figma 中精修
4. **导出 SVG** → 或用代码重新实现为矢量图 (体积更小)
5. **通过 `get_design_context` 提取** → 集成到 React 代码

### 行业图标 Figma → 代码映射

已在 Figma 中创建的图标组件:

| Figma 组件 | 替换的 Emoji | React 实现方式 |
|-----------|-------------|---------------|
| `Icon/Industry/Beauty` (Sparkle) | 💄 | `<Sparkles>` from lucide-react + 渐变圆形背景 |
| `Icon/Industry/Luxury` (Crown) | 👑 | `<Crown>` from lucide-react + 渐变圆形背景 |
| `Icon/Industry/Food` (Utensils) | 🍽️ | `<UtensilsCrossed>` from lucide-react + 渐变圆形背景 |
| `Icon/Industry/Fashion` (Shirt) | 👗 | `<Shirt>` from lucide-react + 渐变圆形背景 |

## 总结: Designer Agent 核心配方 (Path C)

```
Designer Agent (Path C) = 
  Figma MCP (设计系统 + 组件库 + 页面设计)
  + AI 图像生成 (插画/配图 → Figma 精修 → 代码)
  + 设计规范 (DESIGNER_AGENT.md)
  + 图标库 (lucide-react)
  + 动画引擎 (framer-motion)
  + 无障碍原语 (Radix UI)
  + Code Connect (Figma ↔ React 双向映射)
```

**Figma 文件**: https://www.figma.com/design/pLgS03URIRedRzkPIbCPkB

**投入**: 3 个 Claude Code Session, 每个 1-2h 人类时间
**产出**: 从"开源 demo"到"Premium SaaS"级别的视觉升级，且设计资产在 Figma 中持久化、可复用
