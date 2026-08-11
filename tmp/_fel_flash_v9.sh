#!/bin/bash
# FEL 完整烧录 spi_image_v9 (固件 1.6.2 rootfs) + 读回验证
# 流程: 校验 md5 → spiflash-write 全量 → 读回 SPL/rootfs/全量比对
set -e
IMG=/mnt/c/my_project/TUN_NAT_HUB/backup/spi_image_v9.bin
EXPECT_MD5=86793849ad42fc69dcfbd6ee3cac617c

echo "=== 1. FEL 设备 ==="
sunxi-fel list

echo ""
echo "=== 2. 镜像 md5 校验 ==="
MD5=$(md5sum "$IMG" | awk '{print $1}')
echo "镜像: $MD5"
echo "期望: $EXPECT_MD5"
[ "$MD5" = "$EXPECT_MD5" ] && echo "匹配 ✓" || { echo "不匹配, 中止!"; exit 1; }

echo ""
echo "=== 3. 全量烧录 16MB (spiflash-write) ==="
echo "开始: $(date +%H:%M:%S)"
sunxi-fel spiflash-write 0 "$IMG"
echo "烧录完成: $(date +%H:%M:%S)"

echo ""
echo "=== 4. 读回验证 ==="
# SPL 段
sunxi-fel spiflash-read 0 32 /tmp/vfy_spl.bin
head -c 32 "$IMG" > /tmp/exp_spl.bin
cmp /tmp/vfy_spl.bin /tmp/exp_spl.bin && echo "SPL 一致 ✓" || echo "SPL ✗"

# rootfs magic
sunxi-fel spiflash-read 0x710000 16 /tmp/vfy_root.bin
MAGIC=$(head -c 4 /tmp/vfy_root.bin)
[ "$MAGIC" = "hsqs" ] && echo "rootfs magic OK ($MAGIC) ✓" || echo "rootfs ✗ ($MAGIC)"

# 全量 16MB 比对
sunxi-fel spiflash-read 0 16777216 /tmp/vfy_full.bin
SRC=$(md5sum "$IMG" | awk '{print $1}')
GOT=$(md5sum /tmp/vfy_full.bin | awk '{print $1}')
echo "源 md5:   $SRC"
echo "回读 md5: $GOT"
[ "$SRC" = "$GOT" ] && echo "全量一致 ✓✓✓" || echo "全量不一致 ✗"

echo ""
echo "=== 5. 完成 ==="
echo "DONE: $(date +%H:%M:%S)"
