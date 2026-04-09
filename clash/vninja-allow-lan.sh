#!/bin/bash
# V-Ninja 启动后自动开启 allow-lan（监听 0.0.0.0）
# ninja-mihomo 默认监听 127.0.0.1，Docker 容器无法访问
# 通过 API 在启动后修改为 allow-lan: true
for i in $(seq 1 20); do
    sleep 3
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH http://127.0.0.1:9097/configs \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer set-your-secret" \
        -d '{"allow-lan": true}')
    if [ "$HTTP_CODE" = "204" ]; then
        echo "allow-lan enabled successfully"
        exit 0
    fi
done
echo "Failed to enable allow-lan"
exit 1
