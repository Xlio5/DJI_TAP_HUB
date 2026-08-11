#!/bin/bash
# 重建 rootfs v4: v2 + 修正版 setup_v3s.sh (144 DHCP/static + 172 共存)
set -e
cd /mnt/c/my_project/TUN_NAT_HUB

echo "=== 1. 提取 base rootfs_v2 ==="
BASE=backup/rootfs_v2.squashfs
OUT=/tmp/rootfs_v4
rm -rf "$OUT"
unsquashfs -q -d "$OUT" "$BASE" >/dev/null 2>&1
echo "提取完成: $OUT"

echo ""
echo "=== 2. 替换 setup_v3s.sh (144+172 共存) ==="
cp ubuntu/scripts/setup_v3s.sh "$OUT/usr/local/bin/setup_v3s.sh"
chmod +x "$OUT/usr/local/bin/setup_v3s.sh"
echo "--- 144 配置 ---"; grep -n '192.168.144.66' "$OUT/usr/local/bin/setup_v3s.sh"
echo "--- 172 配置 ---"; grep -n '172.20.10.3' "$OUT/usr/local/bin/setup_v3s.sh"

echo ""
echo "=== 3. 确认关键内容 ==="
echo "host key:"; ls "$OUT/etc/dropbear_ed25519_host_key" 2>/dev/null || echo "缺!"
echo "dji_rc:"; md5sum "$OUT/usr/local/bin/dji_rc"

echo ""
echo "=== 4. 打包 squashfs ==="
cd /tmp
rm -f rootfs_v4.squashfs
mksquashfs "$OUT" rootfs_v4.squashfs -comp xz -b 131072 -noappend >/dev/null 2>&1
cp rootfs_v4.squashfs /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_v4.squashfs
echo "rootfs_v4.squashfs: $(ls -la /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_v4.squashfs | awk '{print $5}') bytes"
echo "md5: $(md5sum /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_v4.squashfs | awk '{print $1}')"

echo ""
echo "=== 5. 读回校验 ==="
rm -rf /tmp/v4_check
unsquashfs -q -d /tmp/v4_check /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_v4.squashfs >/dev/null 2>&1
echo "144 IP:"; grep -n '192.168.144.66' /tmp/v4_check/usr/local/bin/setup_v3s.sh
echo "172 IP:"; grep -n '172.20.10.3' /tmp/v4_check/usr/local/bin/setup_v3s.sh
echo "DONE"
