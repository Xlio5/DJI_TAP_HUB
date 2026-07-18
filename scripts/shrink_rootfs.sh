#!/bin/bash
set -e
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
cd /home/xlong/v3s/buildroot-2024.02

echo "=== Original squashfs ==="
ls -lh output/images/rootfs.squashfs

echo ""
echo "=== Trying max compression ==="
for bsize in 1048576 524288 262144 131072; do
  rm -f /tmp/test.sq
  mksquashfs output/target /tmp/test.sq -comp xz -b $bsize -Xdict-size $bsize -noappend 2>&1 | tail -1
  SZ=$(stat -c%s /tmp/test.sq)
  echo "  block=$bsize -> $SZ bytes ($((SZ/1024))KB)"
done

echo ""
echo "=== Best effort with XZ extreme ==="
rm -f /tmp/test2.sq
mksquashfs output/target /tmp/test2.sq -comp xz -b 1048576 -Xdict-size 1048576 -Xbcj arm -noappend 2>&1 | tail -3
SZ=$(stat -c%s /tmp/test2.sq)
echo "XZ-extreme+BCJ: $SZ bytes ($((SZ/1024))KB)"
echo "Fits in 4456448: $([ $SZ -le 4456448 ] && echo YES || echo NO)"
