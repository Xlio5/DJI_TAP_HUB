#!/bin/sh
# setup_v3s.sh - TUN + NAT + USB init (SPI Flash, dr_mode=peripheral)
# 2026-08-16: 砍掉 10.0.0.x 隧道网段, 手机 = 局域网真 IP (x.x.x.11)
set -e

_ts() { echo "[$(date +%H:%M:%S)] $*"; }

TUN_NAME=tun_hub
TUN_MTU=1400
PHONE_IP_OCTET=11          # 手机 IP 尾号 (V3s eth0 = x.x.x.66, 手机 = x.x.x.11)

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

# TUN — 不配 10.0.0.x, 只建接口 (手机地址用 /32 主机路由, 与 eth0 同网段不冲突)
if ! ip link show $TUN_NAME >/dev/null 2>&1; then
    ip tuntap add dev $TUN_NAME mode tun
fi
ip link set $TUN_NAME mtu $TUN_MTU
ip link set $TUN_NAME up
_ts "TUN: $TUN_NAME (mtu=$TUN_MTU, 无内部 IP)"

# IP forwarding
echo 1 > /proc/sys/net/ipv4/ip_forward

# ── 手机在局域网里的真 IP (x.x.x.11) ─────────────────────────
# 砍掉 10.0.0.x: 手机就是局域网一个普通设备。
# V3s 为它做 proxy_arp + /32 路由: 局域网设备 ping/访问这个 IP
# 会被 V3s 代答 ARP 并收进 USB 隧道 → 手机, 零配置直达。
# 出向 (手机→LAN): 手机源 IP = x.x.x.11, 局域网设备直接可达, 无需 MASQUERADE。
LAN_IF=eth0
_ts "LAN: $LAN_IF ($(ip addr show $LAN_IF 2>/dev/null | grep 'inet ' | awk '{print $2}'))"

LAN_IP=$(ip addr show $LAN_IF 2>/dev/null | grep 'inet ' | awk '{print $2}' | cut -d/ -f1)
LAN_PHONE_IP=$(echo "$LAN_IP" | cut -d. -f1-3).$PHONE_IP_OCTET
if [ -n "$LAN_PHONE_IP" ] && [ "$LAN_PHONE_IP" != ".$PHONE_IP_OCTET" ]; then
    # /32 主机路由: 去手机的包走 USB 隧道 (比 /24 更具体, 优先于 eth0)
    ip route del $LAN_PHONE_IP/32 dev $TUN_NAME 2>/dev/null || true
    ip route add $LAN_PHONE_IP/32 dev $TUN_NAME 2>/dev/null || true
    # proxy_arp: 局域网设备 ARP 询问该 IP 时 V3s 代答 (声称自己可达)
    echo 1 > /proc/sys/net/ipv4/conf/$LAN_IF/proxy_arp
    # 入向: LAN → 手机 任意端口放行 (新连接也能进, 真实局域网行为)
    iptables -A FORWARD -i $LAN_IF -o $TUN_NAME -d $LAN_PHONE_IP -j ACCEPT
    # 出向: 手机 → LAN 放行 (源 IP = 手机局域网真 IP, 无需 NAT)
    iptables -A FORWARD -i $TUN_NAME -o $LAN_IF -j ACCEPT
    # 回程: LAN → 手机 已建立的连接放行
    iptables -A FORWARD -i $LAN_IF -o $TUN_NAME -m state --state ESTABLISHED,RELATED -j ACCEPT
    _ts "手机: $LAN_PHONE_IP -> $TUN_NAME (proxy_arp on $LAN_IF, 无 NAT)"
else
    _ts "WARNING: 手机 IP 未配置 (无 eth0 IP)"
fi

_ts "USB: peripheral (DTB)"
_ts "=== Setup complete ==="
