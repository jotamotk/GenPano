# GenPano Auth Module - Design System

> UI 设计规范文档 | 现代简约 SaaS 风格 | v1.0

---

## 1. 设计理念

GenPano 注册登录模块采用**现代简约 SaaS 风格**，灵感来源于 Linear、Notion 等优秀产品。设计目标：

- **专业可信** — 面向企业用户，传递安全感和品质感
- **简洁高效** — 减少视觉噪音，聚焦核心操作
- **品牌一致** — 紫色主色调贯穿全流程，强化品牌识别

---

## 2. 色彩系统 (Color Palette)

### 2.1 主色 (Primary)

| Token | 色值 | 用途 |
|-------|------|------|
| `primary-500` | `#6C5CE7` | 按钮、链接、选中态 |
| `primary-600` | `#5B4BD5` | 按钮 hover |
| `primary-700` | `#4A3BC3` | 按钮 active/pressed |
| `primary-100` | `#EDE9FE` | 浅紫背景、focus ring |
| `primary-50` | `#F5F3FF` | 极浅紫背景 |

### 2.2 背景色 (Background)

| Token | 色值 | 用途 |
|-------|------|------|
| `bg-warm` | `#F5EDE3` | 左面板米色背景 |
| `bg-white` | `#FFFFFF` | 右面板表单区 |
| `bg-gray-50` | `#F9FAFB` | 卡片背景、信息区 |
| `bg-gray-100` | `#F3F4F6` | 禁用输入框背景 |

### 2.3 语义色 (Semantic)

| Token | 色值 | 用途 |
|-------|------|------|
| `success-500` | `#10B981` | 成功图标、验证通过 |
| `success-50` | `#ECFDF5` | 成功背景 |
| `error-500` | `#EF4444` | 错误文字、错误边框 |
| `error-50` | `#FEF2F2` | 错误背景 |
| `warning-500` | `#F59E0B` | 警告提示 |

### 2.4 文本色 (Text)

| Token | 色值 | 用途 |
|-------|------|------|
| `text-primary` | `#1A1A2E` | 标题、重要文字 |
| `text-secondary` | `#4B5563` | 正文 |
| `text-muted` | `#6B7280` | 辅助说明文字 |
| `text-placeholder` | `#9CA3AF` | 输入框占位符 |
| `text-disabled` | `#D1D5DB` | 禁用文字 |

### 2.5 边框色 (Border)

| Token | 色值 | 用途 |
|-------|------|------|
| `border-default` | `#E5E7EB` | 输入框、卡片边框 |
| `border-focus` | `#6C5CE7` | 聚焦边框 |
| `border-error` | `#EF4444` | 错误边框 |
| `border-divider` | `#E5E7EB` | 分割线 |

### 2.6 邮件模板色

| Token | 色值 | 用途 |
|-------|------|------|
| `email-gradient-start` | `#6C5CE7` | Header 渐变起始 |
| `email-gradient-end` | `#8B7CF7` | Header 渐变结束 |
| `email-bg` | `#F5F5F5` | 邮件背景 |
| `email-card-bg` | `#FFFFFF` | 邮件卡片背景 |

---

## 3. 字体系统 (Typography)

### 3.1 字体族

```css
/* 标题字体 */
font-family: 'Nunito', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;

/* 正文字体 */
font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
```

**引入方式** (Google Fonts):
```html
<link href="https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
```

### 3.2 字体层级

| 级别 | 字体 | 大小 | 字重 | 行高 | 用途 |
|------|------|------|------|------|------|
| H1 | Nunito | 32px (2rem) | SemiBold 600 | 1.25 | 页面标题 "登录"、"注册" |
| H2 | Nunito | 24px (1.5rem) | SemiBold 600 | 1.33 | 邮件标题、成功页标题 |
| H3 | Nunito | 20px (1.25rem) | SemiBold 600 | 1.4 | 卡片标题 |
| Subtitle | Inter | 14px (0.875rem) | Regular 400 | 1.5 | 副标题 "没有账号？" |
| Label | Inter | 14px (0.875rem) | Medium 500 | 1.5 | 表单标签 |
| Body | Inter | 14px (0.875rem) | Regular 400 | 1.5 | 正文内容 |
| Body-sm | Inter | 13px (0.8125rem) | Regular 400 | 1.5 | 辅助文字 |
| Caption | Inter | 12px (0.75rem) | Regular 400 | 1.5 | 提示、错误文字 |
| Button | Inter | 16px (1rem) | SemiBold 600 | 1.5 | 按钮文字 |

---

## 4. 组件规范 (Components)

### 4.1 Input 输入框

```
┌──────────────────────────────────────────┐
│  [icon]  Placeholder text      [action]  │
└──────────────────────────────────────────┘
  Error message here
```

| 属性 | 值 |
|------|-----|
| 高度 | 48px |
| 圆角 | 8px (`rounded-lg`) |
| 内边距 | 左 12px (无图标) / 44px (有图标), 右 12px / 44px |
| 边框 (默认) | 1px solid `#E5E7EB` |
| 边框 (hover) | 1px solid `#D1D5DB` |
| 边框 (focus) | 2px solid `#6C5CE7` + `box-shadow: 0 0 0 3px rgba(108,92,231,0.1)` |
| 边框 (error) | 1px solid `#EF4444` |
| 背景 (默认) | `#FFFFFF` |
| 背景 (disabled) | `#F3F4F6` |
| 字体 | Inter 14px Regular |
| Placeholder 色 | `#9CA3AF` |
| 左侧图标 | 20px, `#9CA3AF`, 居中于左侧 12px |
| 右侧图标 | 20px, `#6B7280`, 可点击 (眼睛/编辑) |
| 过渡 | `transition: border-color 200ms ease, box-shadow 200ms ease` |

**错误态输入框**:
- 边框: `#EF4444`
- 下方 4px 显示错误文字: 13px, `#EF4444`

**Tailwind 实现**:
```jsx
// 默认态
className="h-12 w-full rounded-lg border border-gray-200 px-3 text-sm
  transition-all duration-200
  hover:border-gray-300
  focus:border-primary-500 focus:ring-2 focus:ring-primary-500/10 focus:outline-none
  placeholder:text-gray-400"

// 错误态
className="... border-red-500 focus:border-red-500 focus:ring-red-500/10"
```

### 4.2 Primary Button (主按钮)

| 属性 | 值 |
|------|-----|
| 高度 | 48px |
| 宽度 | 100% (全宽) |
| 圆角 | 10px (`rounded-[10px]`) |
| 背景 (默认) | `#6C5CE7` |
| 背景 (hover) | `#5B4BD5` + `translateY(-1px)` + subtle shadow |
| 背景 (active) | `#4A3BC3` + `translateY(0)` |
| 背景 (disabled) | `#6C5CE7` opacity 50% |
| 文字 | 白色, Inter 16px SemiBold |
| 过渡 | `transition: all 200ms ease` |
| Shadow (hover) | `0 4px 12px rgba(108,92,231,0.3)` |

**Tailwind 实现**:
```jsx
className="h-12 w-full rounded-[10px] bg-[#6C5CE7] text-white font-semibold text-base
  transition-all duration-200
  hover:bg-[#5B4BD5] hover:-translate-y-[1px] hover:shadow-lg hover:shadow-purple-500/30
  active:bg-[#4A3BC3] active:translate-y-0
  disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-y-0 disabled:hover:shadow-none"
```

### 4.3 Google OAuth Button

| 属性 | 值 |
|------|-----|
| 高度 | 48px |
| 宽度 | 100% |
| 圆角 | 10px |
| 背景 (默认) | `#FFFFFF` |
| 边框 | 1px solid `#E5E7EB` |
| 背景 (hover) | `#F9FAFB` + subtle shadow |
| 文字 | `#4B5563`, Inter 14px Medium |
| Google 图标 | 20px, 位于文字左侧 8px |

**Tailwind 实现**:
```jsx
className="h-12 w-full rounded-[10px] border border-gray-200 bg-white text-gray-600 font-medium text-sm
  flex items-center justify-center gap-2
  transition-all duration-200
  hover:bg-gray-50 hover:shadow-sm"
```

### 4.4 Link 链接

| 类型 | 样式 |
|------|------|
| Primary Link | `#6C5CE7`, hover: underline, 14px Medium (如 "Sign Up"、"注册") |
| Secondary Link | `#6B7280`, hover: `#6C5CE7`, 14px Regular (如 "忘记密码？") |

### 4.5 Divider (分割线 "Or")

```
────────────────  Or  ────────────────
```

- 线: 1px `#E5E7EB`
- 文字: "Or", 14px, `#9CA3AF`
- 文字背景: 白色 padding 0 16px，遮住分割线

**Tailwind 实现**:
```jsx
<div className="relative my-6">
  <div className="absolute inset-0 flex items-center">
    <div className="w-full border-t border-gray-200" />
  </div>
  <div className="relative flex justify-center text-sm">
    <span className="bg-white px-4 text-gray-400">Or</span>
  </div>
</div>
```

### 4.6 Success State (成功状态)

| 元素 | 样式 |
|------|------|
| 勾号图标 | 64px 圆形, `#10B981`, 2px stroke |
| 动画 | scale: 0→1, 300ms ease-out (入场) |
| 标题 | H2, 24px SemiBold, `#1A1A2E` |
| 描述 | 14px Regular, `#6B7280` |

### 4.7 Info Card (信息卡片)

用于邮件确认页面的邮箱展示和下一步说明区域：

| 属性 | 值 |
|------|-----|
| 背景 | `#F9FAFB` |
| 圆角 | 12px |
| 内边距 | 20px |
| 边框 | none |

### 4.8 Checkbox

| 属性 | 值 |
|------|-----|
| 大小 | 18px |
| 圆角 | 4px |
| 未选中 | border 2px `#D1D5DB` |
| 选中 | 背景 `#6C5CE7`, 白色勾号 |

### 4.9 Password Strength Tooltip

密码字段旁的 (i) 图标，hover 显示密码要求：
- 最少 8 个字符
- 包含大小写字母
- 包含数字

---

## 5. 布局系统 (Layout)

### 5.1 Auth Layout (认证页面布局)

```
┌─────────────────────┬─────────────────────┐
│                     │    [Language ▼]      │
│                     │                     │
│    米色背景          │     H1 标题          │
│    #F5EDE3          │     副标题           │
│                     │                     │
│    3D 粒子艺术       │     [Form Fields]    │
│    动态效果          │                     │
│                     │     [Button]         │
│                     │                     │
│                     │     ─── Or ───       │
│                     │                     │
│                     │     [Google Btn]     │
│                     │                     │
│        50%          │        50%          │
└─────────────────────┴─────────────────────┘
```

| 属性 | 值 |
|------|-----|
| 整体 | `min-h-screen flex` |
| 左面板 | `w-1/2 bg-[#F5EDE3] relative overflow-hidden` |
| 右面板 | `w-1/2 bg-white flex items-center justify-center` |
| 表单容器 | `w-full max-w-[400px] px-8` |
| 语言切换 | `absolute top-6 right-6` |

### 5.2 间距系统

| Token | 值 | 用途 |
|-------|-----|------|
| `space-xs` | 4px | 错误文字与输入框间距 |
| `space-sm` | 8px | Label 到 Input 间距 |
| `space-md` | 16px | 表单元素之间 |
| `space-lg` | 20px | 段落/区块间 |
| `space-xl` | 32px | 大区块间 (如表单到 Divider) |
| `space-2xl` | 48px | 页面标题到表单 |

### 5.3 响应式断点

| 断点 | 宽度 | 行为 |
|------|------|------|
| Desktop | ≥ 1024px | 左右分栏 50/50 |
| Tablet | 768-1023px | 左面板缩小至 40%，右 60% |
| Mobile | < 768px | 隐藏左面板，表单全宽，padding 24px |

---

## 6. 动效规范 (Motion)

### 6.1 交互微动效

| 元素 | 触发 | 效果 | 时长 |
|------|------|------|------|
| Input | Focus | border-color + ring 过渡 | 200ms ease |
| Primary Btn | Hover | 背景变深 + 上浮 1px + shadow | 200ms ease |
| Primary Btn | Active | 回落 + 背景更深 | 100ms ease |
| Google Btn | Hover | 背景灰 + shadow | 200ms ease |
| Link | Hover | 下划线渐现 | 150ms ease |

### 6.2 页面过渡

| 效果 | 描述 | CSS |
|------|------|-----|
| Fade In | 页面进入 | `opacity: 0→1, translateY: 8px→0` |
| 时长 | | 300ms ease-out |

```css
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
.animate-fade-in { animation: fadeIn 300ms ease-out; }
```

### 6.3 成功状态动画

```css
@keyframes scaleIn {
  from { opacity: 0; transform: scale(0.5); }
  to { opacity: 1; transform: scale(1); }
}
.animate-scale-in { animation: scaleIn 400ms cubic-bezier(0.34, 1.56, 0.64, 1); }
```

### 6.4 粒子动画 (左面板)

保持现有 CSS 3D 粒子效果，优化：
- 使用 `will-change: transform` 提升 GPU 加速
- 控制粒子数量 ≤ 50 保证性能
- 移动端不渲染

---

## 7. 页面设计详解

### 7.1 登录页 - Step 1 (邮箱输入)

```
登录                          ← H1, Nunito 32px SemiBold
没有账号？ Sign Up             ← Subtitle 14px + Primary Link

邮箱                           ← Label 14px Medium
┌─────────────────────────┐
│ ✉  email@company.com    │   ← Input 48px, 邮件图标
└─────────────────────────┘
  请输入有效的邮箱地址          ← Error 13px red (条件显示)

[        继续        ]        ← Primary Button 48px

忘记密码？                     ← Secondary Link

────────── Or ──────────      ← Divider

[  G  使用 Google 账号继续 ]   ← Google Button
```

### 7.2 登录页 - Step 2 (密码输入)

```
登录
没有账号？ 注册

邮箱
┌──────────────────────── ✏ ┐
│  frank.wang@lianwei.com    │  ← 禁用态，右侧编辑图标可返回 Step1
└────────────────────────────┘

密码
┌──────────────────────── 👁 ┐
│  ••••••••                  │  ← 密码输入，右侧眼睛切换
└────────────────────────────┘
  密码为空: 请输入密码          ← Error
  如果密码账号不对: 用户名或密码不正确

[        继续        ]

忘记密码？

────────── Or ──────────

[  G  使用 Google 账号登录 ]
```

### 7.3 注册页

```
创建免费账户                    ← H1
已经有账户了？ 登录

邮箱
┌─────────────────────────┐
│  frank.wang@lianwei.com │
└─────────────────────────┘
  请输入有效的邮箱地址

[        注册        ]

注册表示我同意 GenPano 隐私政策和条款  ← 带链接的 Caption

────────── Or ──────────

[  G  使用 Google 继续 ]
```

### 7.4 账户设置页

```
设置您的帐户                    ← H1

邮箱  *
┌──────────────────────────┐
│  ✉  email@company.com    │
└──────────────────────────┘

密码  ⓘ  *                    ← Info 图标 hover 显示密码要求
┌──────────────────────── 👁 ┐
│  输入你的密码                │
└────────────────────────────┘

全名  *
┌──────────────────────────┐
│  👤  你的全名              │
└──────────────────────────┘

公司名称  *
┌──────────────────────────┐
│  🏢  例如：耐克            │
└──────────────────────────┘

☑ 订阅我们的新闻邮件

[        注册        ]
```

### 7.5 邮件确认页 (验证/重置共用)

```
        ✅                     ← 绿色勾号 64px, scale-in 动画

   请查收邮箱                  ← H2 24px
   验证邮件已发送。完成验证后，你可以继续设置账号。 ← Body 14px gray

┌─────────────────────────────┐
│  ✉ 已发送至                  │  ← Info Card, bg-gray-50
│  email@company.com      ✏   │
└─────────────────────────────┘

下一步：
  ① 打开邮箱，查看 GenPano 验证邮件 ← 编号步骤
  ② 点击邮件中的按钮继续设置账号

[     重新发送邮件     ]        ← Primary Button

没有收到邮件？请检查你的垃圾邮件文件夹  ← Caption gray

查看邮件                      ← Link
```

### 7.6 忘记密码页

```
忘记密码？                      ← H1
没有账号？ 注册

将重置密码链接发送至：
┌─────────────────────────┐
│  frank.wang@lianwei.com │
└─────────────────────────┘

[        发送        ]
```

### 7.7 重置密码页

```
重置密码                        ← H1

新密码  ⓘ  *
┌──────────────────────── 👁 ┐
│  输入你的密码                │
└────────────────────────────┘
  请输入有效密码

确认密码  *
┌──────────────────────── 👁 ┐
│  输入你的密码                │
└────────────────────────────┘
  密码不匹配，请重试。

[        Reset        ]
```

### 7.8 密码重置成功页

```
        ✅                     ← 绿色勾号

   密码重置成功                 ← H2

   您的密码已成功重置。          ← Body gray
   您现在可以使用新密码登录。

[        返回        ]         ← Primary Button → 跳转登录页
```

---

## 8. 邮件模板设计规范

### 8.1 通用样式

| 属性 | 值 |
|------|-----|
| 邮件宽度 | 600px, 居中 |
| 外背景 | `#F5F5F5` |
| 卡片背景 | `#FFFFFF` |
| 卡片圆角 | 12px |
| Header 高度 | 80px |
| Header 背景 | 线性渐变 `#6C5CE7 → #8B7CF7` |
| Logo | GenPano 白色 logo, 居中 |
| Body 内边距 | 40px |
| CTA 按钮 | `#6C5CE7`, 圆角 8px, 内边距 14px 32px, 白色文字 |
| Footer 背景 | `#F9FAFB` |
| Footer 文字 | 12px, `#9CA3AF` |

### 8.2 验证邮件

```
┌──────────────────────────────────┐
│     ◇ GenPano                    │  ← 紫色渐变背景
├──────────────────────────────────┤
│                                  │
│  欢迎来到 GenPano                 │  ← H2 bold
│                                  │
│  尊敬的 {UserName}，              │
│  感谢您注册 GenPano               │
│                                  │
│  为了确保您的帐户安全并开始使用     │
│  我们的服务，请单击下面的按钮       │
│  验证您的工作电子邮件。            │
│                                  │
│  [ 验证邮箱  → ]                  │  ← CTA 按钮
│                                  │
│  ──────────────────              │
│                                  │
│  您可以立即开始：                  │
│  ✓ 设置您的GEO品牌                │
│  ✓ 探索核心GEO工具                │
│                                  │
├──────────────────────────────────┤
│  如果您没有请求此电子邮件，        │  ← Footer
│  请忽略它。验证链接将在24小时后过期。│
│                                  │
│  帮助中心  |  隐私政策             │
│  © 2026 EnterpriseOS, 版权所有。  │
└──────────────────────────────────┘
```

### 8.3 重置密码邮件

```
┌──────────────────────────────────┐
│     ◇ GenPano                    │
├──────────────────────────────────┤
│                                  │
│  重置密码                        │  ← H2 bold
│                                  │
│  尊敬的 {UserName}：              │
│  我们收到了您重置创全景账户密码     │
│  的请求。                        │
│                                  │
│  为确保您账户的安全，请点击下方     │
│  按钮设置新密码。如果这不是您的     │
│  操作，请忽略此邮件。              │
│                                  │
│  [ 重置密码  → ]                  │  ← CTA 按钮
│                                  │
│  ──────────────────              │
│                                  │
│  安全提示：                       │
│  ⏰ 此重置链接将在 1 小时后过期     │
│  🔒 如果您没有要求重置密码，       │
│     请立即联系我们的支持团队       │
│                                  │
├──────────────────────────────────┤
│  如果您没有要求发送此邮件，        │
│  请忽略它。密码重置链接将在        │
│  1 小时后过期。                   │
│                                  │
│  帮助中心  |  隐私政策             │
│  © 2026 EnterpriseOS, 保留所有权利│
└──────────────────────────────────┘
```

---

## 9. Tailwind 配置扩展

```js
// tailwind.config.js 扩展
module.exports = {
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#F5F3FF',
          100: '#EDE9FE',
          500: '#6C5CE7',
          600: '#5B4BD5',
          700: '#4A3BC3',
        },
        warm: '#F5EDE3',
      },
      fontFamily: {
        heading: ['Nunito', 'sans-serif'],
        body: ['Inter', 'sans-serif'],
      },
      animation: {
        'fade-in': 'fadeIn 300ms ease-out',
        'scale-in': 'scaleIn 400ms cubic-bezier(0.34, 1.56, 0.64, 1)',
      },
      keyframes: {
        fadeIn: {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        scaleIn: {
          from: { opacity: '0', transform: 'scale(0.5)' },
          to: { opacity: '1', transform: 'scale(1)' },
        },
      },
    },
  },
}
```
