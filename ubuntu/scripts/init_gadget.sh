#!/bin/bash
set -e
echo "=== 加载内核模块 ==="
modprobe libcomposite 2>&1 || echo "libcomposite failed"
modprobe usb_f_fs 2>&1 || echo "usb_f_fs failed"
echo ""
echo "=== lsmod ==="
lsmod | grep -E "libcomp|ffs|gadget"
echo ""
echo "=== UDC ==="
ls /sys/class/udc/ 2>&1
echo ""
echo "=== 尝试手动注册 UDC ==="
# 检查 DWC3 role 是否可以切换
for d in /sys/devices/platform/usbdrd3_0/*/role; do
  [ -f "$d" ] && { echo "$d: $(cat $d)"; echo "尝试设为 device..."; echo device >"$d" 2>&1 || echo "role 切换失败"; }
done
echo ""
echo "=== 再次检查 UDC ==="
ls /sys/class/udc/ 2>&1
