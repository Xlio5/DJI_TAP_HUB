#!/bin/bash
set -e
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
cd /home/xlong/v3s/u-boot

echo "=== Current SPI config ==="
for k in CMD_SF SPI_FLASH DM_SPI_FLASH SPI SPI_SUNXI MTD MTD_SPI_NOR; do
  echo -n "  $k="
  grep "^CONFIG_${k}=" .config 2>/dev/null || echo "NOT SET"
done

echo ""
echo "=== Enabling SPI flash support ==="

# Enable SPI flash + sf command
sed -i 's/# CONFIG_CMD_SF is not set/CONFIG_CMD_SF=y/' .config
sed -i 's/# CONFIG_SPI_FLASH is not set/CONFIG_SPI_FLASH=y/' .config
sed -i 's/# CONFIG_DM_SPI_FLASH is not set/CONFIG_DM_SPI_FLASH=y/' .config
sed -i 's/# CONFIG_MTD is not set/CONFIG_MTD=y/' .config

# Also need SPI flash driver support
sed -i 's/# CONFIG_SPI_FLASH_WINBOND is not set/CONFIG_SPI_FLASH_WINBOND=y/' .config
sed -i 's/# CONFIG_SPI_FLASH_SFDP_SUPPORT is not set/CONFIG_SPI_FLASH_SFDP_SUPPORT=y/' .config

echo ""
echo "=== After ==="
for k in CMD_SF SPI_FLASH DM_SPI_FLASH SPI SPI_SUNXI SPI_FLASH_WINBOND SPI_FLASH_SFDP_SUPPORT MTD; do
  echo -n "  $k="
  grep "^CONFIG_${k}=" .config 2>/dev/null || echo "NOT SET"
done

echo ""
echo "=== Rebuilding U-Boot ==="
rm -f u-boot.bin spl/sunxi-spl.bin
touch .config
make olddefconfig 2>&1 | tail -3
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j$(nproc) 2>&1 | tail -10
echo "Build exit: $?"

echo ""
echo "=== Output ==="
ls -lh spl/sunxi-spl.bin u-boot.bin

echo ""
echo "=== SPL header ==="
hexdump -C -n 32 spl/sunxi-spl.bin

# Create combined image
cat spl/sunxi-spl.bin > /tmp/u-boot-sunxi-with-spl.bin
cat u-boot.bin >> /tmp/u-boot-sunxi-with-spl.bin
cp /tmp/u-boot-sunxi-with-spl.bin /mnt/c/my_project/TUN_NAT_HUB/backup/

cp spl/sunxi-spl.bin /mnt/c/my_project/TUN_NAT_HUB/backup/
cp u-boot.bin /mnt/c/my_project/TUN_NAT_HUB/backup/

echo ""
echo "SPL: $(stat -c%s spl/sunxi-spl.bin) bytes"
echo "U-Boot: $(stat -c%s u-boot.bin) bytes"
echo "Combined: $(stat -c%s /mnt/c/my_project/TUN_NAT_HUB/backup/u-boot-sunxi-with-spl.bin) bytes"
echo ""
echo "=== Verify sf command is compiled in ==="
strings u-boot.bin | grep -E "^sf$|cmd_sf|spi_flash" | head -5
echo "DONE"
