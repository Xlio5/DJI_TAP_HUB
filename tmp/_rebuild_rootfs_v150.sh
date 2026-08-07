#!/bin/bash
# 重建 rootfs v150: 固化 UDP 修复版 dji_rc (fad8b8f2), 沿用 v149 (inittab 已禁用)
set -e
cd /mnt/c/my_project/TUN_NAT_HUB

echo "=== 1. 确认编译产物 (应 fad8b8f2) ==="
md5sum ubuntu/build_v3s/dji_rc

echo ""
echo "=== 2. 提取 base rootfs_v149.squashfs ==="
BASE=backup/rootfs_v149.squashfs
if [ ! -f "$BASE" ]; then
    echo "缺 v149, 用 v148"
    BASE=backup/rootfs_v148.squashfs
fi
OUT=/tmp/rootfs_v150
rm -rf "$OUT"
unsquashfs -q -d "$OUT" "$BASE" >/dev/null 2>&1
echo "提取完成: $OUT (base=$BASE)"

echo ""
echo "=== 3. 替换 dji_rc (正式版) ==="
cp ubuntu/build_v3s/dji_rc "$OUT/usr/local/bin/dji_rc"
chmod +x "$OUT/usr/local/bin/dji_rc"
echo "--- 固化 md5 ---"
md5sum "$OUT/usr/local/bin/dji_rc"

echo ""
echo "=== 4. 确认 inittab ttyS0 仍禁用 ==="
grep -n 'ttyS0' "$OUT/etc/inittab" | head -1

echo ""
echo "=== 5. 打包 squashfs ==="
cd /tmp
rm -f rootfs_v150.squashfs
mksquashfs "$OUT" rootfs_v150.squashfs -comp xz -b 131072 -noappend >/dev/null 2>&1
cp rootfs_v150.squashfs /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_v150.squashfs
echo "rootfs_v150.squashfs: $(ls -la /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_v150.squashfs | awk '{print $5}') bytes"
echo "md5: $(md5sum /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_v150.squashfs | awk '{print $1}')"

echo ""
echo "=== 6. 读回校验 ==="
rm -rf /tmp/v150_check
unsquashfs -q -d /tmp/v150_check /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_v150.squashfs >/dev/null 2>&1
echo "--- 固化 dji_rc md5 (应 fad8b8f2) ---"
md5sum /tmp/v150_check/usr/local/bin/dji_rc
echo "DONE"
