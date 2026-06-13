#!/bin/bash
# setup_nat.sh — 自动检测 LAN 网口并配置 TUN + NAT
# 等待网口获得 IP，支持开机慢 DHCP

set -e
TUN_NAME="tun_hub"
TUN_IP="10.0.0.1"
TUN_PREFIX="24"
TUN_MTU="1400"
TUN_SUBNET="${TUN_IP%.*}.0/24"

echo "=== TUN_NAT_HUB NAT 配置 ==="

# ── 等待并检测 LAN 网口 ───────────────────────────
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

# 开机时 DHCP 可能慢，等待最多 60 秒
LAN_IF=""
for i in $(seq 1 60); do
    LAN_IF=$(get_lan_iface)
    [ -n "$LAN_IF" ] && break
    [ $i -eq 1 ] && echo "等待 LAN 网口获得 IP..."
    sleep 1
done

if [ -z "$LAN_IF" ]; then
    echo "错误: 60 秒后仍未检测到 LAN 网口，TUN 隧道数据无法转发"
    # 仍然创建 TUN 接口供 USB 通信使用
else
    echo "检测到 LAN 网口: $LAN_IF ($(ip addr show $LAN_IF | grep 'inet ' | awk '{print $2}'))"
fi

# ── TUN 接口 ──────────────────────────────────────
if ! ip link show "$TUN_NAME" &>/dev/null; then
    ip tuntap add dev "$TUN_NAME" mode tun
fi
ip addr replace "${TUN_IP}/${TUN_PREFIX}" dev "$TUN_NAME"
ip link set "$TUN_NAME" mtu "$TUN_MTU"
ip link set "$TUN_NAME" txqueuelen 10
ip link set "$TUN_NAME" up
tc qdisc replace dev "$TUN_NAME" root pfifo limit 10 2>/dev/null || true

# ── USB ECM/RNDIS 接口 ──────────────────────────────
USB_IFACE=""
for candidate in usb0 usb1 rndis0; do
    if ip link show "$candidate" &>/dev/null; then
        USB_IFACE="$candidate"
        break
    fi
done

if [ -n "$USB_IFACE" ]; then
    ip addr replace "10.0.0.1/24" dev "$USB_IFACE"
    ip link set "$USB_IFACE" up
    echo "USB Gadget 接口已配置: $USB_IFACE (10.0.0.1/24)"

    # ── DHCP for Android ECM client (可选) ──────────
    # Android 内核检测到 ECM gadget 后会自动 DHCP 获取 IP
    if command -v dnsmasq &>/dev/null; then
        if ! pgrep -f "dnsmasq.*$USB_IFACE" &>/dev/null; then
            dnsmasq --interface="$USB_IFACE" \
                    --bind-interfaces \
                    --dhcp-range=10.0.0.100,10.0.0.200,255.255.255.0,12h \
                    --port=0 \
                    --no-resolv \
                    --no-hosts \
                    2>/dev/null || echo "dnsmasq 启动失败（可能端口冲突，非致命）"
            echo "DHCP 服务已启动: $USB_IFACE (10.0.0.100-200)"
        fi
    fi
else
    echo "警告: 未检测到 USB Gadget 接口，请先运行 setup_gadget.sh"
fi

# ── IP 转发 ────────────────────────────────────────
echo 1 > /proc/sys/net/ipv4/ip_forward

# ── iptables ───────────────────────────────────────
if [ -n "$LAN_IF" ]; then
    # 清除旧规则（忽略不存在的）
    iptables -t nat -D POSTROUTING -s "$TUN_SUBNET" -o "$LAN_IF" -j MASQUERADE 2>/dev/null || true
    iptables -D FORWARD -i "$TUN_NAME" -o "$LAN_IF" -j ACCEPT 2>/dev/null || true
    iptables -D FORWARD -i "$LAN_IF" -o "$TUN_NAME" -m state --state ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || true
    iptables -D FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu 2>/dev/null || true

    # 添加规则
    iptables -t nat -A POSTROUTING -s "$TUN_SUBNET" -o "$LAN_IF" -j MASQUERADE
    iptables -A FORWARD -i "$TUN_NAME" -o "$LAN_IF" -j ACCEPT
    iptables -A FORWARD -i "$LAN_IF" -o "$TUN_NAME" -m state --state ESTABLISHED,RELATED -j ACCEPT
    iptables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu

    echo "NAT 规则已添加: $TUN_NAME ↔ $LAN_IF"
else
    echo "警告: LAN 网口不可用，数据无法转发到局域网"
fi

echo "NAT 配置完成 (ECM/RNDIS 模式)"
