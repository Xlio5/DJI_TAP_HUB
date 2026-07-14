#!/bin/bash
set -e
echo "=== Step 2: Kernel ==="
cd /home/xlong/v3s/linux
./scripts/config --enable MTD_BLOCK_RO 2>/dev/null
./scripts/config --enable SQUASHFS_XZ 2>/dev/null
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- olddefconfig 2>/dev/null
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j$(nproc) zImage dtbs 2>&1 | tail -5
ZIMAGE_SIZE=$(wc -c < arch/arm/boot/zImage)
echo "zImage: ${ZIMAGE_SIZE} bytes"

echo ""
echo "=== Step 3: SPI Image ==="
python3 /mnt/c/my_project/TUN_NAT_HUB/scripts/build_spi_final.py

echo ""
echo "=== DONE ==="
ls -lh /mnt/c/my_project/TUN_NAT_HUB/backup/spi_image.bin
