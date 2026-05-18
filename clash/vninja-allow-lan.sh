#!/bin/bash
# V-Ninja 启动后自动配置：
# 1. 开启 allow-lan（代理端口监听 0.0.0.0，Docker 容器可访问）
# 2. 启动 socat 转发 API 端口（external-controller 只能监听 127.0.0.1，
#    用 socat 转发到 0.0.0.0:9098 让 Docker 容器可以切换节点）

# 等待 API 就绪并开启 allow-lan
for i in $(seq 1 20); do
    sleep 3
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH http://127.0.0.1:9097/configs \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer set-your-secret" \
        -d '{"allow-lan": true}')
    if [ "$HTTP_CODE" = "204" ]; then
        echo "allow-lan enabled successfully"
        break
    fi
done

# 启动 socat 转发 API 端口 (127.0.0.1:9097 → 0.0.0.0:9098)
# 先杀掉旧的 socat 进程
pkill -f "socat.*TCP-LISTEN:9098" 2>/dev/null || true
sleep 1
socat TCP-LISTEN:9098,bind=0.0.0.0,fork,reuseaddr TCP:127.0.0.1:9097 &
echo "API forwarding started on 0.0.0.0:9098"

# Allow docker bridge subnets to reach the socat forwarder.
# UFW default-deny incoming silently drops SYN packets from the worker
# container (genpano_default bridge, 172.18.0.0/16) to host:9098, which
# causes proxy_api_unreachable on every ChatGPT proxy_route_preflight.
# 172.16.0.0/12 covers every default docker bridge (172.17-172.31).
# Idempotent: skip if already allowed; no-op if ufw isn't installed/active.
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "^Status: active"; then
    if ufw status 2>/dev/null | grep -qE '9098/tcp\s+ALLOW IN\s+172\.16\.0\.0/12'; then
        echo "ufw: 172.16.0.0/12 -> :9098/tcp already allowed"
    else
        ufw allow proto tcp from 172.16.0.0/12 to any port 9098 >/dev/null 2>&1 \
            && echo "ufw: allowed 172.16.0.0/12 -> :9098/tcp" \
            || echo "ufw: failed to add allow rule (run as root?)"
    fi
fi
