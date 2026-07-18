#!/bin/bash
set -e
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
cd /home/xlong/v3s/u-boot

echo "=== SPI config ==="
for k in CMD_SF SPI_FLASH DM_SPI_FLASH SPI_FLASH_WINBOND; do
  echo -n "  $k="
  grep "^CONFIG_${k}=" .config || echo "NOT SET"
done

echo ""
echo "=== SPL ==="
hexdump -C -n 32 spl/sunxi-spl.bin
echo ""
echo "=== Output ==="
ls -lh spl/sunxi-spl.bin u-boot.bin
echo ""
echo "=== sf in U-Boot binary ==="
strings u-boot.bin | grep "sf" | head -10

# Create combined image
cat spl/sunxi-spl.bin > /tmp/u-boot-sunxi-with-spl.bin
cat u-boot.bin >> /tmp/u-boot-sunxi-with-spl.bin
cp spl/sunxi-spl.bin u-boot.bin /tmp/u-boot-sunxi-with-spl.bin /mnt/c/my_project/TUN_NAT_HUB/backup/
echo ""
echo "SPL: $(stat -c%s spl/sunxi-spl.bin) bytes"
echo "U-Boot: $(stat -c%s u-boot.bin) bytes"
echo "Combined: $(stat -c%s /mnt/c/my_project/TUN_NAT_HUB/backup/u-boot-sunxi-with-spl.bin) bytes"
echo "DONE"
