# GenPano 第三方集成指南

> 版本: v1.0 | 日期: 2026-03-30

---

## 1. Google OAuth 2.0 集成

### 1.1 概述

GenPano 支持通过 Google 账号一键登录/注册。使用 `passport-google-oauth20` 策略实现。

### 1.2 Google Cloud Console 配置步骤

#### Step 1: 创建项目

1. 访问 [Google Cloud Console](https://console.cloud.google.com/)
2. 创建新项目或选择已有项目

#### Step 2: 启用 API

1. 导航到 **APIs & Services → Library**
2. 搜索并启用 **Google+ API** 和 **Google People API**

#### Step 3: 配置 OAuth 同意屏幕

1. 导航到 **APIs & Services → OAuth consent screen**
2. 选择 **External** (面向所有 Google 用户)
3. 填写应用信息:
   - 应用名称: `GenPano`
   - 用户支持邮箱: 你的邮箱
   - 授权域名: `genpano.com` (生产环境)
4. 添加 Scopes:
   - `email`
   - `profile`
   - `openid`

#### Step 4: 创建 OAuth 2.0 Client ID

1. 导航到 **APIs & Services → Credentials**
2. 点击 **Create Credentials → OAuth 2.0 Client ID**
3. 选择 **Web application**
4. 填写:
   - 名称: `GenPano Web Client`
   - 授权 JavaScript 来源:
     - `http://localhost:3000` (开发)
     - `https://app.genpano.com` (生产)
   - 授权重定向 URI:
     - `http://localhost:4000/api/auth/google/callback` (开发)
     - `https://api.genpano.com/api/auth/google/callback` (生产)
5. 保存，获取 **Client ID** 和 **Client Secret**

### 1.3 环境变量配置

在 `backend/.env` 中添加:

```env
# Google OAuth 2.0
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_CALLBACK_URL=http://localhost:4000/api/auth/google/callback

# 生产环境
# GOOGLE_CALLBACK_URL=https://api.genpano.com/api/auth/google/callback
```

### 1.4 现有代码位置

| 文件 | 描述 |
|------|------|
| `backend/src/routes/auth.ts` | Google OAuth 路由: `GET /auth/google` 和 `GET /auth/google/callback` |
| `backend/src/index.ts` | Passport 初始化 |

### 1.5 流程说明

```
前端                          后端                        Google
  │                            │                            │
  │ ── GET /auth/google ─────→ │                            │
  │                            │ ── 302 重定向 ───────────→ │
  │                            │                            │
  │ ←── Google 授权页面 ────────────────────────────────────│
  │                            │                            │
  │ ── 用户授权 ─────────────────────────────────────────→ │
  │                            │                            │
  │                            │ ←── callback + code ───── │
  │                            │                            │
  │                            │ ── 用 code 换 token ────→ │
  │                            │ ←── user profile ──────── │
  │                            │                            │
  │ ←── 302 重定向 + JWT ───── │                            │
  │     /dashboard?token=xxx   │                            │
```

### 1.6 生产环境注意事项

- [ ] **域名验证**: 在 Google Console 验证你的域名所有权
- [ ] **同意屏幕审核**: 如果请求敏感 scope，需通过 Google 审核
- [ ] **HTTPS 强制**: 回调 URL 必须使用 HTTPS
- [ ] **Client Secret 保密**: 不要提交到代码仓库
- [ ] **Token 刷新**: 当前实现使用 JWT，无需 Google refresh token
- [ ] **错误处理**: 用户取消授权时的优雅降级

### 1.7 常见问题

| 问题 | 解决方案 |
|------|---------|
| `redirect_uri_mismatch` | 确认 Google Console 中的重定向 URI 与 `.env` 中的完全一致 |
| `access_denied` | 检查 OAuth 同意屏幕配置，确认 scope 正确 |
| 回调后 404 | 确认后端路由已注册 `/api/auth/google/callback` |
| 只在开发环境工作 | 生产环境需要添加对应域名的重定向 URI |

---

## 2. 邮件发送集成 (SMTP)

### 2.1 概述

GenPano 使用 `nodemailer` 发送两种邮件:
- **验证邮件**: 注册后验证工作邮箱
- **重置密码邮件**: 忘记密码时发送重置链接

### 2.2 开发环境 (Ethereal)

开发环境自动使用 [Ethereal](https://ethereal.email/) 测试账户，无需配置 SMTP。

**使用方式**:
1. 启动后端: `cd backend && npm run dev`
2. 触发邮件发送 (注册或忘记密码)
3. 控制台会输出 Ethereal 预览链接:
   ```
   Email preview URL: https://ethereal.email/message/xxxxx
   ```
4. 打开链接查看邮件效果

### 2.3 生产环境 SMTP 配置

在 `backend/.env` 中配置:

```env
# SMTP 配置
SMTP_HOST=smtp.your-provider.com
SMTP_PORT=587
SMTP_SECURE=false
SMTP_USER=your-smtp-username
SMTP_PASS=your-smtp-password
EMAIL_FROM="GenPano" <noreply@genpano.com>
```

### 2.4 推荐邮件服务商

| 服务商 | 免费额度 | 优点 | 配置示例 |
|--------|---------|------|---------|
| **SendGrid** | 100 封/天 | 高送达率，API + SMTP 双模式 | `SMTP_HOST=smtp.sendgrid.net` |
| **AWS SES** | 62000 封/月 (EC2) | 便宜，适合大规模 | `SMTP_HOST=email-smtp.us-east-1.amazonaws.com` |
| **Mailgun** | 100 封/天 | 开发者友好 | `SMTP_HOST=smtp.mailgun.org` |
| **Resend** | 3000 封/月 | 现代 API，React Email 支持 | `SMTP_HOST=smtp.resend.com` |

### 2.5 SendGrid 配置详解 (推荐)

#### Step 1: 注册 SendGrid

1. 访问 [sendgrid.com](https://sendgrid.com) 注册账户
2. 完成邮箱验证

#### Step 2: 创建 API Key

1. 导航到 **Settings → API Keys**
2. 点击 **Create API Key**
3. 选择 **Restricted Access**, 仅开启 **Mail Send** 权限
4. 保存 API Key

#### Step 3: 验证发件人

1. 导航到 **Settings → Sender Authentication**
2. 选择 **Single Sender Verification** (快速) 或 **Domain Authentication** (推荐)
3. 按指引完成验证

#### Step 4: 环境变量

```env
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASS=SG.your-api-key-here
EMAIL_FROM="GenPano" <noreply@genpano.com>
```

### 2.6 DNS 配置 (防垃圾邮件)

为确保邮件不进入垃圾邮件箱，需在域名 DNS 中配置以下记录:

#### SPF 记录

```
类型: TXT
主机: @
值: v=spf1 include:sendgrid.net ~all
```

#### DKIM 记录

由邮件服务商提供，通常为:
```
类型: CNAME
主机: s1._domainkey
值: s1.domainkey.u123456.wl123.sendgrid.net
```

#### DMARC 记录

```
类型: TXT
主机: _dmarc
值: v=DMARC1; p=quarantine; rua=mailto:dmarc@genpano.com
```

### 2.7 现有代码位置

| 文件 | 描述 |
|------|------|
| `backend/src/utils/email.ts` | 邮件发送逻辑 + HTML 模板 |
| `backend/src/routes/auth.ts` | 调用邮件发送的路由 |

### 2.8 邮件模板变量

**验证邮件**:
| 变量 | 描述 | 示例 |
|------|------|------|
| `{UserName}` | 用户名 | "Frank Wang" |
| `{verificationUrl}` | 验证链接 | `https://app.genpano.com/setup?token=xxx` |
| `{companyName}` | 公司名 | "Lianwei Tech" |

**重置密码邮件**:
| 变量 | 描述 | 示例 |
|------|------|------|
| `{UserName}` | 用户名 | "Frank Wang" |
| `{resetUrl}` | 重置链接 | `https://app.genpano.com/reset-password?token=xxx` |

### 2.9 常见问题

| 问题 | 解决方案 |
|------|---------|
| 邮件进垃圾箱 | 配置 SPF/DKIM/DMARC 记录 |
| 发送失败 timeout | 检查 SMTP 端口是否被防火墙阻止 (587 或 465) |
| 认证失败 | 确认 SMTP_USER 和 SMTP_PASS 正确 |
| Ethereal 链接失效 | Ethereal 预览链接可能过期，重新发送即可 |
| 模板乱码 | 确保 HTML 头部有 `charset=UTF-8` |

### 2.10 邮件送达率优化

- [ ] 配置 SPF/DKIM/DMARC DNS 记录
- [ ] 使用专属子域名发送 (如 `mail.genpano.com`)
- [ ] 避免使用个人邮箱作为发件人
- [ ] 定期清理无效邮箱 (bounce handling)
- [ ] 监控送达率和投诉率
- [ ] HTML 邮件保持简洁，避免过多图片

---

## 3. 环境变量完整清单

```env
# ===== 服务器 =====
PORT=4000
NODE_ENV=development
FRONTEND_URL=http://localhost:3000

# ===== JWT =====
JWT_SECRET=your-jwt-secret-here
JWT_EXPIRES_IN=7d

# ===== Google OAuth 2.0 =====
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_CALLBACK_URL=http://localhost:4000/api/auth/google/callback

# ===== SMTP 邮件 =====
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_SECURE=false
SMTP_USER=apikey
SMTP_PASS=your-smtp-password
EMAIL_FROM="GenPano" <noreply@genpano.com>

# ===== 数据库 (未来) =====
# DATABASE_URL=postgresql://user:pass@localhost:5432/genpano
```
