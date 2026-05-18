# V-Ninja 代理部署指南

## 架构概述

```
┌─────────────────────────────────────────────────────┐
│  宿主机 (Linux Server)                                │
│                                                       │
│  V-Ninja (clash-ninja)  ──── xvfb (虚拟显示)          │
│    └── ninja-mihomo     ──── 代理端口 0.0.0.0:6789    │
│                              API 端口 127.0.0.1:9097  │
│    └── socat            ──── API 转发 0.0.0.0:9098    │
│                                                       │
│  ┌─ Docker ─────────────────────────────────────────┐ │
│  │  worker  ── http://host.docker.internal:6789 ──► │ │
│  │  beat    ── http://host.docker.internal:9098 ──► │ │
│  │  (国内 LLM: 直连, 海外 LLM: 走代理)              │ │
│  └──────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

## 为什么不在 Docker 里运行

DOGESS VPN 使用私有 **Ninja 协议**（魔改 VLESS），只有 `ninja-mihomo`（闭源 Go 二进制）支持。经过大量尝试，确认以下方案均不可行：

| 尝试过的方案 | 结果 | 原因 |
|---|---|---|
| Docker 内运行 ninja-mihomo + proxy-provider | 加载 0 个节点 | proxy-provider 不支持 ninja 类型 |
| Docker 内运行 ninja-mihomo + inline proxies | DNS 解析失败 | cnameip.xyz 域名在公网 DNS 返回 NXDOMAIN |
| DOH/UDP DNS 解析 cnameip.xyz | 全部 NXDOMAIN | 这些域名只在 DOGESS 私有 DNS 存在 |
| 直接替换域名为 relay IP | 端口不通 | 订阅中的端口在 relay IP 上未开放 |
| 订阅转换器 (bianyuan.xyz) | 403 Access Denied | DOGESS 订阅服务器 IP 白名单限制 |

**唯一可行方案**：V-Ninja（官方 GUI 客户端）运行在宿主机上，它内部处理私有 DNS 和协议协商。

## 安装步骤

### 1. 上传文件到服务器

```bash
# 上传 V-Ninja .deb 安装包
scp V-Ninja_2.3.1_amd64.deb root@server:/opt/genpano/

# 上传订阅文件（从 Windows 客户端导出）
scp RPYnGYJDBZA6.yaml root@server:/root/.local/share/io.github.clash-verge-ninja.clash-verge-ninja/profiles/
```

### 2. 运行安装脚本

```bash
cd /opt/genpano
bash clash/setup-vninja-host.sh
```

脚本自动完成：安装 .deb → 安装 GUI 依赖 → 配置 systemd → 启动服务 → 开启 allow-lan → 启动 socat API 转发。

### 3. 配置订阅

如果是首次安装，需要手动配置订阅：

```bash
VNINJA_DIR=/root/.local/share/io.github.clash-verge-ninja.clash-verge-ninja

# 创建 profiles.yaml
cat > "$VNINJA_DIR/profiles.yaml" << 'EOF'
current: RPYnGYJDBZA6
chain:
  - Merge
items:
- uid: RPYnGYJDBZA6
  type: remote
  name: DOGESS
  url: https://YOUR_SUBSCRIPTION_URL
  file: RPYnGYJDBZA6.yaml
  updated: 0
- uid: Merge
  type: merge
  name: null
  file: Merge.yaml
  updated: 0
EOF

# Merge 配置（强制 allow-lan）
echo "allow-lan: true" > "$VNINJA_DIR/profiles/Merge.yaml"
```

### 4. 验证

```bash
# 代理测试
curl -x http://127.0.0.1:6789 https://httpbin.org/ip

# Docker 容器代理测试
cd /opt/genpano && docker compose exec worker curl -x http://host.docker.internal:6789 -s https://httpbin.org/ip

# API 测试（节点切换需要）
docker compose exec worker curl -s http://host.docker.internal:9098/proxies -H "Authorization: Bearer set-your-secret" | head -c 100
```

## 踩坑记录

### 1. 二进制文件名不是 `v-ninja`

.deb 安装后没有 `/usr/bin/v-ninja`，实际的 GUI 主程序是 `/usr/bin/clash-ninja`（可通过 `cat /usr/share/applications/Clash\ V-Ninja.desktop` 中的 `Exec=` 确认）。

### 2. V-Ninja 检测到旧实例

启动时报 `检测到已有应用实例运行` 然后退出。解决：

```bash
pkill -f clash-ninja
pkill -f ninja-mihomo
sleep 2
systemctl start vninja
```

### 3. allow-lan 不持久

V-Ninja 每次启动都重新生成运行时配置，`allow-lan` 始终为 `false`，Merge.yaml 中的 `allow-lan: true` 不生效。

**解决方案**：systemd ExecStartPost 调用 `vninja-allow-lan.sh`，通过 API 轮询开启：

```bash
curl -X PATCH http://127.0.0.1:9097/configs \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer set-your-secret" \
  -d '{"allow-lan": true}'
```

### 4. API 端口只监听 127.0.0.1

`external-controller` 固定监听 `127.0.0.1:9097`，无法通过 API 修改。Docker 容器无法访问。

**解决方案**：socat 转发

```bash
socat TCP-LISTEN:9098,bind=0.0.0.0,fork,reuseaddr TCP:127.0.0.1:9097 &
```

`vninja-allow-lan.sh` 启动时自动创建转发。

### 5. Ninja 节点在 API 中显示为 Unknown

ninja-mihomo API 返回节点类型为 `Unknown` 而非 `Ninja`，但不影响功能。节点实际上正常工作。

### 6. 代理组名称不匹配

Worker 代码中硬编码 `🍃 Proxies`，但 V-Ninja 订阅中的 AI 代理组叫 `💬 Ai平台`。导致节点切换找不到组，全部失败。

**解决方案**：改为从环境变量 `CLASH_PROXY_GROUP` 读取。

### 7. cnameip.xyz 域名全球 NXDOMAIN

DOGESS 的代理节点域名（如 `static-tun-auto-mnphft.cdn.cnameip.xyz`）在所有公网 DNS（包括 8.8.8.8、1.1.1.1、223.5.5.5、DOH）都返回 NXDOMAIN。这些域名只在 DOGESS 私有网络内部可解析，V-Ninja 内部处理解析。

### 8. curl 测试 ChatGPT 始终 403

这是 Cloudflare JS Challenge，不是 IP 被封。curl 无法执行 JavaScript，永远返回 403。Worker 使用 Camoufox 浏览器，能正常通过 Challenge。不要用 `curl https://chatgpt.com` 的 HTTP 状态码判断代理是否可用。

### 9. UFW 默认拒绝丢弃 docker bridge -> :9098 / :6789 SYN

宿主机若启用 UFW（`Default: deny (incoming), deny (routed)`）并且未为这两个端口配置 allow 规则，worker 容器（位于 `genpano_default` 网桥，172.18.0.0/16）发往宿主机的 SYN 会被 INPUT 链 DROP，curl 表现为 connection timed out（不是 refused）。ninja-mihomo 和 socat 进程本身是健康的——`curl http://127.0.0.1:9098/proxies` 在宿主机上立刻返回 401。

涉及的两个端口与症状：

| 端口 | 服务 | 用途 | 被挡时的 `queries.retry_reason` |
|---|---|---|---|
| 9098 | socat → ninja-mihomo `:9097` | Clash external-controller API（preflight 用） | `proxy_api_unreachable`（`latency_ms ≈ 10043`，命中 `httpx.AsyncClient(timeout=10)`）|
| 6789 | ninja-mihomo mixed-port | 实际 HTTP/SOCKS 代理（浏览器走这里） | `page_load_failed` / `no_response` / `browser_timeout` |

只有 ChatGPT 命中 9098 路径——`_requires_global_proxy_route` 默认仅对 chatgpt 返回 True（参见 `geo_tracker/agent/guest_executor.py:397-411`）。所有海外 LLM 都用 6789。

**解决方案**：`vninja-allow-lan.sh` 在 socat 启动后追加幂等 UFW 规则

```bash
ufw allow proto tcp from 172.16.0.0/12 to any port 9098
ufw allow proto tcp from 172.16.0.0/12 to any port 6789
```

`172.16.0.0/12` 覆盖 docker 默认网桥子网 (172.17–172.31)；不影响公网入站。脚本由 `vninja.service` 的 `ExecStartPost` 在每次开机时调用，所以重启后规则会被重新加上。手动验证：

```bash
sudo ufw status | grep -E '9098|6789'
docker compose exec worker curl -sS --max-time 3 -o /dev/null -w "%{http_code}\n" http://host.docker.internal:9098/proxies   # 期望 401（有鉴权）
docker compose exec worker curl -sS --max-time 12 -o /dev/null --proxy http://host.docker.internal:6789 -w "%{http_code}\n" https://chatgpt.com/   # 期望 403（Cloudflare JS challenge，TCP 通了）
```

### 9. docker compose 的 WARN 日志

Cookie JSON 值中包含 `$o1`、`$g1` 等字符串，docker compose 将其当作变量引用。解决：写入 `.env` 时将 `$` 转义为 `$$`。

### 10. socat 需要单独安装

socat 不是系统预装软件，CI/CD 部署时可能被清理。deploy.yml 中需要检测并安装。

## 日常运维

```bash
# 查看 V-Ninja 状态
systemctl status vninja

# 查看日志
journalctl -u vninja -f

# 重启代理
systemctl restart vninja

# 手动切换节点（API）
curl -X PUT "http://127.0.0.1:9097/proxies/💬 Ai平台" \
  -H "Authorization: Bearer set-your-secret" \
  -H "Content-Type: application/json" \
  -d '{"name":"日本 01（公网；智能）"}'

# 查看当前出口 IP
curl -x http://127.0.0.1:6789 https://httpbin.org/ip

# 查看所有存活节点
curl -s http://127.0.0.1:9097/proxies -H "Authorization: Bearer set-your-secret" | \
  python3 -c "
import json,sys
d=json.load(sys.stdin)
for k,v in d.get('proxies',{}).items():
    if v.get('type')=='Unknown' and v.get('alive'):
        print(k)
"
```

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `CLASH_PROXY_URL` | `http://host.docker.internal:6789` | 代理地址 |
| `CLASH_API_URL` | `http://host.docker.internal:9098` | API 地址（socat 转发） |
| `CLASH_PROXY_GROUP` | `💬 Ai平台` | 节点切换的代理组名称 |
| `PROXY_PROVIDER` | `clash` | 代理类型 |
