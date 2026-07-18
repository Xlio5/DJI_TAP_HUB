#!/bin/bash
set -e
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
PROJECT=/mnt/c/my_project/TUN_NAT_HUB
BUILDROOT=/home/xlong/v3s/buildroot-2024.02

echo "=== Copy fixed scripts to overlay ==="
O=$BUILDROOT/board/allwinner/v3s_overlay
mkdir -p $O/etc/init.d $O/usr/local/bin
cp $PROJECT/ubuntu/scripts/S99tun_nat_hub $O/etc/init.d/
cp $PROJECT/ubuntu/scripts/setup_v3s_fixed.sh $O/usr/local/bin/setup_v3s.sh
chmod +x $O/etc/init.d/S99tun_nat_hub $O/usr/local/bin/setup_v3s.sh

echo "S99 has peripheral lines: $(grep -c 'peripheral' $O/etc/init.d/S99tun_nat_hub)"
echo "setup_v3s has mode switch lines: $(grep -c 'host.*MODE\|echo host\|echo peripheral\|sleep.*3' $O/usr/local/bin/setup_v3s.sh)"

echo ""
echo "=== Generate squashfs ==="
cd $BUILDROOT
rm -f output/images/rootfs.squashfs
mksquashfs output/target output/images/rootfs.squashfs -comp xz -noappend 2>&1 | tail -3
echo "rootfs: $(stat -c%s output/images/rootfs.squashfs) bytes"

echo ""
echo "=== Copy to backup ==="
cp output/images/rootfs.squashfs $PROJECT/backup/rootfs.squashfs

echo ""
echo "=== Build SPI image ==="
cd $PROJECT
python3 -B scripts/build_spi_final.py 2>&1 | tail -8
echo ""
echo "DONE"
ls -lh backup/spi_image.bin
