#!/bin/bash
set -e
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
PROJECT=/mnt/c/my_project/TUN_NAT_HUB
NPROC=20
echo "=== U-Boot ==="
cd /home/xlong/v3s/u-boot
chown -R xlong:xlong . 2>/dev/null || true
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- clean | tail -3
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j$NPROC | tail -5
cp spl/sunxi-spl.bin u-boot.bin $PROJECT/backup/
echo "U-Boot done"

echo ""
echo "=== Kernel ==="
cd /home/xlong/v3s/linux
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- clean | tail -3
sed -i 's/CONFIG_USB_G_SERIAL=m/CONFIG_USB_G_SERIAL=y/' .config
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j$NPROC zImage dtbs | tail -5
cp arch/arm/boot/zImage $PROJECT/backup/zImage_new
cp arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb $PROJECT/backup/sun8i-v3s-licheepi-zero-dock.dtb_new
echo "Kernel done"

echo ""
echo "=== Buildroot ==="
cd /home/xlong/v3s/buildroot-2024.02
chown -R xlong:xlong output/target 2>/dev/null || true
O=board/allwinner/v3s_overlay
mkdir -p $O/etc/init.d $O/usr/local/bin $O/var/log $O/root
cp $PROJECT/ubuntu/scripts/S99tun_nat_hub $O/etc/init.d/
cp $PROJECT/ubuntu/scripts/setup_v3s_fixed.sh $O/usr/local/bin/setup_v3s.sh
chmod +x $O/etc/init.d/S99tun_nat_hub $O/usr/local/bin/setup_v3s.sh
make clean | tail -3
make | tail -20
mksquashfs output/target $PROJECT/backup/rootfs.squashfs -comp xz -b 1048576 -Xdict-size 1048576 -noappend | tail -3
echo ""
echo "=== ALL DONE ==="
ls -lh $PROJECT/backup/sunxi-spl.bin $PROJECT/backup/u-boot.bin $PROJECT/backup/zImage_new $PROJECT/backup/rootfs.squashfs
