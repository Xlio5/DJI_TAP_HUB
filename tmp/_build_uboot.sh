#!/bin/bash
# 完整重编 U-Boot (APB2 24MHz 修复 + PB6 bootcmd + 115200)
set -e
cd /home/xlong/v3s/u-boot
echo "=== 确认 bootcmd ==="
grep 'CONFIG_BOOTCOMMAND' .config | head -c 120
echo ""
echo "=== 重编 U-Boot ==="
NCPU=$(nproc)
make -j${NCPU} ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- 2>&1 | tail -12
echo ""
echo "=== 产物 ==="
md5sum u-boot.bin spl/sunxi-spl.bin
