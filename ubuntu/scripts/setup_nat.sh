#!/bin/bash
# setup_nat.sh - Auto-detect LAN interface and configure TUN + NAT
# Waits for LAN interface to get IP via DHCP (cold boot)
# NOTE: no set -e, best-effort startup

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

# ── LAN 身份地址 (手机在局域网里"直接可见"的 IP) ──────────────
# 与 App 端 TunNatVpnService LAN 身份地址 (x.x.x.11) 一致。
# V3s 为它做 proxy_arp + /32 路由: 局域网设备 ping/访问这个 IP
# 会被 V3s 代答 ARP 并收进 USB 隧道 → 手机, 实现"像真实局域网"的透明双向访问。
LAN_BASE=$(ip addr show "$LAN_IF" 2>/dev/null | grep 'inet ' | awk '{print $2}' | cut -d/ -f1 | cut -d. -f1-3)
LAN_PHONE_IP="${LAN_BASE}.11"
if [ -n "$LAN_IF" ] && [ "$LAN_PHONE_IP" != ".11" ]; then
    # /32 路由: 去手机的包走 USB 隧道
    ip route del "${LAN_PHONE_IP}/32" dev "$TUN_NAME" 2>/dev/null || true
    ip route add "${LAN_PHONE_IP}/32" dev "$TUN_NAME" 2>/dev/null || true
    # proxy_arp: 局域网设备 ARP 询问该 IP 时 V3s 代答 (声称自己可达)
    echo 1 > /proc/sys/net/ipv4/conf/"$LAN_IF"/proxy_arp
    echo "LAN identity: $LAN_PHONE_IP -> $TUN_NAME (proxy_arp on $LAN_IF)"
else
    echo "WARNING: LAN identity 未配置 (无 LAN_IF)"
fi

# iptables rules
if [ -n "$LAN_IF" ]; then
    # Clean old rules
    iptables -t nat -D POSTROUTING -s "$TUN_SUBNET" -o "$LAN_IF" -j MASQUERADE 2>/dev/null || true
    iptables -t nat -D POSTROUTING -s "${LAN_PHONE_IP}/32" -o "$LAN_IF" -j MASQUERADE 2>/dev/null || true
    iptables -D FORWARD -i "$TUN_NAME" -o "$LAN_IF" -j ACCEPT 2>/dev/null || true
    iptables -D FORWARD -i "$LAN_IF" -o "$TUN_NAME" -m state --state ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || true
    iptables -D FORWARD -i "$LAN_IF" -o "$TUN_NAME" -d "$LAN_PHONE_IP" -j ACCEPT 2>/dev/null || true
    iptables -D FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu 2>/dev/null || true

    # Add rules
    iptables -t nat -A POSTROUTING -s "$TUN_SUBNET" -o "$LAN_IF" -j MASQUERADE
    iptables -t nat -A POSTROUTING -s "${LAN_PHONE_IP}/32" -o "$LAN_IF" -j MASQUERADE
    iptables -A FORWARD -i "$TUN_NAME" -o "$LAN_IF" -j ACCEPT
    iptables -A FORWARD -i "$LAN_IF" -o "$TUN_NAME" -m state --state ESTABLISHED,RELATED -j ACCEPT
    # 入向: LAN → 手机 LAN 身份 任意端口放行 (新连接也能进, 真实局域网行为)
    [ -n "$LAN_PHONE_IP" ] && iptables -A FORWARD -i "$LAN_IF" -o "$TUN_NAME" -d "$LAN_PHONE_IP" -j ACCEPT
    iptables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu

    echo "NAT rules: $TUN_NAME <-> $LAN_IF"
else
    echo "WARNING: LAN unavailable, no NAT forwarding"
fi

echo "NAT setup complete (g_serial Pure Bulk mode)"
