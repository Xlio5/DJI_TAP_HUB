#!/bin/bash
cd /home/xlong/v3s/u-boot
echo "=== SPL ==="
hexdump -C -n 32 spl/sunxi-spl.bin
echo ""
echo "=== SPI config ==="
grep -E "CONFIG_CMD_SF|CONFIG_SPI_FLASH=|CONFIG_SPI_SUNXI=|CONFIG_DM_SPI=" .config | grep -v "^#"
echo ""
echo "=== sf in binary ==="
strings u-boot.bin | grep -E "^sf$|spi_flash" | head -5
echo ""
echo "=== Sizes ==="
ls -lh spl/sunxi-spl.bin u-boot.bin
# Create combined
cat spl/sunxi-spl.bin > /tmp/u-boot-sunxi-with-spl.bin
cat u-boot.bin >> /tmp/u-boot-sunxi-with-spl.bin
cp spl/sunxi-spl.bin u-boot.bin /tmp/u-boot-sunxi-with-spl.bin /mnt/c/my_project/TUN_NAT_HUB/backup/
echo ""
echo "Combined: $(stat -c%s /mnt/c/my_project/TUN_NAT_HUB/backup/u-boot-sunxi-with-spl.bin) bytes"
echo "DONE"
