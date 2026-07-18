#!/bin/bash
set -e
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
PROJECT=/mnt/c/my_project/TUN_NAT_HUB
NCPU=20
echo "=== FULL CLEAN BUILD (A/B 4576k equal) ==="

cd /home/xlong/v3s/u-boot
chown -R xlong:xlong . 2>/dev/null || true
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- clean | tail -3
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j$NCPU | tail -5
cp spl/sunxi-spl.bin u-boot.bin $PROJECT/backup/
echo "[UBoot] SPL=$(stat -c%s spl/sunxi-spl.bin) UBoot=$(stat -c%s u-boot.bin)"
strings u-boot.bin | grep -o "root=/dev/mtdblock3" | head -1

cd /home/xlong/v3s/linux
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- clean | tail -3
sed -i 's/CONFIG_USB_G_SERIAL=m/CONFIG_USB_G_SERIAL=y/' .config
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j$NCPU zImage dtbs | tail -5
cp arch/arm/boot/zImage $PROJECT/backup/zImage_new
cp arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb $PROJECT/backup/sun8i-v3s-licheepi-zero-dock.dtb_new
echo "[Kernel] $(stat -c%s $PROJECT/backup/zImage_new) bytes"

cd /home/xlong/v3s/buildroot-2024.02
chown -R xlong:xlong output/target 2>/dev/null || true
O=board/allwinner/v3s_overlay
mkdir -p $O/etc/init.d $O/usr/local/bin $O/var/log $O/root
cp $PROJECT/ubuntu/scripts/S99tun_nat_hub $O/etc/init.d/
cp $PROJECT/ubuntu/scripts/setup_v3s_fixed.sh $O/usr/local/bin/setup_v3s.sh
chmod +x $O/etc/init.d/S99tun_nat_hub $O/usr/local/bin/setup_v3s.sh
make clean | tail -3
make | tail -20
arm-linux-gnueabihf-g++ -std=c++17 -Os -o output/target/usr/local/bin/web_server $PROJECT/ubuntu/src/web_server.cpp -lpthread 2>&1 | tail -2
chmod +x output/target/usr/local/bin/web_server
cp $PROJECT/ubuntu/scripts/S99tun_nat_hub output/target/etc/init.d/
cp $PROJECT/ubuntu/scripts/setup_v3s_fixed.sh output/target/usr/local/bin/setup_v3s.sh
chmod +x output/target/etc/init.d/S99tun_nat_hub output/target/usr/local/bin/setup_v3s.sh
rm -f output/images/rootfs.squashfs
mksquashfs output/target output/images/rootfs.squashfs -comp xz -b 1048576 -Xdict-size 1048576 -noappend | tail -3
cp output/images/rootfs.squashfs $PROJECT/backup/rootfs.squashfs
echo "[rootfs] $(stat -c%s $PROJECT/backup/rootfs.squashfs) bytes"

cd $PROJECT
python3 -B scripts/build_spi_final.py | tail -8
echo ""
echo "=== DONE ==="
ls -lh backup/spi_image.bin backup/rootfs.squashfs backup/zImage_new backup/sunxi-spl.bin backup/u-boot.bin
