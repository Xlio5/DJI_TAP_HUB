#!/bin/bash
# /home/xlong/cold_boot_fix.sh — 冷启动自动修复脚本
PASS=0
FAILS=""
FIXED=""
TOTAL=0

check() {
    local key=$1 name=$2 cmd=$3 fix=$4
    TOTAL=$((TOTAL+1))
    if eval "$cmd" 2>/dev/null; then
        PASS=$((PASS+1))
    else
        FAILS="$FAILS $name"
        eval "$fix" 2>/dev/null || true
        sleep 1
        if eval "$cmd" 2>/dev/null; then
            FIXED="$FIXED $name"
        fi
    fi
}

# 1. 有线网
check wired "wired" \
  "ip -br addr show end1 2>/dev/null | grep -q 192.168.144" \
  "ip addr add 192.168.144.66/24 dev end1 2>/dev/null; ip link set end1 up; nmcli connection up end1-static 2>/dev/null"

# 2. ttyGS0 device
check ttygs0 "ttyGS0" \
  "test -c /dev/ttyGS0" \
  "modprobe -r g_serial 2>/dev/null; sleep 1; modprobe g_serial use_acm=0 use_obex=0 idVendor=0x0BDA idProduct=0x8812; sleep 2"

# 3. VID = 0x0BDA
check vid "VID" \
  "test $(cat /sys/module/g_serial/parameters/idVendor 2>/dev/null || echo 0) -eq 3034" \
  "modprobe -r g_serial 2>/dev/null; sleep 1; modprobe g_serial use_acm=0 use_obex=0 idVendor=0x0BDA idProduct=0x8812; sleep 2"

# 4. ttyGS0 permission 0666
check perm "perm" \
  "stat -c '%a' /dev/ttyGS0 2>/dev/null | grep -q 666" \
  "chmod 666 /dev/ttyGS0 2>/dev/null"

# 5. TUN interface UP
check tun "tun_hub" \
  "ip link show tun_hub 2>/dev/null | grep -q UP" \
  "ip tuntap add dev tun_hub mode tun 2>/dev/null; ip addr add 10.0.0.1/24 dev tun_hub 2>/dev/null; ip link set tun_hub up"

# 6. IP forwarding
check fwd "ip_forward" \
  "cat /proc/sys/net/ipv4/ip_forward | grep -q 1" \
  "echo 1 > /proc/sys/net/ipv4/ip_forward"

# 7. NAT MASQUERADE
check nat "NAT" \
  "iptables -t nat -L POSTROUTING -n 2>/dev/null | grep -q MASQUERADE" \
  "iptables -t nat -A POSTROUTING -s 10.0.0.0/24 -o end1 -j MASQUERADE 2>/dev/null; iptables -A FORWARD -i tun_hub -o end1 -j ACCEPT 2>/dev/null; iptables -A FORWARD -i end1 -o tun_hub -m state --state ESTABLISHED,RELATED -j ACCEPT 2>/dev/null"

# 8. Daemon running
check daemon "daemon" \
  "systemctl is-active tun_nat_hub 2>/dev/null | grep -q active" \
  "systemctl restart tun_nat_hub 2>/dev/null; sleep 2"

# 9. Daemon enabled at boot
check enabled "boot" \
  "systemctl is-enabled tun_nat_hub 2>/dev/null | grep -q enabled" \
  "systemctl enable tun_nat_hub 2>/dev/null"

# 10. Web panel
check web "web" \
  "systemctl is-active tun_web 2>/dev/null | grep -q active" \
  "systemctl restart tun_web 2>/dev/null"

echo ""
echo "=== STATUS ==="
echo "end1:    $(ip -br addr show end1 2>/dev/null | tr '\n' ' ')"
echo "ttyGS0:  $(stat -c '%a' /dev/ttyGS0 2>/dev/null) $(test -c /dev/ttyGS0 && echo OK || echo MISSING)"
echo "VID:PID: $(cat /sys/module/g_serial/parameters/idVendor 2>/dev/null):$(cat /sys/module/g_serial/parameters/idProduct 2>/dev/null)"
echo "tun_hub: $(ip addr show tun_hub 2>/dev/null | grep 'inet ' | awk '{print $2}')"
echo "daemon:  $(systemctl is-active tun_nat_hub 2>/dev/null)"
echo "web:     $(systemctl is-active tun_web 2>/dev/null)"
echo "RESULT:  $PASS/$TOTAL passed"
[ -n "$FIXED" ] && echo "FIXED:   $FIXED"
[ -n "$FAILS" ] && echo "FAILED:  $FAILS"
if [ "$PASS" -eq "$TOTAL" ]; then
    echo "ALL_OK"
else
    echo "SOME_FAILED"
fi
