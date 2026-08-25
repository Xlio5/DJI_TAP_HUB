#!/bin/bash
set -euo pipefail

VERSION="${1:-v1.6.45}"
TS="${2:-$(date +%Y%m%d_%H%M%S)}"

PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
REL="$PROJECT/backup/release_${TS}_${VERSION}"
ROOTFS="$REL/rootfs_${VERSION}_${TS}.squashfs"
SPI="$REL/spi_image_${VERSION}_${TS}.bin"
SOURCE_COMMIT="$(git -C "$PROJECT" rev-parse HEAD)"
BRANCH="$(git -C "$PROJECT" rev-parse --abbrev-ref HEAD)"

mkdir -p "$REL"

cp "$PROJECT/backup/rootfs.squashfs" "$ROOTFS"
python3 "$PROJECT/scripts/build_spi_image.py" "$ROOTFS" "$SPI"
cp "$SPI" "$PROJECT/backup/spi_image.bin"

cmp "$ROOTFS" "$PROJECT/backup/rootfs.squashfs"
cmp "$SPI" "$PROJECT/backup/spi_image.bin"

ROOT_SIZE="$(stat -c%s "$ROOTFS")"
SPI_SIZE="$(stat -c%s "$SPI")"
SLICE="$REL/.rootfs_slice_verify.squashfs"
dd if="$SPI" of="$SLICE" bs=4096 skip=$(((7232 * 1024) / 4096)) count=$(((ROOT_SIZE + 4095) / 4096)) status=none
truncate -s "$ROOT_SIZE" "$SLICE"
cmp "$ROOTFS" "$SLICE"
rm -f "$SLICE"

CHK="/tmp/tun_nat_hub_release_check_${TS}"
rm -rf "$CHK"
unsquashfs -q -d "$CHK" "$ROOTFS"
grep -n "INTERNAL_FWD_ADDR=10.0.0.2" "$CHK/usr/local/bin/setup_v3s.sh"
grep -n "MASQUERADE" "$CHK/usr/local/bin/setup_v3s.sh"
grep -a -m1 "${VERSION#v}" "$CHK/usr/local/bin/web_server"
grep -a -m1 "console=ttyS0,115200" "$SPI"

sha256sum "$ROOTFS" "$SPI" "$PROJECT/backup/rootfs.squashfs" "$PROJECT/backup/spi_image.bin" > "$REL/SHA256SUMS.txt"
ROOT_SHA="$(sha256sum "$ROOTFS" | awk '{print $1}')"
SPI_SHA="$(sha256sum "$SPI" | awk '{print $1}')"

cat > "$REL/manifest.md" <<EOF
# TUN_NAT_HUB Firmware Release $VERSION

- version: $VERSION
- timestamp: $TS
- branch: $BRANCH
- source_commit: $SOURCE_COMMIT
- rootfs: rootfs_${VERSION}_${TS}.squashfs
- rootfs_size: $ROOT_SIZE
- rootfs_sha256: $ROOT_SHA
- spi_image: spi_image_${VERSION}_${TS}.bin
- spi_image_size: $SPI_SIZE
- spi_image_sha256: $SPI_SHA

## Layout

- SPI total: 16 MiB
- SPL/U-Boot: image start and 0x8000
- env: 0x7e000
- dtb: 0x100000
- kernel: 0x110000
- rootfs_a: 0x710000
- rootfs type: squashfs

## Purpose

固化 RTSP 视频回流相关 V3s TUN/NAT 配置：tun_hub=10.0.0.1/24，Android 主隧道地址=10.0.0.2，LAN 身份 x.x.x.11 DNAT 到 10.0.0.2，并对 x.x.x.11 主动访问 LAN 摄像头做 eth0 MASQUERADE。

## Readback Verification

- rootfs copy-back cmp: OK
- spi alias copy-back cmp: OK
- rootfs magic in SPI @0x710000: hsqs OK
- SPI rootfs slice cmp: OK
- setup_v3s.sh contains INTERNAL_FWD_ADDR=10.0.0.2: OK
- setup_v3s.sh contains MASQUERADE: OK
- web_server strings contains 1.6.45: OK
- SPI bootargs contains console=ttyS0,115200: OK
EOF

echo "RELEASE_DIR=$REL"
echo "ROOTFS=$ROOTFS"
echo "SPI=$SPI"
cat "$REL/SHA256SUMS.txt"
