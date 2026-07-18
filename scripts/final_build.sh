#!/bin/bash
set -e
PROJECT=/mnt/c/my_project/TUN_NAT_HUB
BUILDROOT=/home/xlong/v3s/buildroot-2024.02
LINUX=/home/xlong/v3s/linux
UBOOT=/home/xlong/v3s/u-boot

echo "============================================"
echo "  TUN_NAT_HUB FULL REBUILD"
echo "============================================"

# === 1. VERIFY U-BOOT ===
echo ""
echo "[1/6] U-Boot build..."
SPL=$UBOOT/spl/sunxi-spl.bin
UBOOT_BIN=$UBOOT/u-boot.bin
echo "SPL: $(stat -c%s $SPL) bytes"
echo "U-Boot: $(stat -c%s $UBOOT_BIN) bytes"
echo "SPL preload:"
grep "spi0_read_data" $UBOOT/arch/arm/mach-sunxi/spl_spi_sunxi.c | tail -2

# === 2. VERIFY KERNEL ===
echo ""
echo "[2/6] Kernel..."
ZIMAGE=$LINUX/arch/arm/boot/zImage
DTB=$LINUX/arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb
echo "zImage: $(stat -c%s $ZIMAGE) bytes"
echo "DTB: $(stat -c%s $DTB) bytes"
echo "g_serial: $(grep CONFIG_USB_G_SERIAL $LINUX/.config)"
echo "SQUASHFS_XZ: $(grep CONFIG_SQUASHFS_XZ $LINUX/.config)"

# === 3. SETUP OVERLAY ===
echo ""
echo "[3/6] Overlay setup..."
O=$BUILDROOT/board/allwinner/v3s_overlay
mkdir -p $O/etc/init.d $O/usr/local/bin $O/var/log $O/root

# S99 init
cp $PROJECT/ubuntu/scripts/S99tun_nat_hub $O/etc/init.d/
cp $PROJECT/ubuntu/scripts/setup_v3s_fixed.sh $O/usr/local/bin/setup_v3s.sh
chmod +x $O/etc/init.d/S99tun_nat_hub $O/usr/local/bin/setup_v3s.sh

# web_server (pre-compiled by Buildroot)
cp $BUILDROOT/output/target/usr/local/bin/web_server $O/usr/local/bin/

echo "Overlay files:"
find $O -type f | sort

# === 4. BUILD rootfs ===
echo ""
echo "[4/6] Building rootfs..."
cd $BUILDROOT
make 2>&1 | tail -10

ROOTFS=$BUILDROOT/output/images/rootfs.squashfs
echo "rootfs: $(stat -c%s $ROOTFS) bytes"

# === 5. COPY ALL TO BACKUP ===
echo ""
echo "[5/6] Copying to backup..."
cp $ZIMAGE $PROJECT/backup/zImage_new
cp $DTB $PROJECT/backup/sun8i-v3s-licheepi-zero-dock.dtb_new
cp $SPL $PROJECT/backup/
cp $UBOOT_BIN $PROJECT/backup/
cp $ROOTFS $PROJECT/backup/rootfs.squashfs_new

echo "Backup files:"
ls -lh $PROJECT/backup/zImage_new $PROJECT/backup/sun8i-v3s-licheepi-zero-dock.dtb_new $PROJECT/backup/sunxi-spl.bin $PROJECT/backup/u-boot.bin $PROJECT/backup/rootfs.squashfs_new 2>/dev/null

echo ""
echo "============================================"
echo "  BUILD COMPLETE"
echo "============================================"
echo ""
echo "Files ready for SPI image assembly:"
echo "  SPL:       sunxi-spl.bin"
echo "  U-Boot:    u-boot.bin"
echo "  DTB:       sun8i-v3s-licheepi-zero-dock.dtb_new"
echo "  zImage:    zImage_new"
echo "  rootfs:    rootfs.squashfs_new"
echo ""
echo "Next: run build_spi_final.py"
