#!/bin/bash
# FEL 烧录 spi_image_v4 (144+172 IP 共存) + 读回验证
set -e
IMG=/mnt/c/my_project/TUN_NAT_HUB/backup/spi_image_v4.bin
EXPECT_MD5=66286ed5c8435c724cfb2b15d984e68a

echo "=== 1. 设备 ==="
sunxi-fel list

echo "=== 2. 镜像 md5 ==="
MD5=$(md5sum "$IMG" | awk '{print $1}')
[ "$MD5" = "$EXPECT_MD5" ] && echo "匹配 ✓" || { echo "不匹配!"; exit 1; }

echo "=== 3. 烧录 ==="
echo "开始: $(date +%H:%M:%S)"
sunxi-fel spiflash-write 0 "$IMG"
echo "完成: $(date +%H:%M:%S)"

echo "=== 4. 读回验证 ==="
sunxi-fel spiflash-read 0 32 /tmp/vfy_spl.bin
cmp /tmp/vfy_spl.bin <(head -c 32 "$IMG") && echo "SPL ✓" || echo "SPL ✗"
sunxi-fel spiflash-read 0x710000 16 /tmp/vfy_root.bin
[ "$(head -c 4 /tmp/vfy_root.bin)" = "hsqs" ] && echo "rootfs ✓" || echo "rootfs ✗"
sunxi-fel spiflash-read 0 16777216 /tmp/vfy_full.bin
SRC=$(md5sum "$IMG" | awk '{print $1}')
GOT=$(md5sum /tmp/vfy_full.bin | awk '{print $1}')
[ "$SRC" = "$GOT" ] && echo "全量一致 ✓✓✓" || echo "不一致 ✗"
echo "DONE"
