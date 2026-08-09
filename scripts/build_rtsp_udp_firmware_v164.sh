#!/bin/bash
# Build V3s firmware v1.6.4 with RTSP UDP RTP forwarding DNAT auto-retry.
# 修复: web_server 启动时 eth0 IP 未就绪导致 DNAT 规则永久丢失 → 主循环每 2s 重试补齐
set -euo pipefail

PROJECT=${PROJECT:-/mnt/c/my_project/TUN_NAT_HUB}
BASE_ROOTFS=${BASE_ROOTFS:-$PROJECT/backup/release_20260808_v162/rootfs_v162.squashfs}
RELEASE_DIR=${RELEASE_DIR:-$PROJECT/backup/release_20260809_v164}
ROOTFS_OUT=$RELEASE_DIR/rootfs_v164.squashfs
WORK=/tmp/tun_nat_hub_v164

cd "$PROJECT"
mkdir -p "$RELEASE_DIR" "$WORK"

echo "=== 1. Build web_server v1.6.4 for V3s ==="
rm -rf "$WORK/ws_o"
mkdir -p "$WORK/ws_o" ubuntu/build_v3s
for f in rc_map rc_decode; do
    CCACHE_DISABLE=1 arm-linux-gnueabihf-gcc -O2 -s -c \
        -o "$WORK/ws_o/${f}.o" "ubuntu/src/${f}.c"
done
CCACHE_DISABLE=1 arm-linux-gnueabihf-g++ -std=c++17 -Os -s \
    -o ubuntu/build_v3s/web_server \
    ubuntu/src/web_server.cpp "$WORK"/ws_o/*.o -lpthread
WEB_MD5=$(md5sum ubuntu/build_v3s/web_server | awk '{print $1}')
WEB_VER=$(strings ubuntu/build_v3s/web_server | grep '^1\.6\.4$' | head -1)
RTSP_MARK=$(strings ubuntu/build_v3s/web_server | grep '\[rtsp-udp\]' | head -1)
RETRY_MARK=$(strings ubuntu/build_v3s/web_server | grep -c 'RTSP UDP')
echo "web_server md5: $WEB_MD5"
echo "web_server version: ${WEB_VER:-MISSING}"
echo "rtsp marker: ${RTSP_MARK:-MISSING}"
echo "retry log marker count: $RETRY_MARK (expect >=1)"
test "$WEB_VER" = "1.6.4"
test -n "$RTSP_MARK"
test "$RETRY_MARK" -ge 1

echo ""
echo "=== 2. Repack rootfs from v1.6.2 base ==="
rm -rf "$WORK/rootfs"
unsquashfs -q -d "$WORK/rootfs" "$BASE_ROOTFS"
install -m 0755 ubuntu/build_v3s/web_server "$WORK/rootfs/usr/local/bin/web_server"
rm -f "$ROOTFS_OUT"
mksquashfs "$WORK/rootfs" "$ROOTFS_OUT" -comp xz -b 262144 -noappend >/dev/null
ROOTFS_MD5=$(md5sum "$ROOTFS_OUT" | awk '{print $1}')
ROOTFS_SIZE=$(stat -c%s "$ROOTFS_OUT")
echo "rootfs: $ROOTFS_OUT"
echo "rootfs size: $ROOTFS_SIZE"
echo "rootfs md5: $ROOTFS_MD5"
# 大小需 <= 4.78MB (mtd3/mtd4 分区 0x478000), 留点余量
test "$ROOTFS_SIZE" -le 4600000 || echo "WARN: rootfs size $ROOTFS_SIZE near/exceeds partition limit"

echo ""
echo "=== 3. Read-back verify repacked rootfs ==="
rm -rf "$WORK/check"
unsquashfs -q -d "$WORK/check" "$ROOTFS_OUT"
CHECK_VER=$(strings "$WORK/check/usr/local/bin/web_server" | grep '^1\.6\.4$' | head -1)
CHECK_RETRY=$(strings "$WORK/check/usr/local/bin/web_server" | grep -c 'RTSP UDP')
MAGIC=$(xxd -l 4 -p "$ROOTFS_OUT")
echo "check version: ${CHECK_VER:-MISSING}"
echo "check retry marker count: $CHECK_RETRY (expect >=1)"
echo "rootfs magic: $MAGIC"
test "$CHECK_VER" = "1.6.4"
test "$CHECK_RETRY" -ge 1
test "$MAGIC" = "68737173"

cat > "$RELEASE_DIR/manifest_v164.txt" <<EOF
version=1.6.4
feature=rtsp_udp_rtp_forward_dnat_autoretry
rootfs=$ROOTFS_OUT
rootfs_size=$ROOTFS_SIZE
rootfs_md5=$ROOTFS_MD5
web_server_md5=$WEB_MD5
base_rootfs=$BASE_ROOTFS
EOF

cp "$ROOTFS_OUT" "$PROJECT/backup/rootfs_v164.squashfs"

echo ""
echo "=== DONE v1.6.4 ==="
cat "$RELEASE_DIR/manifest_v164.txt"
