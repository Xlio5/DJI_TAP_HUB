#!/bin/bash
# 重建 rootfs v1.6.29 (做法B: 砍 10.0.0.x, 手机 144.11)
# 替换: dji_rc (144.11) + web_server (1.6.29) + usb_tund (tun_hub 不配IP) + setup_v3s.sh
set -e
cd /mnt/c/my_project/TUN_NAT_HUB

echo "=== 确认编译产物 ==="
echo "dji_rc:      $(md5sum ubuntu/build_v3s/dji_rc | cut -d' ' -f1)  (期望 e46cdaa2)"
echo "web_server:  $(md5sum ubuntu/build_v3s/web_server | cut -d' ' -f1)  (期望 22a4d301)"
if [ -f ubuntu/build_v3s/usb_tund ]; then
    echo "usb_tund: $(md5sum ubuntu/build_v3s/usb_tund | cut -d' ' -f1)  (期望 97562926)"
    USB=ubuntu/build_v3s/usb_tund
else
    echo "!! ubuntu/build_v3s/usb_tund 不存在, 先跑 _build_usbtund.sh"
    exit 1
fi

# ── 解包 base + 替换 ──
echo ""
echo "=== 解包 backup/rootfs.squashfs + 替换 ==="
BASE=backup/rootfs.squashfs
OUT=/tmp/rootfs_v1629
rm -rf "$OUT"
unsquashfs -q -d "$OUT" "$BASE" >/dev/null 2>&1
cp ubuntu/build_v3s/dji_rc      "$OUT/usr/local/bin/dji_rc"
cp ubuntu/build_v3s/web_server  "$OUT/usr/local/bin/web_server"
cp "$USB"                        "$OUT/usr/local/bin/usb_tund"
cp ubuntu/scripts/setup_v3s.sh  "$OUT/usr/local/bin/setup_v3s.sh"
# S99 在 /etc/init.d/, 一并替换 (dji_rc 启动参数 144.11)
cp ubuntu/scripts/S99tun_nat_hub "$OUT/etc/init.d/S99tun_nat_hub"
chmod +x "$OUT/usr/local/bin/dji_rc" "$OUT/usr/local/bin/web_server" "$OUT/usr/local/bin/usb_tund" "$OUT/usr/local/bin/setup_v3s.sh" "$OUT/etc/init.d/S99tun_nat_hub"

# ── 打包 ──
echo ""
echo "=== 打包 rootfs_v1629 ==="
cd /tmp
rm -f rootfs_v1629.squashfs
mksquashfs "$OUT" rootfs_v1629.squashfs -comp xz -b 262144 -noappend >/dev/null 2>&1
cp rootfs_v1629.squashfs /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_v1629.squashfs
SIZE=$(stat -c%s /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_v1629.squashfs)
echo "rootfs_v1629: $SIZE bytes = $(echo "scale=2; $SIZE/1048576" | bc) MB"
echo "md5: $(md5sum /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_v1629.squashfs | cut -d' ' -f1)"

# ── 读回验证 ──
echo ""
echo "=== 读回验证 ==="
rm -rf /tmp/v1629_check
unsquashfs -q -d /tmp/v1629_check /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_v1629.squashfs >/dev/null 2>&1
echo "dji_rc:      $(md5sum /tmp/v1629_check/usr/local/bin/dji_rc | cut -d' ' -f1)"
echo "web_server:  $(md5sum /tmp/v1629_check/usr/local/bin/web_server | cut -d' ' -f1)"
echo "usb_tund:    $(md5sum /tmp/v1629_check/usr/local/bin/usb_tund | cut -d' ' -f1)"
echo "setup_v3s:   $(md5sum /tmp/v1629_check/usr/local/bin/setup_v3s.sh | cut -d' ' -f1)"
echo "S99 dji_rc:  $(grep -o 'rcmsg-host [0-9.]*' /tmp/v1629_check/etc/init.d/S99tun_nat_hub)"
echo "magic:       $(xxd -l 4 -p /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_v1629.squashfs)"
echo "DONE"
