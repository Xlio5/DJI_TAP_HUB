#!/bin/bash
set -euo pipefail

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

PROJECT=/mnt/c/my_project/TUN_NAT_HUB
BUILDROOT=/home/xlong/v3s/buildroot-2024.02
TGT=$BUILDROOT/output/target
HOST=$BUILDROOT/output/host/bin
GCC=$HOST/arm-buildroot-linux-gnueabihf-gcc
GPP=$HOST/arm-buildroot-linux-gnueabihf-g++

echo "=== Rootfs-only OTA build ==="
echo "project: $PROJECT"
echo "target:  $TGT"

mkdir -p "$TGT/etc/init.d" "$TGT/usr/local/bin" "$BUILDROOT/output/images" "$PROJECT/backup"

echo "=== Copy startup scripts ==="
cp "$PROJECT/ubuntu/scripts/S99tun_nat_hub" "$TGT/etc/init.d/"
cp "$PROJECT/ubuntu/scripts/setup_v3s.sh" "$TGT/usr/local/bin/setup_v3s.sh"
chmod +x "$TGT/etc/init.d/S99tun_nat_hub" "$TGT/usr/local/bin/setup_v3s.sh"

echo "=== Compile web_server ==="
# 注意: web_server 的 apiRcOutput 依赖 rc_map (rc_map_default/rc_src_name)。
# rc_map.c 必须用 gcc 编译成 .o (C 链接), 否则 g++ 会按 C++ mangle 符号, 与
# web_server.cpp 中经由 extern "C" 包裹的声明 (C 链接) 不匹配 → 链接失败。
WEB_TMP=$(mktemp -d)
"$GCC" -O2 -s -c -o "$WEB_TMP/rc_map.o" "$PROJECT/ubuntu/src/rc_map.c"
"$GPP" -std=c++17 -Os -s -static -Wall \
  -o "$TGT/usr/local/bin/web_server" \
  "$PROJECT/ubuntu/src/web_server.cpp" \
  "$WEB_TMP/rc_map.o" \
  -lpthread
rm -rf "$WEB_TMP"
chmod +x "$TGT/usr/local/bin/web_server"
echo "web_server: $(stat -c%s "$TGT/usr/local/bin/web_server") bytes"

echo "=== Compile dji_rc ==="
DJI_TMP=$(mktemp -d)
trap 'rm -rf "$DJI_TMP"' EXIT
# 注意: dji_rc 依赖 crsf (CRSF 编解码/回传) 和 rc_map (通道映射), 之前漏链导致链接失败
for f in duml rc_decode chmap sbus crsf rc_map; do
  "$GCC" -O2 -s -c -o "$DJI_TMP/${f}.o" "$PROJECT/ubuntu/src/${f}.c"
done
"$GPP" -std=c++17 -O2 -s -Wall \
  -o "$TGT/usr/local/bin/dji_rc" \
  "$PROJECT/ubuntu/src/dji_rc.cpp" \
  "$DJI_TMP/duml.o" "$DJI_TMP/rc_decode.o" "$DJI_TMP/chmap.o" "$DJI_TMP/sbus.o" "$DJI_TMP/crsf.o" "$DJI_TMP/rc_map.o" \
  -lpthread
chmod +x "$TGT/usr/local/bin/dji_rc"
echo "dji_rc: $(stat -c%s "$TGT/usr/local/bin/dji_rc") bytes"

echo "=== Verify startup command ==="
grep -n -- '--rcmsg-host\|--rcmsg-port\|--interval' "$TGT/etc/init.d/S99tun_nat_hub"

echo "=== Build rootfs.squashfs ==="
cd "$BUILDROOT"
rm -f output/images/rootfs.squashfs
mksquashfs output/target output/images/rootfs.squashfs -comp xz -b 1048576 -Xdict-size 1048576 -noappend | tail -3
cp output/images/rootfs.squashfs "$PROJECT/backup/rootfs.squashfs"

ROOTFS="$PROJECT/backup/rootfs.squashfs"
echo "rootfs: $(stat -c%s "$ROOTFS") bytes"
printf "magic: "
hexdump -n 4 -e '4/1 "%c"' "$ROOTFS"
printf "\n"

echo "=== Verify rootfs contents ==="
rm -rf /tmp/tun_nat_hub_rootfs_check
unsquashfs -q -d /tmp/tun_nat_hub_rootfs_check "$ROOTFS"
test -x /tmp/tun_nat_hub_rootfs_check/usr/local/bin/web_server
test -x /tmp/tun_nat_hub_rootfs_check/usr/local/bin/dji_rc
grep -n -- '--rcmsg-host\|--rcmsg-port\|--interval' /tmp/tun_nat_hub_rootfs_check/etc/init.d/S99tun_nat_hub
strings /tmp/tun_nat_hub_rootfs_check/usr/local/bin/dji_rc | grep -E 'RCM1|rcmsg-host|rcmsg-port|65530' | head -20

echo "DONE: $ROOTFS"
