#!/bin/bash
# setup_gadget.sh — 一次性配置 RK3588 USB Gadget (ConfigFS + FunctionFS)
# 使用前确认: 当前的 UDC (USB Device Controller) 没有被其他 gadget 占用
# 查看可用 UDC: ls /sys/class/udc/

set -e

echo "=== TUN_NAT_HUB USB Gadget 配置 ==="

# 加载内核模块
modprobe libcomposite 2>/dev/null || echo "libcomposite 已加载"
modprobe usb_f_fs 2>/dev/null    || echo "usb_f_fs 已加载"

# 先解绑现有 gadget (如果存在)
GADGET=/sys/kernel/config/usb_gadget/tun_nat
if [ -d "$GADGET" ]; then
    echo "清理已有 gadget..."
    if [ -f "$GADGET/UDC" ]; then
        echo "" > "$GADGET/UDC" 2>/dev/null || true
    fi
    # 移除符号链接
    rm -f "$GADGET/configs/c.1/ffs.tun_nat" 2>/dev/null || true
    rmdir "$GADGET/configs/c.1/strings/0x409" 2>/dev/null || true
    rmdir "$GADGET/configs/c.1" 2>/dev/null || true
    rmdir "$GADGET/functions/ffs.tun_nat" 2>/dev/null || true
    rmdir "$GADGET/strings/0x409" 2>/dev/null || true
    rmdir "$GADGET" 2>/dev/null || true
fi

# 卸载 FunctionFS 挂载点（如果已挂载）
if mountpoint -q /dev/usb-ffs/tun_nat 2>/dev/null; then
    umount /dev/usb-ffs/tun_nat
fi
rm -rf /dev/usb-ffs/tun_nat

echo "创建 USB Gadget 实例..."
mkdir -p $GADGET

# ── USB 设备描述符 ──────────────────────────────
echo "0x2207" > $GADGET/idVendor           # 自定义 VID (Rockchip 预留范围)
echo "0x0010" > $GADGET/idProduct          # 自定义 PID
echo "0x0200" > $GADGET/bcdUSB             # USB 2.0
echo "0x0100" > $GADGET/bcdDevice          # 设备版本 1.0

# ── 设备字符串 ──────────────────────────────────
mkdir -p $GADGET/strings/0x409
echo "RK3588"         > $GADGET/strings/0x409/manufacturer
echo "TUN NAT Hub"    > $GADGET/strings/0x409/product
echo "TUNNATHUB2024"  > $GADGET/strings/0x409/serialnumber

# ── 配置描述符 ──────────────────────────────────
mkdir -p $GADGET/configs/c.1/strings/0x409
echo "Bulk Transfer"  > $GADGET/configs/c.1/strings/0x409/configuration
echo "500"            > $GADGET/configs/c.1/MaxPower    # 500mA

# ── FunctionFS 实例 ──────────────────────────────
mkdir -p $GADGET/functions/ffs.tun_nat

# 挂载 FunctionFS
mkdir -p /dev/usb-ffs/tun_nat
mount -t functionfs tun_nat /dev/usb-ffs/tun_nat

# 链接 function 到配置
ln -s $GADGET/functions/ffs.tun_nat $GADGET/configs/c.1/

echo "Gadget 配置完成。"
echo "启动守护进程后将自动激活 UDC。"
echo ""
echo "手动激活命令（守护进程启动后）:"
echo "  UDC=\$(ls /sys/class/udc/ | head -1)"
echo "  echo \$UDC > $GADGET/UDC"
echo ""
echo "查看 gadget 状态:"
echo "  ls $GADGET"
echo "  cat $GADGET/UDC"
