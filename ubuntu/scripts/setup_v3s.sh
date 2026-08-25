#!/bin/sh
# setup_v3s.sh - TUN + NAT + USB init (SPI Flash, dr_mode=peripheral)
# 2026-08-16 v1.6.29 (做法B): 手机主地址 10.0.0.2 + LAN 身份 144.11
#   - 手机 tun0: 10.0.0.2 (主, Android 只对主地址投递隧道包) + 144.11 (副, LAN 身份)
#   - V3s DNAT 144.11 → 10.0.0.2 (端口不变), 绕开 V3s 老内核把 144.11 当 INPUT 吞
set -e

_ts() { echo "[$(date +%H:%M:%S)] $*"; }

TUN_NAME=tun_hub
TUN_IP=10.0.0.1
TUN_PREFIX=24
TUN_MTU=1400
PHONE_IP_OCTET=11          # 手机 LAN 身份 IP 尾号 (V3s eth0 = x.x.x.66, 手机 = x.x.x.11)
INTERNAL_FWD_ADDR=10.0.0.2 # 手机主地址 (内部转发, V3s DNAT 目标)

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

# TUN — V3s 保留 10.0.0.1/24 作为隧道内管理地址，手机主地址为 10.0.0.2。
if ! ip link show $TUN_NAME >/dev/null 2>&1; then
    ip tuntap add dev $TUN_NAME mode tun
fi
ip addr replace ${TUN_IP}/${TUN_PREFIX} dev $TUN_NAME
ip link set $TUN_NAME mtu $TUN_MTU
ip link set $TUN_NAME up
_ts "TUN: $TUN_IP/$TUN_PREFIX (mtu=$TUN_MTU)"

# IP forwarding
echo 1 > /proc/sys/net/ipv4/ip_forward

# ── 局域网身份 (手机 LAN 身份 IP x.x.x.11) ───────────────────
# 手机 = x.x.x.11 (LAN 身份, 电脑可见入口), V3s = x.x.x.66
# V3s DNAT x.x.x.11 → 10.0.0.2 (手机主地址), 端口不变:
#   - 电脑发 x.x.x.11:任意端口 → V3s eth0 → DNAT → 10.0.0.2:同端口
#   - 绕开 V3s 老内核(3.4)把 x.x.x.11 当本地 INPUT 吞包的问题
#   - 手机主地址 10.0.0.2 收 (Android 只对主地址投递隧道包)
LAN_IF=eth0
_ts "LAN: $LAN_IF ($(ip addr show $LAN_IF 2>/dev/null | grep 'inet ' | awk '{print $2}'))"

LAN_IP=$(ip addr show $LAN_IF 2>/dev/null | grep 'inet ' | awk '{print $2}' | cut -d/ -f1 | head -1)
LAN_PHONE_IP=$(echo "$LAN_IP" | cut -d. -f1-3).$PHONE_IP_OCTET
if [ -n "$LAN_PHONE_IP" ] && [ "$LAN_PHONE_IP" != ".$PHONE_IP_OCTET" ]; then
    # proxy_arp: 局域网设备 ARP 询问 x.x.x.11 时 V3s 代答 (电脑能找到入口)
    echo 1 > /proc/sys/net/ipv4/conf/$LAN_IF/proxy_arp

    # /32 主机路由: V3s 知道 x.x.x.11 可达 (proxy_arp 代答前提), 走隧道
    ip route del $LAN_PHONE_IP/32 dev $TUN_NAME 2>/dev/null || true
    ip route add $LAN_PHONE_IP/32 dev $TUN_NAME 2>/dev/null || true
    # 10.0.0.0/24 → tun_hub 路由 (DNAT 后目标 10.0.0.2 走隧道到手机)
    ip route del 10.0.0.0/24 dev $TUN_NAME 2>/dev/null || true
    ip route add 10.0.0.0/24 dev $TUN_NAME 2>/dev/null || true

    # DNAT: LAN 身份 x.x.x.11 → 手机主地址 10.0.0.2 (端口不变)
    iptables -t nat -D PREROUTING -i $LAN_IF -d $LAN_PHONE_IP -j DNAT --to-destination $INTERNAL_FWD_ADDR 2>/dev/null || true
    iptables -t nat -A PREROUTING -i $LAN_IF -d $LAN_PHONE_IP -j DNAT --to-destination $INTERNAL_FWD_ADDR

    # FORWARD 放行: DNAT 后目标 10.0.0.2 转发进隧道
    iptables -D FORWARD -i $LAN_IF -o $TUN_NAME -d $INTERNAL_FWD_ADDR -j ACCEPT 2>/dev/null || true
    iptables -A FORWARD -i $LAN_IF -o $TUN_NAME -d $INTERNAL_FWD_ADDR -j ACCEPT
    # SNAT: 手机以 LAN 身份 x.x.x.11 主动访问同网段摄像头时，必须改源为 V3s eth0。
    # 否则摄像头会直接 ARP x.x.x.11，回包绕过 V3s，RTSP TCP 三次握手卡住。
    iptables -t nat -D POSTROUTING -s $LAN_PHONE_IP/32 -o $LAN_IF -j MASQUERADE 2>/dev/null || true
    iptables -t nat -A POSTROUTING -s $LAN_PHONE_IP/32 -o $LAN_IF -j MASQUERADE
    # 出向: 手机 → LAN 放行
    iptables -D FORWARD -i $TUN_NAME -o $LAN_IF -j ACCEPT 2>/dev/null || true
    iptables -A FORWARD -i $TUN_NAME -o $LAN_IF -j ACCEPT
    # 回程: LAN → 手机 已建立的连接放行
    iptables -D FORWARD -i $LAN_IF -o $TUN_NAME -m state --state ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || true
    iptables -A FORWARD -i $LAN_IF -o $TUN_NAME -m state --state ESTABLISHED,RELATED -j ACCEPT

    _ts "LAN身份: $LAN_PHONE_IP → DNAT → $INTERNAL_FWD_ADDR (端口不变, 隧道转发)"
else
    _ts "WARNING: 手机 IP 未配置 (无 eth0 IP)"
fi

_ts "USB: peripheral (DTB)"
_ts "=== Setup complete ==="
