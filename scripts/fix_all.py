#!/usr/bin/env python3
"""重建 setup_v3s.sh + squashfs + SPI镜像 — 一劳永逸"""
import subprocess, os, time

print("=== Step 1: Create fixed setup script ===")
setup_script = """#!/bin/sh
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
"""

# Write to project
setup_path = r"c:\my_project\TUN_NAT_HUB\ubuntu\scripts\setup_v3s_fixed.sh"
with open(setup_path, "w", newline="\n") as f:
    f.write(setup_script)
print(f"Setup script: {setup_path}")

print("\n=== Step 2: Rebuild squashfs with fixed script ===")
# Copy to WSL and rebuild
subprocess.run(
    ["wsl", "-u", "root", "-e", "bash", "-c",
     f"mkdir -p /tmp/sq/usr/local/bin /tmp/sq/etc/init.d && "
     f"tar xf /home/xlong/v3s/buildroot-2024.02/output/images/rootfs.tar -C /tmp/sq/ && "
     f"cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/build_v3s/web_server /tmp/sq/usr/local/bin/ && "
     f"cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/build_v3s/usb_tund /tmp/sq/usr/local/bin/ && "
     f"cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/scripts/S99tun_nat_hub_clean /tmp/sq/etc/init.d/S99tun_nat_hub && "
     f"cp /tmp/sq/usr/local/bin/setup_v3s.sh /tmp/sq/usr/local/bin/setup_v3s.sh.orig 2>/dev/null; "
     f"cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/scripts/setup_v3s_fixed.sh /tmp/sq/usr/local/bin/setup_v3s.sh && "
     f"chmod +x /tmp/sq/usr/local/bin/web_server /tmp/sq/usr/local/bin/usb_tund /tmp/sq/usr/local/bin/setup_v3s.sh /tmp/sq/etc/init.d/S99tun_nat_hub && "
     f"rm -rf /tmp/sq/usr/lib/python3* 2>/dev/null; "
     f"mksquashfs /tmp/sq /tmp/rootfs_final.squashfs -comp xz -b 128K -noappend 2>&1 && "
     f"cp /tmp/rootfs_final.squashfs /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs.squashfs && "
     f"ls -lh /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs.squashfs"],
    check=True, timeout=120)

print("\n=== Step 3: Rebuild SPI image ===")
subprocess.run(
    ["wsl", "-u", "root", "-e", "bash", "-c",
     "python3 /mnt/c/my_project/TUN_NAT_HUB/scripts/build_spi_final.py"],
    check=True, timeout=30)

print("\n=== Step 4: Upload + flash SPI ===")
import paramiko
SPI = r"c:\my_project\TUN_NAT_HUB\backup\spi_image.bin"
with open(SPI, "rb") as f:
    data = f.read()
print(f"SPI: {len(data)} bytes")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("192.168.144.66", username="root", password="root", timeout=10)

# Upload
chan = ssh.get_transport().open_session()
chan.exec_command("cat > /tmp/spi.bin && echo UP_OK")
time.sleep(0.2)
for i in range(0, len(data), 65536):
    chan.sendall(data[i:i+65536])
chan.shutdown_write()
time.sleep(2)
chan.recv(4096)
chan.close()

# Verify + flash
_, o, _ = ssh.exec_command("wc -c /tmp/spi.bin", timeout=5)
if str(len(data)) in o.read().decode():
    print("Upload OK. Flashing...")
    _, o, e = ssh.exec_command("dd if=/tmp/spi.bin of=/dev/mtdblock0 bs=4096 2>&1 & sleep 20; hexdump -C -n 16 /dev/mtd0 2>&1 | head -3", timeout=30)
    out = o.read().decode()
    print(out[:200])
    print("Done! Power off, remove SD, power on.")
else:
    print("Upload FAILED")

ssh.close()
print("\n=== ALL DONE ===")
