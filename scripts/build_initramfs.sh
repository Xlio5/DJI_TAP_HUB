#!/bin/bash
set -e
cd /home/xlong/v3s/linux
D=/home/xlong/v3s/linux

echo "=== Step 1: Rebuild cpio with TUN_NAT_HUB files ==="
rm -rf /tmp/initramfs_root

# Extract Buildroot rootfs
mkdir -p /tmp/initramfs_root
tar xf /home/xlong/v3s/buildroot-2024.02/output/images/rootfs.tar -C /tmp/initramfs_root/
echo "Base rootfs: $(du -sh /tmp/initramfs_root | cut -f1)"

# Copy TUN_NAT_HUB custom files
mkdir -p /tmp/initramfs_root/usr/local/bin /tmp/initramfs_root/etc/init.d
cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/build_v3s/web_server /tmp/initramfs_root/usr/local/bin/
cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/build_v3s/usb_tund /tmp/initramfs_root/usr/local/bin/
cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/scripts/setup_v3s.sh /tmp/initramfs_root/usr/local/bin/
cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/scripts/S99tun_nat_hub_clean /tmp/initramfs_root/etc/init.d/S99tun_nat_hub
chmod +x /tmp/initramfs_root/usr/local/bin/web_server /tmp/initramfs_root/usr/local/bin/usb_tund /tmp/initramfs_root/usr/local/bin/setup_v3s.sh /tmp/initramfs_root/etc/init.d/S99tun_nat_hub

# Remove python3 leftovers
rm -rf /tmp/initramfs_root/usr/lib/python3* 2>/dev/null || true

echo "Files in /usr/local/bin:"
ls -la /tmp/initramfs_root/usr/local/bin/

# Build cpio
cd /tmp/initramfs_root
find . | cpio -o -H newc 2>/dev/null | gzip > /tmp/rootfs.cpio.gz
ls -lh /tmp/rootfs.cpio.gz

echo ""
echo "=== Step 2: Enable initramfs in kernel config ==="
cd $D

# Enable initramfs
scripts/config --enable BLK_DEV_INITRD
scripts/config --set-str INITRAMFS_SOURCE "/tmp/rootfs.cpio.gz"
scripts/config --enable INITRAMFS_COMPRESSION_GZIP

# Ensure squashfs, mtd, spi are built-in (not modules)
scripts/config --enable SQUASHFS
scripts/config --enable SQUASHFS_XZ
scripts/config --enable SQUASHFS_ZLIB
scripts/config --enable MTD
scripts/config --enable MTD_BLOCK
scripts/config --enable MTD_SPI_NOR
scripts/config --enable MTD_CMDLINE_PARTS
scripts/config --enable SPI_SUN6I
scripts/config --enable SPI
scripts/config --enable SPI_MASTER

make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- olddefconfig 2>&1 | tail -2

echo "=== Config check ==="
grep -E 'INITRAMFS_SOURCE|BLK_DEV_INITRD|SQUASHFS=|MTD_SPI_NOR|SPI_SUN6I' .config | grep -v 'not set\|^#'

echo ""
echo "=== Step 3: Build zImage ==="
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j4 zImage 2>&1 | tail -8

echo "=== Result ==="
ls -lh arch/arm/boot/zImage

echo ""
echo "=== Step 4: Create final SPI image ==="
# Build SPI script
python3 /mnt/c/my_project/TUN_NAT_HUB/scripts/build_spi_initramfs.py
