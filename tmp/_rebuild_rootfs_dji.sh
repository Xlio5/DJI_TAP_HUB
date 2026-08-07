#!/bin/bash
# 重新构建 rootfs: 固化修复版 dji_rc (54e2a723) + web_server + S99
set -e
cd /mnt/c/my_project/TUN_NAT_HUB

echo "=== 1. 确认编译产物 (应为修复版 54e2a723) ==="
md5sum ubuntu/build_v3s/dji_rc

echo ""
echo "=== 2. 提取 base rootfs_new.squashfs ==="
BASE=backup/rootfs_new.squashfs
if [ ! -f "$BASE" ]; then
    echo "缺少 $BASE, 尝试用现有 rootfs_v146.squashfs 作 base"
    BASE=backup/rootfs_v146.squashfs
fi
echo "BASE=$BASE"
OUT=/tmp/rootfs_v147
rm -rf "$OUT"
unsquashfs -q -d "$OUT" "$BASE" >/dev/null 2>&1
echo "提取完成: $OUT"

echo ""
echo "=== 3. 替换二进制 (dji_rc 修复版 + web_server) ==="
cp ubuntu/build_v3s/dji_rc    "$OUT/usr/local/bin/dji_rc"
cp ubuntu/build_v3s/web_server "$OUT/usr/local/bin/web_server"
chmod +x "$OUT/usr/local/bin/dji_rc" "$OUT/usr/local/bin/web_server"
md5sum "$OUT/usr/local/bin/dji_rc" "$OUT/usr/local/bin/web_server"

echo ""
echo "=== 4. 替换 S99 启动脚本 ==="
cp ubuntu/scripts/S99tun_nat_hub "$OUT/etc/init.d/S99tun_nat_hub"
chmod +x "$OUT/etc/init.d/S99tun_nat_hub"
grep dji_rc "$OUT/etc/init.d/S99tun_nat_hub" || true

echo ""
echo "=== 5. 重新打包 squashfs (xz) ==="
cd /tmp
rm -f rootfs_v147.squashfs
mksquashfs "$OUT" rootfs_v147.squashfs -comp xz -b 131072 -noappend >/dev/null 2>&1
cp rootfs_v147.squashfs /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_v147.squashfs
echo "rootfs_v147.squashfs: $(ls -la /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_v147.squashfs | awk '{print $5}') bytes"
echo "magic: $(head -c 4 /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_v147.squashfs)"

echo ""
echo "=== 6. 校验: unsquashfs 验证固化内容 ==="
rm -rf /tmp/v147_check && mkdir -p /tmp/v147_check
unsquashfs -q -d /tmp/v147_check /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_v147.squashfs >/dev/null 2>&1
echo "--- 固化 dji_rc md5 (应 54e2a723) ---"
md5sum /tmp/v147_check/usr/local/bin/dji_rc
echo "--- S99 存在 ---"
ls -la /tmp/v147_check/etc/init.d/S99tun_nat_hub && echo "  S99 OK"
echo "DONE"
