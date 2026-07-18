#!/bin/bash
set -e
cd /home/xlong/v3s/buildroot-2024.02

# Fix ownership
chown -R xlong:xlong output/target 2>/dev/null || true

# Copy overlay files into target
cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/scripts/S99tun_nat_hub output/target/etc/init.d/
cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/scripts/setup_v3s_fixed.sh output/target/usr/local/bin/setup_v3s.sh
chmod +x output/target/etc/init.d/S99tun_nat_hub output/target/usr/local/bin/setup_v3s.sh

# Copy freshly compiled web_server
cp /tmp/web_server output/target/usr/local/bin/

echo "=== Files in target ==="
ls -l output/target/etc/init.d/S99tun_nat_hub
ls -l output/target/usr/local/bin/setup_v3s.sh
ls -l output/target/usr/local/bin/web_server
ls -l output/target/usr/local/bin/usb_tund 2>/dev/null || echo "  usb_tund not found"

# Generate squashfs
echo "=== Generating squashfs (xz) ==="
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
mksquashfs output/target output/images/rootfs.squashfs -comp xz -noappend 2>&1 | tail -5
ls -lh output/images/rootfs.squashfs

# Verify
rm -rf /tmp/vrfy
mkdir /tmp/vrfy
unsquashfs -d /tmp/vrfy output/images/rootfs.squashfs 2>&1 | tail -3

echo ""
echo "=== Verify overlay ==="
ls -l /tmp/vrfy/etc/init.d/S99tun_nat_hub && echo "  S99 OK"
ls -l /tmp/vrfy/usr/local/bin/setup_v3s.sh && echo "  setup_v3s OK"
ls -l /tmp/vrfy/usr/local/bin/web_server && echo "  web_server OK"
find /tmp/vrfy -name usb_tund -type f 2>/dev/null && echo "  usb_tund OK" || echo "  usb_tund MISSING"

# Copy to backup
cp output/images/rootfs.squashfs /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs.squashfs_new
echo ""
echo "=== DONE. rootfs in backup/rootfs.squashfs_new ==="
