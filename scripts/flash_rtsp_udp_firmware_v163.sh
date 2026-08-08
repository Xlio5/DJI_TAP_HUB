#!/bin/bash
# Flash V3s SPI firmware v1.6.3 by FEL and verify by read-back comparison.
set -euo pipefail

PROJECT=${PROJECT:-/mnt/c/my_project/TUN_NAT_HUB}
IMG=${IMG:-$PROJECT/backup/release_20260809_v163/spi_image_v10_v163.bin}
EXPECT_MD5=${EXPECT_MD5:-8bd3f92d6bbaee7cf9d9ae359137fd9b}

echo "=== 1. FEL device ==="
sunxi-fel list

echo ""
echo "=== 2. Image check ==="
test -f "$IMG"
MD5=$(md5sum "$IMG" | awk '{print $1}')
SIZE=$(stat -c%s "$IMG")
echo "image: $IMG"
echo "size:  $SIZE"
echo "md5:   $MD5"
if [ -n "$EXPECT_MD5" ] && [ "$MD5" != "$EXPECT_MD5" ]; then
    echo "ERROR: md5 mismatch, expect $EXPECT_MD5"
    exit 1
fi

echo ""
echo "=== 3. Full SPI write ==="
sunxi-fel spiflash-write 0 "$IMG"

echo ""
echo "=== 4. Read-back verify ==="
sunxi-fel spiflash-read 0 32 /tmp/v163_spl_head.bin
head -c 32 "$IMG" > /tmp/v163_spl_head_expect.bin
cmp /tmp/v163_spl_head.bin /tmp/v163_spl_head_expect.bin
echo "SPL head: OK"

sunxi-fel spiflash-read 0x710000 16 /tmp/v163_rootfs_head.bin
MAGIC=$(head -c 4 /tmp/v163_rootfs_head.bin)
test "$MAGIC" = "hsqs"
echo "rootfs magic: OK ($MAGIC)"

sunxi-fel spiflash-read 0 "$SIZE" /tmp/v163_spi_readback.bin
READ_MD5=$(md5sum /tmp/v163_spi_readback.bin | awk '{print $1}')
echo "source md5:   $MD5"
echo "readback md5: $READ_MD5"
test "$READ_MD5" = "$MD5"

echo ""
echo "DONE: flash and read-back verified"
