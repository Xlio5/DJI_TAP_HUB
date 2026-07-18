#!/bin/bash
set -e
PROJECT=/mnt/c/my_project/TUN_NAT_HUB
BUILDROOT=/home/xlong/v3s/buildroot-2024.02
LINUX=/home/xlong/v3s/linux
UBOOT=/home/xlong/v3s/u-boot
NPROC=$(nproc)

echo "============================================"
echo "  TUN_NAT_HUB FULL CLEAN REBUILD"
echo "  Kernel + U-Boot + Buildroot"
echo "============================================"

# ============================================
# 1. KERNEL: clean + build
# ============================================
echo ""
echo "============================================"
echo "  [1/3] KERNEL"
echo "============================================"
cd $LINUX

echo "--- Cleaning kernel ---"
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- clean 2>&1 | tail -3

# Ensure g_serial is builtin
sed -i 's/CONFIG_USB_G_SERIAL=m/CONFIG_USB_G_SERIAL=y/' .config
echo "g_serial: $(grep CONFIG_USB_G_SERIAL .config)"

echo "--- Building kernel ---"
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j$NPROC zImage dtbs 2>&1 | tail -10

ZIMAGE=$LINUX/arch/arm/boot/zImage
DTB=$LINUX/arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb
KSIZE=$(stat -c%s $ZIMAGE)
echo ""
echo "=== Kernel done ==="
echo "zImage: $KSIZE bytes"
echo "DTB:    $(stat -c%s $DTB) bytes"

# Copy to project
cp $ZIMAGE $PROJECT/backup/zImage_new
cp $DTB $PROJECT/backup/sun8i-v3s-licheepi-zero-dock.dtb_new
echo "Copied to backup/"

# ============================================
# 2. U-BOOT: clean + update SPL + build
# ============================================
echo ""
echo "============================================"
echo "  [2/3] U-BOOT"
echo "============================================"
cd $UBOOT

echo "--- Cleaning U-Boot ---"
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- clean 2>&1 | tail -3

# Update SPL preload kernel size
KHEX=$(printf "0x%X" $KSIZE)
sed -i "s|(size 0x[0-9a-fA-F]*)|(size $KHEX)|" arch/arm/mach-sunxi/spl_spi_sunxi.c
sed -i "s|0x110000, 0x[0-9a-fA-F]*);|0x110000, $KHEX);|" arch/arm/mach-sunxi/spl_spi_sunxi.c
echo "SPL preload size: $KHEX"

echo "--- Building U-Boot ---"
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j$NPROC 2>&1 | tail -10

echo ""
echo "=== U-Boot done ==="
ls -lh spl/sunxi-spl.bin u-boot.bin

cp spl/sunxi-spl.bin $PROJECT/backup/
cp u-boot.bin $PROJECT/backup/
echo "Copied to backup/"

# ============================================
# 3. BUILDROOT: clean + rebuild
# ============================================
echo ""
echo "============================================"
echo "  [3/3] BUILDROOT"
echo "============================================"
cd $BUILDROOT

echo "--- Cleaning Buildroot ---"
make clean 2>&1 | tail -5

echo "--- Setting up overlay ---"
O=board/allwinner/v3s_overlay
mkdir -p $O/etc/init.d $O/usr/local/bin $O/var/log $O/root

cp $PROJECT/ubuntu/scripts/S99tun_nat_hub $O/etc/init.d/
cp $PROJECT/ubuntu/scripts/setup_v3s_fixed.sh $O/usr/local/bin/setup_v3s.sh
chmod +x $O/etc/init.d/S99tun_nat_hub $O/usr/local/bin/setup_v3s.sh

echo "Overlay: $(find $O -type f | wc -l) files"

echo "--- Building Buildroot ---"
make 2>&1 | tail -20

echo ""
echo "=== Buildroot done ==="
ROOTFS=$BUILDROOT/output/images/rootfs.squashfs
echo "rootfs: $(stat -c%s $ROOTFS) bytes"

cp $ROOTFS $PROJECT/backup/rootfs.squashfs_new
echo "Copied to backup/"

echo ""
echo "============================================"
echo "  ALL DONE"
echo "============================================"
echo "SPL:       $(stat -c%s $PROJECT/backup/sunxi-spl.bin) bytes"
echo "U-Boot:    $(stat -c%s $PROJECT/backup/u-boot.bin) bytes"
echo "zImage:    $(stat -c%s $PROJECT/backup/zImage_new) bytes"
echo "DTB:       $(stat -c%s $PROJECT/backup/sun8i-v3s-licheepi-zero-dock.dtb_new) bytes"
echo "rootfs:    $(stat -c%s $PROJECT/backup/rootfs.squashfs_new) bytes"
echo ""
echo "Ready for SPI image assembly."
