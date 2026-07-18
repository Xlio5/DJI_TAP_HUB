#!/bin/bash
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
cd /home/xlong/v3s/buildroot-2024.02
rm -f output/images/rootfs.squashfs
mksquashfs output/target output/images/rootfs.squashfs -comp xz -noappend 2>&1 | tail -5
rm -rf /tmp/fv
mkdir /tmp/fv
unsquashfs -d /tmp/fv output/images/rootfs.squashfs 2>&1 | tail -3

echo "=== S99 ==="
if [ -f /tmp/fv/etc/init.d/S99tun_nat_hub ]; then echo "OK"; else echo "MISSING"; fi

echo "=== setup_v3s ==="
if [ -f /tmp/fv/usr/local/bin/setup_v3s.sh ]; then echo "OK"; else echo "MISSING"; fi

echo "=== web_server ==="
if [ -f /tmp/fv/usr/local/bin/web_server ]; then
  echo "OK ($(stat -c%s /tmp/fv/usr/local/bin/web_server) bytes)"
else
  echo "MISSING"
fi

echo "=== usb_tund ==="
if [ -f /tmp/fv/usr/local/bin/usb_tund ]; then echo "OK"; else echo "MISSING"; fi

cp output/images/rootfs.squashfs /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs.squashfs_new
echo "copied to backup"
