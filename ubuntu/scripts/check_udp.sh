#!/bin/bash
echo "=== NAT rules ==="
iptables -t nat -L POSTROUTING -n -v 2>/dev/null | grep 10.0.0
echo ""
echo "=== FORWARD rules ==="
iptables -L FORWARD -n -v 2>/dev/null | grep -E "tun_hub|end1"
echo ""
echo "=== UDP conntrack (last 10) ==="
conntrack -L -p udp 2>/dev/null | tail -10 || echo "conntrack not installed, checking /proc"
cat /proc/net/nf_conntrack 2>/dev/null | grep udp | tail -10 || echo "no conntrack file"
