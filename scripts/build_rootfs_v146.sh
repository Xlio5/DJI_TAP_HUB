#!/bin/bash
# 构建 v1.4.6 rootfs: 从 rootfs_new.squashfs 提取, 替换 web_server/dji_rc/S99, 禁用 ttyS0 getty
set -e
cd /mnt/c/my_project/TUN_NAT_HUB

BASE=backup/rootfs_new.squashfs      # 含修复版 web_server 的当前 rootfs
OUT=/tmp/rootfs_v146
rm -rf "$OUT"
unsquashfs -q -d "$OUT" "$BASE" >/dev/null 2>&1
echo "提取完成: $OUT"

echo "=== 替换二进制 ==="
cp ubuntu/build_v3s/web_server "$OUT/usr/local/bin/web_server"
cp ubuntu/build_v3s/dji_rc    "$OUT/usr/local/bin/dji_rc"
chmod +x "$OUT/usr/local/bin/web_server" "$OUT/usr/local/bin/dji_rc"
md5sum "$OUT/usr/local/bin/web_server" "$OUT/usr/local/bin/dji_rc"

echo "=== 替换 S99 启动脚本 ==="
cp ubuntu/scripts/S99tun_nat_hub "$OUT/etc/init.d/S99tun_nat_hub"
chmod +x "$OUT/etc/init.d/S99tun_nat_hub"
grep dji_rc "$OUT/etc/init.d/S99tun_nat_hub"

echo "=== 禁用 ttyS0 getty (若有) ==="
if [ -f "$OUT/etc/inittab" ]; then
    echo "--- 原 inittab ttyS0 行 ---"
    grep -n 'ttyS0' "$OUT/etc/inittab" || echo "无 ttyS0"
    sed -i 's|^\(.*ttyS0.*\)$|#\1  # disabled: UART0 用于 SBUS/CRSF 输出|' "$OUT/etc/inittab"
    echo "--- 改后 ---"
    grep -n 'ttyS0' "$OUT/etc/inittab" || echo "无 ttyS0"
else
    echo "无 /etc/inittab"
fi

echo "=== 重新打包 squashfs ==="
cd /tmp
rm -f rootfs_v146.squashfs
mksquashfs "$OUT" rootfs_v146.squashfs -comp xz -b 131072 -noappend >/dev/null 2>&1
cp rootfs_v146.squashfs /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_v146.squashfs
echo "rootfs_v146.squashfs: $(ls -la /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_v146.squashfs | awk '{print $5}') bytes"
echo "magic: $(head -c 4 /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_v146.squashfs)"
echo "md5: $(md5sum /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_v146.squashfs | awk '{print $1}')"

echo ""
echo "=== 校验: unsquashfs 验证内容 ==="
rm -rf /tmp/v146_check && mkdir -p /tmp/v146_check
unsquashfs -q -d /tmp/v146_check /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_v146.squashfs >/dev/null 2>&1
md5sum /tmp/v146_check/usr/local/bin/web_server /tmp/v146_check/usr/local/bin/dji_rc
grep -c 'ttyS0.*disabled' /tmp/v146_check/etc/inittab 2>/dev/null || echo "getty 已禁用 (0)"
echo "DONE"
