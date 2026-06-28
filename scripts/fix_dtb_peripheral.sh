#!/bin/bash
# fix_usb_peripheral.sh — change V3s USB dr_mode from otg to peripheral
set -e
cd /home/xlong/v3s/linux
DTS=arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero.dts

echo "=== Before ==="
grep dr_mode $DTS

# Change otg -> peripheral
sed -i 's/dr_mode = "otg"/dr_mode = "peripheral"/' $DTS

echo "=== After ==="
grep dr_mode $DTS

echo "=== Rebuilding DTB ==="
make -j4 ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- dtbs 2>&1 | tail -5

echo "=== Result ==="
ls -lh arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb
echo "DONE"
