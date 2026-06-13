#!/bin/bash
echo "=== kernel version ==="
uname -r

echo "=== FunctionFS header ==="
find /usr/src -name functionfs.h 2>/dev/null | head -5
find /usr/include -name functionfs.h 2>/dev/null | head -5

echo "=== V2 struct ==="
grep -r "FUNCTIONFS_DESCRIPTORS_MAGIC" /usr/include/ 2>/dev/null | head -5

echo "=== try g_serial ==="
modprobe g_serial 2>&1
ls /sys/class/udc/

echo "=== ffs gadget state ==="
ls /sys/kernel/config/usb_gadget/tun_nat/ 2>&1
cat /sys/kernel/config/usb_gadget/tun_nat/UDC 2>&1

echo "=== dmesg gadget ==="
dmesg | grep -i "gadget\|ffs\|configfs\|udc" | tail -20
