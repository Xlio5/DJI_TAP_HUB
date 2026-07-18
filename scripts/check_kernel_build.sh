#!/bin/bash
cd /home/xlong/v3s/linux
echo "zImage: $(stat -c%s arch/arm/boot/zImage) bytes"
echo "DTB:    $(stat -c%s arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb) bytes"
echo "g_serial: $(grep CONFIG_USB_G_SERIAL .config)"
echo "SQUASHFS_XZ: $(grep CONFIG_SQUASHFS_XZ .config)"
echo "TUN: $(grep "^CONFIG_TUN=" .config)"
