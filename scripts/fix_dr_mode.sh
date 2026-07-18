#!/bin/bash
set -e
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
cd /home/xlong/v3s/linux
echo "=== Current ==="
grep "dr_mode" arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero.dts
echo "=== Fixing ==="
sed -i 's/dr_mode = "otg"/dr_mode = "peripheral"/' arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero.dts
grep "dr_mode" arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero.dts
echo "=== Rebuild DTB ==="
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- dtbs 2>&1 | tail -5
echo "Exit: $?"
ls -lh arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb
cp arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb /mnt/c/my_project/TUN_NAT_HUB/backup/sun8i-v3s-licheepi-zero-dock.dtb_new
echo "DTB copied. DONE"
