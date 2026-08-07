#!/bin/bash
# 重建 rootfs (crsf-bridge): 固化 dji_rc 43b76343, base=rootfs_ch56
set -e
cd /mnt/c/my_project/TUN_NAT_HUB

echo "=== 1. 确认 dji_rc (应 43b76343 bridge 版) ==="
md5sum ubuntu/build_v3s/dji_rc

echo ""
echo "=== 2. 提取 base rootfs_ch56 ==="
BASE=backup/rootfs_ch56.squashfs
OUT=/tmp/rootfs_bridge
rm -rf "$OUT"
unsquashfs -q -d "$OUT" "$BASE" >/dev/null 2>&1
echo "提取完成: $OUT"

echo ""
echo "=== 3. 替换 dji_rc (bridge 版) ==="
cp ubuntu/build_v3s/dji_rc "$OUT/usr/local/bin/dji_rc"
chmod +x "$OUT/usr/local/bin/dji_rc"
md5sum "$OUT/usr/local/bin/dji_rc"

echo ""
echo "=== 4. 打包 squashfs (OTA 固件) ==="
cd /tmp
rm -f rootfs_bridge.squashfs
mksquashfs "$OUT" rootfs_bridge.squashfs -comp xz -b 131072 -noappend >/dev/null 2>&1
cp rootfs_bridge.squashfs /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_bridge.squashfs
echo "rootfs_bridge.squashfs: $(ls -la /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_bridge.squashfs | awk '{print $5}') bytes"
echo "md5: $(md5sum /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_bridge.squashfs | awk '{print $1}')"

echo ""
echo "=== 5. 读回校验 ==="
rm -rf /tmp/bridge_check
unsquashfs -q -d /tmp/bridge_check /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_bridge.squashfs >/dev/null 2>&1
echo "dji_rc md5 (应 43b76343):"
md5sum /tmp/bridge_check/usr/local/bin/dji_rc
echo "DONE"
