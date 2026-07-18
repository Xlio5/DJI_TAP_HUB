#!/bin/bash
set -e
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
cd /home/xlong/v3s/u-boot

echo "=== Current bootcmd ==="
grep CONFIG_BOOTCOMMAND .config

BOOTCMD='setenv bootargs console=ttyS0,115200 root=/dev/mtdblock3 rootfstype=squashfs rootwait mtdparts=firmware:1M(uboot),64k(dtb),6M(kernel),-(rootfs) g_serial.idVendor=0x0BDA g_serial.idProduct=0x8812 g_serial.use_acm=0; fdt addr 0x42000000; bootz 0x41000000 - 0x42000000'

sed -i "s@CONFIG_BOOTCOMMAND=.*@CONFIG_BOOTCOMMAND=\"$BOOTCMD\"@" .config

echo "=== After ==="
grep CONFIG_BOOTCOMMAND .config

echo ""
echo "=== olddefconfig ==="
make olddefconfig 2>&1 | tail -3

echo "=== After olddefconfig ==="
grep CONFIG_BOOTCOMMAND .config

echo ""
echo "=== EXTRA_ENV fallback ==="
if ! grep -q "bootz 0x41000000" .config; then
  sed -i "s@CONFIG_EXTRA_ENV_SETTINGS=.*@CONFIG_EXTRA_ENV_SETTINGS=\"bootcmd=$BOOTCMD\"@" .config
  make olddefconfig 2>&1 | tail -3
  grep CONFIG_EXTRA_ENV_SETTINGS .config
fi

echo ""
echo "=== Building ==="
rm -f u-boot.bin spl/sunxi-spl.bin
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j$(nproc) 2>&1 | tail -5
echo "Exit: $?"

echo ""
echo "=== Verify ==="
strings u-boot.bin | grep "bootz 0x41000000" | head -5
ls -lh spl/sunxi-spl.bin u-boot.bin

cat spl/sunxi-spl.bin > /tmp/uboot_final.bin
cat u-boot.bin >> /tmp/uboot_final.bin
cp spl/sunxi-spl.bin u-boot.bin /tmp/uboot_final.bin /mnt/c/my_project/TUN_NAT_HUB/backup/
echo "DONE"
