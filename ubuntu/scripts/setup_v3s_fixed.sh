#!/bin/sh
# setup_v3s.sh - TUN + NAT + USB init (SPI Flash, dr_mode=peripheral)
set -e

_ts() { echo "[$(date +%H:%M:%S)] $*"; }

setup_uart_clocks() {
    if ! command -v devmem >/dev/null 2>&1; then
        _ts "UART: devmem not available, skip clock fix"
        return 0
    fi

    # APB2 = pll-periph0 / 27 ~= 22.222MHz.  This lets the V3s DW UART
    # 2-bit DLF approximate 921600 baud within 0.5%.
    devmem 0x01c20058 32 0x0200001a >/dev/null 2>&1 || true

    # UART0 console @921600: divisor 1, DLF 2/4.
    devmem 0x01c2800c 32 0x93 >/dev/null 2>&1 || true
    devmem 0x01c28000 32 0x01 >/dev/null 2>&1 || true
    devmem 0x01c28004 32 0x00 >/dev/null 2>&1 || true
    devmem 0x01c280c0 32 0x02 >/dev/null 2>&1 || true
    devmem 0x01c2800c 32 0x13 >/dev/null 2>&1 || true

    # UART1 DJI-B @921600: divisor 1, DLF 2/4.
    devmem 0x01c2840c 32 0x93 >/dev/null 2>&1 || true
    devmem 0x01c28400 32 0x01 >/dev/null 2>&1 || true
    devmem 0x01c28404 32 0x00 >/dev/null 2>&1 || true
    devmem 0x01c284c0 32 0x02 >/dev/null 2>&1 || true
    devmem 0x01c2840c 32 0x13 >/dev/null 2>&1 || true

    # UART2 DJI-A @115200 on the same APB2 clock: divisor 12, DLF 0.
    devmem 0x01c2880c 32 0x93 >/dev/null 2>&1 || true
    devmem 0x01c28800 32 0x0c >/dev/null 2>&1 || true
    devmem 0x01c28804 32 0x00 >/dev/null 2>&1 || true
    devmem 0x01c288c0 32 0x00 >/dev/null 2>&1 || true
    devmem 0x01c2880c 32 0x13 >/dev/null 2>&1 || true

    _ts "UART: APB2=22.222MHz, ttyS0/ttyS1=921600, ttyS2=115200"
}

if [ "$1" = "uart-only" ]; then
    setup_uart_clocks
    exit 0
fi

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
setup_uart_clocks
_ts "=== Setup complete ==="
