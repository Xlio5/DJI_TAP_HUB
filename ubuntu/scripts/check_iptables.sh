#!/bin/bash
echo "=== iptables-save (full FORWARD) ==="
iptables-save 2>/dev/null | grep -A5 "FORWARD" | head -15
echo ""
echo "=== nftables ==="
nft list ruleset 2>/dev/null | head -10 || echo "nftables not installed"
echo ""
echo "=== firewall services ==="
systemctl list-units --type=service --all 2>/dev/null | grep -E "firewall|iptable|netfilter|docker" || echo "none found"
echo ""
echo "=== iptables rules count ==="
iptables -L FORWARD -n -v --line-numbers 2>/dev/null
