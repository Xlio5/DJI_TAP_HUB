#!/bin/bash
# deploy_ubuntu.sh — 部署 Ubuntu 服务端到 RK3588
# 用法: ./scripts/deploy_ubuntu.sh [target_ip]
# 默认目标: root@192.168.88.x (需在 RK3588 上配置 SSH)

set -e

TARGET_IP="${1:-192.168.88.200}"
TARGET="root@${TARGET_IP}"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/ubuntu/build/native"

echo "=== TUN_NAT_HUB 部署到 $TARGET ==="

# ── 检查构建产物 ────────────────────────────────
if [ ! -f "$BUILD_DIR/usb_tund" ]; then
    echo "错误: 未找到构建产物 $BUILD_DIR/usb_tund"
    echo "请先运行: ./scripts/build_all.sh"
    exit 1
fi

echo "--- 上传二进制文件 ---"
scp "$BUILD_DIR/usb_tund" "$TARGET:/usr/local/bin/usb_tund"
ssh "$TARGET" "chmod +x /usr/local/bin/usb_tund"

echo "--- 上传脚本 ---"
scp "$PROJECT_ROOT/ubuntu/scripts/setup_nat.sh" "$TARGET:/usr/local/bin/setup_nat.sh"
ssh "$TARGET" "chmod +x /usr/local/bin/setup_nat.sh"
scp "$PROJECT_ROOT/ubuntu/scripts/setup_gadget.sh" "$TARGET:/usr/local/bin/setup_gadget.sh"
ssh "$TARGET" "chmod +x /usr/local/bin/setup_gadget.sh"

echo "--- 安装 systemd 服务 ---"
scp "$PROJECT_ROOT/ubuntu/config/tun_nat_hub.service" "$TARGET:/etc/systemd/system/tun_nat_hub.service"
ssh "$TARGET" "systemctl daemon-reload"

echo "--- 执行一次性 Gadget 配置 ---"
ssh "$TARGET" "/usr/local/bin/setup_gadget.sh"

echo "--- 启动服务 ---"
ssh "$TARGET" "systemctl enable tun_nat_hub && systemctl restart tun_nat_hub"

echo "--- 检查服务状态 ---"
ssh "$TARGET" "systemctl status tun_nat_hub --no-pager" || true

echo ""
echo "=== 部署完成 ==="
echo "查看日志: ssh $TARGET journalctl -u tun_nat_hub -f"
