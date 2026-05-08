# CI/CD 部署指南

## 架构概述

- **镜像仓库**：阿里云容器镜像服务 (ACR) - 个人版
- **CI/CD**：GitHub Actions
- **部署方式**：Docker Compose

## GitHub Secrets 配置

| Secret | 说明 | 示例值 |
|--------|------|--------|
| `ACR_USERNAME` | 阿里云账号或 RAM 用户名 | `tomatokillerman` |
| `ACR_PASSWORD` | ACR 访问密码 | 在 ACR 控制台 → 访问凭证 设置 |
| `ACR_REGISTRY` | 镜像仓库地址（含命名空间）；workflow 会从这里自动解析登录域名 | `crpi-xxx.cn-shanghai.personal.cr.aliyuncs.com/lianwei_ai_lab` |
| `SERVER_HOST` | 部署服务器 IP | `116.62.36.173` |
| `SERVER_USER` | SSH 用户名 | `root` |
| `SERVER_SSH_KEY` | SSH 私钥 | `-----BEGIN RSA PRIVATE KEY-----...` |
| `JWT_SECRET` / `USER_JWT_SECRET` | App 用户登录 JWT 与 OAuth state 签名密钥，至少 32 字节 | `openssl rand -base64 48` |
| `USER_BASE_URL` / `FRONTEND_URL` | 生产前端公开访问地址，用于邮件链接和 OAuth callback | `https://genpano.example.com` |
| `USER_EMAIL_PROVIDER` / `EMAIL_PROVIDER` | 用户邮件服务商；阿里云 DM 使用 `aliyun_dm` | `aliyun_dm` |
| `USER_EMAIL_FROM` / `EMAIL_FROM` | 用户邮件发件地址，需在邮件服务商侧完成验证 | `GenPano <noreply@example.com>` |
| `ALIYUN_DM_SMTP_USER` | 阿里云 DirectMail SMTP 用户名；未配置时默认使用发件邮箱 | `noreply@example.com` |
| `ALIYUN_DM_SMTP_PASSWORD` | 阿里云 DirectMail SMTP 密码 | 在阿里云 DM 控制台生成 |
| `ALIYUN_DM_SMTP_HOST` | 阿里云 DM SMTP host，可不填使用默认值 | `smtpdm.aliyun.com` |
| `ALIYUN_DM_SMTP_PORT` | 阿里云 DM SMTP 端口，可不填使用默认值 | `465` |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google OAuth 登录配置，可选 | Google Cloud Console |

## App 注册登录部署

- 合并到 `main` 后，`Build & Deploy` 会构建 `frontend`、`backend`、`worker` 镜像，并在 `docker compose up` 前执行 `backend alembic upgrade head`。Admin SPA 现已打包进 `backend` 镜像（`backend/static/admin.html`），无需独立的 `admin-console` 镜像（PR #386）。
- 推送到 `preview/**` 分支后，`Build & Deploy (Preview)` 会构建并部署 `frontend-preview`、`backend-preview`，预览环境访问路径为 `/preview/`。
- 预览环境会使用 `PREVIEW_USER_BASE_URL`、`PREVIEW_FRONTEND_URL`、`PREVIEW_GOOGLE_CALLBACK_URL`。未设置时默认使用 `http://<SERVER_HOST>/preview`。
- 阿里云 DM 的发件域名、发件地址、SMTP 密码必须在阿里云控制台配置完成；GitHub Actions 只负责把这些 secrets 写入服务器 `.env`。
- `USER_EMAIL_PROVIDER` 未配置时默认使用 `preview`，注册邮件会保存到 `/data/email-previews` 并在注册成功页展示临时验证入口，方便在阿里云 DM/DNS 生效前测试注册流程。真实发信准备好后，将 repository variable 或 secret `USER_EMAIL_PROVIDER` 改为 `aliyun_dm`。

## 常见问题

### 1. denied: requested access to the resource is denied

**原因**：`ACR_REGISTRY` 配置不完整

**解决**：确保 `ACR_REGISTRY` 包含命名空间，格式为：
```
crpi-<id>.<region>.personal.cr.aliyuncs.com/<namespace>
```

**注意**：
- 登录地址 ≠ 镜像地址
- 登录只需要 registry 地址
- 推送镜像需要 registry + namespace

### 2. 如何获取 ACR 密码

1. 登录阿里云控制台
2. 进入「容器镜像服务」→「访问凭证」
3. 设置固定密码（不是阿里云登录密码）

### 3. 手动触发部署

```bash
# 本地构建并推送
docker login --username=<用户名> crpi-xxx.cn-shanghai.personal.cr.aliyuncs.com
docker build -t crpi-xxx.../lianwei_ai_lab/genpano:frontend-latest ./frontend
docker push crpi-xxx.../lianwei_ai_lab/genpano:frontend-latest
```

## 镜像列表

| 镜像 | 用途 |
|------|------|
| `genpano:frontend-<tag>` | 前端 (Nginx) |
| `genpano:backend-<tag>` | 后端 API |
| `genpano:worker-<tag>` | Celery Worker |
