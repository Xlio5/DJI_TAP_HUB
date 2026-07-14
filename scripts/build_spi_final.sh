#!/bin/bash
# TUN_NAT_HUB SPI 完整编译 (在 WSL 里运行)
set -e
echo "=== Build U-Boot ==="
cd /home/xlong/v3s/u-boot
bash /mnt/c/my_project/TUN_NAT_HUB/scripts/rebuild_uboot.sh

echo ""
echo "=== Build Kernel ==="
cd /home/xlong/v3s/linux
scripts/config --enable MTD_BLOCK_RO 2>/dev/null; scripts/config --enable SQUASHFS_XZ 2>/dev/null
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- olddefconfig 2>/dev/null
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j4 zImage dtbs 2>&1 | tail -3
echo "zImage: $(wc -c < arch/arm/boot/zImage) bytes"

echo ""
echo "=== Build SPI image ==="
python3 /mnt/c/my_project/TUN_NAT_HUB/scripts/build_spi_final.py
echo "DONE: /mnt/c/my_project/TUN_NAT_HUB/backup/spi_image.bin"
ls -lh /mnt/c/my_project/TUN_NAT_HUB/backup/spi_image.bin
