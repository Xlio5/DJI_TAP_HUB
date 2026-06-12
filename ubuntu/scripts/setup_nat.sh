#!/bin/bash
# setup_nat.sh — 配置 TUN 接口 + NAT + TCP MSS Clamping
# 每次 systemd 服务启动时执行 (ExecStartPre)

set -e

TUN_NAME="tun_hub"
TUN_IP="10.0.0.1"
TUN_PREFIX="24"

echo "=== TUN_NAT_HUB NAT 配置 ==="

# ── 检查 TUN 接口，没有就创建 ───────────────────
if ! ip link show "$TUN_NAME" &>/dev/null; then
    echo "创建 TUN 接口: $TUN_NAME"
    ip tuntap add dev "$TUN_NAME" mode tun
    ip addr add "${TUN_IP}/${TUN_PREFIX}" dev "$TUN_NAME"
    ip link set "$TUN_NAME" up
else
    echo "TUN 接口 $TUN_NAME 已存在，确保配置正确..."
    # 确保 IP 正确
    ip addr replace "${TUN_IP}/${TUN_PREFIX}" dev "$TUN_NAME"
    ip link set "$TUN_NAME" up
fi

echo "TUN 接口:"
ip addr show "$TUN_NAME" | grep inet

# ── 开启 IP 转发 ─────────────────────────────────
echo 1 > /proc/sys/net/ipv4/ip_forward
echo "IP 转发: 已启用"

# ── iptables SNAT ────────────────────────────────
# MASQUERADE: USB 侧的 IP 包 (源 10.0.0.x) 经 eth0/wan 发出时做源地址转换
if iptables -t nat -C POSTROUTING -s "10.0.0.0/24" -o eth0 -j MASQUERADE 2>/dev/null; then
    echo "MASQUERADE 规则已存在，跳过"
else
    iptables -t nat -A POSTROUTING -s "10.0.0.0/24" -o eth0 -j MASQUERADE
    echo "MASQUERADE 规则已添加"
fi

# ── iptables FORWARD ─────────────────────────────
if iptables -C FORWARD -i "$TUN_NAME" -o eth0 -j ACCEPT 2>/dev/null; then
    echo "FORWARD 规则已存在，跳过"
else
    iptables -A FORWARD -i "$TUN_NAME" -o eth0 -j ACCEPT
    iptables -A FORWARD -i eth0 -o "$TUN_NAME" \
        -m state --state ESTABLISHED,RELATED -j ACCEPT
    echo "FORWARD 规则已添加"
fi

# ── TCP MSS Clamping ─────────────────────────────
# 防止 TCP 协商 MSS 过大导致 IP 分片
# TUN MTU 1400 → TCP MSS 目标 ~1360
if iptables -t mangle -C FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu 2>/dev/null; then
    echo "TCPMSS clamping 规则已存在，跳过"
else
    iptables -t mangle -A FORWARD \
        -p tcp --tcp-flags SYN,RST SYN \
        -j TCPMSS --clamp-mss-to-pmtu
    echo "TCPMSS clamping 规则已添加"
fi

# ── 设置 TUN MTU ─────────────────────────────────
ip link set "$TUN_NAME" mtu 1400
echo "TUN MTU 已设为 1400"

echo ""
echo "=== NAT 配置完成 ==="
echo "当前 iptables NAT 规则:"
iptables -t nat -L POSTROUTING -n -v | grep -E "10.0.0|MASQ"
echo ""
echo "当前 FORWARD 规则:"
iptables -L FORWARD -n -v | grep -E "$TUN_NAME|ESTABLISHED"
