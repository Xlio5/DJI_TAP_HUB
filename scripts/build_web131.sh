#!/bin/bash
set -e
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
PROJECT=/mnt/c/my_project/TUN_NAT_HUB
TGT=/home/xlong/v3s/buildroot-2024.02/output/target

echo "=== Compile web_server v1.3.1 ==="
arm-linux-gnueabihf-g++ -std=c++17 -Os -static \
  -o /tmp/web_server_v131 \
  $PROJECT/ubuntu/src/web_server.cpp \
  -lpthread 2>&1 | tail -3

ls -lh /tmp/web_server_v131

echo ""
echo "=== Features check ==="
echo "firmware page: $(strings /tmp/web_server_v131 | grep -c 'firmware/upload') refs"
echo "tmpfs path: $(strings /tmp/web_server_v131 | grep -c 'var/log/new_rootfs') refs"
echo "pending_flash: $(strings /tmp/web_server_v131 | grep -c 'pending_flash') refs"
echo "VERSION: $(strings /tmp/web_server_v131 | grep '#define VERSION' | head -1)"
echo "version string: $(strings /tmp/web_server_v131 | grep '"version.*1.3' | head -1)"
echo "peek size: $(strings /tmp/web_server_v131 | grep 'peek\[2048\]' | head -1)"

echo ""
echo "=== Update target ==="
cp /tmp/web_server_v131 $TGT/usr/local/bin/web_server
chmod +x $TGT/usr/local/bin/web_server

echo ""
echo "=== Rebuild squashfs ==="
cd /home/xlong/v3s/buildroot-2024.02
rm -f output/images/rootfs.squashfs
mksquashfs output/target output/images/rootfs.squashfs -comp xz -b 1048576 -Xdict-size 1048576 -noappend 2>&1 | tail -3
echo "rootfs: $(stat -c%s output/images/rootfs.squashfs) bytes"

echo ""
echo "=== Copy + rebuild SPI image ==="
cp output/images/rootfs.squashfs $PROJECT/backup/rootfs.squashfs
cd $PROJECT
python3 -B scripts/build_spi_final.py 2>&1 | tail -6
echo ""
echo "DONE"
ls -lh backup/spi_image.bin
