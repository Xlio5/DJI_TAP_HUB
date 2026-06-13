#!/bin/bash
echo "=== NAT ==="
iptables -t nat -L POSTROUTING -n -v 2>/dev/null | grep 10.0.0
echo "=== FORWARD ==="
iptables -L FORWARD -n -v 2>/dev/null | grep -E "tun_hub|end1"
echo "=== boot log ==="
journalctl -u tun_nat_hub --no-pager --since "1 min ago" 2>/dev/null | head -20
echo "=== setup_nat log ==="
journalctl -u tun_nat_hub --no-pager -b | grep -E "ExecStartPre|setup_nat|setup_gadget|检测|LAN|致命" | head -10
echo "=== LAN iface ==="
ip -br link show | grep -v lo
