#!/bin/bash
set -e
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
PROJECT=/mnt/c/my_project/TUN_NAT_HUB
CPP=$PROJECT/ubuntu/src/web_server.cpp
TGT=/home/xlong/v3s/buildroot-2024.02/output/target

sed -i 's|"1.3.1"|"1.4.0"|' $CPP
arm-linux-gnueabihf-g++ -std=c++17 -Os -o /tmp/ws140 $CPP -lpthread 2>&1 | tail -2
echo "web_server: $(stat -c%s /tmp/ws140) bytes"
strings /tmp/ws140 | grep "version.*1.4" | head -1

cp /tmp/ws140 $TGT/usr/local/bin/web_server
chmod +x $TGT/usr/local/bin/web_server

cd /home/xlong/v3s/buildroot-2024.02
mksquashfs output/target $PROJECT/backup/rootfs_v140.squashfs -comp xz -b 1048576 -Xdict-size 1048576 -noappend 2>&1 | tail -3
echo "rootfs_v140: $(stat -c%s $PROJECT/backup/rootfs_v140.squashfs) bytes"

sed -i 's|"1.4.0"|"1.3.1"|' $CPP
echo "DONE"
