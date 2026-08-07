#!/bin/bash
# FEL 烧录最终固件 (S99 LF 修复 + 115200 debug)
set -e
IMG=/mnt/c/my_project/TUN_NAT_HUB/backup/spi_image_v146.bin
EXPECT_MD5=2476f3a0979214d16a26b3fbe9a3b119

echo "=== 1. 设备 ==="
sunxi-fel list

echo "=== 2. md5 ==="
MD5=$(md5sum "$IMG" | awk '{print $1}')
echo "镜像: $MD5"
[ "$MD5" = "$EXPECT_MD5" ] && echo "匹配 ✓" || { echo "不匹配!"; exit 1; }

echo "=== 3. 烧录 16MB ==="
echo "开始: $(date +%H:%M:%S)"
time sunxi-fel spiflash-write 0 "$IMG"
echo "完成: $(date +%H:%M:%S)"

echo "=== 4. 读回验证 ==="
sunxi-fel spiflash-read 0 32 /tmp/vfy_spl.bin
cmp /tmp/vfy_spl.bin <(head -c 32 "$IMG") && echo "SPL 一致 ✓" || echo "SPL ✗"
sunxi-fel spiflash-read 0x710000 16 /tmp/vfy_root.bin
[ "$(head -c 4 /tmp/vfy_root.bin)" = "hsqs" ] && echo "rootfs magic OK ✓"

echo "=== 5. 全量 md5 ==="
sunxi-fel spiflash-read 0 16777216 /tmp/vfy_full.bin
SRC=$(md5sum "$IMG" | awk '{print $1}')
GOT=$(md5sum /tmp/vfy_full.bin | awk '{print $1}')
echo "源: $SRC"
echo "回读: $GOT"
[ "$SRC" = "$GOT" ] && echo "全量一致 ✓✓✓" || echo "不一致 ✗"
echo "DONE"
