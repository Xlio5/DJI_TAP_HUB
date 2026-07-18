#!/bin/bash
set -e
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

echo "=== 1. Kernel CONFIG_CMDLINE ==="
cd /home/xlong/v3s/linux
sed -i 's/# CONFIG_CMDLINE_EXTEND is not set/CONFIG_CMDLINE_EXTEND=y/' .config
sed -i 's/# CONFIG_CMDLINE_BOOL is not set/CONFIG_CMDLINE_BOOL=y/' .config
sed -i 's|CONFIG_CMDLINE=".*"|CONFIG_CMDLINE="root=/dev/mtdblock3"|' .config
for a in BOOL EXTEND OVERWRITE; do echo -n "CMDLINE_$a:"; grep "^CONFIG_CMDLINE_$a" .config | head -1; done
grep 'CONFIG_CMDLINE="' .config | head -1

echo ""
echo "=== 2. Rebuild kernel ==="
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j20 zImage 2>&1 | tail -3
cp arch/arm/boot/zImage /mnt/c/my_project/TUN_NAT_HUB/backup/zImage_new
echo "zImage: $(stat -c%s arch/arm/boot/zImage) bytes"

echo ""
echo "=== 3. U-Boot bootcmd (no root=) ==="
cd /home/xlong/v3s/u-boot
chown xlong:xlong .config 2>/dev/null || true
sed -i 's|CONFIG_BOOTCOMMAND=.*|CONFIG_BOOTCOMMAND="setenv bootargs console=ttyS0,115200 rootfstype=squashfs rootwait mtdparts=firmware:1M(uboot),64k(dtb),6M(kernel),4800k(rootfs_a),-(rootfs_b) g_serial.idVendor=0x0BDA g_serial.idProduct=0x8812 g_serial.use_acm=0; fdt addr 0x42000000; bootz 0x41000000 - 0x42000000"|' .config
echo "root from bootcmd: $(grep -c 'root=/dev' .config)"

echo ""
echo "=== 4. Rebuild U-Boot ==="
rm -f spl/sunxi-spl.bin u-boot.bin
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j20 2>&1 | tail -3
cp spl/sunxi-spl.bin u-boot.bin /mnt/c/my_project/TUN_NAT_HUB/backup/
echo "SPL: $(stat -c%s spl/sunxi-spl.bin) UBoot: $(stat -c%s u-boot.bin)"

echo ""
echo "=== 5. Build SPI image ==="
cd /mnt/c/my_project/TUN_NAT_HUB
python3 -B scripts/build_spi_final.py 2>&1 | tail -6
ls -lh backup/spi_image.bin

echo ""
echo "=== 6. FEL flash ==="
sunxi-fel list 2>&1
sunxi-fel spiflash-write 0 backup/spi_image.bin 2>&1
echo "FLASH EXIT=$?"

echo ""
echo "=== 7. Verify ==="
sunxi-fel spiflash-read 0 32 /tmp/vf.bin 2>&1
hexdump -C /tmp/vf.bin
sunxi-fel spiflash-read 0xFC000 1 /tmp/vff.bin 2>&1
printf "Slot flag: "
hexdump -e '1/1 "0x%02X\n"' /tmp/vff.bin

echo ""
echo "DONE v5"
