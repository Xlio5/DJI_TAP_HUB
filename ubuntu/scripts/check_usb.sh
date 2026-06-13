#!/bin/bash
echo '=== dwc3 role ==='
for d in /sys/devices/platform/usbdrd3_0/*/role; do
  [ -f "$d" ] && echo "$d: $(cat $d)"
done
echo '=== dr_mode ==='
find /sys/devices -name 'dr_mode' 2>/dev/null | while read f; do
  echo "$f: $(cat $f 2>&1)"
done
echo '=== dmesg dwc3 ==='
dmesg 2>/dev/null | grep -i dwc3 | tail -20
echo '=== lsmod ==='
lsmod | grep -E 'dwc3|libcomp|ffs|gadget'
echo '=== configfs ==='
ls /sys/kernel/config/usb_gadget/ 2>&1
