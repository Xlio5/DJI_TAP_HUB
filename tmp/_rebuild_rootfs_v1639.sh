#!/bin/bash
# 重建 rootfs v1.6.39: 移除 S99 双 getty (UART0 debug 由 inittab 托管)
set -e
cd /mnt/c/my_project/TUN_NAT_HUB

GPP=/home/xlong/v3s/buildroot-2024.02/output/host/bin/arm-buildroot-linux-gnueabihf-g++
BASE=backup/rootfs.squashfs
OUT=/tmp/rfs_v1639
CHK=/tmp/v1639_check
BLD=/tmp/build_v1639

echo "=== 1. 交叉编译 web_server (v1.6.39) ==="
rm -rf "$BLD"; mkdir -p "$BLD"
cp ubuntu/src/*.cpp ubuntu/src/*.c ubuntu/src/*.h "$BLD/" 2>/dev/null
$GPP -std=c++17 -Os -s -static -Wall -o "$BLD/web_server" "$BLD/web_server.cpp" "$BLD/rc_map.c" -lpthread
ls -la "$BLD/web_server"
echo "VERSION 字符串: $(strings "$BLD/web_server" | grep -oE '1\.6\.3[0-9]' | sort -u | head -1)"

echo
echo "=== 2. 解包 base rootfs ==="
rm -rf "$OUT"
unsquashfs -q -d "$OUT" "$BASE"
echo "解包完成: $(ls "$OUT/usr/local/bin/")"

echo
echo "=== 3. 替换 S99 + web_server ==="
cp ubuntu/scripts/S99tun_nat_hub "$OUT/etc/init.d/S99tun_nat_hub"
cp "$BLD/web_server" "$OUT/usr/local/bin/web_server"
chmod +x "$OUT/etc/init.d/S99tun_nat_hub" "$OUT/usr/local/bin/web_server"

echo
echo "=== 4. 打包 rootfs_v1639 ==="
rm -f /tmp/rootfs_v1639.squashfs
mksquashfs "$OUT" /tmp/rootfs_v1639.squashfs -comp xz -b 262144 -noappend -all-root
cp /tmp/rootfs_v1639.squashfs backup/rootfs_v1639.squashfs
SIZE=$(stat -c%s backup/rootfs_v1639.squashfs)
echo "rootfs_v1639: $SIZE bytes ($(echo "scale=2; $SIZE/1048576" | bc) MB)"

echo
echo "=== 5. 读回验证 ==="
rm -rf "$CHK"
unsquashfs -q -d "$CHK" backup/rootfs_v1639.squashfs
echo "--- S99 getty/ttyS0 残留检查 (应为空) ---"
grep -n 'getty\|ttyS0' "$CHK/etc/init.d/S99tun_nat_hub" || echo "OK: S99 无 getty 残留"
echo "--- S99 dji_rc 行 (应保留 ttySC0) ---"
grep -n 'dji_rc' "$CHK/etc/init.d/S99tun_nat_hub" | head -2
echo "--- web_server VERSION ---"
strings "$CHK/usr/local/bin/web_server" | grep -oE '1\.6\.3[0-9]' | sort -u
echo "--- dji_rc 设备引用 ---"
strings "$CHK/usr/local/bin/dji_rc" | grep -iE 'ttySC0|ttyS0' | sort -u
echo "--- inittab ttyS0 getty (应保留, 唯一 getty) ---"
grep -n 'ttyS0' "$CHK/etc/inittab"
echo "--- uid 检查 (应全为 root 0:0) ---"
unsquashfs -s backup/rootfs_v1639.squashfs | grep -E 'uid|gid'
echo
echo "=== 6. md5 汇总 ==="
echo "rootfs_v1639: $(md5sum backup/rootfs_v1639.squashfs | cut -d' ' -f1)"
echo "旧 rootfs.squashfs: $(md5sum backup/rootfs.squashfs | cut -d' ' -f1)"
echo "DONE"
