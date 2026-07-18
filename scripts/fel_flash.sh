#!/bin/bash
set -e

echo "=== Step 1: Create 16MB FF erase pattern ==="
tr '\000' '\377' < /dev/zero | dd bs=1M count=16 of=/tmp/ff16.bin 2>/dev/null
ls -lh /tmp/ff16.bin

echo "=== Step 2: Erase SPI (write all FF) ==="
sunxi-fel spiflash-write 0 /tmp/ff16.bin
echo "Erase done"

echo "=== Step 3: Write spi_image.bin ==="
sunxi-fel spiflash-write 0 /mnt/c/my_project/TUN_NAT_HUB/backup/spi_image.bin
echo "Write done"

echo "=== Step 4: Verify SPL ==="
sunxi-fel spiflash-read 0 32 /tmp/vfy_spl.bin
hexdump -C /tmp/vfy_spl.bin
SPL_OK=$(hexdump -n 12 -e '1/1 "%02x" ""' /tmp/vfy_spl.bin)
echo "SPL header: $SPL_OK"

echo "=== Step 5: Verify rootfs ==="
sunxi-fel spiflash-read 0x710000 8 /tmp/vfy_root.bin
hexdump -C /tmp/vfy_root.bin

echo "=== ALL DONE ==="
