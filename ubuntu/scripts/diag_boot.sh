#!/bin/bash
echo "=== uptime ==="
uptime
echo ""
echo "=== tun_nat_hub service ==="
systemctl is-active tun_nat_hub
systemctl is-enabled tun_nat_hub
echo ""
echo "=== /dev/ttyGS0 ==="
ls -la /dev/ttyGS0 2>&1
echo ""
echo "=== TUN ==="
ip addr show tun_hub 2>&1 | grep -E "inet|state"
echo ""
echo "=== NAT ==="
iptables -t nat -L POSTROUTING -n 2>/dev/null | grep 10.0.0
echo ""
echo "=== FORWARD ==="
iptables -L FORWARD -n 2>/dev/null | grep -E "tun_hub|end1"
echo ""
echo "=== LAN iface ==="
ip -br addr show 2>/dev/null | grep -E "end1|eth0|enp"
echo ""
echo "=== boot journal ==="
journalctl -u tun_nat_hub --no-pager -b 2>/dev/null | grep -E "setup_nat|setup_gadget|检测|致命|守护进程 v|g_serial|ERROR" | head -20
echo ""
echo "=== ExecStartPre errors ==="
journalctl -u tun_nat_hub --no-pager -b 2>/dev/null | grep -E "ExecStart|exited" | head -10
echo ""
echo "=== recent errors ==="
journalctl -u tun_nat_hub --no-pager -n 10 2>/dev/null
