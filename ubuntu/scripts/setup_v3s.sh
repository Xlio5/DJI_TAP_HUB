#!/bin/sh
# setup_v3s.sh — V3s TUN 虚拟网卡 + iptables NAT 配置
# USB gadget 模式和 daemon 启动由 S99tun_nat_hub 负责
set -e

echo "=== TUN_NAT_HUB V3s Setup ==="

TUN_NAME="tun_hub"
TUN_IP="10.0.0.1"
TUN_PREFIX="24"
TUN_MTU="1400"
TUN_SUBNET="${TUN_IP%.*}.0/24"

# 1. 以太网上线
for iface in eth0 end0 end1 enp1s0; do
    ip link set "$iface" up 2>/dev/null || true
done

# 2. TUN 接口
if ! ip link show "$TUN_NAME" &>/dev/null; then
    ip tuntap add dev "$TUN_NAME" mode tun
fi
ip addr replace "${TUN_IP}/${TUN_PREFIX}" dev "$TUN_NAME"
ip link set "$TUN_NAME" mtu "$TUN_MTU"
ip link set "$TUN_NAME" up
echo "TUN: $TUN_IP/$TUN_PREFIX (mtu=$TUN_MTU)"

# 3. IP 转发
echo 1 > /proc/sys/net/ipv4/ip_forward

# 4. iptables NAT
LAN_IF=""
for iface in eth0 end0 end1 enp1s0; do
    if ip addr show "$iface" 2>/dev/null | grep -q 'inet '; then
        LAN_IF="$iface"
        break
    fi
done

if [ -n "$LAN_IF" ]; then
    echo "LAN: $LAN_IF ($(ip addr show $LAN_IF | grep 'inet ' | awk '{print $2}'))"

    iptables -t nat -D POSTROUTING -s "$TUN_SUBNET" -o "$LAN_IF" -j MASQUERADE 2>/dev/null || true
    iptables -D FORWARD -i "$TUN_NAME" -o "$LAN_IF" -j ACCEPT 2>/dev/null || true
    iptables -D FORWARD -i "$LAN_IF" -o "$TUN_NAME" -m state --state ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || true

    iptables -t nat -A POSTROUTING -s "$TUN_SUBNET" -o "$LAN_IF" -j MASQUERADE
    iptables -A FORWARD -i "$TUN_NAME" -o "$LAN_IF" -j ACCEPT
    iptables -A FORWARD -i "$LAN_IF" -o "$TUN_NAME" -m state --state ESTABLISHED,RELATED -j ACCEPT

    echo "NAT: $TUN_NAME <-> $LAN_IF (MASQUERADE)"
else
    echo "WARNING: 无 LAN 接口有 IP，NAT 未配置"
fi

echo "=== Setup 完成 ==="
