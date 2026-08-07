#!/bin/bash
# 配置 sunxi-fel udev 规则, 授权 USB 访问
set -e
echo "=== 检查 udev 规则目录 ==="
ls /etc/udev/rules.d/ 2>&1 | head

echo "=== 写入 Allwinner FEL udev 规则 ==="
cat > /etc/udev/rules.d/99-sunxi-fel.rules <<'EOF'
# Allwinner FEL mode USB
SUBSYSTEM=="usb", ATTR{idVendor}=="1f3a", MODE="0666"
EOF
chmod 644 /etc/udev/rules.d/99-sunxi-fel.rules
cat /etc/udev/rules.d/99-sunxi-fel.rules

echo "=== 重载 udev 规则 ==="
udevadm control --reload-rules 2>&1 || true
udevadm trigger 2>&1 || true

echo "=== 重新绑定设备权限 ==="
# 重新插拔等价: 让 udev 重新应用权限
sleep 1

echo "=== 测试 sunxi-fel ==="
sunxi-fel list 2>&1 || true

echo "=== 如果还是权限问题, 尝试 chmod 设备节点 ==="
ls -la /dev/bus/usb/001/002 2>&1 || true
chmod 666 /dev/bus/usb/001/002 2>&1 || true
sunxi-fel list 2>&1 || true
echo "DONE"
