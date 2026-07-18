#!/bin/bash
set -e
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
TGT=/home/xlong/v3s/buildroot-2024.02/output/target
PROJECT=/mnt/c/my_project/TUN_NAT_HUB

echo "=== Fix scripts in target ==="
cp $PROJECT/ubuntu/scripts/S99tun_nat_hub $TGT/etc/init.d/
cp $PROJECT/ubuntu/scripts/setup_v3s_fixed.sh $TGT/usr/local/bin/setup_v3s.sh
chmod +x $TGT/etc/init.d/S99tun_nat_hub $TGT/usr/local/bin/setup_v3s.sh

echo "S99 mode lines: $(grep -c 'echo host\|echo peripheral' $TGT/etc/init.d/S99tun_nat_hub)"
echo "setup mode lines: $(grep -c 'echo host\|echo peripheral' $TGT/usr/local/bin/setup_v3s.sh)"

echo ""
echo "=== Regen squashfs ==="
cd /home/xlong/v3s/buildroot-2024.02
rm -f output/images/rootfs.squashfs
mksquashfs output/target output/images/rootfs.squashfs -comp xz -noappend 2>&1 | tail -3
echo "rootfs: $(stat -c%s output/images/rootfs.squashfs) bytes"

echo ""
echo "=== Rebuild SPI image ==="
cp output/images/rootfs.squashfs $PROJECT/backup/rootfs.squashfs
cd $PROJECT
python3 -B scripts/build_spi_final.py 2>&1 | tail -5

echo ""
echo "DONE"
ls -lh backup/spi_image.bin
