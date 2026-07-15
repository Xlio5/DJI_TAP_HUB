#!/bin/bash
cd /home/xlong/v3s/u-boot

echo "=== Phase 1: SPL build (no SPI for main U-Boot) ==="
rm -f .config include/autoconf.mk include/config/auto.conf
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- LicheePi_Zero_defconfig 2>&1 | grep -v '^$'

echo 'CONFIG_SPL_SPI=y' >> .config
echo 'CONFIG_SPL_SPI_SUNXI=y' >> .config
echo 'CONFIG_ENV_IS_IN_SPI_FLASH=y' >> .config
echo 'CONFIG_ENV_OFFSET=0x7E000' >> .config
echo 'CONFIG_ENV_SIZE=0x2000' >> .config
echo 'CONFIG_ENV_SECT_SIZE=0x1000' >> .config
sed -i 's/CONFIG_ENV_IS_IN_FAT=y/# CONFIG_ENV_IS_IN_FAT is not set/' .config

make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- olddefconfig 2>&1 | tail -1
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j4 2>&1 | tail -3

# Save SPL
cp spl/sunxi-spl.bin /tmp/spl-good.bin
cp spl/u-boot-spl.bin /tmp/spl-bin-good.bin
cp u-boot.bin /tmp/uboot-good.bin
echo "SPL: $(wc -c < /tmp/spl-good.bin) bytes, U-Boot: $(wc -c < /tmp/uboot-good.bin) bytes"

echo ""
echo "=== Phase 2: Enable SPI in main U-Boot ONLY ==="

# ADD to .config (not replace, append)
cat >> .config << 'CONFIGEOF'
CONFIG_SPI=y
CONFIG_DM_SPI=y
CONFIG_SPI_SUNXI=y
CONFIG_SPI_FLASH=y
CONFIG_SPI_FLASH_WINBOND=y
CONFIG_CMD_SF=y
CONFIG_SF_DEFAULT_BUS=0
CONFIG_SF_DEFAULT_CS=0
CONFIG_SF_DEFAULT_SPEED=40000000
CONFIG_SF_DEFAULT_MODE=0
CONFIG_SPI_FLASH_BAR=y
CONFIG_ENV_IS_IN_SPI_FLASH=y
CONFIG_ENV_OFFSET=0x7E000
CONFIG_ENV_SIZE=0x2000
CONFIG_ENV_SECT_SIZE=0x1000
# CONFIG_ENV_IS_IN_FAT is not set
CONFIGEOF

# Run olddefconfig which strips SPI, then FIX
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- olddefconfig 2>&1 | tail -1
echo "After olddefconfig: CMD_SF=$(grep -c 'CONFIG_CMD_SF=y' .config), SPI_FLASH=$(grep -c 'CONFIG_SPI_FLASH=y' .config)"

# NOW RE-ADD what was stripped, directly to autoconf.mk (shell doesn't auto-resolve)
echo 'CONFIG_SPI=y' >> include/autoconf.mk
echo 'CONFIG_DM_SPI=y' >> include/autoconf.mk
echo 'CONFIG_SPI_SUNXI=y' >> include/autoconf.mk
echo 'CONFIG_SPI_FLASH=y' >> include/autoconf.mk
echo 'CONFIG_SPI_FLASH_WINBOND=y' >> include/autoconf.mk
echo 'CONFIG_CMD_SF=y' >> include/autoconf.mk
echo 'CONFIG_SF_DEFAULT_BUS=0' >> include/autoconf.mk
echo 'CONFIG_SF_DEFAULT_CS=0' >> include/autoconf.mk
echo 'CONFIG_SF_DEFAULT_SPEED=40000000' >> include/autoconf.mk
echo 'CONFIG_SF_DEFAULT_MODE=0' >> include/autoconf.mk
echo 'CONFIG_SPI_FLASH_BAR=y' >> include/autoconf.mk
echo 'CONFIG_ENV_IS_IN_SPI_FLASH=y' >> include/autoconf.mk
echo 'CONFIG_ENV_OFFSET=0x7E000' >> include/autoconf.mk
echo 'CONFIG_ENV_SIZE=0x2000' >> include/autoconf.mk
echo 'CONFIG_ENV_SECT_SIZE=0x1000' >> include/autoconf.mk

# Also the auto.conf and config.h
cat >> include/config/auto.conf << 'CONFEOF'
CONFIG_SPI=y
CONFIG_DM_SPI=y
CONFIG_SPI_SUNXI=y
CONFIG_SPI_FLASH=y
CONFIG_SPI_FLASH_WINBOND=y
CONFIG_CMD_SF=y
CONFIG_SF_DEFAULT_BUS=0
CONFIG_SF_DEFAULT_CS=0
CONFIG_SF_DEFAULT_SPEED=40000000
CONFIG_SF_DEFAULT_MODE=0
CONFIG_SPI_FLASH_BAR=y
CONFIG_ENV_IS_IN_SPI_FLASH=y
CONFIG_ENV_OFFSET=0x7E000
CONFIG_ENV_SIZE=0x2000
CONFIG_ENV_SECT_SIZE=0x1000
CONFEOF

for def in SPI DM_SPI SPI_SUNXI SPI_FLASH SPI_FLASH_WINBOND CMD_SF SPI_FLASH_BAR; do
    grep -q "CONFIG_${def}" include/config.h 2>/dev/null || echo "#define CONFIG_${def} 1" >> include/config.h
done
echo "#define CONFIG_SF_DEFAULT_BUS 0" >> include/config.h
echo "#define CONFIG_SF_DEFAULT_CS 0" >> include/config.h
echo "#define CONFIG_SF_DEFAULT_SPEED 40000000" >> include/config.h
echo "#define CONFIG_SF_DEFAULT_MODE 0" >> include/config.h

echo ""
echo "=== Phase 3: Build main U-Boot with sf ==="
rm -f cmd/sf.o drivers/spi/spi-sunxi.o cmd/built-in.o drivers/spi/built-in.o u-boot u-boot.bin u-boot-dtb.bin

# Patch spi Makefile to exclude from SPL
if ! grep -q SPL_BUILD drivers/spi/Makefile; then
    sed -i 's/^obj-\$(CONFIG_SPI_SUNXI) += spi-sunxi.o/ifndef CONFIG_SPL_BUILD\nobj-\$(CONFIG_SPI_SUNXI) += spi-sunxi.o\nendif/' drivers/spi/Makefile
fi

# Restore good SPL (compilation will break SPL, but we use saved version)
cp /tmp/spl-good.bin spl/sunxi-spl.bin
cp /tmp/spl-bin-good.bin spl/u-boot-spl.bin
touch spl/sunxi-spl.bin spl/u-boot-spl.bin

echo "Building u-boot.bin..."
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j4 2>&1 | tail -15 || true

echo ""
echo "=== Phase 4: Check and assemble ==="
if strings u-boot 2>/dev/null | grep -q spi_flash_probe; then
    echo "SF FOUND in u-boot!"
    # Manual assembly
    rm -f /tmp/final.bin
    dd if=/tmp/spl-good.bin of=/tmp/final.bin bs=1 conv=notrunc 2>/dev/null
    dd if=u-boot.bin of=/tmp/final.bin bs=1024 seek=32 conv=notrunc 2>/dev/null
    cp /tmp/final.bin u-boot-sunxi-with-spl.bin
    ls -lh u-boot-sunxi-with-spl.bin
    echo "BUILD COMPLETE! Final binary: u-boot-sunxi-with-spl.bin"
else
    echo "SF NOT found in u-boot. Total build failure."
    echo "Checking what objects were built..."
    ls -la cmd/sf.o drivers/spi/spi-sunxi.o 2>/dev/null
    echo "Check compile log..."
    make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- cmd/sf.o 2>&1 | tail -20
fi
