#!/bin/bash
set -e
echo "=== Stop daemon ==="
systemctl stop tun_nat_hub 2>/dev/null || true

echo "=== Unbind all UDC ==="
for g in /sys/kernel/config/usb_gadget/*/UDC; do
    [ -f "$g" ] && echo "" > "$g" 2>/dev/null || true
done

echo "=== Remove old gadgets ==="
for g in /sys/kernel/config/usb_gadget/tun_*; do
    [ -d "$g" ] && {
        # Unlink functions
        for f in "$g"/configs/c.1/*; do
            [ -L "$f" ] && rm -f "$f" 2>/dev/null || true
        done
        rmdir "$g"/configs/c.1/strings/0x409 2>/dev/null || true
        rmdir "$g"/configs/c.1 2>/dev/null || true
        for f in "$g"/functions/*; do
            rmdir "$f" 2>/dev/null || true
        done
        rmdir "$g"/strings/0x409 2>/dev/null || true
        rmdir "$g" 2>/dev/null || true
    }
done

echo "=== Unload old modules ==="
modprobe -r g_serial 2>/dev/null || true
modprobe -r usb_f_fs 2>/dev/null || true

echo "=== Check g_serial parms ==="
modinfo g_serial 2>/dev/null | grep -E "parm|description"

echo "=== Load g_serial non-ACM ==="
modprobe g_serial use_acm=0 use_obex=0 idVendor=0x2207 idProduct=0x0010 2>&1 || echo "modprobe failed, will use configfs"

echo "=== Check result ==="
ls /dev/ttyGS* 2>&1
cat /sys/class/udc/*/state 2>/dev/null || true
lsusb 2>&1 | grep -i "2207\|TUN"
