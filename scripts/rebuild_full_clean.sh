#!/bin/bash
set -eo pipefail
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
PROJECT=/mnt/c/my_project/TUN_NAT_HUB
LINUX=/home/xlong/v3s/linux
UBOOT=/home/xlong/v3s/u-boot
BUILDROOT=/home/xlong/v3s/buildroot-2024.02
NPROC=$(nproc)

exec > >(tee /tmp/rebuild_full.log) 2>&1
echo "============================================"
echo "  FULL CLEAN REBUILD"
echo "  $(date)"
echo "============================================"

# ======= KERNEL =======
echo ""
echo "=== [1/3] KERNEL ==="
cd $LINUX
find . -name '*.o' -delete 2>/dev/null || true
rm -f arch/arm/boot/zImage arch/arm/boot/dts/allwinner/*.dtb

python3 $PROJECT/scripts/patch_v3s_uart921600_clock.py

echo "make clean..."
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- clean 2>&1 | tail -3 || true

sed -i 's/CONFIG_USB_G_SERIAL=m/CONFIG_USB_G_SERIAL=y/' .config
echo "g_serial=$(grep CONFIG_USB_G_SERIAL .config)"

echo "Building kernel..."
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j$NPROC zImage dtbs 2>&1 | tail -5
echo "Kernel exit: $?"

ZIMAGE=$LINUX/arch/arm/boot/zImage
DTB=$LINUX/arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb
KSIZE=$(stat -c%s $ZIMAGE)
KHEX=$(printf "0x%X" $KSIZE)
echo "zImage: $KSIZE bytes ($KHEX)"
echo "DTB: $(stat -c%s $DTB) bytes"
cp $ZIMAGE $PROJECT/backup/zImage_new
cp $DTB $PROJECT/backup/sun8i-v3s-licheepi-zero-dock.dtb_new

# ======= U-BOOT =======
echo ""
echo "=== [2/3] U-BOOT ==="
cd $UBOOT
find . -name '*.o' -delete 2>/dev/null || true
rm -f spl/sunxi-spl.bin u-boot.bin u-boot.img

python3 $PROJECT/scripts/patch_v3s_uart921600_clock.py

chown -R xlong:xlong . 2>/dev/null || true

echo "make clean..."
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- clean 2>&1 | tail -3 || true

# 强制 U-Boot 交互串口和 Linux 控制台都使用 921600。
sed -i 's/^CONFIG_BAUDRATE=.*/CONFIG_BAUDRATE=921600/' .config
sed -i 's/console=ttyS0,115200/console=ttyS0,921600/g' .config
sed -i 's/console=ttyS0,115200/console=ttyS0,921600/g' include/configs/sunxi-common.h
echo "baudrate=$(grep '^CONFIG_BAUDRATE=' .config)"
echo "bootcmd=$(grep '^CONFIG_BOOTCOMMAND=' .config)"

# Update SPL preload
sed -i "s|(size 0x[0-9a-fA-F]*)|(size $KHEX)|" arch/arm/mach-sunxi/spl_spi_sunxi.c
sed -i "s|0x110000, 0x[0-9a-fA-F]*);|0x110000, $KHEX);|" arch/arm/mach-sunxi/spl_spi_sunxi.c

echo "Building U-Boot..."
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j$NPROC 2>&1 | tail -10
echo "U-Boot exit: $?"

echo "SPL: $(stat -c%s spl/sunxi-spl.bin) bytes"
echo "U-Boot: $(stat -c%s u-boot.bin) bytes"
echo "SPL header:"
hexdump -C -n 32 spl/sunxi-spl.bin

cp spl/sunxi-spl.bin $PROJECT/backup/
cp u-boot.bin $PROJECT/backup/

# Create combined image for SD card boot
echo "Creating u-boot-sunxi-with-spl.bin..."
cat spl/sunxi-spl.bin > /tmp/u-boot-sunxi-with-spl.bin
cat u-boot.bin >> /tmp/u-boot-sunxi-with-spl.bin
cp /tmp/u-boot-sunxi-with-spl.bin $PROJECT/backup/
echo "Combined: $(stat -c%s $PROJECT/backup/u-boot-sunxi-with-spl.bin) bytes"

# ======= BUILDROOT =======
echo ""
echo "=== [3/3] BUILDROOT ==="
cd $BUILDROOT
rm -rf output/build output/images output/staging 2>/dev/null || true
chown -R xlong:xlong output/target 2>/dev/null || true

# Ensure overlay is set
O=board/allwinner/v3s_overlay
mkdir -p $O/etc/init.d $O/usr/local/bin $O/var/log $O/root
cp $PROJECT/ubuntu/scripts/S99tun_nat_hub $O/etc/init.d/
cp $PROJECT/ubuntu/scripts/setup_v3s_fixed.sh $O/usr/local/bin/setup_v3s.sh
chmod +x $O/etc/init.d/S99tun_nat_hub $O/usr/local/bin/setup_v3s.sh
sed -i 's|BR2_ROOTFS_OVERLAY=""|BR2_ROOTFS_OVERLAY="board/allwinner/v3s_overlay"|' .config 2>/dev/null || true

echo "Building Buildroot..."
make olddefconfig 2>&1 | tail -3
make 2>&1 | tail -20
echo "Buildroot exit: $?"

ROOTFS=$BUILDROOT/output/images/rootfs.squashfs
if [ -f "$ROOTFS" ]; then
  echo "rootfs: $(stat -c%s $ROOTFS) bytes"

  # Copy fresh web_server + usb_tund into target
  cp output/target/usr/local/bin/web_server $O/usr/local/bin/ 2>/dev/null || true
  cp output/target/usr/local/bin/usb_tund $O/usr/local/bin/ 2>/dev/null || true

  # Rebuild rootfs with overlay
  rm -f output/images/rootfs.squashfs
  mksquashfs output/target output/images/rootfs.squashfs -comp xz -noappend 2>&1 | tail -3

  cp output/images/rootfs.squashfs $PROJECT/backup/rootfs.squashfs_new
  cp output/images/rootfs.squashfs $PROJECT/backup/rootfs.squashfs
  echo "rootfs copied ($(stat -c%s output/images/rootfs.squashfs) bytes)"
else
  echo "ERROR: rootfs not built!"
  exit 1
fi

echo ""
echo "============================================"
echo "  REBUILD COMPLETE $(date)"
echo "============================================"
echo "SPL:     $(stat -c%s $PROJECT/backup/sunxi-spl.bin) bytes"
echo "U-Boot:  $(stat -c%s $PROJECT/backup/u-boot.bin) bytes"
echo "zImage:  $(stat -c%s $PROJECT/backup/zImage_new) bytes"
echo "DTB:     $(stat -c%s $PROJECT/backup/sun8i-v3s-licheepi-zero-dock.dtb_new) bytes"
echo "rootfs:  $(stat -c%s $PROJECT/backup/rootfs.squashfs) bytes"
