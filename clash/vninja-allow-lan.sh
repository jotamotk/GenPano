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
