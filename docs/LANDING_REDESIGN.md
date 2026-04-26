# LANDING_REDESIGN — 官网视觉重做 PRD (v2.1, 2026-04-17)

> **Scope**: 官网 `frontend/src/pages/LandingPage.jsx` 的视觉重做 + 全站 i18n (ZH/EN) 切换器接入 + 官网到应用端的入口映射。
>
> **本文档的职责分界**:
> - **官网侧** (本文档完整覆盖): 视觉语言 (与产品端对齐)、信息架构、文案、语言切换按钮 UX、官网 → 应用的入口映射
> - **产品侧** (本文档只给契约, 落地属于下一 Session): 读取同一个 `genpano_locale` cookie/localStorage key, 保证切换在已登录状态下跨域/跨页生效

---

## 0. 决策摘要 (Frank 确认 2026-04-17 · v2.1 修订)

| 维度 | v1 (上午) | v2.0 (中段) | **v2.1 (当前)** |
|------|---------|-----------|---------------|
| 视觉方向 | Editorial (经济学人 + Stripe Press) | Linear / Vercel 深色工程美学 | **Stripe 浅色风 · 与产品端 DESIGN_TOKENS.md 完全对齐** |
| 色板 | paper #F5F2EC | 深色 #0A0A0A + Linear 紫 | **页面 #FAFAFB · 卡片 #FFFFFF · 主色 #605BFF · 文字 #030229** |
| 字体 | Source Serif 4 + Noto Serif SC | Inter + JetBrains Mono | **Nunito (body/brand) + Inter (fallback) · 数字用 Nunito tabular-nums** |
| Hero 素材 | 真实 Dashboard 截图 ✅ 保留 | 真实 Dashboard 截图 (深色版) | **真实 Dashboard 截图 (浅色原版, 官网内嵌即产品即视感)** |
| 应用入口 | ❌ 未定义 | ❌ 未定义 | **✅ Nav + Hero + 底部 CTA 三处全部接 `/register` `/login` `/industry`** |
| i18n | MVP 只做 zh-CN | 全站 ZH/EN | ✅ 保留 (localStorage + cookie 双写) |

**v2.1 纠偏核心** (Frank 2026-04-17 反馈):
1. **"设计风格和 app 的不搭"** → 放弃自创一套深色工程风, 官网视觉消费和产品端同一套 token (`docs/DESIGN_TOKENS.md`), 用户从官网跳到 `/register` → `/dashboard` 无视觉断层。
2. **"没有到应用端的入口"** → Nav 右上角 + Hero 主 CTA + 底部 CTA + Footer 四处明确接 `/register` `/login` `/industry` 真实路由, 不再用 `#cta` 锚点当入口占位。

v1/v2.0 的**信息骨架继续保留** (Hero / Problem / PANO Method / Product Slices / Industries / Voices / For Agents / Footer), 也保留 i18n 层; 只换视觉皮 + 接入口。

---

## 1. 视觉语言 · Stripe 浅色 (与产品端完全对齐)

### 1.1 为什么是这个方向

**v2.1 的第一性原理**: 官网不是独立的营销物, 而是用户进入产品前看到的"封面"。如果 Landing 是深色工程风, 点击 "查看分数" 进入 `/register` 再进 `/dashboard` 瞬间变成浅色 Stripe 风, 用户体感是"两个不同的产品"——这是 Frank 2026-04-17 反馈的核心问题。

所以本版**不发明新的视觉语言**, 直接消费产品端已经在用的 `docs/DESIGN_TOKENS.md`:
- 主品牌色 `#605BFF` (Figma primary purple, 产品 sidebar/按钮/图表主色)
- 文字 `#030229` (Figma deep navy)
- 页面底 `#FAFAFB` + 卡片 `#FFFFFF`
- 字体 Nunito (产品已用)
- 圆角 Card 12px / Button 6-8px / Banner 24px
- Shadow 轻量 `0 1px 3px rgba(0,0,0,0.04)` 系列
- 图表色板用 `--color-chart-1…7`

官网只是把这些 token 用在 marketing 场景里 (更大的留白、更醒目的 Hero、更密的视觉节奏), 不发明新色、新字、新圆角。

### 1.2 色板 (镜像自 DESIGN_TOKENS.md · 不新增任何 token)

```css
/* Base surfaces */
--color-bg-page:        #FAFAFB   /* 页面主画布 */
--color-bg-card:        #FFFFFF   /* 卡片 / 区块 */
--color-bg-subtle:      #FAFAFB   /* 行内弱对比容器 */
--color-bg-subtle-2:    #F4F4F4   /* selector pill */
--color-bg-badge:       #F0F0FF   /* badge 默认底 */
--color-accent-bg-light: #F0F0FF  /* 提示/洞察卡片背景 */
--color-accent-subtle:   rgba(96,91,255,0.07)

/* Text (ink) */
--color-text-primary:   #030229   /* 主标题、Hero H1 */
--color-text-secondary: #1C1D22   /* 副标题 */
--color-text-body:      #333333   /* 正文 */
--color-text-body-soft: #666666   /* 次要说明 */
--color-text-muted:     #818194   /* nav 未选中、辅助 */
--color-text-faint:     #BEC0C6   /* placeholder */
--color-text-inverse:   #FFFFFF

/* Accent */
--color-accent:         #605BFF
--color-accent-hover:   #5450E6
--color-accent-2:       #8B5CF6   /* gradient companion */
--color-accent-soft:    #ACA9FF

/* Border */
--color-border:         #D0D5DD
--color-border-card:    #F2F4F7
--color-border-subtle:  #E8E8F0
--color-border-strong:  #C1C9D2

/* Chart */
--color-chart-1:        #030229   /* 可见度 */
--color-chart-2:        #FF708B   /* 情感 */
--color-chart-3:        #3B82F6   /* SoV */
--color-chart-4:        #1E3A8A   /* 引用率 */
--color-chart-5:        #605BFF   /* 强调/主题 */
--color-chart-6:        #FDB022   /* 警告 */
--color-chart-7:        #0ABB87   /* 成功 */

/* Semantic */
--color-success: #0ABB87
--color-warning: #F5A623
--color-danger:  #DB373F
```

**禁止** (v2.1):
- v2.0 深色版所有 token (`#0A0A0A` / `#EDEDED` / Linear 紫 `#5E6AD2` 等) 全部清出
- 任何不在 `DESIGN_TOKENS.md` 表里的 hex 值; 新颜色必须先加进 DESIGN_TOKENS 再用
- radial-gradient 背景 blob (v1/v2 都禁, 继续禁)
- 多色线性渐变; 只允许 `#605BFF → #8B5CF6` 这一条唯一品牌渐变 (对应产品 Logo / Share preview), 仅用于 Logo 容器 + Hero gradient-text 的一个词

### 1.3 排版 (与产品 DESIGN_TOKENS.md 对齐)

产品端字体栈: `Nunito → Inter → Microsoft YaHei / Noto Sans SC → system sans`。官网沿用同一栈, 不引入新字体 (不要 Geist / JetBrains Mono)。

| 用途 | Class / 规则 | 说明 |
|------|-------------|------|
| Hero H1 | 自定义 · Nunito 700 | `font-size: clamp(40px, 5.5vw, 64px), line-height: 1.08, letter-spacing: -0.02em`。对应产品 `text-display-1` (3rem) 的放大版, 本版在 Hero 处手动上限到 64px |
| Section H2 | `text-display-2` · Nunito 700 | `2.25rem / 36px` 产品已定义, 直接用 |
| Section H3 / 卡片标题 | `text-heading-2` · Nunito 600 | `1.25rem / 20px` |
| Subtitle | 自定义 · Nunito 400 | `font-size: 17-18px, line-height: 1.65, color: text-body-soft (#666)` |
| Body | `text-body` · Nunito 400 | `1rem / 16px, color: text-body (#333)` |
| Nav / Button | Nunito 500 | `14px, color: text-muted (#818194)` 未激活, `text-primary (#030229)` hover |
| Small-caps label | Nunito 600 | `font-size: 11px, letter-spacing: 0.08em, UPPERCASE, color: accent (#605BFF)` |
| 数字 (KPI / Hero mock) | Nunito 700 · tabular-nums | 产品已定义 `text-data-xl` `text-data-lg`, 直接用; 不引入 JetBrains Mono, 这是与 app 保持一致的关键 |

**禁止**:
- v2.0 引入的 Inter 700 / Geist / JetBrains Mono 全部清出
- 产品端已统一数字用 Nunito tabular-nums, **官网不能单独为"工程感"再引入 mono 字体**
- 不同页面/区块字体不一致

**gradient text 规则** (限一个词, 用产品品牌渐变):

```css
background: linear-gradient(135deg, #605BFF 0%, #8B5CF6 100%);
-webkit-background-clip: text;
background-clip: text;
-webkit-text-fill-color: transparent;
```

Hero 主标题里**最多一个词**用该渐变 (e.g. "AI 正在成为新的**搜索入口**" 中的 "搜索入口")。整行渐变 = Framer AI 站模板感, 禁。

### 1.4 形状 / 间距 (镜像 DESIGN_TOKENS.md)

- **圆角** (严格按产品 token, 不发明新值):
  - Input: 6px (`--radius-input`)
  - Button: 6px (`--radius-btn`) / 8px (`--radius-btn-lg`, 语言切换器等)
  - Badge: 6px (`--radius-badge`)
  - Card 标准: 12px (`--radius-card`)
  - Card 大号 (Hero Dashboard mock 外框 / Bento): 16px (`--radius-card-lg`)
  - Banner (CTA 大横幅): 24px (`--radius-banner`)
  - Pill (tag/chip): 9999px (`--radius-pill`)

- **Border**: `1px solid var(--color-border-card)` (`#F2F4F7`) 作为卡片主分隔, hover 升到 `var(--color-border)` (`#D0D5DD`)
- **Shadow** (产品 token, 不新增):
  - 卡片静态 `shadow-card`: `0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.03)`
  - 卡片悬停 `shadow-card-hover`: `0 8px 24px rgba(50,50,93,0.08)...`
  - Hero Dashboard mock 用 `shadow-elevated`: `0 25px 50px rgba(50,50,93,0.25)`, 强调"这就是 app"
- **Container**: max-width 1200px, px-6 (mobile) → px-10 (desktop)
- **Section padding**: 96px vertical (Hero 112-120px)
- **Grid**: 12-col, gutter 24-32px

### 1.5 动效 (subtle, 与产品端一致)

- 按钮 hover: `transition: background 150ms ease, box-shadow 150ms ease`; primary 从 `#605BFF` → `#5450E6` (产品 accent-hover), shadow 从 `shadow-btn` 升到 `shadow-card`
- 链接 hover: 颜色从 `text-muted` → `text-primary`, 不加 underline (产品端 nav 也不用 underline, 保持一致)
- Arrow 图标 translateX 3px on hover
- Hero Dashboard mock 初始有 `shadow-elevated` + 极轻 `rgba(96,91,255,0.05)` accent ambient, 鼠标悬停略加强
- Nav sticky on scroll: 从透明 → `rgba(255,255,255,0.85) backdrop-blur(12px)` + `border-bottom: 1px solid var(--color-border-card)`
- **禁止**: scroll-jack、parallax、粒子、3D 旋转卡、cursor-follow。这些是"Framer 模板感"指纹

### 1.6 背景装饰 (极克制)

与 v2.0 深色版不同, 浅色底本身足够"亮", 不需要 glow 来"让背景有生气"。所以本版**比深色版更克制**:

- **不加** radial-gradient blob (产品内部也没有, 官网更不应该)
- **允许** Hero + CTA 区块用 **极弱 dot pattern 底纹** (比 grid 更 Stripe):

```css
background-image: radial-gradient(rgba(96,91,255,0.05) 1px, transparent 1px);
background-size: 24px 24px;
```

Hero 区块可以在右侧 screenshot 后方加一个 **品牌渐变柔光环** (而非 blob), 用 `--color-accent-subtle` 的 blur 效果, 让 dashboard mock "浮"起来一点, 但强度要远低于 v2.0 版:

```css
position: absolute; inset: -40px;
background: linear-gradient(135deg, rgba(96,91,255,0.10), rgba(139,92,246,0.06));
filter: blur(60px);
border-radius: 24px;
z-index: -1;
```

---

## 2. 信息架构 (与 v1 相同, 视觉换皮)

顺序不变：

1. **Masthead + Nav**（深色 sticky nav + logo + 链接 + 语言切换 + CTA）
2. **Hero**（Headline + subhead + CTA + 真 Dashboard 截图）
3. **Section II · Problem**（为什么 Semrush/Ahrefs 看不到 AI 回答）
4. **Section III · Method**（PANO 公式 + 5 维度定义）
5. **Section IV · Product**（3 个真实产品切片）
6. **Section V · Industries**（4 行业 + 覆盖数据表）
7. **Section VI · Voices**（真实 Query 样本, 取代虚构 testimonial）
8. **Section VII · For Agents**（MCP 代码片段）
9. **CTA + Footer**

---

## 3. i18n 规范 (新增章节, 两侧契约)

### 3.1 Locale codes

- `zh-CN` · 简体中文 (default for 中文系浏览器)
- `en-US` · English (default for 非中文浏览器)

### 3.2 持久化契约 (⚠️ 官网 + 产品共享)

| 存储位置 | Key | 值 | 作用范围 |
|---------|-----|---|---------|
| `localStorage` | `genpano_locale` | `zh-CN` \| `en-US` | 跨 tab, 主要持久化 |
| `cookie` | `genpano_locale` | `zh-CN` \| `en-US` | SSR 可读, `domain=.genpano.com`, `max-age=31536000` (1 year), `path=/`, `SameSite=Lax` |

**读取顺序** (按优先级)：

1. URL query param `?locale=xx` (只用于分享/debug, 不写持久化)
2. `localStorage.genpano_locale` (客户端)
3. `cookie.genpano_locale` (SSR 首次渲染)
4. `navigator.language` 浏览器语言 (首次访问, `zh*` → `zh-CN`, 其他 → `en-US`)
5. 兜底 `zh-CN`

**写入**: 用户点击语言切换按钮时, 同时写 localStorage + cookie, 然后 `location.reload()` 让 SSR 用新 locale 重新渲染。

### 3.3 语言切换器 UX

**官网版本**:

```
[ZH · EN]   ← 右上角 nav, 当前语言高亮, 另一个灰
```

- 位置: masthead 的 navbar 右侧, CTA 按钮**左边**
- 样式: inline text, 两个语言用 `·` 分隔, 当前 `color: var(--fg)` + font-weight 600, 非当前 `color: var(--fg-muted)` + 500, hover `color: var(--fg-soft)`
- 点击行为: 切换到另一语言, 写入 storage, reload

**产品版本** (契约, 本 Session 不实施):

- 位置: 产品右上角头像 dropdown 中一条 `语言 / Language`, 子菜单 `简体中文 · English`
- 读取同一个 `genpano_locale`
- 下一 Session 在 `DashboardLayout.jsx` 的 user dropdown 中接入

### 3.4 官网文案 i18n 存储

实施到 React 时, 新建:

```
frontend/src/messages/
  zh-CN/
    landing.json       ← 本 Session 所有官网文本
  en-US/
    landing.json
```

每个 key 遵循嵌套路径, 如:

```json
{
  "cover": {
    "eyebrow": "COVER",
    "h1": { "line1": "AI 正在成为", "line2": "新的搜索入口", "line3": "你的品牌在那里吗？" },
    "subtitle": "每一天, 数百万条...",
    "meta": "免费 · 3 引擎 · 4 行业",
    "ctaPrimary": "查看我的品牌分数",
    "ctaSecondary": "方法论 →"
  }
}
```

英文版本参考 §5.2。

### 3.5 字体切换 (subtle)

- `zh-CN`: Inter + Noto Sans SC (默认 fallback 栈)
- `en-US`: 可以只用 Inter (或 Inter + Geist)

不需要中英切换时重载字体——一个 stack 全管:

```css
font-family: 'Inter', 'Noto Sans SC', system-ui, sans-serif;
```

### 3.6 SEO / hreflang

两份 URL 与 hreflang 规则（下一 Session 实施到 Next.js 路由）:

- `https://genpano.com/` → 按 locale 自动
- `https://genpano.com/en` → 英文版固定入口（供分享）
- `https://genpano.com/zh` → 中文版固定入口

`<head>` 加:

```html
<link rel="alternate" hreflang="zh-CN" href="https://genpano.com/zh" />
<link rel="alternate" hreflang="en-US" href="https://genpano.com/en" />
<link rel="alternate" hreflang="x-default" href="https://genpano.com/" />
```

### 3.7 HTML 原型的 i18n 实现

单文件原型用最简单的方式演示:

- 所有双语文本节点加 `data-zh="..."` `data-en="..."` 两个 attr
- JS 在页面加载时读 `localStorage.genpano_locale` 或浏览器语言, 调用 `applyLocale(lang)` 把所有 `[data-zh][data-en]` 的 textContent 换掉
- 切换器点击时 `applyLocale('en-US')` + 写 localStorage + 更新按钮高亮

这只是原型模拟. 真实 React 实现用 next-intl `useTranslations('landing')`, 不是 DOM 改写.

---

## 4. Section-by-Section 规格 (Stripe 浅色版 · v2.1)

> **⚠️ 开发者约束 (不作为 UI 文案)**: 本节所有"本页做/不做 X"、"详情请进入 Y"类措辞仅用于指导实施, 严禁以 i18n key / JSX 文本节点 / PDF 文案形式呈现给最终用户。详见项目 CLAUDE.md "UI vs Prompt 指引边界"。

### 4.1 Masthead + Nav

结构:

```
[G GENPANO]   产品  方法论  行业  开发者      [ZH · EN]  [登录]  [免费查看分数 →]
```

- **Logo**: 20×20px 方块 + 文字 "GENPANO"
  - 方块用 `linear-gradient(135deg, #605BFF 0%, #8B5CF6 100%)` + `border-radius: 6px`, 内嵌白色小三角或 "G" 字母 (Nunito 700)
  - 文字 "GENPANO" 用 Nunito 700, 15px, `color: var(--color-text-primary)`, `letter-spacing: -0.01em`
- **Nav 链接**: Nunito 500, 14px, `color: var(--color-text-muted) #818194`; hover `color: var(--color-text-primary) #030229`, 无 underline (与产品端 DashboardLayout.jsx sidebar 一致)
- **语言切换**: 见 §3.3, 样式用 Nunito 500, 13px, 当前语言 `color: var(--color-text-primary)` + 600, 非当前 `color: var(--color-text-muted)` + 500
- **登录链接** (新增 v2.1): Nunito 500, 14px, `color: var(--color-text-body-soft)`, hover `color: var(--color-text-primary)`, `href="/login"`, 放在 CTA 按钮左边
- **CTA 按钮** (主要入口 → `/register`):
  - 背景 `var(--color-accent) #605BFF`, 文字 `var(--color-text-inverse) #FFFFFF`
  - Radius 6px (`--radius-btn`), padding 10px 18px
  - Font: Nunito 600, 14px
  - Shadow: `var(--shadow-btn)` · hover: `var(--shadow-card)` + `background: var(--color-accent-hover) #5450E6`
  - 右侧 arrow icon `→` hover translateX(3px) 150ms

**Sticky 行为**: scroll > 40px 时
- `background: rgba(255, 255, 255, 0.85)` + `backdrop-filter: blur(12px)`
- `border-bottom: 1px solid var(--color-border-card)`

非 sticky 时完全透明。

### 4.2 Hero

**Layout**: 12-col, 7/5 split (text/screenshot), vertical padding 112px top / 80px bottom.

**Background**:
- `var(--color-bg-page) #FAFAFB` 底
- 极弱 dot pattern (§1.6): `radial-gradient(rgba(96,91,255,0.05) 1px, transparent 1px); background-size: 24px 24px`
- Hero 右侧 screenshot 后方一个 brand-gradient 柔光环 (§1.6), 强度很低

**文字侧 (左 7 列)**:

- **Eyebrow**: Nunito 600, 11px, `letter-spacing: 0.08em`, UPPERCASE, `color: var(--color-accent) #605BFF`
  - ZH: `免费监测`; EN: `FREE GEO MONITORING`
- **H1**: Nunito 700, `clamp(40px, 5.5vw, 64px)`, `line-height: 1.08`, `letter-spacing: -0.02em`, `color: var(--color-text-primary) #030229`
  - 3 行结构保留; 仅 "搜索入口" 一词用品牌渐变 (§1.3)

- **Subtitle**: Nunito 400, 17-18px, `line-height: 1.65`, `color: var(--color-text-body-soft) #666666`, `max-width: 520px`

- **Meta line**: Nunito 500, 13px, `color: var(--color-text-muted) #818194`
  - 用 `·` 分隔, 无 smallcaps (浅色版更 Stripe, 不需要强 typographic treatment)

- **CTA 组** (3 个入口, 从上到下视觉权重递减):
  1. **Primary** → `/register`: `var(--color-accent) #605BFF` 底 + 白字, radius 6px, padding 14px 22px, Nunito 600 15px, `var(--shadow-btn)`, 右 arrow
  2. **Secondary** → `/industry`: `var(--color-bg-card) #FFFFFF` 底 + `1px solid var(--color-border) #D0D5DD` + `color: var(--color-text-primary)`, radius 6px, 同 padding, `var(--shadow-btn)`
     - ZH: `先探索行业数据 →`; EN: `Explore industry data →`
     - 这是"未注册友好"入口, 未登录用户直接进 `/industry` 看 4 个行业真实数据
  3. **Tertiary** (text link) → `/login`: Nunito 500, 14px, `color: var(--color-text-body-soft)`, hover `color: var(--color-accent)`
     - ZH: `已有账号？登录 →`; EN: `Have an account? Log in →`
     - 放在主副 CTA 下方 16px, 同一行文字链接, 不抢视觉权重

**Screenshot 侧 (右 5 列)**:

- **真实 Dashboard 截图** (浅色原版, Playwright 截 `DashboardPage.jsx` 默认状态):
  - PANO 78 Hero + 5 KPI (提及率/SoV/情感/引用/排名) + 趋势 + SoV 饼图 + 竞品列表
  - 所有颜色用产品当前 token, **不加暗色滤镜**——用户看到的截图 = 注册后 `/dashboard` 完全一致
- **外框**:
  - `border-radius: 16px` (`--radius-card-lg`)
  - `border: 1px solid var(--color-border-card) #F2F4F7`
  - `box-shadow: var(--shadow-elevated)` (产品已定义) 让 dashboard 有"浮"感
  - 背后一层 brand-gradient 柔光 (§1.6, 强度低)
- 截图下方**不加**机器感 meta line (`DEMO · DIOR WOMEN · APR 2026` 这种 mono 风的字幕是 v2.0 Dark-Eng 残留), 保持简洁

### 4.3 Section II · Problem

Background: `var(--color-bg-card) #FFFFFF` (和 Hero 的 `#FAFAFB` 形成 1 档节奏对比)

- Eyebrow: Nunito 600, 11px, 大写, accent 色
  - ZH: `问题`; EN: `THE PROBLEM`
- H2: `text-display-2` (Nunito 700, 36px, `color: var(--color-text-primary)`)
- 两栏 6/6:
  - **左**: 3 段正文, Nunito 400, 16px, `line-height: 1.7`, `color: var(--color-text-body)`
  - **右**: 两个并排 comparison card (或堆叠), 每卡 `background: var(--color-bg-subtle) #FAFAFB` + `border: 1px solid var(--color-border-card)` + `border-radius: 12px` (`--radius-card`) + padding 24px
    - **Card A · 传统 SERP**: 5 行"mock 搜索结果行", 每行 `background: #FFFFFF` + 1px border, 标题蓝 `var(--color-chart-3) #3B82F6`, URL `color: var(--color-success)`, 模拟 Google/Baidu 外观
    - **Card B · AI 回答**: 一整段自然语言 paragraph, Nunito 400 15px · line-height 1.7; 品牌名用 `background: var(--color-accent-subtle) rgba(96,91,255,0.07); color: var(--color-accent); padding: 1px 6px; border-radius: 4px`, 表示"被 AI 点名"
    - 底部 1 行 caption (Nunito 500 12px `color: var(--color-text-muted)`): Card A "传统工具看得到"; Card B "只有 GENPANO 看得到"

### 4.4 Section III · Method (PANO Formula)

Background: `var(--color-bg-page) #FAFAFB`

- Eyebrow: `方法论` / `METHOD`
- H2: `text-display-2` ·
  - ZH: `PANO Score · 5 个维度, 一个分数。`
  - EN: `PANO Score · 5 dimensions, one number.`
- Subtitle: Nunito 400 17px, `color: var(--color-text-body-soft)`, max-width 640px
  - ZH: `我们拒绝黑箱。下面是完整公式。`
  - EN: `No black box. Here is the complete formula.`

**公式卡** (max-width 900px, 居中):

- `background: var(--color-bg-card) #FFFFFF`
- `border: 1px solid var(--color-border-card)`
- `border-radius: 16px` (`--radius-card-lg`)
- `box-shadow: var(--shadow-card)`
- padding 40px
- 公式一行 (居中): Nunito 600, 22-26px, `color: var(--color-text-primary)`
  ```
  PANO = w₁·提及率 + w₂·SoV + w₃·情感 + w₄·引用份额 + w₅·排名
  ```
- `w₁` 等权重系数: `color: var(--color-accent) #605BFF` + Nunito 700; 运算符用 `color: var(--color-text-muted)`

**5 维度卡** (5 列 grid, `grid-cols-5` desktop / `grid-cols-2` mobile, gap 16px):

每卡:
- `background: var(--color-bg-card) #FFFFFF`
- `border: 1px solid var(--color-border-card)`
- `border-radius: 12px` (`--radius-card`)
- `box-shadow: var(--shadow-card)` · hover `var(--shadow-card-hover)` + `border-color: var(--color-border)`
- padding 20px 22px
- 结构 (从上到下):
  1. 名称 Nunito 600, 13px, `color: var(--color-text-body-soft)` (不全大写, 产品内部也不全大写)
  2. 真实数字 Nunito 700, 32px tabular-nums, `color: var(--color-text-primary)`
  3. 进度条 3px 高, bg `var(--color-border-card)`, fill `var(--color-accent)` 用对应维度的 chart 色 (chart-1/2/3/4/5)
  4. 简短解释 Nunito 400, 13px, `color: var(--color-text-body-soft)`, 2 行内

| 维度 | 示例数字 | fill 色 |
|------|-------|------|
| 提及率 | 16.2% | `--color-chart-1 #030229` |
| SoV | 22.4% | `--color-chart-3 #3B82F6` |
| 情感 | 0.79 | `--color-chart-2 #FF708B` |
| 引用份额 | 8.1% | `--color-chart-4 #1E3A8A` |
| 行业排名 | #2 | `--color-chart-5 #605BFF` |

下方 caveat 段落 (max-width 800px, Nunito 400 14px, `color: var(--color-text-body-soft)`):

> 早期版本有 9 个维度, 我们在 120 个品牌 × 30 天数据上做了相关性测试, 把相关性 > 0.85 的合并——最终留下 5 个正交指标。加更多不会更准, 只会更难解释。

### 4.5 Section IV · Product (Bento grid)

Background: `var(--color-bg-card) #FFFFFF`

- Eyebrow: `产品` / `PRODUCT`
- H2:
  - ZH: `在 Dashboard 里能看到什么。`
  - EN: `What you'll see inside the dashboard.`

**Bento 4 格** (2×2 grid, gap 20px):

结构不变, 只换视觉到浅色:

| cell | span | 标题 | 配图 |
|------|------|------|------|
| BIG-1 | 2 col | 面板 · 我 vs 竞品 vs 行业 | 面板 mini 截图 (PANO + 5 KPI + SoV 饼) |
| SMALL-1 | 1 col | 品牌详情 · PanoRing | PanoRing mini (产品 PanoRing 组件缩略) |
| SMALL-2 | 1 col | Topics 下钻 | 表格缩略 (Topic → Prompt → Query 3 层) |
| BIG-2 | 2 col | 引擎对比 | 3 引擎并排 sparkline |

每 bento cell:
- `background: var(--color-bg-card) #FFFFFF`
- `border: 1px solid var(--color-border-card)`
- `border-radius: 16px` (`--radius-card-lg`)
- `box-shadow: var(--shadow-card)` · hover `var(--shadow-card-hover)`, `transform: translateY(-2px)`, 150ms ease
- padding 28px
- 顶部 eyebrow Nunito 600, 11px, `color: var(--color-accent)` (e.g. `DASHBOARD`)
- 中间标题 Nunito 700, 22px, `color: var(--color-text-primary)`, 1-2 行
- 下方描述 Nunito 400, 14px, `color: var(--color-text-body-soft)`, 2-3 行
- 底部 product visual (使用产品端同色 token + `--color-chart-*`)

### 4.6 Section V · Industries

Background: `var(--color-bg-page) #FAFAFB`

- Eyebrow: `覆盖` / `COVERAGE`
- H2:
  - ZH: `4 个行业, 380 个品牌, 从 Day 1 就在。`
  - EN: `4 industries, 380 brands, live from day one.`

表格保留 v1 4 行结构 (美妆个护 / 奢侈品 / 食品饮料 / 服装时尚), 浅色:

- 外框: `background: var(--color-bg-card) #FFFFFF` + `border: 1px solid var(--color-border-card)` + `border-radius: 12px`, overflow hidden
- **表头**: `background: var(--color-bg-subtle) #FAFAFB`, `border-bottom: 1px solid var(--color-border-card)`, Nunito 600 12px, `color: var(--color-text-muted)`, `letter-spacing: 0.04em`, UPPERCASE
- **数据行**: `border-bottom: 1px solid var(--color-border-card)` (最后一行无), padding 14px 20px; hover `background: var(--color-bg-subtle)`
- 行业名: Nunito 600, 16px, `color: var(--color-text-primary)`
- 数字列: Nunito 500, 14px, **tabular-nums** (产品同款), `color: var(--color-text-body)` — **禁用 JetBrains Mono 或任何 mono 字体**, 保持与产品一致
- 可选: 每行最右加一个 "查看 →" 链接 → `/industry?category=<slug>`, Nunito 500 13px, accent 色

### 4.7 Section VI · Voices

Background: `var(--color-bg-card) #FFFFFF` (再切回白, 节奏对比)

- Eyebrow: `声音` / `VOICES`
- H2:
  - ZH: `人们正在问 AI 关于品牌的什么。`
  - EN: `What people are asking AI about brands.`
- Subtitle: 同 v1

每张 Query 卡 (3-4 张, grid 或 masonry):
- `background: var(--color-bg-subtle) #FAFAFB`
- `border: 1px solid var(--color-border-card)`
- `border-radius: 12px`
- padding 28px
- `box-shadow: var(--shadow-card)`; hover `var(--shadow-card-hover)`
- 结构:
  1. `QUERY` label: Nunito 600, 11px UPPERCASE, `color: var(--color-text-muted)`
  2. Query text: Nunito 500, 18px, `color: var(--color-text-primary)`, `line-height: 1.5`
  3. Source meta: Nunito 500, 12px, `color: var(--color-text-muted)` (e.g. `ChatGPT · 2026-04-14 · zh-CN`)
  4. **回答节选 block**: `background: var(--color-bg-card) #FFFFFF` + `border-left: 3px solid var(--color-accent)` + padding 16px 20px + Nunito 400 15px + `line-height: 1.7` + radius 8px
  5. **品牌 hit chip** (行内): `background: var(--color-accent-subtle)` + `color: var(--color-accent)` + `border-radius: 4px` + padding 2px 8px + Nunito 600 13px — **无 border** (产品 badge 都无 border, 保持一致)

### 4.8 Section VII · For Agents

Background: `var(--color-bg-page) #FAFAFB`

- Eyebrow: `开发者` / `FOR AGENTS`
- H2:
  - ZH: `GENPANO 也是 Agent 的数据源。`
  - EN: `GENPANO is also a data source for agents.`

两栏 5/7:

- **左 5 列** (文字 + CTA):
  - subtitle Nunito 400, 17px, `color: var(--color-text-body-soft)`
  - CTA: `查看 MCP 接入文档 →` · 白底 + 1px border + accent 文字 + radius 6px
    - EN: `See MCP docs →`

- **右 7 列** (**Code block**, 产品风 code card, **非终端黑底**):
  - 外框:
    - `background: var(--color-bg-card) #FFFFFF`
    - `border: 1px solid var(--color-border-card)`
    - `border-radius: 12px`
    - `box-shadow: var(--shadow-card)`
  - **顶部 file header 条**:
    - `background: var(--color-bg-subtle) #FAFAFB`
    - `border-bottom: 1px solid var(--color-border-card)`
    - padding 10px 16px
    - 左: 一个小文件图标 (lucide `file-code`) + 文件名 `genpano-mcp.ts` (Nunito 500 13px, `color: var(--color-text-body)`) — **不要 macOS 3 圆点** (v2.0 终端 chrome 残留, 与产品浅色语言不搭)
    - 右: "复制" 图标按钮 (lucide `copy`, 16px, hover 高亮)
  - **代码区**:
    - padding 20px 24px
    - 字体: **Nunito 500, 13px, tabular-nums** (不再引入 JetBrains Mono——与产品所有数字/代码保持统一字体栈; Nunito 在等宽数字模式下已足够代码阅读)
      - 例外: 如真的需要 mono 风, 可允许 `font-family: 'Nunito', ui-monospace, monospace` fallback, 但主字体必须 Nunito
    - **Syntax 配色 (GitHub Light 风, 消费产品 chart tokens)**:
      - keywords `color: var(--color-accent) #605BFF` (e.g. `const`, `async`, `function`)
      - strings `color: var(--color-success) #0ABB87`
      - comments `color: var(--color-text-muted) #818194` + italic
      - function name `color: var(--color-chart-3) #3B82F6`
      - numbers `color: var(--color-warning) #F5A623`

### 4.9 Final CTA (section 8)

Background: 整个 section `var(--color-bg-card) #FFFFFF` 底, 中间放一个 banner:

**Banner 卡** (max-width 1100px, 居中):
- `background: linear-gradient(135deg, rgba(96,91,255,0.06) 0%, rgba(139,92,246,0.03) 100%)` + `var(--color-bg-card)` 混合, 整体非常淡的品牌渐变底
- `border: 1px solid var(--color-border-card)`
- `border-radius: 24px` (`--radius-banner`)
- padding 56px 64px
- `box-shadow: var(--shadow-card)`

内容居中:
- H2 大字 (`text-display-2` 或更大, 40-44px):
  - ZH: `注册一个邮箱, 就能看到你品牌的分数。`
  - EN: `One email. See your brand's score.`
- Subtitle Nunito 400, 17px, `color: var(--color-text-body-soft)`, max-width 620px
  - ZH: `我们不问信用卡, 不弹窗问需求——数据已经在了。`
  - EN: `No credit card, no sales calls. The data is already there.`
- **CTA 组** (水平并排, 移动端堆叠):
  - Primary → `/register`: 同 Hero primary
  - Secondary → `/industry`: 同 Hero secondary
    - ZH: `先探索行业数据`; EN: `Explore industries first`

### 4.10 Footer

- Background: `var(--color-bg-card) #FFFFFF`
- 顶部 `border-top: 1px solid var(--color-border-card)`
- padding 64px 0 40px
- **4 列 links** (`grid-cols-4` desktop, `grid-cols-2` mobile, gap 40px):

| 列 | 标题 | 链接 |
|---|------|------|
| 产品 Product | `产品` / `Product` | 面板 → `/register`, 行业 → `/industry`, 方法论 → `#method`, 引擎对比 → `/register` |
| 开发者 Developers | `开发者` / `Developers` | MCP Server, API, 快速开始, GitHub |
| 公司 Company | `公司` / `Company` | 关于, 博客, 联系 |
| 社群 Follow | `社群` / `Follow` | 小红书, Twitter/X, GitHub, 邮件订阅 |

- 列标题: Nunito 600, 13px UPPERCASE letter-spacing 0.06em, `color: var(--color-text-primary)`
- 列链接: Nunito 500, 14px, `color: var(--color-text-body-soft)`, hover `color: var(--color-text-primary)`

- **底部 colophon + 版权一行** (border-top 分隔):
  - 左: Logo + 版权 (Nunito 500, 12px, `color: var(--color-text-muted)`) · "© 2026 GENPANO. 免费工具, 数据说话."
  - 右: 一行 meta (Nunito 400, 12px, `color: var(--color-text-muted)`) · "Built by Frank, Shanghai · 数据每日更新"

### 4.11 应用入口映射 (App Entrance Mapping) — v2.1 新增

> 官网的每一个 CTA / 链接 **必须**直接指向产品端的真实路由, **不得**用 `#cta` 或 `#` 占位。这是 v2.1 对 v2.0 的核心修正之一。

| # | 位置 | 元素 | 文案 (ZH / EN) | 目标路由 | 备注 |
|---|------|------|---------------|---------|------|
| 1 | Nav 右上角 | Primary CTA 按钮 | `免费查看分数 →` / `See your score →` | `/register` | 主转化入口, 全站出现次数最多 |
| 2 | Nav 右上角 | text link | `登录` / `Log in` | `/login` | 已注册用户回流 |
| 3 | Nav 右上角 | `ZH · EN` 切换 | — | 当前页 (reload w/ new locale) | 不跳路由, 触发 i18n 切换 |
| 4 | Hero | Primary CTA | `查看你品牌的分数` / `See your brand's score` | `/register` | 默认带 `?from=landing_hero` UTM 便于分析 |
| 5 | Hero | Secondary CTA | `先探索行业数据 →` / `Explore industry data →` | `/industry` | **未登录友好**, 降低注册前置门槛; `/industry` 必须支持未登录浏览 (PRD §4.1.1b) |
| 6 | Hero | Tertiary text link | `已有账号？登录 →` / `Have an account? Log in →` | `/login` | 视觉权重最低, 避免与 Primary 争夺 |
| 7 | Method (§4.4) | 无 CTA | — | — | Method 本身不放 CTA, 公式本身就是信任锚 |
| 8 | Product Bento (§4.5) | 每 cell 可选 hover 外链 | — | `/dashboard` (需登录) 或 `/register` (未登录) | 通过前端 auth guard 自动路由 |
| 9 | Industries (§4.6) | 每行 "查看 →" | — | `/industry?category=<slug>` | 可选, 不作为主转化 |
| 10 | Voices (§4.7) | 无 CTA | — | — | 纯内容 section |
| 11 | For Agents (§4.8) | CTA | `查看 MCP 接入文档 →` / `See MCP docs →` | `/docs/mcp` (下一 Session 落地) 或临时 `/register?focus=mcp` | MCP 文档页未上线前先指 register |
| 12 | Final CTA (§4.9) | Primary | `免费开始` / `Start free` | `/register` | 带 `?from=landing_final` UTM |
| 13 | Final CTA (§4.9) | Secondary | `先探索行业数据` / `Explore industries first` | `/industry` | 同 Hero Secondary |
| 14 | Footer (§4.10) | 产品列各链接 | — | 各自真实路由, 见 §4.10 表格 | 无登录要求的进 `/industry`; 需登录的进 `/register` |

**所有 `/register` 链接**建议在 React 实施时带上 UTM query, 便于在 Mixpanel (PRD §4.11) 区分不同 CTA 的转化率:

```tsx
<Link href="/register?from=landing_hero" ...>查看你品牌的分数 →</Link>
<Link href="/register?from=landing_final" ...>免费开始</Link>
<Link href="/register?from=nav" ...>免费查看分数 →</Link>
```

**埋点事件** (沿用 PRD §4.11 已定义事件, 本 Session 不新增):
- Nav CTA 点击: `landing_cta_click` with `{ placement: 'nav', target: 'register' }`
- Hero 任一 CTA: `landing_cta_click` with placement 区分 `hero_primary` / `hero_secondary` / `hero_tertiary`
- Final CTA: `landing_cta_click` with placement `final_primary` / `final_secondary`
- 语言切换: `landing_locale_switch` with `{ from: 'zh-CN', to: 'en-US' }`
- 不写 PII, 不写公司名/邮箱 (PRD §4.11.5 红线)

---

## 5. 文案 (中英双语, 全量)

### 5.1 ZH 主文案 (选摘, 完整版写在 messages/zh-CN/landing.json)

- Cover H1: `AI 正在成为 / 新的搜索入口。 / 你的品牌在那里吗？`
- Cover subtitle: 同 v1
- Cover meta: `免费 · 3 个引擎 · 4 个行业 · 注册即开通`
- CTA primary: `查看你品牌的分数`
- CTA secondary: `方法论 →`
- Nav: `产品 · 方法论 · 行业覆盖 · 开发者`
- Problem H2: `为什么传统工具看不到 AI 回答里发生的事。`
- Method H2: `PANO Score · 5 个维度，一个分数。`
- Industries H2: `4 个行业，380 个品牌，从 Day 1 就在。`
- Voices H2: `人们正在问 AI 关于品牌的什么。`
- Agents H2: `GENPANO 也是 Agent 的数据源。`
- Final CTA: `注册一个邮箱, 就能看到你品牌的分数。`

### 5.2 EN 主文案

- Cover H1: `AI is becoming / the new search / front door. / Is your brand there?`
- Cover subtitle: `Millions of brand-related queries happen every day inside ChatGPT, Doubao, and DeepSeek—and brands themselves rarely see any of it. GENPANO makes that space observable.`
- Cover meta: `Free · 3 engines · 4 industries · Instant access after signup`
- CTA primary: `See your brand's score`
- CTA secondary: `How we measure →`
- Nav: `Product · Method · Industries · For Agents`
- Problem H2: `Why traditional SEO tools can't see what happens inside AI answers.`
- Method H2: `PANO Score · 5 dimensions, one number.`
- Industries H2: `4 industries, 380 brands, live from day one.`
- Voices H2: `What people are asking AI about brands.`
- Agents H2: `GENPANO is also a data source for agents.`
- Final CTA: `One email. See your brand's score.`

### 5.3 Tone 对照

| 维度 | ZH | EN |
|------|-----|-----|
| 句长 | 中等, 偶尔长句 | 略短, 更多断句 |
| 口吻 | 冷静工程化, 不卖弄 | Cool, understated, Linear-style "we just built this" |
| 禁用 | 全方位 / 一站式 / 赋能 / 数智化 / AI 驱动 / 解锁 | Unlock / Revolutionize / Next-generation / Powered by / Intelligent / Seamless |
| 鼓励 | 具体数字, 时间戳, "你", 技术名词 | Specific numbers, timestamps, "your", technical terms |

---

## 6. 必须清出的 v2.0 Dark-Eng 残留 (v2.1 迁移清单)

v2.1 的原型会**整个重写** (非 diff), 但 v2.0 深色版写进 React 的代码 / Tailwind config / token 表需要清出。Harness 拦截用的 grep 清单:

- [ ] 任何 `#0A0A0A` / `#050505` / `#1A1A1E` / `#26262B` 深色底 hex (整个 v2.0 的 `--bg` 家族)
- [ ] `#5E6AD2` Linear 紫 (应用端从来没用过, v2.1 只用 `#605BFF`)
- [ ] 字体: `Inter` 作为**主显示字体** (仅允许作为 fallback); `JetBrains Mono` / `JetBrains+Mono` / `font-mono` 在常规 body/KPI 场景; `Geist` / `Figtree`
- [ ] `@fontsource-variable/inter` 作为主字体 (应保留 `@fontsource/nunito` 为主)
- [ ] `@fontsource-variable/jetbrains-mono` 依赖本身 (v2.0 引入, 本版不需要)
- [ ] Hero 截图文件 `hero-dashboard-dark@2x.png` / `hero-dashboard-dark.png` (本版用浅色原版 `hero-dashboard-light@2x.png`)
- [ ] 终端 chrome (红黄绿 3 圆点 `#FF5F57 #FEBC2E #28C840`) 在任何非 code block OS chrome 场景
- [ ] Shiki 的 `github-dark` theme → 改 `github-light` / `light-plus`
- [ ] 背景中的任何 `radial-gradient` blob (v2.1 只允许 1 处 Hero 柔光环 + dot pattern)
- [ ] smallcaps 11px UPPERCASE label 过度使用 (浅色版 eyebrow 保留, 但行内 smallcaps 标签改为普通 Nunito 500)
- [ ] 任何 `href="#cta"` / `href="#register"` 锚点占位 → 全部换成 `/register` `/login` `/industry` 真实路由 (见 §4.11)
- [ ] 任何 sparkle ✨ / rocket 🚀 / lightning ⚡ icon 或 emoji (v1 留下的, 依然禁)
- [ ] 虚构 testimonial (李明 / 王芳 / Sarah K.) — 若还残留, 替换为 Voices 真实 Query 样本

> v1 (Editorial paper) 版的 `Figtree` / `#476AFF` / `paper #F5F2EC` / `Source Serif` / 60px 圆角 / browser chrome / SparkleIcon 等残留清单, 上版已列, 本版继承该禁令。

---

## 7. 技术约定 (v2.1 浅色版)

### 7.1 依赖 (遵循 CLAUDE.md §依赖规则)

**原型** (`design/prototype-landing-v2.html`):
- Tailwind: `https://cdn.tailwindcss.com`
- 字体: Google Fonts (`Nunito` 主字体, `Noto+Sans+SC` CJK fallback, `Inter` optional latin fallback) — **不引入 JetBrains Mono**
- 图表: ECharts CDN (SVG renderer)
- 图标: Lucide CDN
- **i18n**: vanilla JS (`data-zh` / `data-en` attr swap)
- **应用入口**: 每个 CTA / 文字链接 `href` 必须是真实路由 (`/register` / `/login` / `/industry`), 不得用 `#` 或 `#cta` 占位; 原型这一版用相对路径即可 (浏览 file:// 原型会跳不通, 但结构正确)

**React 实施** (Session L2):
- 字体: `@fontsource/nunito` (已在产品中使用, 复用) + `@fontsource/noto-sans-sc` — **移除** `@fontsource-variable/inter` 作为主字体依赖 + **移除** `@fontsource-variable/jetbrains-mono`
- Hero 截图: Playwright 截 `DashboardPage.jsx` **默认浅色状态** (非暗色), 存 `frontend/public/hero-dashboard-light@2x.png` (retina) + `hero-dashboard-light.png` (1x)
- Code 高亮: `shiki` with `github-light` (或 `light-plus`) theme
- i18n: `next-intl`, `messages/zh-CN/landing.json` + `messages/en-US/landing.json`
- Language switcher: 复用 §3.2 的 `genpano_locale` localStorage + cookie 契约 (`frontend/src/lib/locale.ts` 新建)
- CTA 组件: 复用 `frontend/src/components/` 下现有 Button 组件 (若无, 扩展 `ui/button`), **不 fork 新 LandingButton 组件**——与产品端完全同一 Button 保证视觉一致

### 7.2 无障碍 (WCAG AA, 浅色底)

在 `#FAFAFB` / `#FFFFFF` 浅色底上的文字对比度:

- `#030229` (primary) on `#FFFFFF` = 18.7 ✅ AAA
- `#333333` (body) on `#FFFFFF` = 12.6 ✅ AAA
- `#666666` (body-soft) on `#FFFFFF` = 5.7 ✅ AA
- `#818194` (muted) on `#FAFAFB` = 4.5 ✅ AA 边界 (只用于 ≥14px, 不用于 body)
- `#BEC0C6` (faint) on `#FAFAFB` = 2.5 ❌ 只能用于 placeholder 或 ≥24px 装饰字
- `#605BFF` (accent) on `#FFFFFF` = 4.9 ✅ AA (14px+ 通过); 若用于 <14px text, 加 Nunito 600 加粗

颜色永远**不是**信息的唯一载体:
- 情感正/负 chip 除颜色外加 ✓ / – 图标
- 状态徽章除颜色外加文字 label
- 语言切换的当前语言除了颜色高亮, 还加 font-weight 600 和 (可选) 下方 2px underline

### 7.3 Dark / Light mode?

本 Session **浅色单模**, 与产品端一致。产品端未来若引入 dark mode (PRD 暂未规划), 再同步加官网 dark 变体。

### 7.4 性能

- `@font-face font-display: swap`
- Hero 截图 `loading="eager"` + `fetchpriority="high"`, 其他 `loading="lazy"`
- ECharts 用 `renderer: 'svg'` (浅色下 SVG 比 canvas 锐利)
- LCP < 2s, CLS < 0.1
- 不加任何 scroll-jack 或 JS-heavy 动画 (与产品端一致, 保持页面轻量)

---

## 8. Session 规划

### Session L1 (本 Session, 2026-04-17)
1. ✅ `docs/LANDING_REDESIGN.md` v2.1 (本文档)
2. ✅ `design/prototype-landing-v2.html` 浅色 Stripe + ZH/EN 切换 + 真实应用入口
3. ✅ 10 条 anti-AI / anti-v2.0-残留自查清单

### Session L2 (下一次, React 实施)

1. Playwright 截 `DashboardPage.jsx` **浅色默认态** → `frontend/public/hero-dashboard-light@2x.png`
2. 重写 `frontend/src/pages/LandingPage.jsx` (Stripe 浅色, 消费产品 token, 无 v2.0 Dark-Eng 残留)
3. 新建 `frontend/src/messages/zh-CN/landing.json` + `en-US/landing.json`
4. 新建 `frontend/src/lib/locale.ts` 实现 §3.2 读取优先级 + 写入
5. 在 `DashboardLayout.jsx` user dropdown 接入 language switcher, 共享 `genpano_locale`
6. Harness 拦截 grep (pre-commit + CI):
   - 禁用词: `全方位|一站式|AI 驱动|赋能|解锁|Powered by|Unlock|Revolutionize|Seamless`
   - 禁用 v2.0 残留: `#0A0A0A|#5E6AD2|github-dark|JetBrains Mono|hero-dashboard-dark`
   - 禁用占位链接: `href="#cta"|href="#register"|href="#login"` (官网必须接真实路由)
7. 所有 CTA `href` 带 UTM query (`?from=landing_hero|landing_final|nav`) 用于 Mixpanel 分析
8. 跑 Lighthouse: Performance ≥ 90, A11y ≥ 95, LCP < 2s

### Session L3 (真客户上线后)

- Voices 接真实 Response API, 每周轮换
- Industries 表接实时数字
- 加 3-5 个真实 testimonial (有授权后)
- 接入 MCP 文档站后, §4.8 For Agents CTA 改指向 `/docs/mcp`

---

## 9. "AI 感 / v2.0 残留 / 产品不一致" 检查清单 (10 条)

v2.1 PR reviewer 逐条 check, 任何一条命中 = 回炉:

1. [ ] 是否出现 v2.0 深色残留 (`#0A0A0A` / `#050505` / `#5E6AD2` / 任何深底)? 整站底色必须是 `#FAFAFB` 或 `#FFFFFF`
2. [ ] 是否在 body / KPI / 代码区 / 导航等常规场景引入了 `JetBrains Mono` / `Geist` / `Figtree` / `Source Serif`? 主字体必须 Nunito
3. [ ] 是否在产品 DESIGN_TOKENS.md 外新增了任何 hex 值 / 自定义颜色 / 自创圆角 (如 14px / 20px 这种非 token)? 必须 100% 消费 §1.2 列出的 CSS variables
4. [ ] 是否出现禁用词 (全方位 / 一站式 / 解锁 / 赋能 / AI 驱动 / Unlock / Revolutionize / Seamless / Powered by)?
5. [ ] 是否有 >1 处 radial-gradient 装饰? v2.1 只允许 Hero 右侧 screenshot 后方 **1 处**品牌渐变柔光环 (§1.6) + 可选的 dot pattern 底纹
6. [ ] 是否有任何 sparkle ✨ / rocket 🚀 / lightning ⚡ icon 或 emoji?
7. [ ] 是否有 CTA / 链接 用了 `#cta` / `#` / `#register` 占位? 所有入口必须是 §4.11 表中列出的真实路由 (`/register` / `/login` / `/industry`)
8. [ ] 是否出现虚构人物 testimonial (名字 + 头像首字母 + 模糊头衔) 或 "200+ 品牌", "3 倍效率" 这类无根据数字?
9. [ ] 是否有 browser chrome mockup (红黄绿圆点 + URL bar)? 浅色版 **terminal 3 圆点也禁止** (与产品浅色语言不搭)
10. [ ] 是否存在开发者约束泄漏到 UI (CLAUDE.md "UI vs Prompt 指引边界"): 如 "本页只做 X" / "详情请进入 Y" / 🚫 符号 出现在 `messages/*.json` 或 JSX 文本节点?

10 条全 pass = 合格出手。

---

## 10. 参考

**v2.1 取法对象** (浅色 + 产品一致):
- `https://stripe.com` — Light + hairline border + big brand moment + restrained gradient
- `https://linear.app/homepage` — Clean light hero (非 dark 首屏的那一版)
- `https://vercel.com/docs` — Light code blocks w/ file header (本版 §4.8 Code block 参考)
- `https://resend.com/home` — Big light hero screenshot + 克制 brand gradient
- `https://clerk.com` — Real product screenshot in Hero + light bento
- 产品内部锚点: `frontend/src/pages/DashboardPage.jsx` + `docs/DESIGN_TOKENS.md` — **最优先参考**, 官网视觉必须与这两者一致

**避雷**:
- v2.0 Dark-Eng 方向 (Linear/Vercel 深色版) — Frank 2026-04-17 明确否决, 与产品浅色 Stripe 语言不搭
- Builderflow / Framer AI-generated sites — sparkle + radial blob + gradient 横幅模板
- Generic Tailwind UI Landing (社区模板) — 过度装饰 + scroll-jack 动画
- 任何"自创一套视觉语言"的做法 — 官网必须消费产品 token, 不发明新 token

---

*v2.1 于 2026-04-17 覆盖 v2.0 Dark-Eng 方向, 回归 Stripe 浅色 + 与产品 DESIGN_TOKENS.md 完全对齐, 新增 §4.11 应用入口映射表。信息架构 + i18n 契约继承自 v2.0。*
