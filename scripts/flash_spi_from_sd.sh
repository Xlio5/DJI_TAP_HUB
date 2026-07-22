#!/bin/sh
# V3s 端运行：从 SD 卡刷写 SPI Flash
set -e

echo "=== SPI Flash 刷写 (from SD) ==="

# 挂载 SD boot 分区
mount /dev/mmcblk0p1 /mnt 2>/dev/null || mount /dev/mmcblk0p1 /media 2>/dev/null || true

SPI_IMG=$(find /mnt /media -name spi_image.bin -type f 2>/dev/null | head -1)
if [ -z "$SPI_IMG" ]; then
    echo "ERROR: 找不到 spi_image.bin，请确认 SD boot 分区上有这个文件"
    exit 1
fi

echo "镜像: $SPI_IMG ($(wc -c < "$SPI_IMG") bytes)"

# 擦除全片
echo "[1/3] 擦除 SPI Flash..."
flash_erase /dev/mtd0 0 0
echo "      擦除完成"

# 写入
echo "[2/3] 写入 SPI Flash..."
dd if="$SPI_IMG" of=/dev/mtd0 bs=4096
sync
echo "      写入完成"

# 校验
echo "[3/3] 校验..."
EXPECTED=$(wc -c < "$SPI_IMG")
if cmp "$SPI_IMG" /dev/mtd0; then
    echo "      校验通过 ($EXPECTED bytes 一致)"
else
    echo "      *** 校验失败！ ***"
    exit 1
fi

umount /mnt 2>/dev/null || true
umount /media 2>/dev/null || true

echo ""
echo "=== SPI Flash 刷写成功 ==="
echo ""
echo "下一步：重启进入 U-Boot 控制台，设置 SPI 启动环境变量："
echo ""
echo '  setenv bootcmd "sf probe 0; sf read 0x41000000 0x119800 0x5C0000; sf read 0x42000000 0x100000 0x4000; bootz 0x41000000 - 0x42000000"'
echo '  setenv bootargs "console=ttyS0,115200 root=/dev/mtdblock0 rootfstype=squashfs mtdparts=spi0.0:1M(uboot),64K(dtb),5632K(kernel),-(rootfs) g_serial.idVendor=0x0BDA g_serial.idProduct=0x8812 g_serial.use_acm=0"'
echo '  saveenv'
echo '  boot'
echo ""
