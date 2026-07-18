#!/bin/bash
set -e
PROJECT=/mnt/c/my_project/TUN_NAT_HUB
BUILDROOT=/home/xlong/v3s/buildroot-2024.02
NPROC=$(nproc)

echo "=== B1: Buildroot clean ==="
cd $BUILDROOT
make clean 2>&1 | tail -5

echo "=== B2: Overlay setup ==="
O=board/allwinner/v3s_overlay
mkdir -p $O/etc/init.d $O/usr/local/bin $O/var/log $O/root
cp $PROJECT/ubuntu/scripts/S99tun_nat_hub $O/etc/init.d/
cp $PROJECT/ubuntu/scripts/setup_v3s_fixed.sh $O/usr/local/bin/setup_v3s.sh
chmod +x $O/etc/init.d/S99tun_nat_hub $O/usr/local/bin/setup_v3s.sh
echo "Overlay: $(find $O -type f | wc -l) files"

echo "=== B3: Buildroot build ==="
make 2>&1 | tail -20

ROOTFS=$BUILDROOT/output/images/rootfs.squashfs
echo ""
echo "=== Buildroot done ==="
echo "rootfs: $(stat -c%s $ROOTFS) bytes"
cp $ROOTFS $PROJECT/backup/rootfs.squashfs_new
echo "rootfs copied to backup/"
echo "B-LINE COMPLETE"
