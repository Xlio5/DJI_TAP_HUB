#!/bin/bash
cd /home/xlong/v3s/u-boot

echo "=== Clean ==="
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- distclean 2>/dev/null

echo "=== defconfig ==="
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- LicheePi_Zero_defconfig 2>/dev/null

echo "=== Enable SPL SPI ==="
scripts/config --enable SPL_SPI
scripts/config --enable SPL_SPI_SUNXI

echo "=== Embed bootargs + bootcmd ==="
BOOTARGS="console=ttyS0,115200 root=/dev/mtdblock3 rootfstype=squashfs rootwait mtdparts=firmware:1M(uboot),64k(dtb),6M(kernel),-(rootfs)"
BOOTCMD="setenv bootargs ${BOOTARGS}; bootz 0x41000000 - 0x42000000"
scripts/config --set-str BOOTCOMMAND "${BOOTCMD}"

echo "=== oldconfig ==="
yes '' | make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- oldconfig 2>/dev/null

echo "=== Verify ==="
grep -E 'SPL_SPI_SUNXI|BOOTCOMMAND' .config | grep -v 'not set\|#'

echo "=== SPL patch ==="
if grep -q '0x119800' arch/arm/mach-sunxi/spl_spi_sunxi.c; then
    sed -i 's/0x119800/0x110000/g' arch/arm/mach-sunxi/spl_spi_sunxi.c
fi

echo "=== Build ==="
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j4 2>&1 | tail -8

echo "=== Verify binary ==="
strings u-boot 2>/dev/null | grep 'setenv bootargs' | head -3
strings u-boot 2>/dev/null | grep 'bootz 0x41000000' | head -3
echo ""
echo "SPL:" $(wc -c < spl/sunxi-spl.bin 2>/dev/null) "bytes"
echo "U-Boot:" $(wc -c < u-boot.bin 2>/dev/null) "bytes"
ls -lh spl/sunxi-spl.bin u-boot.bin u-boot-sunxi-with-spl.bin 2>/dev/null
