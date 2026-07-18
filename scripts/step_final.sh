#!/bin/bash
set -e
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

echo "STEP 1: Verify target overlay"
cd /home/xlong/v3s/buildroot-2024.02
test -f output/target/etc/init.d/S99tun_nat_hub || { echo "S99 MISSING"; exit 1; }
test -f output/target/usr/local/bin/setup_v3s.sh || { echo "setup MISSING"; exit 1; }
test -f output/target/usr/local/bin/web_server || { echo "web_server MISSING"; exit 1; }
echo "  All overlay files present"

echo "STEP 2: Generate squashfs"
rm -f output/images/rootfs.squashfs
mksquashfs output/target output/images/rootfs.squashfs -comp xz -noappend > /dev/null 2>&1
SIZE=$(stat -c%s output/images/rootfs.squashfs)
echo "  rootfs: $SIZE bytes"

echo "STEP 3: Copy to project"
cp output/images/rootfs.squashfs /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs.squashfs
chmod 666 /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs.squashfs
echo "  Copied to backup/rootfs.squashfs"

echo "STEP 4: Verify squashfs integrity"
MAGIC=$(hexdump -n 4 -e '4/1 "%c"' output/images/rootfs.squashfs)
if [ "$MAGIC" = "hsqs" ]; then
  echo "  Magic OK: $MAGIC"
else
  echo "  Magic FAIL: $MAGIC"
  exit 1
fi

echo ""
echo "===== ALL DONE ====="
echo "rootfs: $SIZE bytes @ $(date)"
echo "Ready for SPI image assembly"
