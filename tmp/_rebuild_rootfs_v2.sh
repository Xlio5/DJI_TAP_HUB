#!/bin/bash
# 重建 rootfs v2:
#   - dropbear host key 固化 (/etc/dropbear_ed25519_host_key)
#   - S50dropbear 去 -R (持久 key)
#   - dji_rc 86f48284 + web_server 69f47711
#   - S99 + inittab getty 禁用
set -e
cd /mnt/c/my_project/TUN_NAT_HUB

echo "=== 1. 确认二进制 + key ==="
md5sum ubuntu/build_v3s/dji_rc ubuntu/build_v3s/web_server 2>/dev/null || echo "需先编译"
ls -la tmp/dropbear_ed25519_host_key 2>/dev/null || echo "缺 host key"
ls -la tmp/S50dropbear_new 2>/dev/null || echo "缺 S50dropbear"

echo ""
echo "=== 2. 提取 base rootfs_new.squashfs ==="
BASE=backup/rootfs_new.squashfs
OUT=/tmp/rootfs_v2
rm -rf "$OUT"
unsquashfs -q -d "$OUT" "$BASE" >/dev/null 2>&1
echo "提取完成: $OUT"

echo ""
echo "=== 3. 替换二进制 (dji_rc + web_server) ==="
cp ubuntu/build_v3s/dji_rc     "$OUT/usr/local/bin/dji_rc"
cp ubuntu/build_v3s/web_server "$OUT/usr/local/bin/web_server"
chmod +x "$OUT/usr/local/bin/dji_rc" "$OUT/usr/local/bin/web_server"
md5sum "$OUT/usr/local/bin/dji_rc" "$OUT/usr/local/bin/web_server"

echo ""
echo "=== 4. dropbear host key 固化 ==="
cp tmp/dropbear_ed25519_host_key "$OUT/etc/dropbear_ed25519_host_key"
chmod 600 "$OUT/etc/dropbear_ed25519_host_key"
ls -la "$OUT/etc/dropbear_ed25519_host_key"

echo ""
echo "=== 5. S50dropbear 替换 (去 -R) ==="
cp tmp/S50dropbear_new "$OUT/etc/init.d/S50dropbear"
chmod +x "$OUT/etc/init.d/S50dropbear"
grep -n 'DROPBEAR_ARGS' "$OUT/etc/init.d/S50dropbear" | head -2

echo ""
echo "=== 6. S99 + inittab getty 禁用 ==="
cp ubuntu/scripts/S99tun_nat_hub "$OUT/etc/init.d/S99tun_nat_hub"
chmod +x "$OUT/etc/init.d/S99tun_nat_hub"
sed -i 's|^\(.*ttyS0.*\)$|#\1  # disabled: UART0 由 dji_rc 管理|' "$OUT/etc/inittab" 2>/dev/null || echo "无 inittab"
grep -n 'ttyS0' "$OUT/etc/inittab" | head -2

echo ""
echo "=== 7. 打包 squashfs ==="
cd /tmp
rm -f rootfs_v2.squashfs
mksquashfs "$OUT" rootfs_v2.squashfs -comp xz -b 131072 -noappend >/dev/null 2>&1
cp rootfs_v2.squashfs /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_v2.squashfs
echo "rootfs_v2.squashfs: $(ls -la /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_v2.squashfs | awk '{print $5}') bytes"
echo "md5: $(md5sum /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_v2.squashfs | awk '{print $1}')"

echo ""
echo "=== 8. 读回校验 ==="
rm -rf /tmp/v2_check
unsquashfs -q -d /tmp/v2_check /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_v2.squashfs >/dev/null 2>&1
echo "dji_rc (应 86f48284):"; md5sum /tmp/v2_check/usr/local/bin/dji_rc
echo "host key:"; ls -la /tmp/v2_check/etc/dropbear_ed25519_host_key 2>/dev/null || echo "缺 key!"
echo "S50dropbear 去-R:"; grep -c 'DROPBEAR_ARGS' /tmp/v2_check/etc/init.d/S50dropbear
echo "DONE"
