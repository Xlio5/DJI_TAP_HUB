#!/bin/bash
# 重建 rootfs v1.6.40: 修复 aux_tmux_set PIO 布局错误 (PB8/PB9 被误配 GPIO, UART0 debug 断连)
set -e
cd /mnt/c/my_project/TUN_NAT_HUB

GCC=/home/xlong/v3s/buildroot-2024.02/output/host/bin/arm-buildroot-linux-gnueabihf-gcc
GPP=/home/xlong/v3s/buildroot-2024.02/output/host/bin/arm-buildroot-linux-gnueabihf-g++
BASE=backup/rootfs.squashfs
OUT=/tmp/rfs_v1640
CHK=/tmp/v1640_check
BLD=/tmp/build_v1640

echo "=== 1. 编译 C 模块 (duml rc_decode chmap sbus rc_map) ==="
rm -rf "$BLD"; mkdir -p "$BLD"
for f in duml rc_decode chmap sbus rc_map crsf; do
    $GCC -O2 -s -c -o "$BLD/$f.o" "ubuntu/src/$f.c"
    echo "  $f.o OK"
done

echo "=== 2. 编译 dji_rc ==="
cp ubuntu/src/dji_rc.cpp ubuntu/src/*.h "$BLD/" 2>/dev/null
$GPP -std=c++17 -O2 -s -Wall -o "$BLD/dji_rc" "$BLD/dji_rc.cpp" \
    "$BLD/duml.o" "$BLD/rc_decode.o" "$BLD/chmap.o" "$BLD/sbus.o" "$BLD/rc_map.o" "$BLD/crsf.o" -lpthread
ls -la "$BLD/dji_rc"

echo "=== 3. 编译 web_server (v1.6.40) ==="
cp ubuntu/src/web_server.cpp "$BLD/"
$GPP -std=c++17 -Os -s -static -Wall -o "$BLD/web_server" "$BLD/web_server.cpp" "$BLD/rc_map.o" -lpthread
ls -la "$BLD/web_server"
echo "VERSION: $(strings "$BLD/web_server" | grep -oE '1\.6\.4[0-9]' | sort -u | head -1)"

echo "=== 4. 解包 base rootfs ==="
rm -rf "$OUT"
unsquashfs -q -d "$OUT" "$BASE"

echo "=== 5. 替换 dji_rc + web_server + S99 ==="
cp "$BLD/dji_rc"   "$OUT/usr/local/bin/dji_rc"
cp "$BLD/web_server" "$OUT/usr/local/bin/web_server"
cp ubuntu/scripts/S99tun_nat_hub "$OUT/etc/init.d/S99tun_nat_hub"
chmod +x "$OUT/usr/local/bin/dji_rc" "$OUT/usr/local/bin/web_server" "$OUT/etc/init.d/S99tun_nat_hub"

echo "=== 6. 打包 rootfs_v1640 ==="
rm -f /tmp/rootfs_v1640.squashfs
mksquashfs "$OUT" /tmp/rootfs_v1640.squashfs -comp xz -b 262144 -noappend -all-root
cp /tmp/rootfs_v1640.squashfs backup/rootfs_v1640.squashfs
echo "rootfs_v1640: $(stat -c%s backup/rootfs_v1640.squashfs) bytes"

echo "=== 7. 读回验证 ==="
rm -rf "$CHK"
unsquashfs -q -d "$CHK" backup/rootfs_v1640.squashfs
echo "--- S99 getty 残留 (应无) ---"
grep -c '/sbin/getty' "$CHK/etc/init.d/S99tun_nat_hub" || echo "0 (OK)"
echo "--- S99 dji_rc 行 ---"
grep -c 'ttySC0' "$CHK/etc/init.d/S99tun_nat_hub"
echo "--- web_server VERSION ---"
strings "$CHK/usr/local/bin/web_server" | grep -oE '1\.6\.4[0-9]' | sort -u
echo "--- dji_rc 设备引用 (应含 ttySC0, 不应含 ttyS0 输出) ---"
strings "$CHK/usr/local/bin/dji_rc" | grep -iE '/dev/ttyS[0-9]|/dev/ttySC' | sort -u
echo "--- dji_rc 里 0x28 危险注释确认 (应含 PB_CFG1 警告) ---"
strings "$CHK/usr/local/bin/dji_rc" | grep -i 'PB8\|严禁\|PB_CFG1' | head -3
echo "--- uid ---"
unsquashfs -s backup/rootfs_v1640.squashfs | grep -E 'Number of (uids|gids)'
echo "md5: $(md5sum backup/rootfs_v1640.squashfs | cut -d' ' -f1)"
echo "DONE"
