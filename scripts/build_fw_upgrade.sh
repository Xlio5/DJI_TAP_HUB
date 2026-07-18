#!/bin/bash
set -e
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
PROJECT=/mnt/c/my_project/TUN_NAT_HUB

echo "=== Compile web_server ==="
arm-linux-gnueabihf-g++ -std=c++17 -Os -static \
  -o /tmp/web_server_fw \
  $PROJECT/ubuntu/src/web_server.cpp \
  -lpthread 2>&1 | tail -3
ls -lh /tmp/web_server_fw

echo ""
echo "=== Checks ==="
strings /tmp/web_server_fw | grep "var/log/new_rootfs"
strings /tmp/web_server_fw | grep "pending_flash"
strings /tmp/web_server_fw | grep "Reboot now to flash"

echo ""
echo "=== Update target ==="
TGT=/home/xlong/v3s/buildroot-2024.02/output/target
cp /tmp/web_server_fw $TGT/usr/local/bin/web_server
cp $PROJECT/ubuntu/scripts/S99tun_nat_hub $TGT/etc/init.d/
chmod +x $TGT/etc/init.d/S99tun_nat_hub $TGT/usr/local/bin/web_server
echo "S99 pending_flash lines: $(grep -c 'pending_flash' $TGT/etc/init.d/S99tun_nat_hub)"

echo ""
echo "=== Regen rootfs ==="
cd /home/xlong/v3s/buildroot-2024.02
rm -f output/images/rootfs.squashfs
mksquashfs output/target output/images/rootfs.squashfs -comp xz -noappend 2>&1 | tail -3
cp output/images/rootfs.squashfs $PROJECT/backup/rootfs.squashfs
echo "rootfs: $(stat -c%s $PROJECT/backup/rootfs.squashfs) bytes"

echo ""
echo "=== Build SPI image ==="
cd $PROJECT
python3 -B scripts/build_spi_final.py 2>&1 | tail -5
echo ""
echo "DONE"
ls -lh backup/spi_image.bin
