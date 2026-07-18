#!/bin/bash
set -e
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
PROJECT=/mnt/c/my_project/TUN_NAT_HUB
TGT=/home/xlong/v3s/buildroot-2024.02/output/target

echo "=== 1. Copy U-Boot ==="
cp /home/xlong/v3s/u-boot/spl/sunxi-spl.bin $PROJECT/backup/
cp /home/xlong/v3s/u-boot/u-boot.bin $PROJECT/backup/

echo "=== 2. Copy init scripts ==="
cp $PROJECT/ubuntu/scripts/S99tun_nat_hub $TGT/etc/init.d/
cp $PROJECT/ubuntu/scripts/setup_v3s_fixed.sh $TGT/usr/local/bin/setup_v3s.sh
chmod +x $TGT/etc/init.d/S99tun_nat_hub $TGT/usr/local/bin/setup_v3s.sh
echo "S99 A/B lines: $(grep -c mtdblock $TGT/etc/init.d/S99tun_nat_hub)"

echo "=== 3. Compile web_server ==="
arm-linux-gnueabihf-g++ -std=c++17 -Os -static \
  -o $TGT/usr/local/bin/web_server \
  $PROJECT/ubuntu/src/web_server.cpp -lpthread 2>&1 | tail -2
ls -lh $TGT/usr/local/bin/web_server

echo "=== 4. Build squashfs ==="
cd /home/xlong/v3s/buildroot-2024.02
rm -f output/images/rootfs.squashfs
mksquashfs output/target output/images/rootfs.squashfs -comp xz -noappend 2>&1 | tail -3
cp output/images/rootfs.squashfs $PROJECT/backup/rootfs.squashfs
echo "rootfs: $(stat -c%s $PROJECT/backup/rootfs.squashfs) bytes"

echo "=== 5. Build SPI image ==="
cd $PROJECT
python3 -B scripts/build_spi_final.py
echo ""
echo "=== DONE ==="
ls -lh backup/spi_image.bin
