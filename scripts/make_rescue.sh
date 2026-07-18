#!/bin/bash
set -e

PROJECT=/mnt/c/my_project/TUN_NAT_HUB
RESCUE_DIR=/tmp/rescue_build_$$

echo "=== Building rescue v5 in $RESCUE_DIR ==="
rm -rf "$RESCUE_DIR"
mkdir -p "$RESCUE_DIR/bin" "$RESCUE_DIR/dev" "$RESCUE_DIR/proc" "$RESCUE_DIR/sys" "$RESCUE_DIR/tmp" "$RESCUE_DIR/mnt"

cp "$PROJECT/backup/busybox_static" "$RESCUE_DIR/bin/busybox"
chmod +x "$RESCUE_DIR/bin/busybox"

cd "$RESCUE_DIR/bin"
for cmd in sh mount ls cat dd echo sleep mknod mkdir hexdump sync umount; do
  ln -sf busybox $cmd
done
cd /

echo "=== Busybox check ==="
file "$RESCUE_DIR/bin/busybox"

cat > "$RESCUE_DIR/init" << 'INITEOF'
#!/bin/sh
export PATH=/bin
mount -t proc proc /proc
mount -t devtmpfs devtmpfs /dev
mount -t sysfs sysfs /sys

echo "============================================"
echo "  TUN_NAT_HUB SPI Rescue v5"
echo "============================================"

echo "[1/3] Mount SD..."
mkdir -p /mnt/sd
for i in 1 2 3 4 5 6 7 8 9 10; do
  sleep 1
  mount /dev/mmcblk0p1 /mnt/sd 2>/dev/null && break
  mount /dev/mmcblk1p1 /mnt/sd 2>/dev/null && break
  echo "  retry $i/10..."
done

echo "[2/3] Flash SPI (full image)..."
dd if=/mnt/sd/spi_image.bin of=/dev/mtd0 bs=4096
sync

echo "[3/3] Verify:"
hexdump -C -n 32 /dev/mtd0
dd if=/dev/mtd0 bs=4096 skip=1808 count=1 2>/dev/null | hexdump -C -n 16

umount /mnt/sd 2>/dev/null
echo ""
echo "============================================"
echo "  DONE. Power off, remove SD, power on."
echo "============================================"
exec /bin/sh
INITEOF
chmod +x "$RESCUE_DIR/init"

cd "$RESCUE_DIR"
OUTFILE="$PROJECT/backup/rescue.cpio.gz"
echo "=== Building cpio.gz -> $OUTFILE ==="
find . | cpio -o -H newc 2>/dev/null | gzip > "$OUTFILE"
ls -lh "$OUTFILE"
echo "Rescue v5: $OUTFILE"
echo "=== Done ==="
