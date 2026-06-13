#!/bin/bash
set -x
echo "=== unload g_serial ==="
modprobe -r g_serial 2>&1 || true

echo "=== UDC state ==="
ls /sys/class/udc/
cat /sys/kernel/config/usb_gadget/tun_nat/UDC 2>&1

echo "=== FFS struct ==="
grep -A40 "descs_head_v2" /usr/include/linux/usb/functionfs.h 2>/dev/null | head -50

echo "=== FFS magic values ==="
grep "FUNCTIONFS_DESCRIPTORS_MAGIC\|FUNCTIONFS_HAS" /usr/include/linux/usb/functionfs.h

echo "=== Current gadget UDC ==="
cat /sys/kernel/config/usb_gadget/tun_nat/UDC

echo "=== Bind UDC to our gadget ==="
echo "fc000000.usb" > /sys/kernel/config/usb_gadget/tun_nat/UDC 2>&1
cat /sys/kernel/config/usb_gadget/tun_nat/UDC

echo "=== Check ep0 ==="
ls -la /dev/usb-ffs/tun_nat/ep0 2>&1

echo "=== Try python write again ==="
python3 /tmp/test_ffs_write.py 2>&1
