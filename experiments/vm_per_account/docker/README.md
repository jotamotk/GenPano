# Docker-based VM-per-account 部署 (单主机多容器)

跑在你**现有 ECS 升级后**的 docker, 不依赖 GitHub Actions / Aliyun ECS provision API。每个容器 = 1 个隔离的 Chrome + 持久 profile, 操作员通过 noVNC 远程登录, Celery worker 通过 CDP 远程驱动。

## 适用场景

- 你现有 ECS 升级到 ≥ 16 GB RAM 后, 想在同一台机器上跑 backend + 2-5 个 Doubao Chrome 容器
- 一次性升级一台机器, 不开多台 ECS
- 接受 R1.6 风险 (多账号同 IP), 数据驱动决定要不要加 qg.net 住宅代理

## ECS 升级建议

| 当前 | 跑容器数 | 推荐升级到 |
|---|---|---|
| 2c8g (`ecs.g7.large`) | 1 容器 PoC | 不动也能跑 |
| 升 4c16g (`ecs.g7.xlarge`) | 2-3 容器 | +~¥150/月 |
| 升 8c32g (`ecs.g7.2xlarge`) | 5-6 容器 | +~¥450/月 |

容器资源 cap (docker-compose 里已限): 每容器 2 GB RAM + 1 vCPU。

## 一次性部署

```bash
# 在你 ECS 上 (升级配置 + 重启后):

# 1. 装 docker (如果还没)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER  # 重新登录生效

# 2. 装 Tailscale on host (不在容器内)
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --authkey=$TAILSCALE_AUTH_KEY --hostname=ecs-prod

# 3. 拉 repo, 进 docker 目录
git clone <repo> && cd trash_test/experiments/vm_per_account/docker

# 4. 配 .env
cp .env.example .env
# 编辑 .env, 把 VNC_PASSWORD_01/02 改成你自己的 (e.g. openssl rand -hex 4 生成)

# 5. 起容器
docker compose up -d

# 验证
docker compose ps
docker compose logs doubao-01 | tail -20
curl http://127.0.0.1:9222/json/version    # 应返回 Chrome 信息
curl http://127.0.0.1:6080/                  # 应返回 noVNC HTML
```

## 操作员登录豆包

ECS 上 Tailscale 已加入 tailnet → 你 Windows/手机 Tailscale 客户端也加 tailnet → 直接连:

```
http://<ecs-tailscale-ip>:6080/vnc.html   ← doubao-01 noVNC
http://<ecs-tailscale-ip>:6081/vnc.html   ← doubao-02 noVNC
```

输 VNC 密码 (`.env` 里的 `VNC_PASSWORD_01` / `_02`) → 进 Xfce 桌面 → Chrome 已开在 doubao.com → **手机号登录** (不用 APP, 收 SMS) → 跟你平时浏览器登豆包一样。

登录态自动持久化到 `./data/profile-doubao-01/`, 容器重启仍在。

## Celery worker 从 CDP 抓数据

ECS 上的 backend / worker 直接读 `127.0.0.1:9222` (CDP) / `127.0.0.1:9223`:

```python
# geo_tracker/agent/executors/remote_vm.py (PR #1121 已 merge)
browser = await playwright.chromium.connect_over_cdp("http://127.0.0.1:9222")
context = browser.contexts[0]   # 持久 profile, 不注入 cookie
# 下面跟现有 guest_executor 逻辑完全一样
```

通过 `vm_registry` env 配置:
```
VM_REGISTRY_CSV=doubao-01:http://127.0.0.1:9222,doubao-02:http://127.0.0.1:9223
```

并把对应 `llm_accounts` row 的 `execution_mode='vm_session'` + `vm_id='doubao-01'`。

## 常用操作

```bash
# 看所有容器
docker compose ps

# 重启某个容器 (登录态保留)
docker compose restart doubao-01

# 完全销毁 + 删除登录态
docker compose down
rm -rf ./data/profile-doubao-01

# 查容器内 log
docker compose logs -f doubao-01

# 进容器 shell debug
docker compose exec doubao-01 bash

# 增加容器: 复制 docker-compose.yml 里 doubao-02 段, 改名 doubao-03 + 端口 6082/9224
```

## 风险 & Mitigation

### R1.6: 所有容器共享 ECS 公网 IP → Doubao 可能跨账号关联

- **PoC 阶段先不管**, 跑 1-2 周看实际数据 (单账号成功率 vs 跨账号 ban 关联率)
- **如果触发**: 加 `--proxy-server=http://qg_ip:port` 到容器 Chrome 启动参数, 一个容器一个 qg 静态 IP

### 抢 backend 资源

- 容器 RAM/CPU cap 已经在 docker-compose 里 (2 GB / 1 vCPU)
- 跑前用 `htop` / `free -h` 看 baseline, 起容器后再看, 确认没把 backend 挤死

### Chrome session 过期 (~7-30 天后)

- `login_watchdog` (PR #1119 vm_side) 每 60s 检测, 检到掉登录就 POST `/admin/api/vm/needs_relogin` 触发 Slack
- 你 noVNC 重新扫码登录即可, profile 复用

## 关闭一切

```bash
docker compose down
sudo tailscale down   # 如果不想保留 Tailscale 在 host
```
