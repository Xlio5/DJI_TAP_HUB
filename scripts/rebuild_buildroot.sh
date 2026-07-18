#!/bin/bash
set -e
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
cd /home/xlong/v3s/buildroot-2024.02

echo "=== Step 1: Fix ownership ==="
chown -R xlong:xlong output/target 2>/dev/null || true
echo "Done"

echo ""
echo "=== Step 2: Update overlay ==="
O=board/allwinner/v3s_overlay
mkdir -p $O/etc/init.d $O/usr/local/bin $O/var/log $O/root
cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/scripts/S99tun_nat_hub $O/etc/init.d/
cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/scripts/setup_v3s_fixed.sh $O/usr/local/bin/setup_v3s.sh
chmod +x $O/etc/init.d/S99tun_nat_hub $O/usr/local/bin/setup_v3s.sh
TMPFS_COUNT=$(grep -c tmpfs $O/etc/init.d/S99tun_nat_hub)
echo "S99 has tmpfs: $TMPFS_COUNT (expect 3)"

# Enable overlay in config
sed -i 's|BR2_ROOTFS_OVERLAY=""|BR2_ROOTFS_OVERLAY="board/allwinner/v3s_overlay"|' .config
grep BR2_ROOTFS_OVERLAY .config

echo ""
echo "=== Step 3: make clean ==="
make clean 2>&1 | tail -5
echo "Clean exit: $?"

echo ""
echo "=== Step 4: olddefconfig ==="
make olddefconfig 2>&1 | tail -3

echo ""
echo "=== Step 5: make ==="
make 2>&1 | tail -30
echo "Make exit: $?"

echo ""
echo "=== Step 6: Verify output ==="
if [ -f output/images/rootfs.squashfs ]; then
    SIZE=$(stat -c%s output/images/rootfs.squashfs)
    MAGIC=$(hexdump -n 4 -e '4/1 "%c"' output/images/rootfs.squashfs)
    echo "rootfs: $SIZE bytes, magic: $MAGIC"

    # Extract and verify S99 has tmpfs
    rm -rf /tmp/rfs_check
    mkdir /tmp/rfs_check
    unsquashfs -d /tmp/rfs_check output/images/rootfs.squashfs 2>&1 | tail -3
    echo "S99 in rootfs:"
    ls -l /tmp/rfs_check/etc/init.d/S99tun_nat_hub 2>/dev/null && echo "  EXISTS" || echo "  MISSING!"
    echo "tmpfs in rootfs S99:"
    grep -c tmpfs /tmp/rfs_check/etc/init.d/S99tun_nat_hub 2>/dev/null || echo "  0"

    # Copy to project
    cp output/images/rootfs.squashfs /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs.squashfs
    cp output/images/rootfs.squashfs /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs.squashfs_new
    echo "Copied to backup/"
else
    echo "ERROR: rootfs.squashfs not found!"
    exit 1
fi

echo ""
echo "=== DONE ==="
