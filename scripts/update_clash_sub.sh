#!/usr/bin/env bash
# 更新 Clash 代理订阅
# 用法:
#   bash scripts/update_clash_sub.sh                          # 用配置里的默认链接
#   bash scripts/update_clash_sub.sh "https://xxx?clash=1"    # 指定新链接

set -euo pipefail

CLASH_DIR="${CLASH_DIR:-/opt/genpano/clash}"
CONFIG_FILE="$CLASH_DIR/config.yaml"
PROVIDER_FILE="$CLASH_DIR/proxies/ninja.yaml"

# 订阅链接：优先用参数传入，否则从 config.yaml 提取
SUB_URL="${1:-}"
if [ -z "$SUB_URL" ]; then
    SUB_URL=$(grep -A2 'ninja-sub' "$CONFIG_FILE" | grep 'url:' | sed 's/.*url: *"//;s/".*//' | head -1)
fi

if [ -z "$SUB_URL" ]; then
    echo "✗ 未找到订阅链接，请传入参数: bash $0 \"https://your-sub-url\""
    exit 1
fi

echo "=== Clash 订阅更新 ==="
echo "订阅链接: $SUB_URL"

# 1. 下载订阅
echo ""
echo "[1/4] 下载订阅..."
TMP_FILE=$(mktemp /tmp/clash_sub_XXXXX.yaml)
HTTP_CODE=$(curl -sf -o "$TMP_FILE" -w "%{http_code}" --connect-timeout 15 --max-time 30 "$SUB_URL" 2>/dev/null || echo "000")

if [ "$HTTP_CODE" != "200" ] || [ ! -s "$TMP_FILE" ]; then
    echo "  ✗ 下载失败 (HTTP $HTTP_CODE)"
    rm -f "$TMP_FILE"
    exit 1
fi
echo "  ✓ 下载成功 ($(wc -c < "$TMP_FILE") bytes)"

# 2. 提取 proxies 段，生成纯代理列表文件（proxy-provider 格式）
echo ""
echo "[2/4] 提取代理节点..."
python3 -c "
import yaml, sys

with open('$TMP_FILE', 'r') as f:
    data = yaml.safe_load(f)

proxies = data.get('proxies', [])
if not proxies:
    print('  ✗ 订阅中未找到 proxies 段')
    sys.exit(1)

# 验证节点有效性
valid = [p for p in proxies if p.get('server') and p.get('port')]
print(f'  总节点: {len(proxies)}, 有效: {len(valid)}')

if not valid:
    print('  ✗ 没有有效节点（server/port 为空）')
    sys.exit(1)

# 写入纯代理列表（proxy-provider 格式）
output = {'proxies': valid}
with open('$PROVIDER_FILE', 'w') as f:
    yaml.dump(output, f, allow_unicode=True, default_flow_style=False)

print(f'  ✓ 已写入 $PROVIDER_FILE')

# 打印前5个节点
for p in valid[:5]:
    print(f'    {p[\"name\"]:30s} {p.get(\"server\",\"?\")}:{p.get(\"port\",\"?\")}  type={p.get(\"type\",\"?\")}')
if len(valid) > 5:
    print(f'    ... 共 {len(valid)} 个节点')
"

if [ $? -ne 0 ]; then
    rm -f "$TMP_FILE"
    exit 1
fi

rm -f "$TMP_FILE"

# 3. 确保 config.yaml 用 type: file（不让 Clash 自动用 http 覆盖）
echo ""
echo "[3/4] 更新配置..."

# 检查当前是否还是 type: http，改成 type: file
if grep -q 'type: http' "$CONFIG_FILE" 2>/dev/null; then
    # 把 proxy-provider 从 http 改成 file，避免 Clash 自动下载覆盖我们处理好的文件
    sed -i 's/type: http/type: file/' "$CONFIG_FILE"
    # 注释掉 url 和 interval（file 类型不需要）
    sed -i '/ninja-sub/,/health-check/{
        s/^\(\s*\)url: /\1# url: /
        s/^\(\s*\)interval: /\1# interval: /
    }' "$CONFIG_FILE"
    echo "  ✓ proxy-provider 已从 http 改为 file（防止自动覆盖）"
else
    echo "  ✓ 配置已是 file 类型，无需修改"
fi

# 4. 重启 Clash
echo ""
echo "[4/4] 重启 Clash..."
cd /opt/genpano
docker compose restart clash 2>/dev/null || docker-compose restart clash 2>/dev/null
sleep 8

# 验证
CLASH_IP=$(docker inspect genpano-clash-1 --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' 2>/dev/null || echo "")
if [ -z "$CLASH_IP" ]; then
    echo "  ⚠ 无法获取 Clash 容器 IP，请手动验证"
else
    echo ""
    echo "=== 验证 ==="
    # 触发健康检查
    curl -sf "http://$CLASH_IP:9090/providers/proxies/ninja-sub/healthcheck" > /dev/null 2>&1 || true
    sleep 5

    curl -s "http://$CLASH_IP:9090/providers/proxies/ninja-sub" 2>/dev/null | python3 -c "
import json,sys
data=json.load(sys.stdin)
proxies=data.get('proxies',[])
alive=[p for p in proxies if p.get('alive')]
print(f'总节点: {len(proxies)}, 存活: {len(alive)}')
for p in alive[:5]:
    h=p.get('history',[{}])
    d=h[-1].get('delay',0) if h else 0
    print(f'  ✓ {p[\"name\"]:30s} {d}ms')
if len(alive) > 5:
    print(f'  ... 共 {len(alive)} 个存活')
if not alive:
    print('  ⚠ 0 存活，等待健康检查完成后再试:')
    print(f'    curl http://{\"$CLASH_IP\"}:9090/providers/proxies/ninja-sub/healthcheck')
" 2>/dev/null || echo "  ⚠ 无法读取节点状态"

    # 测试 ChatGPT
    echo ""
    echo "测试 ChatGPT 连通性..."
    HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" \
        -x http://localhost:7890 --connect-timeout 10 --max-time 15 \
        https://chatgpt.com 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" != "000" ]; then
        echo "  ✓ ChatGPT 可达 (HTTP $HTTP_CODE)"
    else
        echo "  ✗ ChatGPT 仍不可达"
    fi
fi

echo ""
echo "=== 完成 ==="
echo ""
echo "以后更新订阅只需:"
echo "  bash /opt/genpano/scripts/update_clash_sub.sh"
echo "  bash /opt/genpano/scripts/update_clash_sub.sh \"https://新链接\""
