#!/bin/bash
set -e
PROJECT=/mnt/c/my_project/TUN_NAT_HUB
LINUX=/home/xlong/v3s/linux
UBOOT=/home/xlong/v3s/u-boot
NPROC=$(nproc)

echo "=== A1: Kernel clean ==="
cd $LINUX
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- clean 2>&1 | tail -3
sed -i 's/CONFIG_USB_G_SERIAL=m/CONFIG_USB_G_SERIAL=y/' .config

echo "=== A2: Kernel build ==="
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j$NPROC zImage dtbs 2>&1 | tail -10

ZIMAGE=$LINUX/arch/arm/boot/zImage
DTB=$LINUX/arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb
KSIZE=$(stat -c%s $ZIMAGE)
KHEX=$(printf "0x%X" $KSIZE)
echo "Kernel: $KSIZE bytes ($KHEX)"
cp $ZIMAGE $PROJECT/backup/zImage_new
cp $DTB $PROJECT/backup/sun8i-v3s-licheepi-zero-dock.dtb_new
echo "Kernel done"

echo ""
echo "=== A3: U-Boot clean ==="
cd $UBOOT
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- clean 2>&1 | tail -3

echo "=== A4: SPL patch (kernel=$KHEX) ==="
sed -i "s|(size 0x[0-9a-fA-F]*)|(size $KHEX)|" arch/arm/mach-sunxi/spl_spi_sunxi.c
sed -i "s|0x110000, 0x[0-9a-fA-F]*);|0x110000, $KHEX);|" arch/arm/mach-sunxi/spl_spi_sunxi.c
grep -A5 "TUN_NAT_HUB" arch/arm/mach-sunxi/spl_spi_sunxi.c

echo "=== A5: U-Boot build ==="
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j$NPROC 2>&1 | tail -10

echo "U-Boot done"
ls -lh spl/sunxi-spl.bin u-boot.bin
cp spl/sunxi-spl.bin u-boot.bin $PROJECT/backup/

echo ""
echo "=== A-LINE COMPLETE ==="
echo "zImage: $(stat -c%s $PROJECT/backup/zImage_new) bytes"
echo "DTB:    $(stat -c%s $PROJECT/backup/sun8i-v3s-licheepi-zero-dock.dtb_new) bytes"
echo "SPL:    $(stat -c%s $PROJECT/backup/sunxi-spl.bin) bytes"
echo "U-Boot: $(stat -c%s $PROJECT/backup/u-boot.bin) bytes"
