#!/bin/bash
# FEL 全量烧录并读回验证 16MB SPI 镜像。
# 用法: scripts/fel_flash_verify.sh backup/spi_image_xxx.bin
set -euo pipefail

IMG=${1:-}
if [ -z "$IMG" ] || [ ! -f "$IMG" ]; then
    echo "用法: $0 <spi_image.bin>" >&2
    exit 1
fi

SIZE=$(stat -c%s "$IMG")
if [ "$SIZE" -ne 16777216 ]; then
    echo "镜像大小不是 16MB: $SIZE" >&2
    exit 1
fi

ROOTFS_OFF=0x710000
WORK=/tmp/tun_hub_fel_verify
mkdir -p "$WORK"

echo "=== 1. FEL 设备 ==="
sunxi-fel list

echo ""
echo "=== 2. 本地镜像校验 ==="
SRC_MD5=$(md5sum "$IMG" | awk '{print $1}')
echo "image: $IMG"
echo "md5:   $SRC_MD5"
dd if="$IMG" of="$WORK/rootfs_head.bin" bs=1 skip=$((ROOTFS_OFF)) count=4 status=none
ROOT_MAGIC=$(cat "$WORK/rootfs_head.bin")
if [ "$ROOT_MAGIC" != "hsqs" ]; then
    echo "rootfs magic 错误: $ROOT_MAGIC" >&2
    exit 1
fi
echo "rootfs magic @ 0x710000: hsqs"

echo ""
echo "=== 3. 烧录 16MB SPI flash ==="
date '+start: %F %T'
sunxi-fel spiflash-write 0 "$IMG"
date '+done:  %F %T'

echo ""
echo "=== 4. 写后读回验证 ==="
sunxi-fel spiflash-read 0 32 "$WORK/read_spl_head.bin"
cmp "$WORK/read_spl_head.bin" <(head -c 32 "$IMG")
echo "SPL head: OK"

sunxi-fel spiflash-read "$ROOTFS_OFF" 4 "$WORK/read_rootfs_head.bin"
READ_MAGIC=$(cat "$WORK/read_rootfs_head.bin")
if [ "$READ_MAGIC" != "hsqs" ]; then
    echo "读回 rootfs magic 错误: $READ_MAGIC" >&2
    exit 1
fi
echo "rootfs magic: OK"

sunxi-fel spiflash-read 0 16777216 "$WORK/read_full.bin"
READ_MD5=$(md5sum "$WORK/read_full.bin" | awk '{print $1}')
echo "source md5:   $SRC_MD5"
echo "readback md5: $READ_MD5"
if [ "$SRC_MD5" != "$READ_MD5" ]; then
    echo "全量读回不一致" >&2
    exit 1
fi

echo "全量读回一致: OK"
