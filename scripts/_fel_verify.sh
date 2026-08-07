#!/bin/bash
# FEL 烧录后读回验证: 对比 SPI 内容与 spi_image.bin
set -e
IMG=/mnt/c/my_project/TUN_NAT_HUB/backup/spi_image.bin

echo "=== 1. 读回 SPL 头 (前 32 字节) ==="
sunxi-fel spiflash-read 0 32 /tmp/vfy_spl.bin
hexdump -C /tmp/vfy_spl.bin | head -4
echo "  源镜像 SPL:"
head -c 32 "$IMG" | hexdump -C | head -4
echo "  SPL 对比: $(cmp /tmp/vfy_spl.bin <(head -c 32 "$IMG") && echo '一致 ✓' || echo '不一致 ✗')"

echo ""
echo "=== 2. 读回 rootfs magic (0x710000) ==="
sunxi-fel spiflash-read 0x710000 16 /tmp/vfy_root.bin
echo "  读回 rootfs magic: $(head -c 16 /tmp/vfy_root.bin | xxd -p)"
echo "  源镜像 rootfs magic: $(dd if="$IMG" bs=1 skip=$((0x710000)) count=16 2>/dev/null | xxd -p)"
if [ "$(head -c 16 /tmp/vfy_root.bin | xxd -p)" = "$(dd if="$IMG" bs=1 skip=$((0x710000)) count=16 2>/dev/null | xxd -p)" ]; then
    echo "  rootfs magic 一致 ✓"
else
    echo "  rootfs magic 不一致 ✗"
fi

echo ""
echo "=== 3. 读回整镜像并全量对比 (16MB, 需要时间) ==="
sunxi-fel spiflash-read 0 16777216 /tmp/vfy_full.bin
FULL_SRC=$(cat "$IMG" | md5sum | awk '{print $1}')
FULL_READ=$(md5sum /tmp/vfy_full.bin | awk '{print $1}')
echo "  源镜像 md5: $FULL_SRC"
echo "  读回 md5:   $FULL_READ"
if [ "$FULL_SRC" = "$FULL_READ" ]; then
    echo "  全量对比: 一致 ✓✓✓"
else
    echo "  全量对比: 不一致 ✗ (SPI 写入可能有问题)"
fi
echo "DONE"
