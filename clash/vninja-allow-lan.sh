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

# Allow docker bridge subnets to reach the socat forwarder (9098) AND
# the ninja-mihomo proxy port (6789). UFW default-deny incoming silently
# drops SYN packets from the worker container (genpano_default bridge,
# 172.18.0.0/16) to either port, which causes:
#   - port 9098: proxy_api_unreachable during proxy_route_preflight
#   - port 6789: browser navigation to chatgpt.com surfaces as
#     page_load_failed / no_response / browser_timeout
# 172.16.0.0/12 covers every default docker bridge (172.17-172.31).
# Idempotent: skip if already allowed; no-op if ufw isn't installed/active.
ufw_allow_docker_to_port () {
    local port="$1"
    if ufw status 2>/dev/null | grep -qE "${port}/tcp\\s+ALLOW IN\\s+172\\.16\\.0\\.0/12"; then
        echo "ufw: 172.16.0.0/12 -> :${port}/tcp already allowed"
        return 0
    fi
    if ufw allow proto tcp from 172.16.0.0/12 to any port "${port}" >/dev/null 2>&1; then
        echo "ufw: allowed 172.16.0.0/12 -> :${port}/tcp"
    else
        echo "ufw: failed to add allow rule for :${port}/tcp (run as root?)"
    fi
}

if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "^Status: active"; then
    ufw_allow_docker_to_port 9098
    ufw_allow_docker_to_port 6789
fi
