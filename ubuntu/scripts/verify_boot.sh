#!/bin/bash
echo "=== uptime ==="
uptime
echo ""
echo "=== service ==="
systemctl is-active tun_nat_hub
systemctl is-enabled tun_nat_hub
echo ""
echo "=== LAN IP ==="
ip addr show end1 2>/dev/null | grep inet
echo ""
echo "=== FORWARD ==="
iptables -L FORWARD -n 2>/dev/null | grep -E "tun_hub|end1"
echo ""
echo "=== NAT ==="
iptables -t nat -L POSTROUTING -n 2>/dev/null | grep 10.0.0
echo ""
echo "=== boot log ==="
journalctl -u tun_nat_hub --no-pager -b 2>/dev/null | grep -E "setup_nat|LAN|NAT|守护进程 v|致命|ERROR|g_serial" | head -10
echo ""
echo "=== recent stats ==="
journalctl -u tun_nat_hub --no-pager -n 3 2>/dev/null
