#!/bin/sh
# v3s_check.sh — V3s 端到端就绪检查
echo "=== ttyGS0 ==="
ls -l /dev/ttyGS0 2>&1
echo "=== TUN ==="
ip addr show tun_hub 2>/dev/null | grep inet
echo "=== NAT ==="
iptables -t nat -L POSTROUTING -n 2>/dev/null | grep MASQUERADE
echo "=== FORWARD ==="
iptables -L FORWARD -n 2>/dev/null | grep ACCEPT
echo "=== ip_forward ==="
cat /proc/sys/net/ipv4/ip_forward
echo "=== DAEMON ==="
pidof usb_tund 2>/dev/null && echo "running" || echo "STOPPED"
echo "=== WEB ==="
pidof python3 2>/dev/null && echo "running" || echo "STOPPED"
echo "=== UDC ==="
ls /sys/class/udc/
cat /sys/class/udc/*/state 2>/dev/null
cat /sys/class/udc/*/function 2>/dev/null
echo "=== VID/PID ==="
cat /sys/module/g_serial/parameters/idVendor 2>/dev/null || echo "no-g_serial-sysfs"
cat /sys/module/g_serial/parameters/idProduct 2>/dev/null || echo "no-g_serial-sysfs"
echo "=== DONE ==="
