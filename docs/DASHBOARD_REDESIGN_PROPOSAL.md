# Dashboard Redesign Proposal — 三路视觉方向对比

> **状态**: 提案阶段，不改动现有 frontend
> **日期**: 2026-04-17 (v2 更新：加入 Editorial / Linear 两个对照)
> **参考**: Notion / Attio · Financial Times / The Economist · Linear / Vercel / Geist
> **交付物**: 本文档 + 3 个并排原型
>  - `design/prototype-dashboard-v3.html` — Notion/Attio "温柔现代" (**Ink Navy #1E3A5F**)
>  - `design/prototype-dashboard-v4-editorial.html` — Editorial "报刊风" (**Claret #9C2B2E** on **FT Cream #FAF5EA**)
>  - `design/prototype-dashboard-v5-linear.html` — Linear/Geist "极简黑灰" (**Electric Blue #2563EB**)
> **原则**: PRD-first。本提案经你确认后再决定是否写入 `docs/PRD.md` 的 §4.6.1a，以及是否进入 Claude Code Session 落地到 `frontend/`

## 0. TL;DR 三方对比

| 维度 | v3 Notion/Attio | v4 Editorial/FT | v5 Linear/Geist |
|---|---|---|---|
| **主色** | Ink Navy `#1E3A5F` | Claret `#9C2B2E` | Electric Blue `#2563EB` |
| **背景** | Warm white `#FBFBFA` | Cream paper `#FAF5EA` | Pure white `#FFFFFF` |
| **字体主体** | Inter (Sans) | Source Serif 4 / Playfair Display | Inter (紧凑) |
| **数据字体** | Inter tabular | Serif + JetBrains Mono | JetBrains Mono 全场 |
| **卡片圆角** | 8px | 0 (报刊式硬线) | 6px |
| **阴影** | 1px hairline | 1-3px hard rule | 1px hairline |
| **信息密度** | 中 | 中偏低 (留白大) | 高 |
| **差异化** | 中 (SaaS 常见区间) | **最高** (品类独此一家) | 低 (撞款多) |
| **学习成本** | 低 | 中 (读起来像报纸) | 最低 |
| **适合人群** | 品牌团队 + SEO 全覆盖 | 高端品牌 / 有审美洁癖的决策者 | 工程背景 / SEO 从业者 |
| **风险** | 差异化弱 | 中文 Serif 字体在 Chrome 渲染偏弱 | 辨识度几乎为零 |
| **叙事契合** | 良好 | **最强** (和 Report 深化框架/Stack 三读者视角天然搭) | 中等 |
| **实施工作量** | 最小 (换肤即可) | 大 (要调 Serif 中文排版) | 中 |

---

## 1. "廉价模板感"的根因诊断

我把当前 Dashboard (见 `frontend/src/pages/DashboardPage.jsx` + `design/prototype-v2.html`) 和"温柔现代"参照系做了对比，下面 8 条是具体病灶，按影响面排序：

### 1.1 字体：Nunito 是成也败也

Nunito 是圆润 friendly sans，主要用在"中小企业 SaaS / 儿童教育 / wellness"类产品。一旦用到 B 端数据分析工具上，视觉语言会立刻"矮一级"——它在呼喊 *"我是一个亲切的工具"*，但 Frank 的用户 (SEO 从业者、品牌团队) 需要的是 *"我是一个严肃的数据基础设施"*。对比 Attio 用 Inter、Linear 用 Inter Display + Inter Variable、Notion 用 Inter + Söhne。

### 1.2 主色 #605BFF 紫：SaaS "撞色" 重灾区

这个紫和 Stripe / Framer / Linear / Vercel / 无数 Producthunt SaaS 几乎一模一样的区段。辨识度几乎为零，且紫色饱和度偏高，大面积出现时 (比如 hero banner / 登录页渐变) 会显得"廉价营销味"。Notion/Attio 几乎不用饱和紫。

### 1.3 圆角 12-24px + 软阴影：Bubble 语汇

当前 token 规定 card=12px、card-lg=16px、banner=24px，再叠加 `shadow-card` 的双层投影——形成典型的 *"Figma 新手模板"* 语汇。Notion 全站卡片圆角 6-8px 且几乎不用阴影；Attio 全部 6px 圆角 + 1px hairline border 分区。圆角+阴影组合越多，模板感越重。

### 1.4 KPI 卡片 "metric soup"：5 个卡片并排、视觉权重均等

Dashboard ① 区块的 "5 KPI" 被渲染成 5 个等宽卡片 (`lg:grid-cols-5`)，每个卡片都有 label + 大数字 + 变化箭头 + sparkline。这是典型的 Bootstrap Admin Template 结构——所有指标都重要 = 所有指标都不重要。真正好的 Dashboard 会把 **1 个核心数字** 提到视觉焦点，其余指标作为 context 下沉。

### 1.5 Hero 区块信息重复 + 占位浪费

当前 Hero 里包含：品牌名、英文名、行业标签、排名 #X、PANO Score 大号、等级标签、行业均值对比条。但排名 #X 在下方 KPI 卡里又出现一次，变化 delta 在 KPI 里又各自出现一次。"温柔现代"风格要求信息不重复——每个数字只在一个位置出现，其他地方靠 *位置* 暗示层级。

### 1.6 图表：Recharts 默认样式 + 多色彩虹

Recharts 配合 token 里的 chart-1 到 chart-7 共 7 条色，加上 sentiment bar 的 5 色，Dashboard 页光是"颜色种类"就接近 10 种。Notion/Attio 的图表语汇是：**灰阶主体 + 1 个强调色**。主角数据用深色实线，竞品浅灰，行业均值虚线，涨跌用绿/红只在数字旁——**图表本身不上品牌色**。

### 1.7 Badge / Tag / Pill 满天飞

看当前 DashboardPage.jsx，一个视图里可能出现：tier badge、change badge、engine filter pill、profile group pill、alert severity pill、KPI sparkline tone badge。Notion/Attio 的策略是 **1 种 badge 形状 + 2 种色 (neutral / accent)**，剩下全部去 badge 化，改用冒号分隔或缩进。

### 1.8 中文排版：没有为中文字形单独调距

当前 `font-ui-cn` 只是映射到 Microsoft YaHei + Noto Sans SC，没有 `letter-spacing` / `line-height` 为中文做调整。中文方块字在默认 1.5 行高下会显得拥挤。好的中文 UI：行高 1.6-1.75，不给中文加 letter-spacing (英文才需要)，标题字重用 500-600 (不用 700 bold，中文太"胖"则丑)。

---

## 2. 视觉方向：三个锚点

如果要给新 Dashboard 一句话 style guide，我提议：

> **"墨色为主，只有数据会说话。分区靠 1px 线，不靠阴影；强调靠字号和字重，不靠颜色；品牌色只在选中态和主 CTA 出现一次。"**

三个具体参照：

| 锚点 | 我们借什么 |
|---|---|
| **Notion** | 黑字 + 浅灰分区 + Inter 体系；小阴影；Emoji 图标只用在内容区 (不用在 UI) |
| **Attio** | 数据表格为主角，hover 极淡；Sidebar 窄 + Monochrome；右侧 Detail Panel 作为 inspector |
| **Vercel Observability** | 数据图表灰阶为主，accent 只在主线；Sparkline 和数据同列对齐 |

---

## 3. 三路主色方案 (每个美学对应一个)

三个变体的主色不同，但同属"低饱和 + 高权威"家族——保证未来任一被选中后，品牌感一致：

### v3 路线 · **Ink Navy** `#1E3A5F`

- HSL: (213°, 52%, 25%) — 深灰蓝，Mercury/Ramp/Pitch 家族
- 配合 Notion/Attio "温柔现代"的 warm white 背景 `#FBFBFA`
- Hover: `#162B47` · Soft: `#EEF2F7` · Softer: `#F7F9FC`
- 最"稳妥"路线；品牌辨识度中等，但实施风险最小

### v4 路线 · **Claret** `#9C2B2E` on **FT Cream** `#FAF5EA`

- Claret 本身 HSL: (358°, 57%, 39%) — FT 签名红，权威但不张扬
- 背景 Cream 纸色 `#FAF5EA` 是整套方案最强的视觉识别符
- 文字主体仍是深灰 `#1A1A1A`，Claret 只出现在标题重点字、上升箭头、引号
- 配合 Playfair Display (标题) + Source Serif 4 (正文) 做"报纸社论"感
- 适合：如果 GENPANO 想长期走"有话语权的监测机构"路线，像 FT/Bloomberg 在金融领域的角色定位

### v5 路线 · **Electric Blue** `#2563EB`

- HSL: (221°, 83%, 53%) — 纯蓝，饱和度较高但面积极小
- 全站灰阶，Blue 只出现在：主 CTA、选中态导航项、唯一一条主角数据线
- 数据/表格字体全部用 **JetBrains Mono** (等宽)，保证列对齐
- 配合 Linear/Vercel/Geist 家族的 pure-white 背景 + 6px 圆角 + 极小 hover 变化
- 适合：你未来的用户偏工程 / 数据分析背景，重视键盘操作和信息密度

**决策提示**：
- 若追求 **最快见效**、**最低实施风险** → 选 v3
- 若追求 **品类差异化**、**叙事契合 Stack 三层读者视角** → 选 v4
- 若追求 **最高信息密度**、**Power User 首日效率** → 选 v5
- 或: **双皮肤模式** — 用 v3/v5 之一做日常面板，v4 专供 PDF 体检报告 / 月度简报的渲染

---

## 4. Token 层面的具体调整 (相对现有 `docs/DESIGN_TOKENS.md`)

下面是提议的 diff 方向。**不动结构 token 分类**，只是替换值。这让你能随时 A/B toggle：

### 4.1 字体 (按变体)

| 项 | v3 Notion/Attio | v4 Editorial | v5 Linear/Geist |
|---|---|---|---|
| Body | **Inter** 400/500 | **Source Serif 4** 400/500 | **Inter** 400/500 (紧凑) |
| 大标题 | Inter 500 + Instrument Serif eyebrow | **Playfair Display** 600 | Inter 500/600 |
| 小号标签 | Inter 500 small-caps | Inter 500 all-caps | Inter 500 tracking 0.06 |
| 中文 | PingFang SC / Noto Sans SC | **Noto Serif SC** (重点字) + Noto Sans SC (正文) | PingFang SC / Noto Sans SC |
| 数据 | Inter tabular-nums | Playfair Display tabular + JetBrains Mono (deltas) | **JetBrains Mono** (全场) |
| 风险 | 无 | 中文 Serif 渲染 Chrome 弱于 Safari，需手动调 line-height 1.7+ | 无 |

### 4.2 Color (按选中的变体替换 accent 值)

```diff
# 通用替换 (无论选哪个变体都要做)
- --color-accent: #605BFF          /* ← 废弃 SaaS 紫 */
- --color-accent-hover: #5450E6
- --color-accent-2: #8B5CF6
- --color-accent-bg-light: #F0F0FF

# 按变体选其一:

# v3 Ink Navy
+ --color-accent: #1E3A5F
+ --color-accent-hover: #162B47
+ --color-accent-bg-light: #EEF2F7

# v4 Claret (注意还要改 bg-page 为 cream)
+ --color-accent: #9C2B2E
+ --color-accent-hover: #7A2123
+ --color-accent-bg-light: #F3DBD8
+ --color-bg-page: #FAF5EA     /* ← 重点: 改纸色底 */

# v5 Electric Blue
+ --color-accent: #2563EB
+ --color-accent-hover: #1E50C9
+ --color-accent-bg-light: #EFF4FE
```

文字色整体加深一档 (Notion-ish 黑)：
```diff
- --color-text-primary: #030229
+ --color-text-primary: #0F0F10         /* 近黑但不纯黑 */
- --color-text-muted: #818194
+ --color-text-muted: #6B6B6E           /* 中性灰，不带蓝 */
```

表面层去"彩"：
```diff
- --color-bg-page: #FAFAFB
+ --color-bg-page: #FBFBFA              /* 微暖白 (纸感) */
- --color-border-card: #F2F4F7
+ --color-border-card: #EAEAEA          /* 纯中性灰 border */
```

图表色从"彩虹 7 色"收敛到"灰阶 + 1 主 + 2 情绪"：
```diff
- chart-1..chart-7 (紫/粉/蓝/深蓝/紫/黄/绿)
+ chart-primary: #0B6E5E     /* 主角 (我) */
+ chart-neutral-strong: #111  /* 次要角色 */
+ chart-neutral-mid: #8E8E93
+ chart-neutral-soft: #D0D0D0
+ chart-grid: #EFEFEE
+ chart-positive: #047857    /* 深森林绿：只用在正向数字 */
+ chart-negative: #B91C1C    /* 深红：只用在负向数字 */
```

### 4.3 Radius

```diff
- --radius-card: 12px      → 8px
- --radius-card-lg: 16px   → 10px
- --radius-banner: 24px    → 12px
- --radius-pill: 9999px    → 保留但极少使用
+ 所有 badge 统一用 4px (方块感)
```

### 4.4 Shadow

```diff
- shadow-card: 双层投影
+ shadow-card: 0 0 0 1px #EAEAEA  /* "border as shadow"，等价于 hairline */
- shadow-card-hover: 0 8px 24px rgba(50,50,93,0.08)
+ shadow-card-hover: 0 0 0 1px #1F1F1F / 6% (仅描边变深)
只有 modal / dropdown 保留 shadow-elevated
```

### 4.5 Spacing Density

| 项 | 当前 | 提议 |
|---|---|---|
| Card padding | 20px | **24px** 主区 / **16px** 次级 (更呼吸) |
| Section 间距 | 24px | **40px** (大留白) |
| Table row 高度 | 40px | **36px** (数据密度) |
| KPI 区块 padding | p-5 | **p-6 + 内部 divider** |

---

## 5. Dashboard 信息架构的具体改造

保留 PRD §4.6.1a 的 5 块骨架 (Hero / 5 KPI / 竞争视图 / 趋势 / 告警)，但重新分布视觉权重：

### 5.1 布局：从"单列 5 段"改为"主 2/3 + 侧 1/3"

```
┌────────────────────────────────────────────────────────────┐
│  Top Bar: 筛选 (主筛选 + 扩展筛选 + ProfileGroup)              │
├──────────────────────────────────┬─────────────────────────┤
│  Main (2/3)                      │  Side (1/3)             │
│                                  │                         │
│  ① Hero Score Panel              │  ⭐ Alerts (Top 3 P0/P1) │
│     品牌名 · PANO 82 · ↑3.2       │   提到前置,用户一眼看到    │
│     行业均值 73 · 我 +9 · #2/12   │                         │
│                                  │  ─────────────────       │
│  ② Trend Chart (大)              │                         │
│     单线 teal 实线 + 2 条灰虚线    │  📌 Rank Summary         │
│                                  │     行业 #2/12           │
│  ③ KPI Row (5 项表格式,不是卡片)   │     环比 +1              │
│     提及率  18.5%   ▁▂▃▂▅  +2.1%  │                         │
│     SoV     24.3%   ▅▅▅▃▅  +0.8%  │  ─────────────────       │
│     情感    +82     ▁▂▂▃▃  +5     │                         │
│     引用份额 15.7%  ▂▃▃▄▅  +1.2%  │  🎯 Focus Today          │
│     排名    #2      ─────  +1     │     AI 推荐的 1 条行动建议 │
│                                  │                         │
│  ④ SoV Horizontal Bar            │                         │
│     我/竞 A/竞 B/竞 C/其他        │                         │
│                                  │                         │
└──────────────────────────────────┴─────────────────────────┘
```

**关键迁移动作**：

1. **KPI 从 5 Card → 表格式 5 Row**：label 左对齐 / 数字 tabular-nums / sparkline inline / delta 右对齐。数据列对齐一眼扫完。Density 提升 ~3x。
2. **Alerts 前移到右侧 sidebar 顶部**：用户不用翻到最下面才看到紧急诊断。
3. **Hero 精简**：移除"等级标签"(Excellent/Good/Medium…) 这类修辞词，改成"行业均值 73 · 我 +9"直接给位置。
4. **SoV 从饼图改成 horizontal stacked bar**：对比性更好，宽度占满，和趋势图同一列对齐。
5. **竞品四象限气泡图**：不出现在面板首屏，移到折叠展开或单独 Tab (你已经有 `/brands/:id` 做单品牌深度了，面板不需要 scatter)。

### 5.2 移除的东西

- 去掉"等级色带" (Excellent/Good/Medium/Pass/Attention) —— 过度 gamify
- 去掉 KPI 卡的彩色 icon (✨💡🎯 等 emoji)
- 去掉 hero 的 gradient background
- 去掉卡片上方的渐变"decorator"条
- 筛选栏的 sticky bg 从卡片色变成纸色 (和页面同色，只用下边 hairline 区分)

### 5.3 新增的东西

- **Focus Today 卡**：右下一条 AI 推荐的行动 (`data/alerts` 最高优先级那条的自然语言版)。取代旧的 "P0/P1 分级" 冰冷列表。
- **Tabular-nums 大数字**：`font-variant-numeric: tabular-nums` 让对比数字等宽对齐。
- **(可选) Section Serif Heading**：给每一块加一个极小号的 Serif label (如 *Visibility*、*Velocity*、*Positioning*)，作为"温柔感"来源。不是必须，看原型效果。

---

## 6. 实施路径 (如果采纳)

按低风险 → 高风险排序，每步独立可回滚：

### Step 1 — Token 换肤 (2h)
- 在 `frontend/src/index.css` 的 `:root` 里加 `--theme: canopy` 变体开关
- 替换 accent / text / border / radius / shadow 的值
- **不动任何 JSX**，只看视觉 diff

### Step 2 — 字体迁移 (1h)
- 切 Nunito → Inter；加 Instrument Serif 作为 optional display font
- 更新 `tailwind.config.js` fontFamily

### Step 3 — Dashboard 页信息架构 (4-6h)
- 新建 `DashboardPage.v3.jsx` (不覆盖原页)，路由加 `/dashboard?v=3` 开关
- 实现上图的 2/3 + 1/3 布局
- KPI 从 Card 改 Table Row
- SoV 从 PieChart 改 horizontal stacked bar
- 告警条迁移到 sidebar

### Step 4 — 图表色收敛 (2h)
- 把 chart-1…chart-7 改成 chart-primary + chart-neutral-* + chart-positive/negative
- 全局 grep `var(--color-chart-\d)` 替换引用

### Step 5 — 复用扩散 (按需)
- 若 Dashboard 效果满意，把 token 扩散到 BrandDetailPage / TopicsPage

**建议**：Step 1+2 可以在任何时间做，风险极低；Step 3 是本次的主要工作量；Step 4+5 可以等 Step 3 上线后观察 1 周再决定。

---

## 7. 不做的事 (Guardrails)

为了保证提案聚焦，以下事项**明确不在本次范围内**：

- 不改 PRD §4.6.1a 的 5 区块骨架 (Hero/5 KPI/竞争视图/趋势/告警)
- 不动 i18n 文案 (除非 KPI label 因为改了表格式需要增加"单位"后缀)
- 不动 Admin 后台 / Brands / Topics 三页 (本次只打样 Dashboard)
- 不加新依赖 (Inter + Instrument Serif 走 Google Fonts CDN 即可)
- 不碰 mock 数据结构

---

## 8. 一个开放问题

**Serif 作为 Accent Heading 你接受吗？**

"温柔现代"的关键差异化就是 Sans + Serif 混排 (Attio / Linear 营销页 / Vercel Blog 都在用)。原型里我会放一个小号 Serif 作为 Section label (如 "Visibility" 用 Instrument Serif)。如果你觉得太文艺，一行 token 就能切回全 Sans——原型给你看了再决定。

---

## 9. 参考清单

- Attio 产品首页 + Dashboard 截图
- Notion Database View (6.1 版) 卡片语汇
- Vercel Observability Dashboard 数据密度参照
- Linear Issues View 筛选栏设计
- Stripe Climate Dashboard 大数字对齐
- 现有 `docs/DESIGN_TOKENS.md`
- 现有 `frontend/src/pages/DashboardPage.jsx` (PRD §4.6.1a 区块实现)

---

**下一步**：

1. 并排打开三个原型对比视觉：
   - `design/prototype-dashboard-v3.html` (Notion/Attio · Ink Navy)
   - `design/prototype-dashboard-v4-editorial.html` (FT/报刊 · Claret)
   - `design/prototype-dashboard-v5-linear.html` (Linear/Geist · Electric Blue)
2. 选定一个路线 (或双皮肤组合)
3. 再决定是否进 PRD / Session 落地——本提案不要求立即实施。

建议决策框架：
- 先问 "**GENPANO 未来 2-3 年给用户留下什么感觉？**"
  - "可靠的品牌监测中介" → v4
  - "省事的 SaaS 工具" → v3
  - "快速决策的数据控制台" → v5
- 再问 "**首批种子用户日常用得最顺手的是哪个？**" (前后答案冲突时，优先用户)
