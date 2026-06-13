#!/bin/bash
# switch_to_raw.sh — 切换到非ACM纯Bulk模式
set -e

echo "=== Stop daemon ==="
systemctl stop tun_nat_hub 2>/dev/null || true

echo "=== Unbind gadgets ==="
for g in /sys/kernel/config/usb_gadget/*/UDC; do
    [ -f "$g" ] && echo "" > "$g" 2>/dev/null || true
done
sleep 1

echo "=== Clean configfs ==="
for g in /sys/kernel/config/usb_gadget/tun_* /sys/kernel/config/usb_gadget/g_raw; do
    [ -d "$g" ] || continue
    for l in "$g"/configs/c.1/*; do [ -L "$l" ] && rm -f "$l" 2>/dev/null; done
    rmdir "$g"/configs/c.1/strings/0x409 2>/dev/null || true
    rmdir "$g"/configs/c.1 2>/dev/null || true
    for fdir in "$g"/functions/*; do rmdir "$fdir" 2>/dev/null || true; done
    rmdir "$g"/strings/0x409 2>/dev/null || true
    rmdir "$g" 2>/dev/null || true
done
rm -rf /dev/ffs-* 2>/dev/null || true

echo "=== Unload old ==="
modprobe -r g_serial 2>/dev/null || true
modprobe -r usb_f_fs 2>/dev/null || true

echo "=== Try g_serial use_acm=0 ==="
UDC=$(ls /sys/class/udc/ | head -1)
modprobe g_serial use_acm=0 use_obex=0 idVendor=0x2207 idProduct=0x0010 2>&1 && echo "g_serial loaded" || {
    echo "g_serial failed, using configfs fallback"

    G=/sys/kernel/config/usb_gadget/g_raw
    mkdir -p $G
    echo "0x2207" > $G/idVendor
    echo "0x0010" > $G/idProduct
    echo "0x0200" > $G/bcdUSB

    mkdir -p $G/strings/0x409
    echo "RK3588" > $G/strings/0x409/manufacturer
    echo "TUN NAT Hub" > $G/strings/0x409/product

    mkdir -p $G/configs/c.1
    echo "500" > $G/configs/c.1/MaxPower

    # Use FunctionFS
    mkdir -p $G/functions/ffs.raw
    mkdir -p /dev/ffs-raw
    mount -t functionfs raw /dev/ffs-raw 2>/dev/null || true
    ln -sf $G/functions/ffs.raw $G/configs/c.1/

    echo "$UDC" > $G/UDC 2>/dev/null || true
}

echo "=== Check ==="
ls /dev/ttyGS* 2>/dev/null || echo "no ttyGS"
ls /dev/ffs-raw/ 2>/dev/null || echo "no ffs-raw"
echo "=== Restart daemon ==="
systemctl start tun_nat_hub
systemctl is-active tun_nat_hub
