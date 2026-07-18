#!/bin/bash
set -e
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
TGT=/home/xlong/v3s/buildroot-2024.02/output/target
PROJECT=/mnt/c/my_project/TUN_NAT_HUB

echo "=== Copy timestamp scripts ==="
cp $PROJECT/ubuntu/scripts/S99tun_nat_hub $TGT/etc/init.d/
cp $PROJECT/ubuntu/scripts/setup_v3s_fixed.sh $TGT/usr/local/bin/setup_v3s.sh
chmod +x $TGT/etc/init.d/S99tun_nat_hub $TGT/usr/local/bin/setup_v3s.sh
echo "S99 has _ts: $(grep -c '_ts' $TGT/etc/init.d/S99tun_nat_hub)"
echo "setup has _ts: $(grep -c '_ts' $TGT/usr/local/bin/setup_v3s.sh)"

echo ""
echo "=== Regen rootfs ==="
cd /home/xlong/v3s/buildroot-2024.02
rm -f output/images/rootfs.squashfs
mksquashfs output/target output/images/rootfs.squashfs -comp xz -noappend 2>&1 | tail -3

cp output/images/rootfs.squashfs $PROJECT/backup/rootfs.squashfs
echo "rootfs: $(stat -c%s $PROJECT/backup/rootfs.squashfs) bytes"

echo ""
echo "=== Build SPI image ==="
cd $PROJECT
python3 -B scripts/build_spi_final.py 2>&1 | tail -5
echo "DONE"
ls -lh backup/spi_image.bin
