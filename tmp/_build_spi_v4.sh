#!/bin/bash
# 打包完整 spi_image v4: 新 U-Boot + 内核 + rootfs_v4
set -e
cd /mnt/c/my_project/TUN_NAT_HUB
python3 -B scripts/build_spi_image.py backup/rootfs_v4.squashfs backup/spi_image_v4.bin 2>&1 | tail -8
echo ""
md5sum backup/spi_image_v4.bin
echo "DONE"
