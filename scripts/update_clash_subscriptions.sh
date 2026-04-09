#!/usr/bin/env bash
# 手动/自动更新 Clash 代理订阅 + 健康检查
# 用法:
#   手动: bash scripts/update_clash_subscriptions.sh
#   自动: 加入 crontab (见底部说明)

set -euo pipefail

CLASH_API="${CLASH_API:-http://localhost:9090}"
CLASH_SECRET="${CLASH_SECRET:-}"
AUTH_HEADER=""
if [ -n "$CLASH_SECRET" ]; then
    AUTH_HEADER="-H \"Authorization: Bearer $CLASH_SECRET\""
fi

echo "=== $(date) === Clash 订阅更新开始 ==="

# 1. 触发 proxy-provider 订阅更新
echo "[1/4] 触发订阅更新..."
PROVIDERS=$(curl -sf $CLASH_API/providers/proxies $AUTH_HEADER 2>/dev/null || echo "")
if [ -z "$PROVIDERS" ]; then
    echo "  ⚠ 无法连接 Clash API ($CLASH_API)"
    echo "  尝试通过 docker 访问..."
    CLASH_API="http://clash:9090"
    # 如果是在宿主机上跑，需要通过 docker exec
    PROVIDERS=$(docker compose exec -T clash curl -sf http://localhost:9090/providers/proxies 2>/dev/null || echo "")
    if [ -z "$PROVIDERS" ]; then
        echo "  ✗ Clash API 不可达，退出"
        exit 1
    fi
fi

# 提取所有 provider 名称并逐个更新
PROVIDER_NAMES=$(echo "$PROVIDERS" | python3 -c "
import json,sys
data=json.load(sys.stdin)
for name in data.get('providers',{}):
    if name != 'default':
        print(name)
" 2>/dev/null || echo "")

if [ -z "$PROVIDER_NAMES" ]; then
    echo "  ⚠ 未找到 proxy-provider"
else
    for name in $PROVIDER_NAMES; do
        echo "  更新 provider: $name"
        HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" \
            -X PUT "$CLASH_API/providers/proxies/$name" $AUTH_HEADER 2>/dev/null || echo "000")
        if [ "$HTTP_CODE" = "204" ] || [ "$HTTP_CODE" = "200" ]; then
            echo "  ✓ $name 更新成功"
        else
            echo "  ✗ $name 更新失败 (HTTP $HTTP_CODE)"
        fi
    done
fi

# 等待订阅更新完成
sleep 3

# 2. 查看当前可用节点
echo ""
echo "[2/4] 当前可用节点:"
curl -sf "$CLASH_API/providers/proxies" $AUTH_HEADER 2>/dev/null | python3 -c "
import json,sys
data=json.load(sys.stdin)
for pname, pinfo in data.get('providers',{}).items():
    if pname == 'default': continue
    proxies = pinfo.get('proxies',[])
    alive = [p for p in proxies if p.get('alive', False)]
    dead = [p for p in proxies if not p.get('alive', False)]
    print(f'  {pname}: {len(alive)} alive / {len(dead)} dead / {len(proxies)} total')
    for p in alive[:10]:
        delay = p.get('history',[-1])
        last_delay = delay[-1].get('delay',0) if delay else 0
        print(f'    ✓ {p[\"name\"]:30s} {last_delay:>5d}ms')
    if len(alive) > 10:
        print(f'    ... 还有 {len(alive)-10} 个')
" 2>/dev/null || echo "  ⚠ 无法获取节点列表"

# 3. 测试 ChatGPT 连通性
echo ""
echo "[3/4] 测试 ChatGPT 连通性..."
HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" \
    -x http://localhost:7890 --connect-timeout 10 --max-time 15 \
    https://chatgpt.com 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "403" ] || [ "$HTTP_CODE" = "301" ] || [ "$HTTP_CODE" = "302" ]; then
    echo "  ✓ ChatGPT 可达 (HTTP $HTTP_CODE)"
else
    echo "  ✗ ChatGPT 不可达 (HTTP $HTTP_CODE)"
    echo "  可能原因: 所有节点都被 Cloudflare 封了，需要换机场/订阅"
fi

# 4. 测试 Google (Gemini) 连通性
echo ""
echo "[4/4] 测试 Google 连通性..."
HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" \
    -x http://localhost:7890 --connect-timeout 10 --max-time 15 \
    https://gemini.google.com 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "301" ] || [ "$HTTP_CODE" = "302" ]; then
    echo "  ✓ Google 可达 (HTTP $HTTP_CODE)"
else
    echo "  ✗ Google 不可达 (HTTP $HTTP_CODE)"
fi

echo ""
echo "=== 完成 ==="

# ──────────────────────────────────────────────
# 自动化: 加入 crontab，每 6 小时更新一次
#
#   crontab -e
#   0 */6 * * * cd /opt/genpano && bash scripts/update_clash_subscriptions.sh >> logs/clash_update.log 2>&1
#
# 或者加入 docker-compose 作为 sidecar:
#   见 README
# ──────────────────────────────────────────────
