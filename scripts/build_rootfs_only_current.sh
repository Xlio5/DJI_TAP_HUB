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
cp "$PROJECT/ubuntu/scripts/setup_v3s_fixed.sh" "$TGT/usr/local/bin/setup_v3s.sh"
chmod +x "$TGT/etc/init.d/S99tun_nat_hub" "$TGT/usr/local/bin/setup_v3s.sh"

echo "=== Compile web_server ==="
"$GPP" -std=c++17 -Os -s -static -Wall \
  -o "$TGT/usr/local/bin/web_server" \
  "$PROJECT/ubuntu/src/web_server.cpp" \
  -lpthread
chmod +x "$TGT/usr/local/bin/web_server"
echo "web_server: $(stat -c%s "$TGT/usr/local/bin/web_server") bytes"

echo "=== Compile dji_rc ==="
DJI_TMP=$(mktemp -d)
trap 'rm -rf "$DJI_TMP"' EXIT
for f in duml rc_decode chmap sbus; do
  "$GCC" -O2 -s -c -o "$DJI_TMP/${f}.o" "$PROJECT/ubuntu/src/${f}.c"
done
"$GPP" -std=c++17 -O2 -s -Wall \
  -o "$TGT/usr/local/bin/dji_rc" \
  "$PROJECT/ubuntu/src/dji_rc.cpp" \
  "$DJI_TMP/duml.o" "$DJI_TMP/rc_decode.o" "$DJI_TMP/chmap.o" "$DJI_TMP/sbus.o" \
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
