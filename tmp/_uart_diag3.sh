#!/bin/bash
set +e
cd /mnt/c/my_project/TUN_NAT_HUB

echo "========== 1. 从 spi_image_v1638 提取内嵌 squashfs (rootfs_a @0x710000) =========="
dd if=backup/spi_image_v1638_20260823_txhz_debug.bin of=/tmp/rfs_from_spi.squashfs bs=1 skip=$((0x710000)) count=$((4576*1024)) 2>/dev/null
ls -la /tmp/rfs_from_spi.squashfs

echo
echo "========== 2. 对比 内嵌rootfs vs 单独rootfs 文件 =========="
md5sum /tmp/rfs_from_spi.squashfs backup/rootfs_v1638_20260823_txhz_debug.squashfs
S1=$(md5sum /tmp/rfs_from_spi.squashfs | cut -d' ' -f1)
S2=$(md5sum backup/rootfs_v1638_20260823_txhz_debug.squashfs | cut -d' ' -f1)
[ "$S1" = "$S2" ] && echo "SAME ROOTFS" || echo "DIFFERENT ROOTFS"

echo
echo "========== 3. 解包 内嵌rootfs 检查 S99/getty/dji_rc =========="
rm -rf /tmp/rfs_spi
unsquashfs -d /tmp/rfs_spi /tmp/rfs_from_spi.squashfs >/dev/null 2>&1
echo "--- S99 里 getty/dji_rc/ttySC ---"
grep -n 'getty\|dji_rc\|ttySC\|ttyS0' /tmp/rfs_spi/etc/init.d/S99tun_nat_hub 2>&1 | head -20
echo "--- inittab ttyS0 ---"
grep -n 'ttyS0' /tmp/rfs_spi/etc/inittab 2>&1
echo "--- dji_rc 二进制 ---"
ls -la /tmp/rfs_spi/usr/local/bin/ 2>&1 | grep -E 'dji_rc|web_server'
echo "--- dji_rc 二进制 ttyS0/ttySC 引用 ---"
strings /tmp/rfs_spi/usr/local/bin/dji_rc 2>/dev/null | grep -iE 'ttyS0|ttySC' | sort -u

echo
echo "========== 4. 单独 rootfs_v1638 的 S99 头 =========="
head -8 backup/rootfs_v1638_20260823_txhz_debug.squashfs | xxd | head -3
echo "(直接 hexdump squashfs 头, 供参考)"
