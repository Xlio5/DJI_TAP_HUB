#!/bin/bash
# 完整重编内核 (zImage + DTB)
set -e
cd /home/xlong/v3s/linux
NCPU=$(nproc)
echo "=== 重编内核 zImage ==="
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- zImage 2>&1 | tail -5
echo ""
echo "=== 重编 DTB ==="
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- allwinner/sun8i-v3s-licheepi-zero-dock.dtb 2>&1 | tail -5
echo ""
echo "=== 产物 ==="
ls -la arch/arm/boot/zImage arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb
md5sum arch/arm/boot/zImage arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb
