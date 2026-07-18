#!/bin/bash
set -e
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
PROJECT=/mnt/c/my_project/TUN_NAT_HUB
TGT=/home/xlong/v3s/buildroot-2024.02/output/target

echo "=== Compile web_server ==="
arm-linux-gnueabihf-g++ -std=c++17 -Os -o $TGT/usr/local/bin/web_server $PROJECT/ubuntu/src/web_server.cpp -lpthread 2>&1 | tail -2
chmod +x $TGT/usr/local/bin/web_server

WS=$TGT/usr/local/bin/web_server
echo "mtdblock4: $(strings $WS | grep -c mtdblock4)"
echo "/dev/mtdblock0: $(strings $WS | grep -c /dev/mtdblock0)"
echo "Flashed to: $(strings $WS | grep -c 'Flashed to')"

echo "=== Copy init scripts ==="
cp $PROJECT/ubuntu/scripts/S99tun_nat_hub $TGT/etc/init.d/
cp $PROJECT/ubuntu/scripts/setup_v3s_fixed.sh $TGT/usr/local/bin/setup_v3s.sh
chmod +x $TGT/etc/init.d/S99tun_nat_hub $TGT/usr/local/bin/setup_v3s.sh

echo "=== Build rootfs ==="
cd /home/xlong/v3s/buildroot-2024.02
rm -f output/images/rootfs.squashfs
mksquashfs output/target output/images/rootfs.squashfs -comp xz -b 1048576 -Xdict-size 1048576 -noappend | tail -3
cp output/images/rootfs.squashfs $PROJECT/backup/rootfs.squashfs
echo "rootfs: $(stat -c%s $PROJECT/backup/rootfs.squashfs) bytes"

echo "=== Build SPI image ==="
cd $PROJECT
python3 -B scripts/build_spi_final.py | tail -5
echo "spi_image: $(stat -c%s backup/spi_image.bin) bytes"
echo "DONE"
