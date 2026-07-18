#!/bin/bash
set -e
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
cd /home/xlong/v3s/buildroot-2024.02

echo "=== Fixing overlay config ==="
# Enable overlay
sed -i 's|BR2_ROOTFS_OVERLAY=""|BR2_ROOTFS_OVERLAY="board/allwinner/v3s_overlay"|' .config
grep BR2_ROOTFS_OVERLAY .config

echo "=== Copy web_server to overlay ==="
ls -l output/target/usr/local/bin/web_server
cp output/target/usr/local/bin/web_server board/allwinner/v3s_overlay/usr/local/bin/
echo "web_server in overlay:"
ls -l board/allwinner/v3s_overlay/usr/local/bin/web_server

echo "=== Rebuilding rootfs ==="
make 2>&1 | tail -10

echo ""
echo "=== Verify new rootfs ==="
ls -lh output/images/rootfs.squashfs

echo "=== Check overlay in rootfs ==="
rm -rf /tmp/chk2
mkdir /tmp/chk2
unsquashfs -d /tmp/chk2 output/images/rootfs.squashfs 2>&1 | tail -3
ls -l /tmp/chk2/etc/init.d/S99* 2>/dev/null && echo "S99 OK" || echo "S99 MISSING"
ls -l /tmp/chk2/usr/local/bin/setup_v3s.sh 2>/dev/null && echo "setup_v3s OK" || echo "setup_v3s MISSING"
ls -l /tmp/chk2/usr/local/bin/web_server 2>/dev/null && echo "web_server OK" || echo "web_server MISSING"

echo ""
echo "=== Copy to backup ==="
cp output/images/rootfs.squashfs /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs.squashfs_new
echo "rootfs copied to backup/"
echo "DONE"
