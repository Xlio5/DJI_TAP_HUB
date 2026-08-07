#!/bin/bash
# FEL 烧录 spi_image_v147.bin (PB6 检测 bootcmd 版) + 读回验证
set -e
IMG=/mnt/c/my_project/TUN_NAT_HUB/backup/spi_image_v147.bin
EXPECT_MD5=c1243a9abc2c0404600323b598b437e5

echo "=== 1. 设备 ==="
sunxi-fel list

echo "=== 2. 镜像 md5 ==="
MD5=$(md5sum "$IMG" | awk '{print $1}')
echo "镜像: $MD5  期望: $EXPECT_MD5"
[ "$MD5" = "$EXPECT_MD5" ] && echo "匹配 ✓" || { echo "不匹配!"; exit 1; }

echo "=== 3. 烧录 16MB ==="
echo "开始: $(date +%H:%M:%S)"
sunxi-fel spiflash-write 0 "$IMG"
echo "完成: $(date +%H:%M:%S)"

echo "=== 4. 读回验证 ==="
echo "--- SPL (前 32B) ---"
sunxi-fel spiflash-read 0 32 /tmp/vfy_spl.bin
cmp /tmp/vfy_spl.bin <(head -c 32 "$IMG") && echo "SPL 一致 ✓" || echo "SPL ✗"

echo "--- U-Boot 段 bootcmd (含 PB6?) ---"
sunxi-fel spiflash-read 0x8000 64 /tmp/vfy_uboot.bin

echo "--- rootfs magic ---"
sunxi-fel spiflash-read 0x710000 16 /tmp/vfy_root.bin
[ "$(head -c 4 /tmp/vfy_root.bin)" = "hsqs" ] && echo "rootfs magic OK ✓" || echo "rootfs ✗"

echo "--- 全量 md5 ---"
sunxi-fel spiflash-read 0 16777216 /tmp/vfy_full.bin
SRC=$(md5sum "$IMG" | awk '{print $1}')
GOT=$(md5sum /tmp/vfy_full.bin | awk '{print $1}')
echo "源: $SRC"
echo "回读: $GOT"
[ "$SRC" = "$GOT" ] && echo "全量一致 ✓✓✓" || echo "不一致 ✗"

echo "=== 5. 重启设备 (从 SPI 启动) ==="
sunxi-fel reset 2>/dev/null || echo "(reset 不可用, 手动重启)"
echo "DONE"
