#!/bin/bash
PROJECT=/mnt/c/my_project/TUN_NAT_HUB
LINUX=/home/xlong/v3s/linux
UBOOT=/home/xlong/v3s/u-boot
BUILDROOT=/home/xlong/v3s/buildroot-2024.02
NPROC=$(nproc)

echo "============================================"
echo "  TUN_NAT_HUB FULL REBUILD"
echo "============================================"

# ============ 1. KERNEL ============
echo ""
echo "=== [1/3] KERNEL ==="
cd $LINUX
echo "make clean..."
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- clean 2>&1 | tail -3

sed -i 's/CONFIG_USB_G_SERIAL=m/CONFIG_USB_G_SERIAL=y/' .config
echo "g_serial: $(grep CONFIG_USB_G_SERIAL .config)"

echo "Building..."
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j$NPROC zImage dtbs 2>&1 | tail -5

ZIMAGE=$LINUX/arch/arm/boot/zImage
DTB=$LINUX/arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb
KSIZE=$(stat -c%s $ZIMAGE)
KHEX=$(printf "0x%X" $KSIZE)
echo "Done: zImage=$KSIZE bytes DTB=$(stat -c%s $DTB) bytes"
cp $ZIMAGE $PROJECT/backup/zImage_new
cp $DTB $PROJECT/backup/sun8i-v3s-licheepi-zero-dock.dtb_new

# ============ 2. U-BOOT ============
echo ""
echo "=== [2/3] U-BOOT ==="
cd $UBOOT
echo "make clean..."
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- clean 2>&1 | tail -3

sed -i "s|(size 0x[0-9a-fA-F]*)|(size $KHEX)|" arch/arm/mach-sunxi/spl_spi_sunxi.c
sed -i "s|0x110000, 0x[0-9a-fA-F]*);|0x110000, $KHEX);|" arch/arm/mach-sunxi/spl_spi_sunxi.c

echo "Building..."
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j$NPROC 2>&1 | tail -5

cp spl/sunxi-spl.bin $PROJECT/backup/
cp u-boot.bin $PROJECT/backup/
echo "Done: SPL=$(stat -c%s $PROJECT/backup/sunxi-spl.bin) U-Boot=$(stat -c%s $PROJECT/backup/u-boot.bin)"

# ============ 3. BUILDROOT ============
echo ""
echo "=== [3/3] BUILDROOT ==="
cd $BUILDROOT

echo "Cleaning (rm -rf output)..."
rm -rf output/build output/images output/staging output/target 2>/dev/null
echo "Clean done"

echo "Overlay setup..."
O=board/allwinner/v3s_overlay
mkdir -p $O/etc/init.d $O/usr/local/bin $O/var/log $O/root
cp $PROJECT/ubuntu/scripts/S99tun_nat_hub $O/etc/init.d/
cp $PROJECT/ubuntu/scripts/setup_v3s_fixed.sh $O/usr/local/bin/setup_v3s.sh
chmod +x $O/etc/init.d/S99tun_nat_hub $O/usr/local/bin/setup_v3s.sh

echo "Building Buildroot..."
make 2>&1 | tail -30

ROOTFS=$BUILDROOT/output/images/rootfs.squashfs
if [ -f "$ROOTFS" ]; then
  cp $ROOTFS $PROJECT/backup/rootfs.squashfs_new
  echo "Done: rootfs=$(stat -c%s $ROOTFS) bytes"
else
  echo "ERROR: rootfs.squashfs not found!"
  exit 1
fi

echo ""
echo "============================================"
echo "  BUILD COMPLETE"
echo "============================================"
