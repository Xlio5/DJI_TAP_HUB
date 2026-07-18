#!/bin/bash
set -e
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
PROJECT=/mnt/c/my_project/TUN_NAT_HUB
BUILDROOT=/home/xlong/v3s/buildroot-2024.02

echo "=== 1. Build optimized squashfs (XZ -b 1M) ==="
cd $BUILDROOT
rm -f output/images/rootfs.squashfs
mksquashfs output/target output/images/rootfs.squashfs -comp xz -b 1048576 -Xdict-size 1048576 -noappend 2>&1 | tail -3
SZ=$(stat -c%s output/images/rootfs.squashfs)
echo "rootfs: $SZ bytes ($(($SZ/1024))KB)"
cp output/images/rootfs.squashfs $PROJECT/backup/rootfs.squashfs

echo ""
echo "=== 2. Rebuild U-Boot with 4800k mtdparts ==="
cd /home/xlong/v3s/u-boot
grep -o "4800k(rootfs_a)" .config | head -1
rm -f u-boot.bin spl/sunxi-spl.bin
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j20 2>&1 | tail -3
ls -lh spl/sunxi-spl.bin u-boot.bin
cp spl/sunxi-spl.bin u-boot.bin $PROJECT/backup/

echo ""
echo "=== 3. Build SPI image ==="
cd $PROJECT
python3 -B scripts/build_spi_final.py
echo ""
echo "=== DONE ==="
ls -lh backup/spi_image.bin
echo "Slot flag: $(hexdump -s 0xFC000 -n 1 -e '1/1 "0x%02X\n"' backup/spi_image.bin)"
