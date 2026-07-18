#!/bin/bash
set -e
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
cd /home/xlong/v3s/linux

echo "=== Fix: CONFIG_CMDLINE_EXTEND + clean build ==="
sed -i 's/CONFIG_CMDLINE_OVERWRITE=y/# CONFIG_CMDLINE_OVERWRITE is not set/' .config
sed -i 's/# CONFIG_CMDLINE_EXTEND is not set/CONFIG_CMDLINE_EXTEND=y/' .config
grep CMDLINE_EXTEND .config | head -1

echo "=== Clean rebuild ==="
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- clean 2>&1 | tail -3
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j20 zImage dtbs 2>&1 | tail -5
cp arch/arm/boot/zImage /mnt/c/my_project/TUN_NAT_HUB/backup/zImage_new
cp arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb /mnt/c/my_project/TUN_NAT_HUB/backup/sun8i-v3s-licheepi-zero-dock.dtb_new
echo "zImage: $(stat -c%s arch/arm/boot/zImage) bytes"
echo "DTB: $(stat -c%s arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb) bytes"
echo "DONE"
