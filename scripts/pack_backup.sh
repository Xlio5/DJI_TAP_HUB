#!/bin/bash
set -e
DEST="/mnt/c/my_project/TUN_NAT_HUB/backup"
TMP=$(mktemp -d)

echo "=== TUN_NAT_HUB V3s 完整备份打包 ==="
echo ""

# 1. Kernel images
cp /home/xlong/v3s/linux/arch/arm/boot/zImage $TMP/zImage
cp /home/xlong/v3s/linux/arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb $TMP/sun8i-v3s-licheepi-zero-dock.dtb
echo "OK: zImage (5.7M), DTB (13K)"

# 2. APK
cp /mnt/c/my_project/TUN_NAT_HUB/android/app/build/outputs/apk/debug/app-debug.apk $TMP/app-debug.apk
echo "OK: app-debug.apk"

# 3. usb_tund binary
cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/build_v3s/usb_tund $TMP/usb_tund
file $TMP/usb_tund
echo "OK: usb_tund"

# 4. Scripts
cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/scripts/S99tun_nat_hub $TMP/S99tun_nat_hub
cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/scripts/setup_v3s.sh $TMP/setup_v3s.sh
cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/scripts/v3s_start.sh $TMP/v3s_start.sh
cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/web_panel.py $TMP/web_panel.py
echo "OK: scripts (S99tun_nat_hub, setup_v3s.sh, v3s_start.sh, web_panel.py)"

# 5. U-Boot env
cat > $TMP/uboot_env.txt << 'UBOOTEOF'
bootcmd=fatload mmc 0:1 0x41000000 zImage; fatload mmc 0:1 0x42000000 sun8i-v3s-licheepi-zero-dock.dtb; bootz 0x41000000 - 0x42000000
bootargs=console=ttyS0,115200 root=/dev/mmcblk0p2 rootwait g_serial.idVendor=0x0BDA g_serial.idProduct=0x8812 g_serial.use_acm=0
UBOOTEOF
echo "OK: uboot_env.txt"

# 6. Version info
cat > $TMP/VERSION.txt << VEREOF
TUN_NAT_HUB V3s v1.1.0
Build: $(date '+%Y-%m-%d %H:%M')
Kernel: 7.1.0 (Linux 6.6.18 headers, ARMv7 sun8i-v3s)
DTB: dr_mode=otg, USB peripheral via init script
Netfilter: iptables filter/nat/mangle built-in
USB: g_serial VID=0x0BDA PID=0x8812
Daemon: usb_tund v5 (ARMv7 ELF, 29K)
APK: app-debug.apk, hardware low-latency decoder fix
     selectCodec c2.qti.avc.decoder.low_latency
     RTP timestamp rebase fix (firstStampUs offset)
Init: BusyBox /etc/init.d/S99tun_nat_hub
VEREOF
echo "OK: VERSION.txt"

# 7. Pack
cd $TMP
tar czf "$DEST/tun_nat_hub_v3s_backup.tar.gz" .
echo ""
echo "=== Done ==="
ls -lh "$DEST/tun_nat_hub_v3s_backup.tar.gz"

# List contents
echo ""
echo "=== Contents ==="
tar tzf "$DEST/tun_nat_hub_v3s_backup.tar.gz"

rm -rf $TMP
