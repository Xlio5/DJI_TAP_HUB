#!/bin/bash
# _build_v1712.sh — 构建固件 v1.6.12 (统一 400k 波特率, S99 --out-baud 400000)
set -e
PROJ=/mnt/c/my_project/TUN_NAT_HUB
BASE="$PROJ/backup/rootfs_v169.squashfs"
OUT=/home/xlong/build_v1712
OUT_SQ="$PROJ/backup/rootfs_v1712.squashfs"

echo "=== 1. 提取 base rootfs_v169 ==="
rm -rf "$OUT"; sleep 1; mkdir -p "$OUT"
unsquashfs -q -f -d "$OUT" "$BASE" 2>&1 | tail -1

echo "=== 2. 替换二进制 + 启动脚本 ==="
cp "$PROJ/ubuntu/build_v3s/dji_rc" "$OUT/usr/local/bin/dji_rc"
cp "$PROJ/ubuntu/build_v3s/web_server" "$OUT/usr/local/bin/web_server"
cp "$PROJ/ubuntu/scripts/S99tun_nat_hub" "$OUT/etc/init.d/S99tun_nat_hub"
cp "$PROJ/ubuntu/scripts/setup_v3s.sh" "$OUT/usr/local/bin/setup_v3s.sh"
chmod +x "$OUT/usr/local/bin/dji_rc" "$OUT/usr/local/bin/web_server" "$OUT/etc/init.d/S99tun_nat_hub" "$OUT/usr/local/bin/setup_v3s.sh"
echo "dji_rc: $(md5sum "$OUT/usr/local/bin/dji_rc" | awk '{print $1}')"
echo "web_server: $(strings "$OUT/usr/local/bin/web_server" | grep -o '1.6.12' | head -1)"
echo "S99 baud: $(grep -o 'out-baud [0-9]*' "$OUT/etc/init.d/S99tun_nat_hub")"

echo "=== 3. 校验关键配置 ==="
echo "172 IP: $(grep -c '172\.' "$OUT/usr/local/bin/setup_v3s.sh" 2>/dev/null || echo 0)"
head -1 "$OUT/etc/init.d/S99tun_nat_hub" | xxd | head -1

echo "=== 4. 打包 + 验证尾 ==="
rm -f /tmp/rootfs_v1712.sq
mksquashfs "$OUT" /tmp/rootfs_v1712.sq -comp xz -b 131072 -noappend 2>&1 | tail -1
python3 "$PROJ/tmp/_add_rootfs_tail.py" /tmp/rootfs_v1712.sq "$OUT_SQ"

echo "=== 5. 读回校验 ==="
rm -rf /home/xlong/v1712_check
unsquashfs -q -f -d /home/xlong/v1712_check "$OUT_SQ" 2>&1 | tail -1
echo "dji_rc: $(md5sum /home/xlong/v1712_check/usr/local/bin/dji_rc | awk '{print $1}')"
echo "web_server: $(strings /home/xlong/v1712_check/usr/local/bin/web_server | grep -o '1.6.12' | head -1)"
echo "S99 baud: $(grep -o 'out-baud [0-9]*' /home/xlong/v1712_check/etc/init.d/S99tun_nat_hub)"
echo "DONE"
