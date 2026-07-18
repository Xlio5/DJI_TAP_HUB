#!/bin/bash
cd /home/xlong/v3s/linux

echo "=== Kernel Config Audit ==="
echo ""

# SQUASHFS
for k in SQUASHFS SQUASHFS_XZ SQUASHFS_ZSTD SQUASHFS_LZO SQUASHFS_LZMA SQUASHFS_FILE_DIRECT SQUASHFS_DECOMP_MULTI; do
  val=$(grep "^CONFIG_${k}=" .config 2>/dev/null || echo "NOT SET")
  echo "  $k = $val"
done

echo ""
echo "=== Critical MTD/SPI ==="
for k in MTD MTD_SPI_NOR MTD_BLKDEVS MTD_BLOCK SPI SPI_SUN6I CMDLINE_PART; do
  val=$(grep "^CONFIG_${k}=" .config 2>/dev/null || echo "NOT SET")
  echo "  $k = $val"
done

echo ""
echo "=== g_serial / USB ==="
for k in USB_G_SERIAL USB_MUSB_HDRC USB_SUNXI; do
  val=$(grep "^CONFIG_${k}=" .config 2>/dev/null || echo "NOT SET")
  echo "  $k = $val"
done

echo ""
echo "=== TUN ==="
grep "^CONFIG_TUN=" .config 2>/dev/null || echo "TUN NOT SET"

echo ""
echo "=== Kernel version ==="
head -5 Makefile | grep -E '^(VERSION|PATCHLEVEL|SUBLEVEL|NAME)'
