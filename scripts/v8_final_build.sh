#!/bin/bash
set -e
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
PROJECT=/mnt/c/my_project/TUN_NAT_HUB
TGT=/home/xlong/v3s/buildroot-2024.02/output/target

echo "=== 1. U-Boot verify ==="
strings /home/xlong/v3s/u-boot/u-boot.bin | grep -o "root=/dev/mtdblock3"
strings /home/xlong/v3s/u-boot/u-boot.bin | grep -o "tun_nat_version=v1.3.1"
cp /home/xlong/v3s/u-boot/spl/sunxi-spl.bin /home/xlong/v3s/u-boot/u-boot.bin $PROJECT/backup/

echo ""
echo "=== 2. Kernel + DTB ==="
cp /home/xlong/v3s/linux/arch/arm/boot/zImage $PROJECT/backup/zImage_new
cp /home/xlong/v3s/linux/arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb $PROJECT/backup/sun8i-v3s-licheepi-zero-dock.dtb_new

echo ""
echo "=== 3. web_server ==="
arm-linux-gnueabihf-g++ -std=c++17 -Os -o $TGT/usr/local/bin/web_server $PROJECT/ubuntu/src/web_server.cpp -lpthread 2>&1 | tail -2
chmod +x $TGT/usr/local/bin/web_server
ls -lh $TGT/usr/local/bin/web_server

echo ""
echo "=== 4. Overlay ==="
O=/home/xlong/v3s/buildroot-2024.02/board/allwinner/v3s_overlay
mkdir -p $O/etc/init.d $O/usr/local/bin $O/var/log $O/root
cp $PROJECT/ubuntu/scripts/S99tun_nat_hub $O/etc/init.d/
cp $PROJECT/ubuntu/scripts/setup_v3s_fixed.sh $O/usr/local/bin/setup_v3s.sh
chmod +x $O/etc/init.d/S99tun_nat_hub $O/usr/local/bin/setup_v3s.sh
echo "S99 v1.3.1: $(grep -c v1.3.1 $O/etc/init.d/S99tun_nat_hub)"
echo "DHCP 3s: $(grep -c "seq 1 3" $O/usr/local/bin/setup_v3s.sh)"

echo ""
echo "=== 5. squashfs ==="
cd /home/xlong/v3s/buildroot-2024.02
rm -f output/images/rootfs.squashfs
mksquashfs output/target output/images/rootfs.squashfs -comp xz -b 1048576 -Xdict-size 1048576 -noappend 2>&1 | tail -3
cp output/images/rootfs.squashfs $PROJECT/backup/rootfs.squashfs
echo "rootfs: $(stat -c%s $PROJECT/backup/rootfs.squashfs) bytes"

echo ""
echo "=== 6. SPI image + FEL ==="
cd $PROJECT
python3 -B scripts/build_spi_final.py 2>&1 | tail -5
ls -lh backup/spi_image.bin
echo ""
sunxi-fel list 2>&1 || { echo "FEL NOT FOUND!"; exit 1; }
sunxi-fel spiflash-write 0 backup/spi_image.bin 2>&1
echo "EXIT=$?"
sunxi-fel spiflash-read 0 32 /tmp/v8.bin 2>&1
hexdump -C /tmp/v8.bin
echo "DONE v8"
