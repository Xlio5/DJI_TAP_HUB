#!/bin/bash
# 重建 rootfs (CRSF 增强版): 固化 dji_rc 9f867cf9, base=rootfs_v150
set -e
cd /mnt/c/my_project/TUN_NAT_HUB

echo "=== 1. 确认 dji_rc (应 9f867cf9) ==="
md5sum ubuntu/build_v3s/dji_rc

echo ""
echo "=== 2. 提取 base rootfs_v150 ==="
BASE=backup/rootfs_v150.squashfs
OUT=/tmp/rootfs_crsf
rm -rf "$OUT"
unsquashfs -q -d "$OUT" "$BASE" >/dev/null 2>&1
echo "提取完成: $OUT"

echo ""
echo "=== 3. 替换 dji_rc (CRSF 增强版) ==="
cp ubuntu/build_v3s/dji_rc "$OUT/usr/local/bin/dji_rc"
chmod +x "$OUT/usr/local/bin/dji_rc"
md5sum "$OUT/usr/local/bin/dji_rc"

echo ""
echo "=== 4. 打包 squashfs (OTA 固件) ==="
cd /tmp
rm -f rootfs_crsf.squashfs
mksquashfs "$OUT" rootfs_crsf.squashfs -comp xz -b 131072 -noappend >/dev/null 2>&1
cp rootfs_crsf.squashfs /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_crsf.squashfs
echo "rootfs_crsf.squashfs: $(ls -la /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_crsf.squashfs | awk '{print $5}') bytes"
echo "md5: $(md5sum /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_crsf.squashfs | awk '{print $1}')"

echo ""
echo "=== 5. 读回校验 ==="
rm -rf /tmp/crsf_check
unsquashfs -q -d /tmp/crsf_check /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_crsf.squashfs >/dev/null 2>&1
echo "dji_rc md5 (应 9f867cf9):"
md5sum /tmp/crsf_check/usr/local/bin/dji_rc
echo "DONE"
