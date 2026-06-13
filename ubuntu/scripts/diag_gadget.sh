#!/bin/bash
echo "=== DRD state ==="
for f in $(find /sys/devices/platform/usbdrd3_0 -name 'mode' 2>/dev/null); do
  echo "$f: $(cat $f 2>&1)"
done

echo ""
echo "=== DWC3 role ==="
for f in $(find /sys/devices/platform/usbdrd3_0 -name 'role' 2>/dev/null); do
  echo "$f: $(cat $f 2>&1)"
done

echo ""
echo "=== extcon ==="
for f in $(find /sys/devices/platform/usbdrd3_0 -name 'cable.*' 2>/dev/null); do
  [ -f "$f/state" ] && echo "$f/state: $(cat $f/state)"
  [ -f "$f/name" ] && echo "$f/name: $(cat $f/name)"
done

echo ""
echo "=== Type-C ==="
ls /sys/class/typec/ 2>&1
for p in /sys/class/typec/port*; do
  [ -d "$p" ] && {
    echo "$p:"
    [ -f "$p/data_role" ] && echo "  data_role: $(cat $p/data_role)"
    [ -f "$p/power_role" ] && echo "  power_role: $(cat $p/power_role)"
  }
done

echo ""
echo "=== udc ==="
ls /sys/class/udc/ 2>&1

echo ""
echo "=== configfs gadget ==="
ls /sys/kernel/config/usb_gadget/ 2>&1

echo ""
echo "=== dmesg recent drd ==="
dmesg | grep -i 'drd\|dwc3\|gadget\|udc\|otg' | tail -20
