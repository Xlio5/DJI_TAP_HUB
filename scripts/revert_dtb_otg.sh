#!/bin/bash
cd /home/xlong/v3s/linux
DTS=arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero.dts
echo "=== Before ==="
grep dr_mode $DTS
sed -i 's/dr_mode = "peripheral"/dr_mode = "otg"/' $DTS
echo "=== After ==="
grep dr_mode $DTS
make -j4 ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- dtbs
echo "=== Result ==="
ls -lh arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb
