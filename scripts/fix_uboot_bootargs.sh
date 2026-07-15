#!/bin/bash
cd /home/xlong/v3s/u-boot

# Update BOOTCOMMAND to include g_serial VID/PID
NEW_BOOTCMD='setenv bootargs console=ttyS0,115200 root=/dev/mtdblock3 rootfstype=squashfs rootwait mtdparts=firmware:1M(uboot),64k(dtb),6M(kernel),-(rootfs) g_serial.idVendor=0x0BDA g_serial.idProduct=0x8812 g_serial.use_acm=0; bootz 0x41000000 - 0x42000000'

scripts/config --set-str BOOTCOMMAND "$NEW_BOOTCMD"

echo "New BOOTCOMMAND:"
grep CONFIG_BOOTCOMMAND .config

# Build only u-boot (SPL unchanged)
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j4 2>&1 | tail -5

echo "U-Boot built"
ls -lh u-boot.bin
strings u-boot | grep 'idVendor=0x0BDA' | head -3
