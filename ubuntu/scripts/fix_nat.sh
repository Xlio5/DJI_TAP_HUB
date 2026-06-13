#!/bin/bash
# Fix: replace eth0 with end1 (RK3588 ethernet interface)
iptables -t nat -D POSTROUTING -s 10.0.0.0/24 -o eth0 -j MASQUERADE 2>/dev/null
iptables -t nat -D POSTROUTING -s 10.0.0.0/24 -o end1 -j MASQUERADE 2>/dev/null
iptables -t nat -A POSTROUTING -s 10.0.0.0/24 -o end1 -j MASQUERADE

iptables -D FORWARD -i tun_hub -o eth0 -j ACCEPT 2>/dev/null
iptables -D FORWARD -i eth0 -o tun_hub -m state --state ESTABLISHED,RELATED -j ACCEPT 2>/dev/null
iptables -D FORWARD -i tun_hub -o end1 -j ACCEPT 2>/dev/null
iptables -D FORWARD -i end1 -o tun_hub -m state --state ESTABLISHED,RELATED -j ACCEPT 2>/dev/null

iptables -A FORWARD -i tun_hub -o end1 -j ACCEPT
iptables -A FORWARD -i end1 -o tun_hub -m state --state ESTABLISHED,RELATED -j ACCEPT

echo "=== NAT ==="
iptables -t nat -L POSTROUTING -n | grep 10.0.0
echo "=== FORWARD ==="
iptables -L FORWARD -n | grep -E "tun_hub|end1"
echo "Done"
