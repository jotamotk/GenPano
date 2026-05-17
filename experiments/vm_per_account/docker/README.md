# Docker-based VM-per-account 部署 (单主机多容器)

跑在你**现有 ECS 升级后**的 docker, 通过 GitHub Actions CI/CD 自动部署 + SSH 隧道做操作员浏览器访问。每个容器 = 1 个隔离的 Chrome + 持久 profile, Celery worker 通过 CDP 远程驱动。

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

## 部署模式: CI/CD via GitHub Actions

不在 ECS 上手动跑命令。在 GitHub Actions UI 点按钮, workflow SSH 进 ECS 替你操作。

### 一次性: 配 GitHub Secret

进 https://github.com/jotamotk/trash_test/settings/secrets/actions, 检查 + 添加:

**已有 (其它 workflow 已经在用, 复用即可)**:

| Secret | 值 |
|---|---|
| `SERVER_HOST` | ECS 公网 IP (e.g. `116.62.36.xxx`) |
| `SERVER_USER` | SSH 用户名 (e.g. `root` 或 `ubuntu`) |
| `SERVER_SSH_KEY` | SSH 私钥 PEM 格式 |
| `SERVER_SSH_PORT` | 22 (可选, 默认 22) |

**本 workflow 新加**:

| Secret | 值 |
|---|---|
| `ECS_REPO_PATH` | ECS 上 repo 绝对路径 (e.g. `/opt/trash_test` 或 `/root/trash_test`) |
| `VNC_PASSWORD_01` | doubao-01 noVNC 密码 (e.g. 跑 `openssl rand -hex 4` 生成) |
| `VNC_PASSWORD_02` | doubao-02 noVNC 密码 |

### 第一次部署: 跑 `action=bootstrap`

1. 进 https://github.com/jotamotk/trash_test/actions/workflows/vm-docker-deploy.yml
2. 点 **Run workflow** → 选 `action=bootstrap` → 点 **Run workflow**
3. 等 ~3-5 分钟, workflow 会在 ECS 上:
   - 装 docker (如未装)
   - 装 ufw + 配置 firewall (deny 6080-9232 公网, allow SSH)
   - clone 本 repo 到 `$ECS_REPO_PATH`
   - 用 docker-compose build 镜像

### 启动容器: 跑 `action=up`

1. 同 workflow, 选 `action=up`
2. workflow 把 `VNC_PASSWORD_01/02` 写到 `.env`, 跑 `docker compose up -d`
3. 容器跑起来, Chrome + noVNC + x11vnc 起来
4. workflow Summary 区会打印一条 SSH 隧道命令 (见下)

### 操作员 noVNC 浏览器访问 (SSH 隧道)

Windows 操作员 (PowerShell / Windows Terminal, OpenSSH 内置):

```bash
ssh -N -p 22 \
  -L 6080:127.0.0.1:6080 -L 6081:127.0.0.1:6081 \
  -L 9222:127.0.0.1:9222 -L 9223:127.0.0.1:9223 \
  <ECS_SSH_USER>@<ECS_PUBLIC_IP>
```

`-N` = 只建隧道不开 shell, 终端窗口保持开着。

如果你 SSH key 不在默认路径, 加 `-i path/to/vm-deploy-key`。

**保持这个 SSH 终端不关**, 浏览器 (Windows Chrome 即可) 开:

```
http://localhost:6080/vnc.html   ← doubao-01
http://localhost:6081/vnc.html   ← doubao-02
```

→ Connect → 输 VNC 密码 (`VNC_PASSWORD_01` 那个值) → 看到 Xfce 桌面 + Chrome 在 doubao.com → **点 "手机号登录"** 输手机号 → 收 SMS → 输验证码 → 登录成功。

登录态持久化在 ECS 上的 `<ECS_REPO_PATH>/experiments/vm_per_account/docker/data/profile-doubao-01/`, Chrome 重启仍在。

## CI/CD 日常操作清单

通过 `vm-docker-deploy.yml` workflow 的 `action` 输入:

| 想做的事 | `action` | 附加输入 |
|---|---|---|
| 首次准备环境 | `bootstrap` | — |
| 启动容器 | `up` | — |
| 关闭容器 (保留登录态) | `down` | — |
| 重启一个容器 | `restart` | `container=doubao-01` |
| 看日志 | `logs` | `container=doubao-01` + `tail_lines=200` |
| 拉最新代码到 ECS | `pull` | — |
| 看资源状态 (free / df / ufw / docker ps) | `status` | — |
| ⚠️ 完全销毁容器 + 删登录态 | `destroy` | — (危险!) |

## Celery worker 从 CDP 抓数据 (跟现有 backend 集成)

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

## 风险 & Mitigation

### R1.6: 所有容器共享 ECS 公网 IP → Doubao 可能跨账号关联

- **PoC 阶段先不管**, 跑 1-2 周看实际数据 (单账号成功率 vs 跨账号 ban 关联率)
- **如果触发**: 加 `--proxy-server=http://qg_ip:port` 到容器 Chrome 启动参数, 一个容器一个 qg 静态 IP

### 抢 backend 资源

- 容器 RAM/CPU cap 已经在 docker-compose 里 (2 GB / 1 vCPU)
- 跑前 `action=status` 看 baseline, 起容器后再看, 确认没把 backend 挤死

### Chrome session 过期 (~7-30 天后)

- `login_watchdog` (PR #1119 vm_side) 每 60s 检测, 检到掉登录就 POST `/admin/api/vm/needs_relogin` 触发 Slack
- 你重开 SSH 隧道 + noVNC 重新登录即可, profile 复用
