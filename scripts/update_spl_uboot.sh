#!/bin/bash
set -e
cd /home/xlong/v3s/u-boot

KHEX=0x5A78B8
SPL=arch/arm/mach-sunxi/spl_spi_sunxi.c

echo "=== Before ==="
grep -A5 "TUN_NAT_HUB" $SPL

# Update kernel size in comment and code
sed -i "s|(size 0x[0-9a-fA-F]*)|(size $KHEX)|" $SPL
sed -i "s|0x110000, 0x[0-9a-fA-F]*);|0x110000, $KHEX);|" $SPL

echo "=== After ==="
grep -A5 "TUN_NAT_HUB" $SPL

echo ""
echo "=== Building U-Boot ==="
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j$(nproc) 2>&1 | tail -10

echo ""
echo "=== Output ==="
ls -lh spl/sunxi-spl.bin u-boot.bin

# Copy to project backup
cp spl/sunxi-spl.bin /mnt/c/my_project/TUN_NAT_HUB/backup/
cp u-boot.bin /mnt/c/my_project/TUN_NAT_HUB/backup/
echo "U-Boot binaries copied to backup/"
