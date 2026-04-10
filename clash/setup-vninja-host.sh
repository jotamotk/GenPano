#!/bin/bash
# V-Ninja 宿主机安装脚本
# 在服务器上运行，安装 V-Ninja 及其依赖，配置 systemd 自启动
#
# 用法:
#   sudo bash setup-vninja-host.sh /path/to/V-Ninja_2.3.1_amd64.deb
#
# 前提条件:
#   - Ubuntu/Debian 系统
#   - 已有 V-Ninja .deb 安装包
#   - 已有 DOGESS 订阅文件 (raw_sub.yaml)

set -e

DEB_FILE="${1:-/opt/genpano/V-Ninja_2.3.1_amd64.deb}"
VNINJA_DATA_DIR="/root/.local/share/io.github.clash-verge-ninja.clash-verge-ninja"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "═══════════════════════════════════════════════════"
echo "  V-Ninja 宿主机安装脚本"
echo "═══════════════════════════════════════════════════"

# 1. 检查 .deb 文件
if [ ! -f "$DEB_FILE" ]; then
    echo "✗ 未找到 V-Ninja 安装包: $DEB_FILE"
    echo "  用法: $0 /path/to/V-Ninja_xxx_amd64.deb"
    exit 1
fi
echo "✓ 安装包: $DEB_FILE"

# 2. 安装 V-Ninja .deb
echo ""
echo "── 安装 V-Ninja ──────────────────────────────────"
dpkg -i "$DEB_FILE" 2>/dev/null || true
apt-get install -f -y --no-install-recommends

# 3. 安装 GUI 依赖 (V-Ninja 是 Tauri 应用，需要 WebKit)
echo ""
echo "── 安装 GUI 依赖 ─────────────────────────────────"
apt-get update -qq
apt-get install -y --no-install-recommends \
    xvfb \
    libwebkit2gtk-4.0-37 \
    libgtk-3-0 \
    libayatana-appindicator3-1 \
    libjavascriptcoregtk-4.0-18 \
    dbus-x11 \
    socat
echo "✓ GUI 依赖安装完成"

# 4. 验证二进制文件
echo ""
echo "── 验证安装 ──────────────────────────────────────"
for bin in clash-ninja clash-ninja-service ninja-mihomo; do
    if command -v "$bin" &>/dev/null; then
        echo "  ✓ $bin: $(which $bin)"
    else
        echo "  ✗ $bin: 未找到"
    fi
done

# 5. 创建 V-Ninja 数据目录和配置
echo ""
echo "── 配置 V-Ninja ─────────────────────────────────"
mkdir -p "$VNINJA_DATA_DIR/profiles"

# 检查是否已有订阅配置
if [ -f "$VNINJA_DATA_DIR/profiles.yaml" ]; then
    echo "  ✓ profiles.yaml 已存在（保留现有配置）"
else
    echo "  ⚠ profiles.yaml 不存在"
    echo "    请手动配置订阅或复制 raw_sub.yaml 到 profiles 目录"
fi

# 6. 安装 allow-lan 脚本和 systemd 服务
echo ""
echo "── 安装 systemd 服务 ─────────────────────────────"
cp "$SCRIPT_DIR/vninja-allow-lan.sh" /usr/local/bin/vninja-allow-lan.sh
chmod +x /usr/local/bin/vninja-allow-lan.sh
cp "$SCRIPT_DIR/vninja.service" /etc/systemd/system/vninja.service
systemctl daemon-reload
systemctl enable vninja
echo "  ✓ vninja.service 已安装并启用"
echo "  ✓ vninja-allow-lan.sh 已安装"

# 7. 停止旧进程并启动服务
echo ""
echo "── 启动 V-Ninja ─────────────────────────────────"
pkill -f clash-ninja 2>/dev/null || true
pkill -f ninja-mihomo 2>/dev/null || true
sleep 2
systemctl start vninja

# 8. 等待代理端口就绪（含 allow-lan 生效时间）
echo ""
echo "── 等待代理端口 ─────────────────────────────────"
for i in $(seq 1 25); do
    if netstat -tlnp 2>/dev/null | grep -q ":::6789 " || \
       ss -tlnp 2>/dev/null | grep -q ":::6789 "; then
        echo "  ✓ 代理端口 6789 已就绪 (0.0.0.0)"
        break
    fi
    echo "  等待中... ($i/25)"
    sleep 3
done

# 9. 测试代理
echo ""
echo "── 测试代理连通性 ─────────────────────────────────"
HTTP_CODE=$(curl -x http://127.0.0.1:6789 -s --max-time 15 -o /dev/null -w "%{http_code}" https://www.google.com 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    echo "  ✓ 代理测试成功 (Google: HTTP $HTTP_CODE)"
elif [ "$HTTP_CODE" != "000" ]; then
    echo "  ~ 代理有响应 (Google: HTTP $HTTP_CODE)，可能需要等待节点健康检查"
else
    echo "  ⚠ 代理暂时无法连接，可能需要等待节点上线"
    echo "  手动测试: curl -x http://127.0.0.1:6789 https://www.google.com"
fi

echo ""
echo "═══════════════════════════════════════════════════"
echo "  安装完成！"
echo ""
echo "  代理地址: http://0.0.0.0:6789"
echo "  API 地址: http://127.0.0.1:9097"
echo ""
echo "  Docker 容器通过 host.docker.internal:6789 访问代理"
echo "  管理命令:"
echo "    systemctl status vninja    # 查看状态"
echo "    systemctl restart vninja   # 重启服务"
echo "    journalctl -u vninja -f    # 查看日志"
echo "═══════════════════════════════════════════════════"
