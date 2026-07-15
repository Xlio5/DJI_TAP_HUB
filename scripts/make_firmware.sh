#!/bin/bash
# ==========================================
# TUN_NAT_HUB 固件生成脚本
# 生成 rootfs.squashfs (4MB) 和 spi_image.bin (16MB)
# ==========================================
set -e

echo "=== TUN_NAT_HUB 固件生成 ==="
echo ""

# 检查前置产物
[ -f /home/xlong/v3s/u-boot/spl/sunxi-spl.bin ] || { echo "ERROR: U-Boot SPL 未编译"; exit 1; }
[ -f /home/xlong/v3s/u-boot/u-boot.bin ]      || { echo "ERROR: U-Boot 未编译"; exit 1; }
[ -f /home/xlong/v3s/linux/arch/arm/boot/zImage ] || { echo "ERROR: Kernel 未编译"; exit 1; }
[ -f /mnt/c/my_project/TUN_NAT_HUB/ubuntu/build_v3s/web_server ] || { echo "ERROR: web_server 未编译"; exit 1; }

# Step 1: 构建 rootfs.squashfs
echo "Step 1: 构建 rootfs.squashfs..."
rm -rf /tmp/sq_build
mkdir -p /tmp/sq_build/usr/local/bin /tmp/sq_build/etc/init.d /tmp/sq_build/lib/modules/7.1.0

# 提取 Buildroot rootfs
tar xf /home/xlong/v3s/buildroot-2024.02/output/images/rootfs.tar -C /tmp/sq_build/

# 复制 TUN_NAT_HUB 应用
cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/build_v3s/web_server /tmp/sq_build/usr/local/bin/
cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/build_v3s/usb_tund    /tmp/sq_build/usr/local/bin/

# 复制 g_serial 内核模块
cp /home/xlong/v3s/linux/drivers/usb/gadget/legacy/g_serial.ko /tmp/sq_build/lib/modules/7.1.0/

# 复制启动脚本
cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/scripts/S99tun_nat_hub_final /tmp/sq_build/etc/init.d/S99tun_nat_hub
cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/scripts/setup_v3s_fixed.sh /tmp/sq_build/usr/local/bin/setup_v3s.sh
chmod +x /tmp/sq_build/usr/local/bin/web_server /tmp/sq_build/usr/local/bin/usb_tund
chmod +x /tmp/sq_build/etc/init.d/S99tun_nat_hub /tmp/sq_build/usr/local/bin/setup_v3s.sh

# 清理 Python3 残留
rm -rf /tmp/sq_build/usr/lib/python3* 2>/dev/null || true

# 运行 depmod
cd /tmp/sq_build
depmod -b . 7.1.0 2>/dev/null || true

# 打包 squashfs
mksquashfs /tmp/sq_build /tmp/rootfs.squashfs -comp xz -b 128K -noappend 2>&1 | tail -2
ls -lh /tmp/rootfs.squashfs

# 复制到项目
cp /tmp/rootfs.squashfs /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs.squashfs
echo "  -> backup/rootfs.squashfs (4MB, Web 升级用)"

# Step 2: 构建完整 SPI 镜像
echo ""
echo "Step 2: 构建 spi_image.bin..."
python3 /mnt/c/my_project/TUN_NAT_HUB/scripts/build_spi_final.py 2>&1 | tail -5
echo "  -> backup/spi_image.bin (16MB, 首次量产烧录用)"

echo ""
echo "=== 完成 ==="
echo "Web 固件升级:     backup/rootfs.squashfs"
echo "量产 SPI 镜像:     backup/spi_image.bin"
