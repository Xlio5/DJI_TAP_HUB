#!/bin/bash
# setup_nat.sh - Auto-detect LAN interface and configure TUN + NAT
# Waits for LAN interface to get IP via DHCP (cold boot)
set -e

TUN_NAME="tun_hub"
TUN_IP="10.0.0.1"
TUN_PREFIX="24"
TUN_MTU="1400"
TUN_SUBNET="${TUN_IP%.*}.0/24"

echo "=== TUN_NAT_HUB NAT Setup ==="

# Detect LAN interface (has an IP)
get_lan_iface() {
    for pattern in "end[0-9]*" "eth[0-9]*" "en[0-9]*"; do
        for iface in $(ip -br link 2>/dev/null | awk '{print $1}' | grep "^$pattern\$" 2>/dev/null); do
            if ip addr show "$iface" 2>/dev/null | grep -q 'inet '; then
                echo "$iface"
                return 0
            fi
        done
    done
    return 1
}

# Wait up to 60s for DHCP on cold boot
LAN_IF=""
for i in $(seq 1 60); do
    LAN_IF=$(get_lan_iface)
    [ -n "$LAN_IF" ] && break
    [ $i -eq 1 ] && echo "Waiting for LAN interface to get IP..."
    sleep 1
done

if [ -z "$LAN_IF" ]; then
    echo "ERROR: No LAN interface with IP after 60s"
else
    echo "LAN interface: $LAN_IF ($(ip addr show $LAN_IF | grep 'inet ' | awk '{print $2}'))"
fi

# Create TUN interface
if ! ip link show "$TUN_NAME" &>/dev/null; then
    ip tuntap add dev "$TUN_NAME" mode tun
fi
ip addr replace "${TUN_IP}/${TUN_PREFIX}" dev "$TUN_NAME"
ip link set "$TUN_NAME" mtu "$TUN_MTU"
ip link set "$TUN_NAME" txqueuelen 10
ip link set "$TUN_NAME" up
tc qdisc replace dev "$TUN_NAME" root pfifo limit 10 2>/dev/null || true

# Enable IP forwarding
echo 1 > /proc/sys/net/ipv4/ip_forward

# iptables rules
if [ -n "$LAN_IF" ]; then
    # Clean old rules
    iptables -t nat -D POSTROUTING -s "$TUN_SUBNET" -o "$LAN_IF" -j MASQUERADE 2>/dev/null || true
    iptables -D FORWARD -i "$TUN_NAME" -o "$LAN_IF" -j ACCEPT 2>/dev/null || true
    iptables -D FORWARD -i "$LAN_IF" -o "$TUN_NAME" -m state --state ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || true
    iptables -D FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu 2>/dev/null || true

    # Add rules
    iptables -t nat -A POSTROUTING -s "$TUN_SUBNET" -o "$LAN_IF" -j MASQUERADE
    iptables -A FORWARD -i "$TUN_NAME" -o "$LAN_IF" -j ACCEPT
    iptables -A FORWARD -i "$LAN_IF" -o "$TUN_NAME" -m state --state ESTABLISHED,RELATED -j ACCEPT
    iptables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu

    echo "NAT rules: $TUN_NAME <-> $LAN_IF"
else
    echo "WARNING: LAN unavailable, no NAT forwarding"
fi

echo "NAT setup complete (g_serial Pure Bulk mode)"
