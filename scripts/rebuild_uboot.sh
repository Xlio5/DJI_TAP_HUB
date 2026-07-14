#!/bin/bash
set -e
cd /home/xlong/v3s/u-boot

echo "=== TUN_NAT_HUB U-Boot SPL build (SPI boot) ==="

rm -f .config include/autoconf.mk include/config/auto.conf
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- LicheePi_Zero_defconfig 2>/dev/null

# Minimal config: SPL SPI only (no DM SPI needed for main U-Boot)
cat >> .config << 'EOF'
CONFIG_SPL_SPI=y
CONFIG_SPL_SPI_SUNXI=y
CONFIG_ENV_IS_IN_SPI_FLASH=y
CONFIG_ENV_OFFSET=0x7E000
CONFIG_ENV_SIZE=0x2000
CONFIG_ENV_SECT_SIZE=0x1000
EOF

sed -i 's/CONFIG_ENV_IS_IN_FAT=y/# CONFIG_ENV_IS_IN_FAT is not set/' .config
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- olddefconfig 2>/dev/null

# Verify SPL config stuck
grep -q 'CONFIG_SPL_SPI_SUNXI=y' .config || { echo "SPI config stripped! Adding back..."; echo 'CONFIG_SPL_SPI=y' >> .config; echo 'CONFIG_SPL_SPI_SUNXI=y' >> .config; make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- olddefconfig 2>/dev/null; }

echo "SPL SPI: $(grep -c 'SPL_SPI_SUNXI=y' .config) configs"

# Patch SPL code
python3 /mnt/c/my_project/TUN_NAT_HUB/scripts/patch_spl.py

# Build
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j4 2>&1 | tail -8

echo "SPL: $(wc -c < spl/sunxi-spl.bin) bytes"
echo "U-Boot: $(wc -c < u-boot-sunxi-with-spl.bin) bytes"
ls -lh spl/sunxi-spl.bin u-boot-sunxi-with-spl.bin
