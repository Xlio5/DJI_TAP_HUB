#!/bin/bash
# make_sd_flash.sh — 制作 SD 卡刷写盘（从 SD 卡启动后烧录 SPI Flash）
# 用法: sudo bash make_sd_flash.sh /dev/sdX
#   /dev/sdX 是 SD 卡设备（如 /dev/sdb，不是 /dev/sdb1！）
set -e

if [ -z "$1" ]; then
    echo "用法: sudo bash make_sd_flash.sh /dev/sdX"
    echo "  /dev/sdX 是 SD 卡设备（如 /dev/sdb）"
    exit 1
fi

SDX="$1"
V3S=/home/xlong/v3s
PROJ=/mnt/c/my_project/TUN_NAT_HUB

echo "=== 警告: 将清除 $SDX 所有数据! ==="
echo "按 Ctrl+C 取消, 5秒后继续..."
sleep 5

echo "=== 1. 分区 ==="
sfdisk "$SDX" << 'EOF'
label: dos
size=64M, type=6
type=83
EOF
sleep 1

echo "=== 2. 格式化 ==="
mkfs.vfat -F 16 -n BOOT "${SDX}1"
mkfs.ext4 -L ROOTFS "${SDX}2"

echo "=== 3. 挂载 ==="
mkdir -p /tmp/sd_boot /tmp/sd_root
mount "${SDX}1" /tmp/sd_boot
mount "${SDX}2" /tmp/sd_root

echo "=== 4. 复制 kernel + dtb ==="
cp $V3S/linux/arch/arm/boot/zImage /tmp/sd_boot/
cp $V3S/linux/arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb /tmp/sd_boot/

echo "=== 5. 写 U-Boot boot.scr (自动启动+SPI刷写辅助) ==="
cat > /tmp/boot.cmd << 'CMDEOF'
setenv bootargs console=ttyS0,115200 panic=5 root=/dev/mmcblk0p2 rootwait rw
fdt addr 0x42000000
load mmc 0:1 0x41000000 zImage
load mmc 0:1 0x42000000 sun8i-v3s-licheepi-zero-dock.dtb
bootz 0x41000000 - 0x42000000
CMDEOF
mkimage -C none -A arm -T script -d /tmp/boot.cmd /tmp/sd_boot/boot.scr

echo "=== 6. 解压 rootfs ==="
tar xf $V3S/buildroot-2024.02/output/images/rootfs.tar -C /tmp/sd_root/ 2>/dev/null || true

echo "=== 7. 复制 SPI 镜像到 rootfs ==="
cp $PROJ/backup/spi_image.bin /tmp/sd_root/root/

echo "=== 8. 初始化脚本（SSH + 刷写说明）==="
mkdir -p /tmp/sd_root/etc/init.d

cat > /tmp/sd_root/etc/init.d/S50sshd << 'INITEOF'
#!/bin/sh
case "$1" in start)
    echo "Starting dropbear SSH..."
    /usr/sbin/dropbear -p 22 ;;
  stop) killall dropbear ;;
  restart) $0 stop; sleep 1; $0 start ;;
esac
INITEOF
chmod +x /tmp/sd_root/etc/init.d/S50sshd

# 静态 IP
cat >> /tmp/sd_root/etc/network/interfaces << 'IPEOF'

auto eth0
iface eth0 inet static
    address 192.168.144.66
    netmask 255.255.255.0
IPEOF

echo "=== 9. 写入 MOTD ==="
cat > /tmp/sd_root/etc/motd << 'MOTDEOF'
╔══════════════════════════════════════════════╗
║  TUN_NAT_HUB SD Rescue / Flash Utility      ║
║  SPI 镜像已放在 /root/spi_image.bin (16MB)  ║
║                                              ║
║  烧录 SPI Flash:                             ║
║    flash_erase /dev/mtd0 0 0                 ║
║    dd if=/root/spi_image.bin of=/dev/mtd0 bs=4096 ║
║                                              ║
║  烧录完毕 → 关机 → 拔 SD 卡 → 上电          ║
╚══════════════════════════════════════════════╝
MOTDEOF

echo "=== 10. 卸载 ==="
umount /tmp/sd_boot /tmp/sd_root

echo "=== 11. 写 U-Boot SPL ==="
dd if=$V3S/u-boot/u-boot-sunxi-with-spl.bin of="$SDX" bs=1024 seek=8

echo ""
echo "=== DONE! SD 卡已就绪 ==="
echo "插入 V3s → 上电 → SSH root@192.168.144.66"
echo "然后执行:"
echo "  flash_erase /dev/mtd0 0 0"
echo "  dd if=/root/spi_image.bin of=/dev/mtd0 bs=4096"
echo "  sync && poweroff"
echo "  拔 SD 卡 → 上电 → SPI Flash 启动!"
