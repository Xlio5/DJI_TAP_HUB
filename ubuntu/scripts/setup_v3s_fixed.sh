#!/bin/sh
# setup_v3s.sh - TUN + NAT + USB init (SPI Flash edition)
set -e

TUN_NAME=tun_hub
TUN_IP=10.0.0.1
TUN_PREFIX=24
TUN_MTU=1400
TUN_SUBNET=10.0.0.0/24

echo "=== TUN_NAT_HUB V3s Setup ==="

# Bring up eth0
ip link set eth0 up 2>/dev/null || true

# Wait for DHCP (30s max)
for i in $(seq 1 30); do
    if ip addr show eth0 2>/dev/null | grep -q 'inet '; then
        break
    fi
    [ $i -eq 1 ] && echo "Waiting for DHCP..."
    sleep 1
done

# DHCP failed? Set static
if ! ip addr show eth0 2>/dev/null | grep -q 'inet '; then
    echo "DHCP failed, using static IP"
    ip addr add 192.168.144.66/24 dev eth0 2>/dev/null || true
fi
ip link set eth0 up

# Default route
ip route replace default via 192.168.144.1 dev eth0 2>/dev/null || true

# TUN interface
if ! ip link show $TUN_NAME >/dev/null 2>&1; then
    ip tuntap add dev $TUN_NAME mode tun
fi
ip addr replace ${TUN_IP}/${TUN_PREFIX} dev $TUN_NAME
ip link set $TUN_NAME mtu $TUN_MTU
ip link set $TUN_NAME up
echo "TUN: $TUN_IP/$TUN_PREFIX (mtu=$TUN_MTU)"

# IP forwarding
echo 1 > /proc/sys/net/ipv4/ip_forward

# LAN interface
LAN_IF=eth0
echo "LAN: $LAN_IF ($(ip addr show $LAN_IF 2>/dev/null | grep 'inet ' | awk '{print $2}'))"

# iptables NAT + FORWARD
iptables -t nat -D POSTROUTING -s $TUN_SUBNET -o $LAN_IF -j MASQUERADE 2>/dev/null || true
iptables -D FORWARD -i $TUN_NAME -o $LAN_IF -j ACCEPT 2>/dev/null || true
iptables -D FORWARD -i $LAN_IF -o $TUN_NAME -m state --state ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || true

iptables -t nat -A POSTROUTING -s $TUN_SUBNET -o $LAN_IF -j MASQUERADE
iptables -A FORWARD -i $TUN_NAME -o $LAN_IF -j ACCEPT
iptables -A FORWARD -i $LAN_IF -o $TUN_NAME -m state --state ESTABLISHED,RELATED -j ACCEPT
echo "NAT: $TUN_NAME <-> $LAN_IF (MASQUERADE)"

# USB mode: host -> sleep -> peripheral (force DJI RC detection)
MODE_SYSFS=/sys/devices/platform/soc/1c19000.usb/musb-hdrc.2.auto/mode
if [ -f "$MODE_SYSFS" ]; then
    echo host > "$MODE_SYSFS" 2>/dev/null || true
    sleep 3
    echo peripheral > "$MODE_SYSFS" 2>/dev/null || true
    echo "USB: peripheral mode"
fi

echo "=== Setup complete ==="
