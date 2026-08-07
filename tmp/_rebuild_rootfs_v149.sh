#!/bin/bash
# 重建 rootfs v149: 禁用 inittab ttyS0 getty + 固化 getty_stop 增强版 dji_rc
set -e
cd /mnt/c/my_project/TUN_NAT_HUB

echo "=== 1. 确认编译产物 (应 68a6b7b5 getty_stop增强) ==="
md5sum ubuntu/build_v3s/dji_rc

echo ""
echo "=== 2. 提取 base rootfs_new.squashfs ==="
BASE=backup/rootfs_new.squashfs
OUT=/tmp/rootfs_v149
rm -rf "$OUT"
unsquashfs -q -d "$OUT" "$BASE" >/dev/null 2>&1
echo "提取完成: $OUT"

echo ""
echo "=== 3. 禁用 inittab ttyS0 getty (关键) ==="
echo "--- 禁用前 ---"
grep -n 'ttyS0' "$OUT/etc/inittab" || echo "无 ttyS0 行"
sed -i 's|^\(.*ttyS0.*\)$|#\1  # disabled: UART0 由 dji_rc 管理 (SBUS/CRSF 输出)|' "$OUT/etc/inittab"
echo "--- 禁用后 ---"
grep -n 'ttyS0' "$OUT/etc/inittab" || echo "无 ttyS0 行"

echo ""
echo "=== 4. 固化二进制 ==="
cp ubuntu/build_v3s/dji_rc     "$OUT/usr/local/bin/dji_rc"
cp ubuntu/build_v3s/web_server "$OUT/usr/local/bin/web_server"
chmod +x "$OUT/usr/local/bin/dji_rc" "$OUT/usr/local/bin/web_server"
echo "--- 固化 md5 ---"
md5sum "$OUT/usr/local/bin/dji_rc" "$OUT/usr/local/bin/web_server"

echo ""
echo "=== 5. S99 启动脚本 ==="
cp ubuntu/scripts/S99tun_nat_hub "$OUT/etc/init.d/S99tun_nat_hub"
chmod +x "$OUT/etc/init.d/S99tun_nat_hub"
grep dji_rc "$OUT/etc/init.d/S99tun_nat_hub" | head -2 || true

echo ""
echo "=== 6. 打包 squashfs ==="
cd /tmp
rm -f rootfs_v149.squashfs
mksquashfs "$OUT" rootfs_v149.squashfs -comp xz -b 131072 -noappend >/dev/null 2>&1
cp rootfs_v149.squashfs /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_v149.squashfs
echo "rootfs_v149.squashfs: $(ls -la /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_v149.squashfs | awk '{print $5}') bytes"
echo "magic: $(head -c 4 /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_v149.squashfs)"
echo "md5: $(md5sum /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_v149.squashfs | awk '{print $1}')"

echo ""
echo "=== 7. 读回校验 ==="
rm -rf /tmp/v149_check
unsquashfs -q -d /tmp/v149_check /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_v149.squashfs >/dev/null 2>&1
echo "--- 固化 dji_rc md5 (应 68a6b7b5) ---"
md5sum /tmp/v149_check/usr/local/bin/dji_rc
echo "--- inittab ttyS0 (应已禁用) ---"
grep -n 'ttyS0' /tmp/v149_check/etc/inittab || echo "✓ 无 ttyS0 启用行"
echo "DONE"
