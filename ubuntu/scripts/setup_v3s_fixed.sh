#!/bin/sh
# setup_v3s.sh - TUN + NAT + USB init (SPI Flash, dr_mode=peripheral)
# 2026-08-25 v1.6.45: 与 setup_v3s.sh 保持一致，保留文件名仅兼容旧构建脚本。
#   - V3s tun_hub: 10.0.0.1/24
#   - 手机主地址: 10.0.0.2
#   - 手机 LAN 身份: x.x.x.11，经 V3s DNAT 到 10.0.0.2
#   - 手机主动访问 LAN 摄像头时做 SNAT，避免回包绕过 V3s。
set -e

_ts() { echo "[$(date +%H:%M:%S)] $*"; }

TUN_NAME=tun_hub
TUN_IP=10.0.0.1
TUN_PREFIX=24
TUN_MTU=1400
PHONE_IP_OCTET=11
INTERNAL_FWD_ADDR=10.0.0.2

_ts "=== TUN_NAT_HUB Setup ==="

# eth0 - try DHCP 3s, fallback static
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
# 备用固定 IP 172.20.10.3 (iPhone 热点网段), 与 144 共存。
ip addr add 172.20.10.3/24 dev eth0 2>/dev/null || true
ip link set eth0 up
ip route replace default via 192.168.144.1 dev eth0 2>/dev/null || true

# TUN - V3s 保留 10.0.0.1/24 作为隧道内管理地址，手机主地址为 10.0.0.2。
if ! ip link show $TUN_NAME >/dev/null 2>&1; then
    ip tuntap add dev $TUN_NAME mode tun
fi
ip addr replace ${TUN_IP}/${TUN_PREFIX} dev $TUN_NAME
ip link set $TUN_NAME mtu $TUN_MTU
ip link set $TUN_NAME up
_ts "TUN: $TUN_IP/$TUN_PREFIX (mtu=$TUN_MTU)"

# IP forwarding
echo 1 > /proc/sys/net/ipv4/ip_forward

LAN_IF=eth0
_ts "LAN: $LAN_IF ($(ip addr show $LAN_IF 2>/dev/null | grep 'inet ' | awk '{print $2}'))"

LAN_IP=$(ip addr show $LAN_IF 2>/dev/null | grep 'inet ' | awk '{print $2}' | cut -d/ -f1 | head -1)
LAN_PHONE_IP=$(echo "$LAN_IP" | cut -d. -f1-3).$PHONE_IP_OCTET
if [ -n "$LAN_PHONE_IP" ] && [ "$LAN_PHONE_IP" != ".$PHONE_IP_OCTET" ]; then
    echo 1 > /proc/sys/net/ipv4/conf/$LAN_IF/proxy_arp

    ip route del $LAN_PHONE_IP/32 dev $TUN_NAME 2>/dev/null || true
    ip route add $LAN_PHONE_IP/32 dev $TUN_NAME 2>/dev/null || true
    ip route del 10.0.0.0/24 dev $TUN_NAME 2>/dev/null || true
    ip route add 10.0.0.0/24 dev $TUN_NAME 2>/dev/null || true

    iptables -t nat -D PREROUTING -i $LAN_IF -d $LAN_PHONE_IP -j DNAT --to-destination $INTERNAL_FWD_ADDR 2>/dev/null || true
    iptables -t nat -A PREROUTING -i $LAN_IF -d $LAN_PHONE_IP -j DNAT --to-destination $INTERNAL_FWD_ADDR

    iptables -D FORWARD -i $LAN_IF -o $TUN_NAME -d $INTERNAL_FWD_ADDR -j ACCEPT 2>/dev/null || true
    iptables -A FORWARD -i $LAN_IF -o $TUN_NAME -d $INTERNAL_FWD_ADDR -j ACCEPT

    iptables -t nat -D POSTROUTING -s $LAN_PHONE_IP/32 -o $LAN_IF -j MASQUERADE 2>/dev/null || true
    iptables -t nat -A POSTROUTING -s $LAN_PHONE_IP/32 -o $LAN_IF -j MASQUERADE

    iptables -D FORWARD -i $TUN_NAME -o $LAN_IF -j ACCEPT 2>/dev/null || true
    iptables -A FORWARD -i $TUN_NAME -o $LAN_IF -j ACCEPT
    iptables -D FORWARD -i $LAN_IF -o $TUN_NAME -m state --state ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || true
    iptables -A FORWARD -i $LAN_IF -o $TUN_NAME -m state --state ESTABLISHED,RELATED -j ACCEPT

    _ts "LAN身份: $LAN_PHONE_IP -> DNAT -> $INTERNAL_FWD_ADDR (端口不变, 隧道转发)"
else
    _ts "WARNING: 手机 IP 未配置 (无 eth0 IP)"
fi

_ts "USB: peripheral (DTB)"
_ts "=== Setup complete ==="
