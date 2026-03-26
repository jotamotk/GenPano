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
| `ACR_REGISTRY` | 镜像仓库地址（含命名空间） | `crpi-xxx.cn-shanghai.personal.cr.aliyuncs.com/lianwei_ai_lab` |
| `SERVER_HOST` | 部署服务器 IP | `116.62.36.173` |
| `SERVER_USER` | SSH 用户名 | `root` |
| `SERVER_SSH_KEY` | SSH 私钥 | `-----BEGIN RSA PRIVATE KEY-----...` |

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
