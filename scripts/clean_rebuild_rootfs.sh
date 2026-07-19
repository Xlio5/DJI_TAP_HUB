#!/bin/bash
set -e
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
PROJECT=/mnt/c/my_project/TUN_NAT_HUB

echo "=== Clean rebuild rootfs (fix SQUASHFS corruption) ==="

cd /home/xlong/v3s/buildroot-2024.02

# Setup overlay with latest scripts
O=board/allwinner/v3s_overlay
mkdir -p $O/etc/init.d $O/usr/local/bin $O/var/log $O/root
cp $PROJECT/ubuntu/scripts/S99tun_nat_hub $O/etc/init.d/
cp $PROJECT/ubuntu/scripts/setup_v3s_fixed.sh $O/usr/local/bin/setup_v3s.sh
chmod +x $O/etc/init.d/S99tun_nat_hub $O/usr/local/bin/setup_v3s.sh

echo "=== Buildroot make (overlay handles web_server) ==="
make 2>&1 | tail -20

echo "=== Generate clean squashfs ==="
rm -f output/images/rootfs.squashfs
mksquashfs output/target output/images/rootfs.squashfs -comp xz -b 1048576 -Xdict-size 1048576 -noappend | tail -3

# Add 12B verification tail
python3 -c "
import zlib, struct
data = open('output/images/rootfs.squashfs','rb').read()
crc = zlib.crc32(data) & 0xFFFFFFFF
open('output/images/rootfs.squashfs','ab').write(b'TUN_NAT_HUB' + struct.pack('<I', crc))
print('rootfs: %d bytes, CRC=0x%08X' % (len(data)+12, crc))
"

cp output/images/rootfs.squashfs $PROJECT/backup/rootfs.squashfs

echo "=== Build SPI image ==="
cd $PROJECT
python3 -B scripts/build_spi_final.py | tail -6

echo ""
echo "=== DONE ==="
ls -lh backup/rootfs.squashfs backup/spi_image.bin
