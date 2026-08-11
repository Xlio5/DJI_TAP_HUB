#!/bin/sh
# setup_v3s.sh - TUN + NAT + USB init (SPI Flash, dr_mode=peripheral)
set -e

_ts() { echo "[$(date +%H:%M:%S)] $*"; }

TUN_NAME=tun_hub
TUN_IP=10.0.0.1
TUN_PREFIX=24
TUN_MTU=1400
TUN_SUBNET=10.0.0.0/24

_ts "=== TUN_NAT_HUB Setup ==="

# eth0 — try DHCP 3s, fallback static
ip link set eth0 up 2>/dev/null || true
for i in $(seq 1 3); do
    if ip addr show eth0 2>/dev/null | grep -q 'inet '; then break; fi
    sleep 1
done
if ip addr show eth0 2>/dev/null | grep -q 'inet '; then
    _ts "eth0: DHCP OK"
else
    _ts "eth0: static 192.168.144.66/24"
    ip addr add 192.168.144.66/24 dev eth0 2>/dev/null || true
fi
# 备用固定 IP 172.20.10.3 (iPhone 热点网段), 与 144 共存
# 万一摄像头不在 144 网段, 仍可用 172.20.10.3 进 SSH 调试
ip addr add 172.20.10.3/24 dev eth0 2>/dev/null || true
ip link set eth0 up
ip route replace default via 192.168.144.1 dev eth0 2>/dev/null || true

# TUN
if ! ip link show $TUN_NAME >/dev/null 2>&1; then
    ip tuntap add dev $TUN_NAME mode tun
fi
ip addr replace ${TUN_IP}/${TUN_PREFIX} dev $TUN_NAME
ip link set $TUN_NAME mtu $TUN_MTU
ip link set $TUN_NAME up
_ts "TUN: $TUN_IP/$TUN_PREFIX (mtu=$TUN_MTU)"

# IP forwarding
echo 1 > /proc/sys/net/ipv4/ip_forward

# NAT
LAN_IF=eth0
_ts "LAN: $LAN_IF ($(ip addr show $LAN_IF 2>/dev/null | grep 'inet ' | awk '{print $2}'))"

iptables -t nat -D POSTROUTING -s $TUN_SUBNET -o $LAN_IF -j MASQUERADE 2>/dev/null || true
iptables -D FORWARD -i $TUN_NAME -o $LAN_IF -j ACCEPT 2>/dev/null || true
iptables -D FORWARD -i $LAN_IF -o $TUN_NAME -m state --state ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || true

iptables -t nat -A POSTROUTING -s $TUN_SUBNET -o $LAN_IF -j MASQUERADE
iptables -A FORWARD -i $TUN_NAME -o $LAN_IF -j ACCEPT
iptables -A FORWARD -i $LAN_IF -o $TUN_NAME -m state --state ESTABLISHED,RELATED -j ACCEPT
_ts "NAT: $TUN_NAME <-> $LAN_IF (MASQUERADE)"

_ts "USB: peripheral (DTB)"
_ts "=== Setup complete ==="
