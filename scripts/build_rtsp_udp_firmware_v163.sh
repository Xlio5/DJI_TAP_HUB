#!/bin/bash
# Build V3s firmware v1.6.3 with persistent RTSP UDP RTP forwarding.
set -euo pipefail

PROJECT=${PROJECT:-/mnt/c/my_project/TUN_NAT_HUB}
BASE_ROOTFS=${BASE_ROOTFS:-$PROJECT/backup/release_20260808_v162/rootfs_v162.squashfs}
RELEASE_DIR=${RELEASE_DIR:-$PROJECT/backup/release_20260809_v163}
ROOTFS_OUT=$RELEASE_DIR/rootfs_v163.squashfs
SPI_OUT=$RELEASE_DIR/spi_image_v10_v163.bin
WORK=/tmp/tun_nat_hub_v163

cd "$PROJECT"
mkdir -p "$RELEASE_DIR" "$WORK"

echo "=== 1. RTSP NAT helper unit test ==="
g++ -std=c++17 -Iubuntu/src -o "$WORK/rtsp_nat_helper_test" ubuntu/tests/rtsp_nat_helper_test.cpp
"$WORK/rtsp_nat_helper_test"

echo ""
echo "=== 2. Build web_server v1.6.3 for V3s ==="
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
WEB_VER=$(strings ubuntu/build_v3s/web_server | grep '^1\.6\.3$' | head -1)
RTSP_MARK=$(strings ubuntu/build_v3s/web_server | grep '\[rtsp-udp\]' | head -1)
echo "web_server md5: $WEB_MD5"
echo "web_server version: ${WEB_VER:-MISSING}"
echo "rtsp marker: ${RTSP_MARK:-MISSING}"
test "$WEB_VER" = "1.6.3"
test -n "$RTSP_MARK"

echo ""
echo "=== 3. Repack rootfs from v1.6.2 base ==="
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

echo ""
echo "=== 4. Build SPI image ==="
python3 -B scripts/build_spi_image.py "$ROOTFS_OUT" "$SPI_OUT"
SPI_MD5=$(md5sum "$SPI_OUT" | awk '{print $1}')
SPI_SIZE=$(stat -c%s "$SPI_OUT")
echo "spi image: $SPI_OUT"
echo "spi size: $SPI_SIZE"
echo "spi md5: $SPI_MD5"

echo ""
echo "=== 5. Read-back verify repacked rootfs ==="
rm -rf "$WORK/check"
unsquashfs -q -d "$WORK/check" "$ROOTFS_OUT"
CHECK_VER=$(strings "$WORK/check/usr/local/bin/web_server" | grep '^1\.6\.3$' | head -1)
CHECK_MARK=$(strings "$WORK/check/usr/local/bin/web_server" | grep '\[rtsp-udp\]' | head -1)
MAGIC=$(xxd -l 4 -p "$ROOTFS_OUT")
echo "check version: ${CHECK_VER:-MISSING}"
echo "check rtsp marker: ${CHECK_MARK:-MISSING}"
echo "rootfs magic: $MAGIC"
test "$CHECK_VER" = "1.6.3"
test -n "$CHECK_MARK"
test "$MAGIC" = "68737173"

cat > "$RELEASE_DIR/manifest_v163.txt" <<EOF
version=1.6.3
feature=rtsp_udp_rtp_forward_persistent
rootfs=$ROOTFS_OUT
rootfs_size=$ROOTFS_SIZE
rootfs_md5=$ROOTFS_MD5
spi_image=$SPI_OUT
spi_size=$SPI_SIZE
spi_md5=$SPI_MD5
web_server_md5=$WEB_MD5
base_rootfs=$BASE_ROOTFS
EOF

cp "$ROOTFS_OUT" "$PROJECT/backup/rootfs_v163.squashfs"
cp "$SPI_OUT" "$PROJECT/backup/spi_image_v10_v163.bin"

echo ""
echo "=== DONE v1.6.3 ==="
cat "$RELEASE_DIR/manifest_v163.txt"
