# GENPANO Design Tokens

> **为什么有这个文档**: Figma 只表达"UI 风格预期"，不是 prototype。要避免再次把 Figma 的页面结构 1:1 搬进 React，导致 PRD → 原型 → 前端 三者脱节。这个文档把 Figma 提取出来的**视觉样式**锁定为一套独立 token 层，页面/组件按 `docs/PRD.md` + `design/prototype*.html` 的结构来重建，样式则统一消费这些 token。

**Production theme (v1 MVP, LOCKED)**: `--color-accent: #605BFF`. Alternative themes (Ink Navy, Claret, Electric Blue) listed in DASHBOARD_REDESIGN_PROPOSAL are pending A/B in Phase 2. **Do not implement theme switching in MVP.**

## 架构原则

```
┌─────────────────────────────────────────────────────┐
│  PRD (docs/PRD.md)                                  │
│    ↓  定义 要做什么 (功能、流程、数据结构)           │
│                                                     │
│  Prototype (design/prototype*.html)                 │
│    ↓  定义 页面怎么组织 (信息架构、交互)             │
│                                                     │
│  Pages / Components (frontend/src/pages, components)│
│    ↓  消费 token (文字颜色、圆角、阴影、间距)        │
│                                                     │
│  Design Tokens (本文档 + index.css + tailwind.config)│
│       定义 长什么样 (Figma 风格)                    │
└─────────────────────────────────────────────────────┘
```

**关键约束**:
- Figma mock 只用作"风格参考"，不作为页面结构来源
- 页面 JSX 里 **不允许** 写 inline hex 颜色 (`#605BFF`)；必须用 token 类或 CSS 变量
- Token 改动是 "换肤"级别的；结构/布局改动走 PRD → prototype 路径

## Token 存放位置

| 层 | 文件 | 作用 |
|---|---|---|
| CSS Variables | `frontend/src/index.css` `:root` | 真理源。运行时可被 JS 读取 (`getComputedStyle`) |
| Tailwind theme | `frontend/tailwind.config.js` | 生成 Tailwind utility (`bg-accent-500`, `rounded-card`) |
| Component classes | `frontend/src/index.css` `@layer components` | `.t-card` / `.t-btn-primary` / `.t-badge-*` 等语义组件 |
| Utility helpers | `frontend/src/index.css` `@layer utilities` | `.text-themed-primary` / `.bg-themed-page` 等语义别名 |

两边必须保持一致。改一个 token 要同时改 `index.css` 和 `tailwind.config.js` 对应项。

## Color Tokens

### 品牌色 (Accent — Figma primary purple #605BFF)

| Token | 值 | 用法 |
|---|---|---|
| `--color-accent` / `accent-500` | `#605BFF` | 主 CTA、链接、激活态图标 |
| `--color-accent-hover` / `accent-600` | `#5450E6` | primary button hover |
| `--color-accent-2` | `#8B5CF6` | 渐变 companion (Logo、分享预览卡) |
| `--color-accent-bg-light` / `info-bg` | `#F0F0FF` | 提示/洞察卡片背景 |
| `--color-accent-subtle` | `rgba(96,91,255,0.07)` | 弱底色、悬停 |
| `--color-accent-soft` / `accent-400` | `#ACA9FF` | sidebar 激活渐变起点 |
| `--color-accent-alpha-30` | `rgba(96,91,255,0.30)` | "查看全景" banner 背景 |
| `--color-accent-alpha-05` | `rgba(96, 91, 255, 0.05)` | Landing dot pattern glow |
| `--color-accent-alpha-10` | `rgba(96, 91, 255, 0.10)` | Landing glow effect |
| `--color-accent-2-alpha-06` | `rgba(139, 92, 246, 0.06)` | Landing accent-2 glow |

### 文字 (Text)

| Token | 值 | 用法 |
|---|---|---|
| `--color-text-primary` / `ink` | `#030229` | 主标题、重要数字 (Figma deep navy) |
| `--color-text-secondary` / `ink-secondary` | `#1C1D22` | 副标题 |
| `--color-text-body` / `ink-body` | `#333` | 表单/正文 |
| `--color-text-body-soft` / `ink-body-soft` | `#666` | 次要标签 |
| `--color-text-muted` / `ink-muted` | `#818194` | 说明、导航未选中 |
| `--color-text-faint` / `ink-faint` | `#BEC0C6` | placeholder、极弱提示 |
| `--color-text-inverse` | `#FFFFFF` | 深底色上的文字 |

### 表面 (Surface)

| Token | 值 | 用法 |
|---|---|---|
| `--color-bg-page` / `surface-page` | `#FAFAFB` | 页面主画布 |
| `--color-bg-card` / `surface` | `#FFFFFF` | 卡片 / 弹窗 |
| `--color-bg-subtle` | `#FAFAFB` | 行内弱对比容器 (metric row) |
| `--color-bg-subtle-2` | `#F4F4F4` | 品牌/项目选择器 pill |
| `--color-bg-badge` | `#F0F0FF` | 默认 badge 背景 |

### Overlay (覆盖层 & Scrim)

| Token | 值 | 用法 |
|---|---|---|
| `--color-overlay-drawer` | `rgba(28, 29, 34, 0.42)` | Drawer 背景遮罩 |
| `--color-scrim` | `rgba(0, 0, 0, 0.4)` | Modal/Dialog 背景遮罩 |

### 边框 (Border)

| Token | 值 | 用法 |
|---|---|---|
| `--color-border` / `border-DEFAULT` | `#D0D5DD` | 表单/输入框 (Figma 标准) |
| `--color-border-card` / `border-card` | `#F2F4F7` | 卡片轻描边 |
| `--color-border-subtle` / `border-subtle` | `#E8E8F0` | 图表网格、极弱分隔 |
| `--color-border-strong` / `border-strong` | `#C1C9D2` | 强调分隔 |

### 图表 (Chart — Figma dashboard 四线图)

| Line | Token | 值 |
|---|---|---|
| 可见度 | `chart-1` | `#030229` |
| 情感 | `chart-2` / `sentiment-positive` | `#FF708B` |
| 品牌声量 | `chart-3` | `#3B82F6` |
| 引用率 | `chart-4` | `#1E3A8A` |
| 强调/主题 | `chart-5` | `#605BFF` |
| 警告 | `chart-6` | `#FDB022` |
| 成功 | `chart-7` | `#0ABB87` |

图表统一用 `var(--color-chart-N)`，不要在 JSX 里直接写 `#3B82F6`。

### 引擎品牌色 (Engine Brand Colors)

| Engine | Token | 值 | 说明 |
|---|---|---|---|
| ChatGPT | `--color-engine-chatgpt` | `#10A37F` | OpenAI 品牌绿 |
| 豆包 | `--color-engine-doubao` | `#3B82F6` | 字节品牌蓝 |
| DeepSeek | `--color-engine-deepseek` | `#8B5CF6` | DeepSeek 品牌紫 |

引擎色用于按引擎拆分的图表 (趋势线、堆叠柱)，统一用 `var(--color-engine-*)` 引用。

### Tooltip 表面 (Tooltip Surface)

| Token | 值 | 用法 |
|---|---|---|
| `--color-tooltip-bg` | `#ffffff` | Recharts Tooltip contentStyle.background |

所有 Recharts `<Tooltip contentStyle={{ background: ... }}>` 统一用 `var(--color-tooltip-bg)`，禁止内联 `#ffffff`。

### Heatmap 色带 (Heatmap Color Scales, 2026-04-20 新增)

BrandTopicHeatmap 组件使用两套色带, 覆盖两种语义:

**Sequential (0 → max, 用于 mentionRate / SoV / 引用份额 等单向指标)**

| 档位 | Token | 值 | 用法 |
|---|---|---|---|
| 0 (空/极低) | `--color-heatmap-seq-0` | `#F4F4F5` (zinc-100) | 无样本或 < 2% |
| 1 | `--color-heatmap-seq-1` | `#E4E4E7` (zinc-200) | 2-10% |
| 2 | `--color-heatmap-seq-2` | `#C7D2FE` (indigo-200) | 10-25% |
| 3 | `--color-heatmap-seq-3` | `#818CF8` (indigo-400) | 25-50% |
| 4 | `--color-heatmap-seq-4` | `#605BFF` (品牌 accent) | 50-75% |
| 5 (最高) | `--color-heatmap-seq-5` | `#3730A3` (indigo-800) | > 75% |

**Diverging (-1 ↔ +1, 用于 sentiment / sovDelta / 胜负差 等双向指标)**

| 档位 | Token | 值 | 用法 |
|---|---|---|---|
| neg-strong | `--color-heatmap-div-neg-2` | `#DC2626` (red-600) | < -0.5 或严重负 |
| neg | `--color-heatmap-div-neg-1` | `#FCA5A5` (red-300) | -0.5 ~ -0.1 |
| zero | `--color-heatmap-div-zero` | `#F4F4F5` (zinc-100) | -0.1 ~ +0.1 (中性) |
| pos | `--color-heatmap-div-pos-1` | `#86EFAC` (green-300) | +0.1 ~ +0.5 |
| pos-strong | `--color-heatmap-div-pos-2` | `#16A34A` (green-600) | > +0.5 |

所有热力图单元格背景必须走上述 token, 禁止内联 hex 或使用硬编码 Tailwind 阶。

### 图表数据 & 行为契约 (Chart Contracts) ⚠️ 强制

Chart color token 只管"颜色"; 以下 7 条契约约束"什么数据能进图"、"图怎么长"。每一条都对应过一个已修复的 Bug (2026-04-17), 进 Harness pre-commit + CI grep 拦截回归。

#### C1. 原子组件默认 100% 填充 — 禁止固定像素默认

- `<MiniSparkline>` / 同类 sparkline 原子组件: `width`、`height` **默认值必须是 `'100%'`**。
- 调用方在**外层 wrapper** 用 Tailwind 尺寸类 (`h-10`, `flex-1`, `w-full`, `w-[200px]`) 控制尺寸。
- 🚫 **禁止** 在原子组件默认参数中写 `width = 100` / `height = 32` 等像素字面量 — 会把所有 `<div className="flex-1">` 的调用方锁死在 100px (2026-04-17 已修复 root cause)。
- ✅ 只允许**显式**传数字: `<MiniSparkline width={200} height={40} />`。

#### C2. 排行/分布柱图默认单色 + 数值标签

- `<HorizontalBar>` 用于排名/占比分布时, 默认传 `monochrome showLabels`。
- 🚫 **禁止** 给柱图 `data[]` 每项单独写不同 hex 色 (6 种颜色并排 = 视觉噪声)。
- 视觉诉求: **值的高低是唯一视觉变量**, 颜色不做分类编码。
- `defaultColor` 走 `var(--color-accent)` 或 chart token; 禁止字面 hex。

#### C3. SoV / 占比饼图: "其他" ≤ 10%

- 若占比图 `其他` 片 > 任一真实品牌片, 说明 **数据集不完整**, 必须扩充到 Top 8+。
- 🚫 禁止让灰色"其他"成为视觉焦点 (直接吞噬品牌洞察)。
- Donut 配 > 5 项图例时: Donut `size ≥ 200`, 图例采用 `grid-cols-2` 布局。

#### C4. Sentiment 展示统一百分比整数

- 面向用户的 KPI / 卡片 / 表格 / 排行榜: `${Math.round(sentiment * 100)}%` → `"82%"`。
- 🚫 **禁止** `sentimentValue.toFixed(2)` 给终端用户看 `"0.82"`。
- **唯一例外**: 当 Y 轴原生值域是 `[0, 1]` (如 `CompetitorQuadrant` scatter 的 `ReferenceLine y={0.75}`), tooltip 可保留 decimal 以与轴同单位; 此例外必须加代码注释标注。

#### C5. Sparkline 数据平滑性

- rank / metric 的 sparkline 合成逻辑必须用**连续函数**: 线性趋势 + `sin/cos * 振幅<1` 扰动。
- 🚫 **禁止** 离散台阶模式 `i % N === 0 ? +V : 0` — 直接产生锯齿波, 误导用户判读 (Bug#2, 2026-04-17)。
- rank 类 sparkline (`trendIsRank: true`): 外部应反转 Y 轴 (低值 = 更好)。
- mock 合成值要像真实数据: 有**趋势** + 小扰动, 不是周期脉冲。

#### C6. "放大胜利者" — 排行榜 Hero 变体

- 行业 PANO Score 排行榜、Topic 热门榜等多项排名场景: Top 1 应用 **Hero 卡片**:
  - 横向布局 (`flex items-center gap-8`)
  - `PanoRing size={150}` (比 #2-N 的 100 大一截)
  - 渐变背景 `linear-gradient(135deg, var(--color-bg-card) 0%, var(--color-bg-badge) 100%)`
  - `border-left: 4px solid var(--color-accent)`
  - `shadow: 0 8px 24px rgba(99,91,255,0.12)`
  - 左上角 Badge `#1` + change badge + "行业领军"标签
- 2 - N 名走普通 `grid-cols-4` 网格。
- 这和知识图谱"放大胜利者"是同一视觉原则, 2026-04-17 扩展到排行榜。

#### C7. Mock 数据字段内在一致性

- 若实体 (Brand/Product) 同时有 `ranking` 字段和排序指标字段 (`panoScore`):
  - `ranking` 必须与 **按排序指标降序排列后的索引+1** 完全一致。
- 🚫 **禁止** 让"排行榜位置 `#idx+1`"和"排名 Badge `#brand.ranking`"同时出现但互相矛盾 (Bug#1, 2026-04-17: 迪奥 panoScore 排第 4 位但 ranking=7)。
- 规则适用于 `frontend/src/data/mock.js` 的 BRANDS / PRODUCTS, 以及后端 API 契约。
- 建议在数据定义文件末尾加 assertion: `assert BRANDS.every((b, i) => b.ranking === i + 1)` (按 `panoScore desc` 排序后)。

#### C8. Drawer / Side-Sheet 契约 (2026-04-20 新增, 配合 §4.6.1a-drilldown)

KPI Drawer (Mode A 右侧抽屉下钻) 是 GENPANO 引入的第一个非 Modal 非 Popover 的覆盖层形态, 必须与 Dialog / Tooltip 区分清楚并统一实现:

- **实现库**: 必须用 `@radix-ui/react-dialog` (复用 Modal 底座, 不引入 `vaul` / `sheetjs-react-sheet` 等第二家抽屉库)
- **宽度**: 桌面默认 `560px` (lg ≥ 1024px), 平板 `min(560px, 80vw)` (md 768-1023), 移动 `100vw` 全屏展开 (sm < 768)
  - 🚫 **禁止**: 手写数字 (如 `w-[620px]` / `w-[500px]`), 必须经 token `--drawer-width-desktop: 560px` / `--drawer-width-tablet-max: 80vw`
- **侧向**: 默认右侧 (`right: 0`), 左侧仅保留给未来可能的"全局导航抽屉", 当前不启用
- **Overlay (backdrop)**: `rgba(28, 29, 34, 0.42)` (与 Dialog 同底色), token `--color-overlay-drawer`
- **动画**: 进入 `translate-x-full → 0` 220ms cubic-bezier(0.16, 1, 0.3, 1) (ease-out-expo), 退出 180ms 对称
  - 🚫 **禁止**: 默认 transition-all / 300ms 过长 / linear 时序
- **Header**: 固定 64px 高, `border-bottom: 1px solid var(--color-border-default)`, 左侧标题 + 指标当前值, 右侧"展开全页 ↗" secondary link + 关闭 X
- **Footer**: 可选, 若存在则高度 56px, `border-top: 1px solid var(--color-border-default)`, 承载"导出 CSV" / "跳转 Full-page" / 其他 primary 动作
- **Body**: 滚动区, padding `20px 24px`, 内部分 section 用 `--color-border-subtle` 分隔
- **Scroll lock**: Radix Dialog 已自带 body scroll lock, 不再手写
- **关闭条件**: ESC / 点击 overlay / 点击关闭 X / 路由切换时自动 close
- **URL state**: Drawer 打开时 URL 追加 `?drilldown=<kpi_name>` (source of truth), 便于直链 / 刷新保持状态; 关闭时清理 query

**Harness grep (pre-commit + CI)**:

```bash
# (C8-1) Drawer 宽度禁止硬编码 px, 必须经 token
grep -rnE "className=.*\bw-\[(4[5-9][0-9]|5[0-9][0-9]|6[0-4][0-9])px\]" \
  frontend/src/components/drilldown --include='*.jsx'

# (C8-2) 禁止引入第二家抽屉库
grep -rnE "from ['\"]vaul['\"]|from ['\"]sheetjs-react-sheet['\"]|from ['\"]react-modal-sheet['\"]" \
  frontend/src --include='*.jsx' --include='*.tsx' --include='*.js' --include='*.ts'

# (C8-3) Drawer 动画时长禁超 250ms 或小于 180ms
grep -rnE "duration-(100|1[0-7][0-9]|2[6-9][0-9]|[3-9][0-9][0-9])\s.*drawer|drawer.*duration-(100|1[0-7][0-9]|2[6-9][0-9]|[3-9][0-9][0-9])" \
  frontend/src/components/drilldown --include='*.jsx'
```

任何一条有输出即视为"Drawer 契约回归", PR 必须修复方可合并。

#### C9. Heatmap & Chart Token 边界规则 (2026-04-20 新增, 配合 PRD §4.6-IA-v2.L)

**Boundary rule (C-P1-1)**: `BrandTopicHeatmap` 组件**只能使用** `--color-heatmap-*` token (diverging + sequential 色带)。所有其他图表 (趋势线、堆叠柱、散点等) **只能使用** `--color-chart-*` token。禁止在两个家族间混用。所有跨界使用由 CI grep 规则 C9-mix 在 `scripts/ci-check.mjs` 中拦截。

BrandTopicHeatmap 组件在实现时必须满足以下条件, 禁止:

- 内联 hex (如 `fill="#818CF8"`)
- Tailwind 非 heatmap 色阶 (如 `bg-indigo-400`, `bg-green-500`)
- 从 `--color-chart-*` 借用线图色

**Harness grep (pre-commit + CI)**:

```bash
# (C9-1) BrandTopicHeatmap 不得使用 chart-N / sentiment-* token 借色
grep -nE "var\(--color-(chart-[0-9]|sentiment-(positive|negative|neutral))" \
  frontend/src/components/charts/BrandTopicHeatmap.jsx

# (C9-2) Heatmap 组件不得出现内联 hex
grep -nE "(fill|background)[:=]\s*['\"]?#[0-9a-fA-F]{3,8}" \
  frontend/src/components/charts/BrandTopicHeatmap.jsx
```

#### C10. Brand Mode 分析页全局 Filter Bar 统一出口 (2026-04-20 新增, 配合 PRD §4.6-IA-v2.K)

Brand Mode 下 6 个深度分析页 (Visibility / Topics / Sentiment / Citations / Products / Competitors) 的筛选状态**必须**经 `useBrandAnalysisFilters()` hook 读取, 禁止:

- 页面内部 `useState` 存时间/引擎/画像 (应走 URL)
- 直接 `useSearchParams()` 绕过 hook (绕过会导致字段名 drift)
- 自建局部 Filter Bar 组件

Overview 页 (`/brand/overview`) 例外: 其筛选器集成在 `BrandPanoramaPanel` 内, 但**必须**也经同一 hook 同步 URL state, 保证切 Overview ↔ 其他分析页时状态不丢。

**Harness grep (pre-commit + CI)**:

```bash
# (C10-1) 6 分析页必须 import 统一组件
for f in frontend/src/pages/brand/Brand{Visibility,Topics,Sentiment,Citations,Products,Competitors}Page.jsx; do
  grep -q "BrandAnalysisFilterBar\|useBrandAnalysisFilters" "$f" || echo "MISSING: $f"
done

# (C10-2) 分析页禁止自写本地时间 state
grep -rnE "useState\s*\(\s*['\"]7d|useState.*dateRange|useState.*fromDate" \
  frontend/src/pages/brand/ --include='*.jsx'
```

#### C11. mentionRate 数据必须存小数 [0, 1] (2026-04-20 新增, 配合 PRD §4.6-IA-v2.N)

**因为 2026-04-20 Frank 反馈出现 "1620%" bug**, `mentionRate` 字段在整个系统 (mock.js / DB / API / UI) **必须**是 0-1 小数, 在 UI 渲染层统一 ×100。不得混用百分比存储格式。

- 存储层: `0.162` (表示 16.2%)
- 展示层: `{(value * 100).toFixed(1)}%` 或 `${Math.round(value * 1000) / 10}%`
- 禁止的写法:
  - ❌ `Math.round(value * 100)` + `%` (当 value 已是 16.2, 会渲染 1620%)
  - ❌ 存储层写 `18.5` (百分比字面量)
  - ❌ 某些字段是百分比、某些是小数的混用

**Harness (scripts/check-data-contracts.mjs)**:

```javascript
// 运行时断言
import { BRANDS, PRODUCTS, TOPICS } from '../frontend/src/data/mock.js';
for (const b of BRANDS) {
  if (b.mentionRate > 1 || b.mentionRate < 0) {
    throw new Error(`C11 violation: BRANDS[${b.id}].mentionRate = ${b.mentionRate} (must be 0-1 decimal)`);
  }
}
// 同样断言 PRODUCTS 和 TOPICS 的 mentionRate
```

**Harness grep**:

```bash
# (C11-1) mock.js 里 mentionRate 字段不得出现 > 1 的值
grep -nE "mentionRate:\s*[1-9][0-9]*(\.[0-9]+)?[,\s}]" frontend/src/data/mock.js

# (C11-2) UI 代码不得用 `Math.round(value * 100)` 渲染 mentionRate (会放大 100 倍)
grep -rnE "mentionRate.*Math\.round\s*\(.*\*\s*100\s*\)" frontend/src/pages --include='*.jsx'
```

#### C12. Sentiment Distribution 必须用 Donut (2026-04-20 新增, 配合 PRD §4.6-IA-v2.N)

**因为 2026-04-20 Frank 反馈 BrandSentimentPage 的 Distribution 用 3 个大号文字百分比显得"图表坏了"**, 情感分布 (正/中/负 三段占比) **必须**用 `<DonutChart>` 组件, 不得:

- 用 3 个大号 `<span className="text-3xl">` 文字堆叠
- 用 HorizontalBar / StackedBar 替代 (那是引擎分布, 不是总体分布)
- 用 Recharts 原生 `<PieChart>` 绕开封装 (样式会 drift)

**Harness grep (pre-commit + CI)**:

```bash
# (C12-1) BrandSentimentPage 必须 import DonutChart
grep -q "import.*DonutChart" frontend/src/pages/brand/BrandSentimentPage.jsx || \
  echo "C12 violation: BrandSentimentPage missing DonutChart import"

# (C12-2) BrandSentimentPage 不得用 text-3xl+ 渲染 sentiment 百分比 (标志性反模式)
grep -nE "text-(3xl|4xl|5xl).*(positive|negative|neutral)Pct|(positivePct|negativePct|neutralPct).*text-(3xl|4xl|5xl)" \
  frontend/src/pages/brand/BrandSentimentPage.jsx
```

#### C13. CompetitorQuadrantChart 气泡尺寸 caller-controlled + 必带 label (2026-04-20 新增, 配合 PRD §4.6-IA-v2.M + BCG 矩阵修复)

**因为 2026-04-20 Frank 反馈 "矩阵非常乱"** — 原 `CompetitorQuadrantChart.jsx` shape override 内写死 `radius = 40 + zNorm * 360`, 产生 40-400px 半径 (80-800px 直径) 的气泡, 密集场景必然互相覆盖; 且气泡本身无文字标签, 用户要 hover 才能辨识品牌。

**契约**:

- `CompetitorQuadrantChart` 必须暴露两个 prop:
  - `bubbleRadius`: `[number, number]` 形式的 `[rMin, rMax]`, 默认 `[8, 24]` (小气泡, 低拥挤风险); 调用方按页面密度可调大, 但**不得**在组件内硬编码 > 40 的 `rMax`
  - `showLabels`: `boolean`, 默认 `true`; 标签渲染在气泡正下方 `cy + radius + 10`, `textAnchor='middle'`, `fontSize={10}`
- 半径映射: sqrt 面积正比 — `zNorm = sqrt((z - zMin) / zRange)`, `radius = rMin + zNorm * (rMax - rMin)`; ⚠️ 禁止线性映射 `radius = rMin + zNorm * (rMax - rMin)` 前不开根号 (线性会让小 z 值过小, 大 z 值霸屏)
- 标签文本截断: `rawName.length > 10 → rawName.slice(0, 9) + '…'`
- Primary 品牌: `payload.isPrimary === true` → 气泡 `fillOpacity=0.85` + `stroke=var(--color-accent)` + 标签 `fontWeight=600 fill=var(--color-accent)`; 其余: `fillOpacity=0.55` + `stroke=var(--color-border-subtle)` + 标签 `fontWeight=400 fill=var(--color-text-muted)`

**Harness grep (pre-commit + CI)**:

```bash
# (C13-1) CompetitorQuadrantChart 不得硬编码 radius > 40 的 literal
grep -nE "radius\s*=\s*[4-9][0-9]|r=\{?\s*[4-9][0-9][^0-9]" \
  frontend/src/components/charts/CompetitorQuadrantChart.jsx

# (C13-2) 气泡半径必须 sqrt 映射 (禁线性)
grep -q "Math\.sqrt" frontend/src/components/charts/CompetitorQuadrantChart.jsx || \
  echo "C13 violation: CompetitorQuadrantChart missing sqrt radius mapping"

# (C13-3) showLabels prop 必须存在
grep -q "showLabels" frontend/src/components/charts/CompetitorQuadrantChart.jsx || \
  echo "C13 violation: CompetitorQuadrantChart missing showLabels prop"
```

#### C14. V2 分析页密度标准 (2026-04-20 新增, 配合 PRD §4.6-IA-v2.K-N)

**因为 2026-04-20 Frank 反馈 "可见性的图表排列太过于松散"** — Brand Mode 6 个分析页 (Visibility / Topics / Sentiment / Citations / Products / Competitors) 各自延续了旧页的 padding / 字号 / 垂直节奏, 导致跨页不一致 + 信息密度低。V2 密度规范如下:

| 元素 | Class | 值 |
|---|---|---|
| 页面垂直节奏 | `space-y-3` | 0.75rem = 12px |
| 页面标题 | `text-xl font-brand font-bold` | 1.25rem, weight 700 |
| 页面副标题 | `text-xs text-themed-muted` | 0.75rem, muted |
| Card padding | `p-3` | 0.75rem |
| Card section header | `text-[13px] font-semibold text-themed-primary` | 13px (精确像素) |
| Card section meta | `text-[11px] text-themed-muted` | 11px (精确像素) |
| KPI/Threat card 大数字 | `text-lg font-bold` | 1.125rem |
| KPI/Threat card 标签 | `text-[11px] text-themed-muted uppercase tracking-wide` | 11px |
| Card 内垂直分段 | `space-y-2` (不用 `space-y-4`) | 0.5rem |

**禁止**:
- `text-2xl` / `text-3xl` 做页面标题 (那是 Landing 专用)
- `p-4` / `p-5` / `p-6` 做 Card padding (已由 `p-3` 替代)
- `space-y-4` / `space-y-6` 做页面节奏 (太松)
- `text-sm` 做副标题 (优先 `text-xs`; `text-sm` 仅用于 body)

**Harness grep (pre-commit + CI)**:

```bash
# (C14-1) V2 分析页不得用 text-2xl/text-3xl 做标题
grep -rnE "<h[12][^>]*text-(2xl|3xl|4xl)" frontend/src/pages/brand/ --include='*.jsx' \
  | grep -v "// C14-exempt"

# (C14-2) V2 分析页不得用 p-4 以上做 Card padding
grep -rnE "className=[\"'][^\"']*\bp-[4-9]\b" frontend/src/pages/brand/ --include='*.jsx' \
  | grep -v "// C14-exempt"

# (C14-3) V2 分析页不得用 space-y-[4-9] 做页面节奏 (根 div 限制)
grep -rnE "return\s*\(\s*<div\s+className=[\"'][^\"']*space-y-[4-9]" \
  frontend/src/pages/brand/ --include='*.jsx'
```

**C14-exempt 例外**: 若页面顶部确有 marketing-level Hero 需要 text-2xl 标题 (目前 V2 无此需求), 在标题行末尾加 `{/* C14-exempt: hero */}` 注释规避 grep。

---

#### C15. BrandProductDetailPage 路由契约 (2026-04-20 Wave-4, 配合 PRD §4.6-IA-v2.O)

**定位**: Frank 2026-04-20 傍晚校正 — Wave-4 初版误读为"列表页扩 7 区", 已于同日回滚。真正要固化的是 **详情页 `/brand/products/:productId?brandId=:brandId` 的 brandId 从 query string 读取契约**, 修复 `useParams()` 解构 `brandId` 得 undefined 导致整页 "暂无数据" 的 P0 bug。

**契约**:

1. **productId 走 path param** — `useParams().productId`, 对应 App.jsx 路由 `<Route path="/brand/products/:productId" />`。
2. **brandId 走 query string** — `useSearchParams()[0].get('brandId')`, 禁止从 `useParams` 解构 (会得 undefined)。与 Brand Mode 其他 sub-view (`/brand/overview?brandId=`, `/brand/visibility?brandId=` 等) 保持一致, 使 BrandPicker 切换只改 query 不跳 sub-view。
3. **brand 可为 null** — productId 若缺失/不匹配才渲染空状态; brand 缺失时 UI 必须降级而不崩 (品牌链接 `disabled`, 品牌名 fallback 到 `product.brand` / `product.brandEn`, industry/category 计算三元短路)。反向 fallback: 若 `brandId` 为空, 由 `PRODUCTS.find(...)` 反查 `product.brand` 字段匹配 BRANDS。
4. **Legacy URL 301** — App.jsx 保留 `/brands/:brandId/products/:productId` → 301 `/brand/products/:productId?brandId=:brandId`, 确保旧书签/外链不挂。

**Harness**:

```bash
# (C15-1) BrandProductDetailPage 禁从 useParams 解构 brandId (brandId 是 query string)
grep -nE "useParams\(\)[^{]*\{[^}]*\bbrandId\b" \
  frontend/src/pages/BrandProductDetailPage.jsx \
  frontend/src/pages/brand/BrandProductDetailPage.jsx 2>/dev/null
# 期望: 无输出

# (C15-2) BrandProductDetailPage 必须 import useSearchParams (brandId 查询字符串读取)
grep -q "useSearchParams" frontend/src/pages/BrandProductDetailPage.jsx || \
  echo "C15-2 violation: BrandProductDetailPage missing useSearchParams import"

# (C15-3) 空状态守卫仅基于 product (productId), 禁基于 brand 也返回空页
grep -nE "if\s*\(\s*!brand[^)]*\)\s*\{?\s*return\b.*(Empty|暂无)" \
  frontend/src/pages/BrandProductDetailPage.jsx
# 期望: 无输出 (若 brand 不存在也必须降级渲染而非空白页)
```

**为什么是契约而不是建议**: Frank 原文 "目前点击某一个详细的产品后, 应该是基于这些产品的 GEO 数据, 但是目前是空的" 是真实 P0 bug; 同时 Brand Mode IA v2.0 已把"brandId 走 query string"作为全 sub-view 统一约定, Detail Page 偏离这条约定即退化成空白页。契约固化防止回归。

### Sentiment Bar (Topics 页情感分布)

| Segment | Token | 值 |
|---|---|---|
| 正面 | `sentiment.positive` | `#FF708B` |
| 中性 | `sentiment.neutral` | `#DFE3F3` |
| 警告 | `sentiment.warning` | `#FDB022` |
| 品牌高亮 | `sentiment.brand` | `#605BFF` |
| 柔和辅助 | `sentiment.mild` | `#C9C7F8` |

**Token usage note (C-P1-3)**: `--color-sentiment-{positive,neutral,negative}` 用于 KPI 卡片的情感分数和 Drawer 下钻中的情感指标。`--color-chart-*` 用于通用图表系列 (时间序列、堆叠柱、散点等)。当两者都适用时 (例：情感着色的柱状图)，情感色优先。

### 语义 (Semantic)

| Token | 值 | 用法 |
|---|---|---|
| `--color-success` | `#0ABB87` | 正向变化、"+5.2%" |
| `--color-success-hover` | `#0A9B74` | 成功状态 hover (base -10%) |
| `--color-warning` | `#F5A623` | 注意、降级 |
| `--color-danger` | `#DC2626` | 错误表单提示、P0 诊断 |
| `--color-danger-hover` | `#B91C1C` | 危险状态 hover (base -10%) |
| `--color-info` | `#605BFF` | 信息提示 (同 accent) |
| `--color-text-on-accent` | `#FFFFFF` | 深色背景上的文字 |

### 环境标识 (Environment Band, Admin Session A0 新增)

Admin 登录页左侧色带 / 顶栏环境徽章使用。**与 semantic success/warning/danger 语义分离**——env 色只标识"这是哪个环境"，不暗示成功/失败。

| Token | 值 | 用法 |
|---|---|---|
| `--color-env-dev` | `#10B981` (emerald) | 本地 / dev 环境色带 |
| `--color-env-dev-bg` | `rgba(16,185,129,0.10)` | dev 浅底 (徽章内填) |
| `--color-env-staging` | `#F59E0B` (amber) | staging 环境色带 |
| `--color-env-staging-bg` | `rgba(245,158,11,0.10)` | staging 浅底 |
| `--color-env-prod` | `#EF4444` (red) | production 环境色带 (⚠️ 严重提示) |
| `--color-env-prod-bg` | `rgba(239,68,68,0.10)` | prod 浅底 |

**消费入口**: 前端读 `import.meta.env.VITE_ENV_NAME` (dev / staging / prod)，映射到对应 token。同一组件**不得**同时用 `--color-success` 和 `--color-env-dev` 表达同一语义（它们是不同的轴）。

## Typography

### 字体栈

- **Body/Brand**: `Nunito` → `Inter` (fallback) → `Microsoft YaHei` / `Noto Sans SC` (中文) → system sans
- **Utility 类**: `.font-brand` (Nunito 专用，标题/Logo)、`.font-ui-cn` (中文导航标签)

### 字号阶梯 (Tailwind)

| Class | 值 | 用途 |
|---|---|---|
| `text-display-1` | 3rem / 700 | 营销页 hero |
| `text-display-2` | 2.25rem / 700 | 主标题 |
| `text-heading-1` | 1.5rem / 700 | 页面 H1 |
| `text-heading-2` | 1.25rem / 600 | 区块 H2 |
| `text-heading-3` | 1.125rem / 600 | 卡片 H3 |
| `text-data-xl` | 2.25rem / 700 | 大数字 (PanoScore) |
| `text-data-lg` | 1.5rem / 700 | 中号数字 |
| `text-body` | 1rem | 正文 |
| `text-body-sm` | 0.875rem | 次要正文 |
| `text-body-xs` | 0.75rem | 辅助说明 |

## Radius

| Token | 值 | 用途 |
|---|---|---|
| `--radius-input` / `rounded-input` | 6px | 输入框、小按钮 |
| `--radius-btn` / `rounded-btn` | 6px | 主要按钮 |
| `--radius-btn-lg` / `rounded-btn-lg` | 8px | 语言选择器等 |
| `--radius-badge` / `rounded-badge` | 6px | Badge / tag |
| `--radius-card` / `rounded-card` | 12px | 标准卡片 |
| `--radius-card-lg` / `rounded-card-lg` | 16px | 大卡片 |
| `--radius-banner` / `rounded-banner` | 24px | "查看全景" 类 banner |
| `--radius-pill` / `rounded-pill` | 9999px | 全圆角标签 |

## Drawer Dimensions

| Token | 值 | 用途 |
|---|---|---|
| `--drawer-width-desktop` | `560px` | 桌面端 Drawer 宽度 (lg ≥ 1024px) |
| `--drawer-width-tablet` | `min(560px, 80vw)` | 平板 Drawer 宽度 (md 768-1023px) |
| `--drawer-width-mobile` | `100vw` | 移动端 Drawer 全屏宽度 (sm < 768px) |
| `--drawer-animation-duration` | `220ms` | Drawer 进出动画时长 |

## Shadow

| Token | 值 | 用途 |
|---|---|---|
| `shadow-card` | `0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.03)` | 卡片静态 |
| `shadow-card-hover` | `0 8px 24px rgba(50,50,93,0.08)...` | 卡片悬停 |
| `shadow-elevated` | `0 25px 50px rgba(50,50,93,0.25)` | Modal / 弹层 |
| `shadow-btn` | `0 1px 3px rgba(0,0,0,0.10)...` | 按钮静态 |
| `shadow-input` | `0 1px 2px rgba(16,24,40,0.05)` | 输入框 |

## Gradient

| Token | 值 | 用途 |
|---|---|---|
| `bg-gradient-accent` | `linear-gradient(135deg, #605BFF 0%, #8B5CF6 100%)` | Logo、Share preview |
| `bg-gradient-warm` | `linear-gradient(135deg, #FFC7D4, #FFE0C7)` | User avatar 暖色方块 |
| `bg-gradient-nav-active` | `linear-gradient(90deg, rgba(172,169,255,1) 0%, rgba(172,169,255,0) 24%)` | Sidebar 激活项背景 |

## Component Classes (`@layer components`)

这些是高层语义组件，页面应优先使用它们而不是手写样式：

| Class | 作用 |
|---|---|
| `.t-card` + `.t-card-interactive` | 卡片容器 (hover 升起) |
| `.t-btn-primary` / `.t-btn-secondary` / `.t-btn-ghost` | 按钮 (对应 `<Button variant="...">`) |
| `.t-badge` + `.t-badge-{default|accent|success|warning|danger|info}` | Badge |
| `.t-tabs` + `.t-tab` + `.t-tab-active` | 标签页 |
| `.t-input` / `.t-input-error` | 输入框 |
| `.t-table` | 表格 (自动应用行 hover) |
| `.t-sidebar` (light) / `.t-sidebar-dark` (reserved) | 侧边栏 |
| `.t-header` | 顶部 header (带 backdrop blur) |
| `.t-progress-track` | 进度条轨道 |

## Utility Helpers (`@layer utilities`)

页面里写布局时用这些而不是 inline hex：

| Class | 对应 Token |
|---|---|
| `.text-themed-primary` | `--color-text-primary` |
| `.text-themed-muted` | `--color-text-muted` |
| `.text-themed-accent` | `--color-accent-text` |
| `.bg-themed-page` | `--color-bg-page` |
| `.bg-themed-card` | `--color-bg-card` |
| `.bg-themed-accent-soft` | `--color-accent-bg-light` |
| `.border-themed` / `.border-themed-card` / `.border-themed-subtle` | 三档 border |
| `.font-brand` | Nunito |
| `.font-ui-cn` | Microsoft YaHei |

## 使用规则 (⚠️ 强制)

### ✅ 应该这样写

```jsx
// 页面文字
<h2 className="text-heading-2 text-themed-primary">品牌可见度</h2>

// 卡片容器
<Card className="p-6">...</Card>   // 用 Card 组件
// 或
<div className="t-card">...</div>  // 直接用 component class

// 按钮
<Button variant="primary">创建项目</Button>
<button className="t-btn-primary px-4 py-2">...</button>

// 图表色
<Line stroke="var(--color-chart-1)" />
<div className="bg-sentiment-positive" />

// 渐变
<div className="bg-gradient-accent" />
```

### ❌ 不应该这样写

```jsx
// 禁止: 裸 hex
<h2 style={{ color: '#030229' }}>...</h2>
<div className="bg-[#605BFF]">...</div>

// 禁止: 绕过 token 的 Tailwind 魔法值
<div className="rounded-[12px] shadow-[0_25px_50px_rgba(50,50,93,0.25)]" />

// 禁止: 在组件里重新定义品牌色
const styles = { primary: '#605BFF' };
```

### 例外情况

- **一次性插画颜色** (e.g., 空状态 SVG 里的插画色) — 允许 inline，但要在 PR 里说明
- **第三方库强制要求的 prop** (e.g., `<PanoRing color="#605BFF" />`) — 应该改成 prop 接收 token 字符串并在内部 `var()`
- **Figma 原样移植的临时页** — 这是**已知债务** (见"迁移进度")；新页面严禁复现

## 迁移进度

### Brand Mode 页面 (`/brand/*`)

| 页面 | 状态 | 说明 |
|---|---|---|
| `BrandOverviewPage.jsx` (BrandPanoramaPanel) | 🟢 Golden 标准 | 所有 brand 页面的设计参考; 全量 token 消费 |
| `BrandVisibilityPage.jsx` | 🟢 Token 对齐 | 2026-04-20 按 golden 标准重写 |
| `BrandSentimentPage.jsx` | 🟢 Token 对齐 | 2026-04-20 按 golden 标准重写 |
| `BrandCitationsPage.jsx` | 🟢 Token 对齐 | 2026-04-20 按 golden 标准重写 |
| `BrandCompetitorsPage.jsx` | 🟢 Token 对齐 | 2026-04-20 按 golden 标准重写 |
| `BrandProductsPage.jsx` | 🟢 Token 对齐 | 2026-04-20 按 golden 标准重写 |
| `BrandTopicsPage.jsx` | 🟡 待重写 | 从旧 TopicsPage 迁移, 四层 drill-down 需按 PRD 重建 |
| `BrandDiagnosticsPage.jsx` | 🟡 待建 | Session T2' 待建 |
| `BrandReportsPage.jsx` | 🟡 待建 | Session T2' 待建 |

### Industry Mode 页面 (`/industry/*`)

| 页面 | 状态 | 说明 |
|---|---|---|
| `IndustryOverviewPage.jsx` | 🟢 按 prototype 构建 | 使用 token 体系 |
| `IndustryRankingPage.jsx` | 🟡 待建 | Session T3' 待建 |
| `IndustryTopicsPage.jsx` | 🟡 待建 | Session T3' 待建 |
| `IndustryKnowledgeGraphPage.jsx` | 🟢 按 prototype 构建 | AntV G6, token 体系 |

### 共享页面 & 布局

| 页面 | 状态 | 说明 |
|---|---|---|
| `DashboardLayout.jsx` | 🟡 混合 | 2026-04-20 重构 Mode Toggle + 侧栏; 部分 Figma 遗留 |
| `AuthPage.jsx` | 🔴 Figma 原样移植 | 含 inline hex；待按 PRD §4.1.1-form 重建 |
| `OnboardingPage.jsx` | 🟡 待建 | Session T4' 待建, 独立 4 步引导 |
| `BrandsPage.jsx` | 🟢 按 prototype 构建 | 品牌集市 grid, 使用 token 体系 |
| `LandingPage.jsx` | 🟡 独立组件 (BfButton) | Builderflow 风格营销页 |

### 图表组件 (`components/charts/`)

| 组件 | 状态 | 说明 |
|---|---|---|
| `TrendChart.jsx` | 🟢 Token 对齐 | tooltip / axis / grid 全量 token |
| `HorizontalBar.jsx` | 🟢 Token 对齐 | defaultColor 改为 `var(--color-accent)` |
| `DonutChart.jsx` | 🟢 Token 对齐 | stroke 改为 `var(--color-bg-card)` |
| `CompetitorQuadrantChart.jsx` | 🟢 Token 对齐 | tooltip 使用 token |
| `PanoRing.jsx` | 🟢 Token 对齐 | 阈值色改为 `var(--color-accent/success/warning/danger)` |
| `MiniSparkline.jsx` | 🟢 C1 合规 | 默认宽高 100% |

🟡 页面将在后续 Session (见 `docs/CLAUDE_CODE_SESSIONS.md`) 按 PRD 重建，届时结构换掉、样式消费这里的 token。

## 改动这份 token 的流程

1. 修改 `frontend/src/index.css` `:root` 里的 CSS 变量
2. 同步 `frontend/tailwind.config.js` `theme.extend` 里的对应项
3. 如果新增或重命名 token，更新本文档的表格
4. 跑 `npm run dev` 视觉 diff，重点看 Dashboard / Topics / Brands 三页
5. 不需要跨文件替换 hex — token 消费方自动生效

## 参考

- Figma 提取源: Auth / Dashboard / Topics / DashboardLayout (2026-04)
- 样式原则: `docs/DESIGNER_AGENT.md` — Stripe/Linear 风格精简
- 依赖规则: `CLAUDE.md` → "依赖规则" — 禁止手写生产级组件
