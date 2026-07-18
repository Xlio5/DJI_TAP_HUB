#!/bin/bash
set -e
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
cd /home/xlong/v3s/u-boot
chown xlong:xlong .config 2>/dev/null || true

BOOTCMD='setenv bootargs console=ttyS0,115200 root=/dev/mtdblock3 rootfstype=squashfs rootwait mtdparts=firmware:1M(uboot),64k(dtb),6M(kernel),4800k(rootfs_a),-(rootfs_b) g_serial.idVendor=0x0BDA g_serial.idProduct=0x8812 g_serial.use_acm=0; fdt addr 0x42000000; bootz 0x41000000 - 0x42000000'

sed -i "s|CONFIG_BOOTCOMMAND=.*|CONFIG_BOOTCOMMAND=\"$BOOTCMD\"|" .config
echo "Hardcoded root=/dev/mtdblock3: $(grep -c 'root=/dev/mtdblock3' .config)"

echo "=== Rebuild U-Boot ==="
rm -f spl/sunxi-spl.bin u-boot.bin
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j20 | tail -5
cp spl/sunxi-spl.bin u-boot.bin /mnt/c/my_project/TUN_NAT_HUB/backup/
echo "UBoot has mtdblock3: $(strings u-boot.bin | grep -c 'root=/dev/mtdblock3')"

echo "=== SPI image ==="
cd /mnt/c/my_project/TUN_NAT_HUB
python3 -B scripts/build_spi_final.py | tail -6

echo "=== FEL flash ==="
sunxi-fel list
sunxi-fel spiflash-write 0 backup/spi_image.bin
echo "FEL exit=$?"
sunxi-fel spiflash-read 0 32 /tmp/v8.bin
hexdump -C /tmp/v8.bin
echo "DONE"
