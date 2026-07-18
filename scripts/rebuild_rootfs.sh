#!/bin/bash
set -e
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
PROJECT=/mnt/c/my_project/TUN_NAT_HUB
BUILDROOT=/home/xlong/v3s/buildroot-2024.02

echo "=== Step 1: Update overlay ==="
O=$BUILDROOT/board/allwinner/v3s_overlay
cp $PROJECT/ubuntu/scripts/S99tun_nat_hub $O/etc/init.d/
cp $PROJECT/ubuntu/scripts/setup_v3s_fixed.sh $O/usr/local/bin/setup_v3s.sh
chmod +x $O/etc/init.d/S99tun_nat_hub $O/usr/local/bin/setup_v3s.sh
echo "S99 has tmpfs: $(grep -c tmpfs $O/etc/init.d/S99tun_nat_hub)"
echo "Setup size: $(stat -c%s $O/usr/local/bin/setup_v3s.sh) bytes"

echo ""
echo "=== Step 2: Generate squashfs ==="
cd $BUILDROOT
rm -f output/images/rootfs.squashfs
mksquashfs output/target output/images/rootfs.squashfs -comp xz -noappend
SIZE=$(stat -c%s output/images/rootfs.squashfs)
echo "rootfs: $SIZE bytes, magic: $(hexdump -n 4 -e '4/1 "%c"' output/images/rootfs.squashfs)"
cp output/images/rootfs.squashfs $PROJECT/backup/rootfs.squashfs
echo "Copied to backup/"

echo ""
echo "=== Step 3: Build SPI image ==="
cd $PROJECT
python3 -B scripts/build_spi_final.py

echo ""
echo "=== DONE ==="
echo "rootfs: $SIZE bytes ($(date))"
