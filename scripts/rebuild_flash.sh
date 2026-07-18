#!/bin/bash
set -e
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
PROJECT=/mnt/c/my_project/TUN_NAT_HUB
TGT=/home/xlong/v3s/buildroot-2024.02/output/target

echo "=== Compile web_server ==="
arm-linux-gnueabihf-g++ -std=c++17 -Os -o /tmp/wstest $PROJECT/ubuntu/src/web_server.cpp -lpthread 2>&1 | tail -2
FC004=$(strings /tmp/wstest | grep -c 0xFC004)
BUF2=$(strings /tmp/wstest | grep -c 'buf\[2\]')
echo "0xFC004 refs: $FC004"
echo "buf[2] refs: $BUF2"
if [ "$FC004" -lt 1 ] || [ "$BUF2" -lt 1 ]; then
    echo "ERROR: web_server missing confirmed/retry code!"
    exit 1
fi

cp /tmp/wstest $TGT/usr/local/bin/web_server
chmod +x $TGT/usr/local/bin/web_server

cp $PROJECT/ubuntu/scripts/S99tun_nat_hub $TGT/etc/init.d/
cp $PROJECT/ubuntu/scripts/setup_v3s_fixed.sh $TGT/usr/local/bin/setup_v3s.sh
chmod +x $TGT/etc/init.d/S99tun_nat_hub $TGT/usr/local/bin/setup_v3s.sh

echo "=== Build rootfs ==="
cd /home/xlong/v3s/buildroot-2024.02
rm -f output/images/rootfs.squashfs
mksquashfs output/target output/images/rootfs.squashfs -comp xz -b 1048576 -Xdict-size 1048576 -noappend | tail -3
cp output/images/rootfs.squashfs $PROJECT/backup/rootfs.squashfs

echo "=== Build SPI image ==="
cd $PROJECT
python3 -B scripts/build_spi_final.py | tail -5

echo "=== FEL flash ==="
sunxi-fel spiflash-write 0 backup/spi_image.bin
echo "EXIT=$?"
sunxi-fel spiflash-read 0 32 /tmp/v9f.bin
hexdump -C /tmp/v9f.bin
echo "DONE"
