#!/bin/bash
# setup_raw_bulk.sh — 创建纯 Bulk 端点 USB Gadget (非 CDC ACM)
# 使用 configfs + ffs (FunctionFS) 函数
set -e

GADGET=/sys/kernel/config/usb_gadget/g_raw

echo "=== Cleanup ==="
# Unbind
for g in /sys/kernel/config/usb_gadget/*/UDC; do
    [ -f "$g" ] && echo "" > "$g" 2>/dev/null || true
done
sleep 1

# Remove old
for g in /sys/kernel/config/usb_gadget/g_raw /sys/kernel/config/usb_gadget/tun_nat /sys/kernel/config/usb_gadget/tun_acm; do
    if [ -d "$g" ]; then
        for l in "$g"/configs/c.1/*; do [ -L "$l" ] && rm -f "$l" 2>/dev/null; done
        rmdir "$g"/configs/c.1/strings/0x409 2>/dev/null || true
        rmdir "$g"/configs/c.1 2>/dev/null || true
        rmdir "$g"/functions/ffs.raw 2>/dev/null || true
        rmdir "$g"/strings/0x409 2>/dev/null || true
        rmdir "$g" 2>/dev/null || true
    fi
done

echo "=== Create new gadget ==="
mkdir -p $GADGET
echo "0x2207" > $GADGET/idVendor
echo "0x0010" > $GADGET/idProduct
echo "0x0200" > $GADGET/bcdUSB
echo "0x0100" > $GADGET/bcdDevice

mkdir -p $GADGET/strings/0x409
echo "RK3588"         > $GADGET/strings/0x409/manufacturer
echo "TUN NAT Hub"    > $GADGET/strings/0x409/product
echo "TUNNATHUB2024"  > $GADGET/strings/0x409/serialnumber

mkdir -p $GADGET/configs/c.1/strings/0x409
echo "RAW Bulk"    > $GADGET/configs/c.1/strings/0x409/configuration
echo "500"         > $GADGET/configs/c.1/MaxPower

# Use FunctionFS
mkdir -p $GADGET/functions/ffs.raw
mkdir -p /dev/ffs-raw
mount -t functionfs raw /dev/ffs-raw 2>/dev/null || true
ln -sf $GADGET/functions/ffs.raw $GADGET/configs/c.1/

# Activate UDC
UDC=$(ls /sys/class/udc/ | head -1)
if [ -n "$UDC" ]; then
    echo "$UDC" > $GADGET/UDC
    echo "Gadget g_raw bound to $UDC"
fi

echo "=== Done ==="
ls -la /dev/ffs-raw/
