#!/bin/sh
# setup_v3s.sh — V3s 一键配置 (g_serial + TUN + NAT + daemon)
# V3s 上所有驱动已编译进内核，无需 modprobe
set -e

echo "=== TUN_NAT_HUB V3s Setup ==="

TUN_NAME="tun_hub"
TUN_IP="10.0.0.1"
TUN_PREFIX="24"
TUN_MTU="1400"
TUN_SUBNET="${TUN_IP%.*}.0/24"

# 1. USB Gadget: g_serial 已内置，只需触发绑定
#    (modprobe 报 /lib/modules 缺失可忽略 — 驱动已在内核中)
if [ -c /dev/ttyGS0 ]; then
    echo "g_serial: /dev/ttyGS0 已就绪"
else
    # 尝试通过 sysfs 触发（如果模块未自动加载）
    echo "触发 g_serial..."
    modprobe g_serial use_acm=0 idVendor=0x0BDA idProduct=0x8812 2>/dev/null || true
    if [ ! -c /dev/ttyGS0 ]; then
        # 如果模块内建，可能需要 echo 到 sysfs
        echo "g_serial" > /sys/kernel/config/usb_gadget/ 2>/dev/null || true
    fi
fi
chmod 666 /dev/ttyGS0 2>/dev/null || true
ls -l /dev/ttyGS0

# 2. 以太网（如果网线已插）
ip link set eth0 up 2>/dev/null || true

# 3. TUN 接口
if ! ip link show "$TUN_NAME" &>/dev/null; then
    ip tuntap add dev "$TUN_NAME" mode tun
fi
ip addr replace "${TUN_IP}/${TUN_PREFIX}" dev "$TUN_NAME"
ip link set "$TUN_NAME" mtu "$TUN_MTU"
ip link set "$TUN_NAME" up
echo "TUN: $TUN_IP/$TUN_PREFIX (mtu=$TUN_MTU)"

# 4. IP 转发
echo 1 > /proc/sys/net/ipv4/ip_forward

# 5. iptables NAT（如果 LAN 接口有 IP）
LAN_IF=""
for iface in eth0 end0 end1 enp1s0; do
    if ip addr show "$iface" 2>/dev/null | grep -q 'inet '; then
        LAN_IF="$iface"
        break
    fi
done

if [ -n "$LAN_IF" ]; then
    echo "LAN: $LAN_IF ($(ip addr show $LAN_IF | grep 'inet ' | awk '{print $2}'))"

    # 清旧规则
    iptables -t nat -D POSTROUTING -s "$TUN_SUBNET" -o "$LAN_IF" -j MASQUERADE 2>/dev/null || true
    iptables -D FORWARD -i "$TUN_NAME" -o "$LAN_IF" -j ACCEPT 2>/dev/null || true
    iptables -D FORWARD -i "$LAN_IF" -o "$TUN_NAME" -m state --state ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || true

    # 新规则
    iptables -t nat -A POSTROUTING -s "$TUN_SUBNET" -o "$LAN_IF" -j MASQUERADE
    iptables -A FORWARD -i "$TUN_NAME" -o "$LAN_IF" -j ACCEPT
    iptables -A FORWARD -i "$LAN_IF" -o "$TUN_NAME" -m state --state ESTABLISHED,RELATED -j ACCEPT

    echo "NAT: $TUN_NAME <-> $LAN_IF (MASQUERADE)"
else
    echo "WARNING: 无 LAN 接口有 IP，NAT 未配置"
fi

echo "=== Setup 完成 ==="
