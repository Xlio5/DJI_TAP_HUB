#!/bin/bash
# setup_nat.sh — 自动检测 LAN 网口并配置 TUN + NAT
# 每次守护进程启动前由 systemd ExecStartPre 调用

set -e
TUN_NAME="tun_hub"
TUN_IP="10.0.0.1"
TUN_PREFIX="24"
TUN_MTU="1400"

# ── 自动检测 LAN 网口 ─────────────────────────────
# 优先选物理网口（end* > eth* > en*），排除 lo/wlan/tun/docker
detect_lan_iface() {
    for pattern in "end[0-9]*" "eth[0-9]*" "en[0-9]*"; do
        for iface in $(ip -br link 2>/dev/null | awk '{print $1}' | grep "^$pattern\$" 2>/dev/null); do
            # 确认该接口有 IP
            if ip addr show "$iface" 2>/dev/null | grep -q 'inet '; then
                echo "$iface"
                return 0
            fi
        done
    done
    echo ""
    return 1
}

LAN_IF=$(detect_lan_iface)
if [ -z "$LAN_IF" ]; then
    echo "警告: 未检测到 LAN 网口，NAT 将不生效"
else
    echo "检测到 LAN 网口: $LAN_IF"
fi

# ── TUN 接口 ──────────────────────────────────────
if ! ip link show "$TUN_NAME" &>/dev/null; then
    ip tuntap add dev "$TUN_NAME" mode tun
fi
ip addr replace "${TUN_IP}/${TUN_PREFIX}" dev "$TUN_NAME"
ip link set "$TUN_NAME" mtu "$TUN_MTU"
ip link set "$TUN_NAME" up

# ── IP 转发 ────────────────────────────────────────
echo 1 > /proc/sys/net/ipv4/ip_forward

# ── iptables NAT ───────────────────────────────────
if [ -n "$LAN_IF" ]; then
    # 清除旧规则
    iptables -t nat -D POSTROUTING -s "${TUN_IP%.*}.0/24" -o "$LAN_IF" -j MASQUERADE 2>/dev/null || true
    iptables -D FORWARD -i "$TUN_NAME" -o "$LAN_IF" -j ACCEPT 2>/dev/null || true
    iptables -D FORWARD -i "$LAN_IF" -o "$TUN_NAME" -m state --state ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || true

    # 添加新规则
    iptables -t nat -A POSTROUTING -s "${TUN_IP%.*}.0/24" -o "$LAN_IF" -j MASQUERADE
    iptables -A FORWARD -i "$TUN_NAME" -o "$LAN_IF" -j ACCEPT
    iptables -A FORWARD -i "$LAN_IF" -o "$TUN_NAME" -m state --state ESTABLISHED,RELATED -j ACCEPT

    # TCP MSS Clamping
    iptables -t mangle -D FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu 2>/dev/null || true
    iptables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu
fi

echo "NAT 配置完成 ($TUN_NAME → $LAN_IF)"
