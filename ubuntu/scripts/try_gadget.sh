#!/bin/bash
echo "=== 检查 role 文件 ==="
find /sys/devices/platform/usbdrd3_0 -name 'role' -ls 2>&1

echo ""
echo "=== 尝试直接切换 DWC3 模式 ==="
# 方法1: 通过 DWC3 debug mode 切换
if [ -f /sys/kernel/debug/usb/fc000000.usb/mode ]; then
  echo "debug mode file exists"
  cat /sys/kernel/debug/usb/fc000000.usb/mode
  echo "device" > /sys/kernel/debug/usb/fc000000.usb/mode 2>&1 && echo "switched!" || echo "switch failed"
fi

echo ""
echo "=== 方法2: unbind + rebind ==="
echo "fc000000.usb" > /sys/bus/platform/drivers/dwc3/unbind 2>&1 && echo "unbound" || echo "unbind failed"
sleep 1
echo "fc000000.usb" > /sys/bus/platform/drivers/dwc3/bind 2>&1 && echo "re-bound" || echo "rebind failed"
sleep 1

echo ""
echo "=== 检查 UDC ==="
ls /sys/class/udc/

echo ""
echo "=== GCTL ==="
cat /sys/kernel/debug/usb/fc000000.usb/regdump 2>/dev/null | grep GCTL
