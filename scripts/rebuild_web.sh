#!/bin/bash
set -e
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

echo "=== Compile web_server v1.3.1 ==="
arm-linux-gnueabihf-g++ -std=c++17 -Os -static \
  -o /tmp/web_server_v131 \
  /mnt/c/my_project/TUN_NAT_HUB/ubuntu/src/web_server.cpp \
  -lpthread 2>&1 | tail -5

ls -lh /tmp/web_server_v131

echo ""
echo "=== Features in binary ==="
strings /tmp/web_server_v131 | grep "固件升级"
strings /tmp/web_server_v131 | grep "firmware/upload" | head -2

echo ""
echo "=== Update target ==="
TGT=/home/xlong/v3s/buildroot-2024.02/output/target
cp /tmp/web_server_v131 $TGT/usr/local/bin/web_server
ls -lh $TGT/usr/local/bin/web_server

echo ""
echo "=== Rebuild rootfs ==="
cd /home/xlong/v3s/buildroot-2024.02
rm -f output/images/rootfs.squashfs
mksquashfs output/target output/images/rootfs.squashfs -comp xz -noappend 2>&1 | tail -3

cp output/images/rootfs.squashfs /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs.squashfs

echo ""
echo "=== SPI image ==="
cd /mnt/c/my_project/TUN_NAT_HUB
python3 -B scripts/build_spi_final.py 2>&1 | tail -5

echo ""
echo "DONE"
ls -lh backup/spi_image.bin
