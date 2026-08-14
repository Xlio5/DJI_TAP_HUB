#!/bin/bash
# _pack_rootfs_v169.sh — 打包 rootfs_v169 (base v168 提取 + 替换 dji_rc/web_server/S99)
# 产物 backup/rootfs_v169.squashfs。S99 用 git 版(LF), 避免 Windows CRLF 破坏 busybox。
set -e
cd /mnt/c/work/tun_-nat_-hub
BASE=backup/rootfs_v168.squashfs
OUT=/tmp/rootfs_v169_build
rm -rf "$OUT"
echo "=== 提取 base $BASE ==="
unsquashfs -q -f -d "$OUT" "$BASE"

echo "=== 替换二进制/脚本 ==="
cp ubuntu/build_v3s/dji_rc      "$OUT/usr/local/bin/dji_rc"
cp ubuntu/build_v3s/web_server  "$OUT/usr/local/bin/web_server"
# S99 去 CRLF (工作区被 Windows 转 CRLF, 会破坏 busybox)
sed 's/\r$//' ubuntu/scripts/S99tun_nat_hub > "$OUT/etc/init.d/S99tun_nat_hub"
chmod 755 "$OUT/etc/init.d/S99tun_nat_hub"

echo "=== 校验关键配置 ==="
echo "-- S99 LF (应 0a):"; head -1 "$OUT/etc/init.d/S99tun_nat_hub" | xxd | head -1
echo "-- S99 out-baud:"; grep -o "out-baud [0-9]*" "$OUT/etc/init.d/S99tun_nat_hub"
echo "-- 172 备用 IP 数:"; grep -c "172\." "$OUT/usr/local/bin/setup_v3s.sh" || true

echo "=== 打包 (XZ) ==="
mksquashfs "$OUT" /tmp/rootfs_v169.sq -comp xz -b 131072 -noappend 2>&1 | tail -1

echo "=== 加校验尾 (TUN_NAT_HUB + CRC32) ==="
python3 -c "
import zlib, struct
data = open('/tmp/rootfs_v169.sq','rb').read()
crc = zlib.crc32(data) & 0xFFFFFFFF
tail = b'TUN_NAT_HUB' + struct.pack('<I', crc)
open('backup/rootfs_v169.squashfs','wb').write(data + tail)
print(f'OK {len(data)+len(tail)}B, CRC=0x{crc:08X}')
"
ls -la backup/rootfs_v169.squashfs

echo "=== 读回校验 ==="
unsquashfs -q -d /tmp/v169_check backup/rootfs_v169.squashfs
echo "-- dji_rc md5:"; md5sum /tmp/v169_check/usr/local/bin/dji_rc ubuntu/build_v3s/dji_rc
echo "-- web_server md5:"; md5sum /tmp/v169_check/usr/local/bin/web_server ubuntu/build_v3s/web_server
echo "-- web_server 版本:"; strings /tmp/v169_check/usr/local/bin/web_server | grep -oE "1\.6\.9" | head -1
echo "-- 校验尾:"; xxd backup/rootfs_v169.squashfs | tail -1
