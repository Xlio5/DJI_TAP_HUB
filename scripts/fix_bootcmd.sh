#!/bin/bash
set -e
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
cd /home/xlong/v3s/u-boot

BOOTCMD='setenv bootargs console=ttyS0,115200 root=/dev/mtdblock3 rootfstype=squashfs rootwait mtdparts=firmware:1M(uboot),64k(dtb),6M(kernel),-(rootfs) g_serial.idVendor=0x0BDA g_serial.idProduct=0x8812 g_serial.use_acm=0; fdt addr 0x42000000; bootz 0x41000000 - 0x42000000'

echo "=== Before ==="
grep CONFIG_BOOTCOMMAND .config

# Replace bootcmd
sed -i "s|CONFIG_BOOTCOMMAND=.*|CONFIG_BOOTCOMMAND=${BOOTCMD}|" .config

echo "=== After ==="
grep CONFIG_BOOTCOMMAND .config

echo ""
echo "=== olddefconfig ==="
make olddefconfig 2>&1 | tail -3

echo ""
echo "=== Rebuilding ==="
rm -f u-boot.bin spl/sunxi-spl.bin
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j$(nproc) 2>&1 | tail -5
echo "Exit: $?"

echo ""
ls -lh spl/sunxi-spl.bin u-boot.bin

echo ""
echo "=== Verify ==="
strings u-boot.bin | grep "bootz 0x41000000" | head -3

# Create combined image
cat spl/sunxi-spl.bin > /tmp/u-boot-sunxi-with-spl.bin
cat u-boot.bin >> /tmp/u-boot-sunxi-with-spl.bin
cp spl/sunxi-spl.bin u-boot.bin /tmp/u-boot-sunxi-with-spl.bin /mnt/c/my_project/TUN_NAT_HUB/backup/

echo ""
echo "SPL: $(stat -c%s spl/sunxi-spl.bin) bytes"
echo "U-Boot: $(stat -c%s u-boot.bin) bytes"
echo "DONE"
