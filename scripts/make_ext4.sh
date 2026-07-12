#!/bin/bash
set -e

ROOTFS_TAR=/home/xlong/v3s/buildroot-2024.02/output/images/rootfs.tar
TUN_DIR=/mnt/c/my_project/TUN_NAT_HUB
OUT=/tmp/rootfs_new.ext4

echo "=== Extracting rootfs ==="
rm -rf /tmp/clean_root
mkdir -p /tmp/clean_root
tar xf "$ROOTFS_TAR" -C /tmp/clean_root/
echo "OK: $(du -sh /tmp/clean_root/ | cut -f1)"

echo "=== Copying TUN_NAT_HUB files ==="
mkdir -p /tmp/clean_root/usr/local/bin
cp "$TUN_DIR/ubuntu/build_v3s/web_server" /tmp/clean_root/usr/local/bin/
cp "$TUN_DIR/ubuntu/build_v3s/usb_tund" /tmp/clean_root/usr/local/bin/
cp "$TUN_DIR/ubuntu/scripts/setup_v3s.sh" /tmp/clean_root/usr/local/bin/
chmod +x /tmp/clean_root/usr/local/bin/web_server
chmod +x /tmp/clean_root/usr/local/bin/usb_tund
chmod +x /tmp/clean_root/usr/local/bin/setup_v3s.sh
echo "OK"

echo "=== Writing init script ==="
mkdir -p /tmp/clean_root/etc/init.d
cp "$TUN_DIR/ubuntu/scripts/S99tun_nat_hub_clean" /tmp/clean_root/etc/init.d/S99tun_nat_hub
chmod +x /tmp/clean_root/etc/init.d/S99tun_nat_hub
echo "OK"

echo "=== Creating ext4 image ==="
rm -f "$OUT"
MKFS="/home/xlong/v3s/buildroot-2024.02/output/host/sbin/mkfs.ext4"
"$MKFS" -d /tmp/clean_root -L rootfs -O '^64bit' "$OUT" 200M
ls -lh "$OUT"

echo "=== Copy to project ==="
cp "$OUT" /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_new.ext4
echo "Done! $(ls -lh "$OUT")"
