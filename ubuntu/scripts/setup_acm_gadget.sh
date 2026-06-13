#!/bin/bash
# setup_acm_gadget.sh — 使用 CDC ACM (USB 串口) 替代 FunctionFS
# CDC ACM 提供 2 个 Bulk 端点 (IN + OUT)，内核自动处理 USB 枚举
# 用户态只需读写 /dev/ttyGS0

set -e
echo "=== TUN_NAT_HUB ACM Gadget 配置 ==="

GADGET=/sys/kernel/config/usb_gadget/tun_acm

# 清理旧配置
if [ -d "$GADGET" ]; then
    echo "清理旧 gadget..."
    [ -f "$GADGET/UDC" ] && echo "" > "$GADGET/UDC" 2>/dev/null || true
    rm -f "$GADGET/configs/c.1/acm.0" 2>/dev/null || true
    rmdir "$GADGET/configs/c.1/strings/0x409" 2>/dev/null || true
    rmdir "$GADGET/configs/c.1" 2>/dev/null || true
    rmdir "$GADGET/functions/acm.0" 2>/dev/null || true
    rmdir "$GADGET/strings/0x409" 2>/dev/null || true
    rmdir "$GADGET" 2>/dev/null || true
fi

# 卸载占用 UDC 的驱动
modprobe -r g_serial 2>/dev/null || true

echo "创建 ACM Gadget..."
mkdir -p $GADGET

echo "0x2207" > $GADGET/idVendor
echo "0x0010" > $GADGET/idProduct
echo "0x0200" > $GADGET/bcdUSB
echo "0x0100" > $GADGET/bcdDevice

mkdir -p $GADGET/strings/0x409
echo "RK3588"         > $GADGET/strings/0x409/manufacturer
echo "TUN NAT Hub"    > $GADGET/strings/0x409/product
echo "TUNNATHUB2024"  > $GADGET/strings/0x409/serialnumber

# 配置
mkdir -p $GADGET/configs/c.1/strings/0x409
echo "ACM Bulk"  > $GADGET/configs/c.1/strings/0x409/configuration
echo "500"       > $GADGET/configs/c.1/MaxPower

# ACM 函数 (CDC ACM = 2 Bulk endpoints + 1 Interrupt)
mkdir -p $GADGET/functions/acm.0
ln -s $GADGET/functions/acm.0 $GADGET/configs/c.1/ 2>/dev/null || true

# 激活 UDC
UDC=$(ls /sys/class/udc/ | head -1)
if [ -n "$UDC" ]; then
    echo "$UDC" > $GADGET/UDC
    echo "UDC 已绑定: $UDC"
else
    echo "警告: 无可用 UDC"
fi

echo ""
echo "=== ACM Gadget 配置完成 ==="
echo "设备节点: /dev/ttyGS0"
echo "Android 端会看到: VID=0x2207 PID=0x0010 CDC ACM 设备"

# 检查
ls -la /dev/ttyGS* 2>&1 || echo "ttyGS0 将在 UDC 激活后出现"
cat $GADGET/UDC 2>&1
