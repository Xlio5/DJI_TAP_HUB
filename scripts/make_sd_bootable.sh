#!/bin/bash
# 制作可启动 SD 卡镜像 — U-Boot SPL 在 8KB 偏移 (SD 卡规范)
set -e

OUT="/tmp/sdcard_boot.img"
UBOOT="/home/xlong/v3s/u-boot/u-boot-sunxi-with-spl.bin"

# Create 200MB SD image
dd if=/dev/zero of="$OUT" bs=1M count=200 2>/dev/null

# U-Boot at 8KB offset (SD card standard)
dd if="$UBOOT" of="$OUT" bs=1024 seek=8 conv=notrunc 2>/dev/null

# Partition table - 1 partition FAT32
echo "n
p
1


t
b
w" | fdisk "$OUT" 2>/dev/null

# Format partition via loop
LOOP=$(losetup -fP --show "$OUT")
partprobe "$LOOP" 2>/dev/null
mkfs.vfat -n BOOT "${LOOP}p1" 2>/dev/null

# Mount and copy files
TMPMNT=$(mktemp -d)
mount "${LOOP}p1" "$TMPMNT"

# Copy kernel files
cp /home/xlong/v3s/linux/arch/arm/boot/zImage "$TMPMNT/zImage"
cp /home/xlong/v3s/linux/arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb "$TMPMNT/"
cp /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs.squashfs "$TMPMNT/"
cp /mnt/c/my_project/TUN_NAT_HUB/backup/spi_image.bin "$TMPMNT/"

# Also copy web_server for convenience
cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/build_v3s/web_server "$TMPMNT/"

ls -lh "$TMPMNT/"
umount "$TMPMNT"
losetup -d "$LOOP"
rmdir "$TMPMNT"

# Compress
gzip -c "$OUT" > /mnt/c/my_project/TUN_NAT_HUB/backup/sdcard_boot.img.gz
ls -lh /mnt/c/my_project/TUN_NAT_HUB/backup/sdcard_boot.img.gz
echo "Done! Flash to SD card with: zcat sdcard_boot.img.gz | dd of=/dev/sdX bs=4M"
