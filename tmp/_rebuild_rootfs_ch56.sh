#!/bin/bash
# 重建 rootfs (CRSF增强 + CH5/CH6对调): 固化 dji_rc 86f48284, base=rootfs_crsf
set -e
cd /mnt/c/my_project/TUN_NAT_HUB

echo "=== 1. 确认 dji_rc (应 86f48284) ==="
md5sum ubuntu/build_v3s/dji_rc

echo ""
echo "=== 2. 提取 base rootfs_crsf ==="
BASE=backup/rootfs_crsf.squashfs
OUT=/tmp/rootfs_ch56
rm -rf "$OUT"
unsquashfs -q -d "$OUT" "$BASE" >/dev/null 2>&1
echo "提取完成: $OUT"

echo ""
echo "=== 3. 替换 dji_rc (CRSF增强 + CH5/CH6对调) ==="
cp ubuntu/build_v3s/dji_rc "$OUT/usr/local/bin/dji_rc"
chmod +x "$OUT/usr/local/bin/dji_rc"
md5sum "$OUT/usr/local/bin/dji_rc"

echo ""
echo "=== 4. 打包 squashfs ==="
cd /tmp
rm -f rootfs_ch56.squashfs
mksquashfs "$OUT" rootfs_ch56.squashfs -comp xz -b 131072 -noappend >/dev/null 2>&1
cp rootfs_ch56.squashfs /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_ch56.squashfs
echo "rootfs_ch56.squashfs: $(ls -la /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_ch56.squashfs | awk '{print $5}') bytes"
echo "md5: $(md5sum /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_ch56.squashfs | awk '{print $1}')"

echo ""
echo "=== 5. 读回校验 ==="
rm -rf /tmp/ch56_check
unsquashfs -q -d /tmp/ch56_check /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_ch56.squashfs >/dev/null 2>&1
echo "dji_rc md5 (应 86f48284):"
md5sum /tmp/ch56_check/usr/local/bin/dji_rc
echo "DONE"
