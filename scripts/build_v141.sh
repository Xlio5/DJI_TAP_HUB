#!/bin/bash
set -e
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
PROJECT=/mnt/c/my_project/TUN_NAT_HUB
NCPU=20
echo "=== FULL CLEAN BUILD v1.4.1 ==="

python3 -c "
cpp = open('$PROJECT/ubuntu/src/web_server.cpp').read()
old = '<pre class=\"code-block\" id=\"net-info\"></pre>'
new_card = '<pre class=\"code-block\" id=\"net-info\"></pre></div>\n      <div class=\"grid2\" style=\"margin-top:16px\">\n        <div class=\"card\"><h3>System</h3><pre class=\"code-block\" id=\"sys-info\">loading...</pre></div>\n        <div class=\"card\"><h3>iptables</h3><pre class=\"code-block\" id=\"ipt-info\" style=\"max-height:200px\"></pre></div>'
cpp = cpp.replace(old, new_card)
open('$PROJECT/ubuntu/src/web_server.cpp','w').write(cpp)
print('sys-info card added')
"

cd /home/xlong/v3s/u-boot
chown -R xlong:xlong . 2>/dev/null || true
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- clean | tail -3
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j$NCPU | tail -5
cp spl/sunxi-spl.bin u-boot.bin $PROJECT/backup/

cd /home/xlong/v3s/linux
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- clean | tail -3
sed -i 's/CONFIG_USB_G_SERIAL=m/CONFIG_USB_G_SERIAL=y/' .config
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j$NCPU zImage dtbs | tail -5
cp arch/arm/boot/zImage $PROJECT/backup/zImage_new
cp arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb $PROJECT/backup/sun8i-v3s-licheepi-zero-dock.dtb_new

cd /home/xlong/v3s/buildroot-2024.02
chown -R xlong:xlong output/target 2>/dev/null || true
O=board/allwinner/v3s_overlay
mkdir -p $O/etc/init.d $O/usr/local/bin $O/var/log $O/root
cp $PROJECT/ubuntu/scripts/S99tun_nat_hub $O/etc/init.d/
cp $PROJECT/ubuntu/scripts/setup_v3s_fixed.sh $O/usr/local/bin/setup_v3s.sh
chmod +x $O/etc/init.d/S99tun_nat_hub $O/usr/local/bin/setup_v3s.sh
make clean | tail -3
make | tail -20
arm-linux-gnueabihf-g++ -std=c++17 -Os -o output/target/usr/local/bin/web_server $PROJECT/ubuntu/src/web_server.cpp -lpthread | tail -2
chmod +x output/target/usr/local/bin/web_server
cp $PROJECT/ubuntu/scripts/S99tun_nat_hub output/target/etc/init.d/
cp $PROJECT/ubuntu/scripts/setup_v3s_fixed.sh output/target/usr/local/bin/setup_v3s.sh
chmod +x output/target/etc/init.d/S99tun_nat_hub output/target/usr/local/bin/setup_v3s.sh
rm -f output/images/rootfs.squashfs
mksquashfs output/target output/images/rootfs.squashfs -comp xz -b 1048576 -Xdict-size 1048576 -noappend | tail -3
python3 -c "
import zlib, struct
data = open('output/images/rootfs.squashfs','rb').read()
crc = zlib.crc32(data) & 0xFFFFFFFF
open('output/images/rootfs.squashfs','ab').write(b'TUN_NAT_HUB' + struct.pack('<I', crc))
"
cp output/images/rootfs.squashfs $PROJECT/backup/rootfs.squashfs

cd $PROJECT
python3 -B scripts/build_spi_final.py | tail -8
echo "=== DONE ==="
ls -lh backup/sunxi-spl.bin backup/u-boot.bin backup/zImage_new backup/rootfs.squashfs backup/spi_image.bin
