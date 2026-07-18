#!/bin/sh
echo "=== V3s Upgrade ==="
cd /tmp
echo "[1/5] Downloading web_server..."
wget -q -O web_server_new http://192.168.144.88:8888/web_server_new
echo "[2/5] Installing..."
killall web_server 2>/dev/null; sleep 1
cp /tmp/web_server_new /usr/local/bin/web_server; chmod +x /usr/local/bin/web_server
echo "[3/5] Downloading rootfs..."
wget -q -O new_rootfs.sq http://192.168.144.88:8888/rootfs.squashfs
echo "[4/5] Flashing..."
dd if=/tmp/new_rootfs.sq of=/dev/mtd0 bs=4096 seek=1808 2>&1; sync
echo "[5/5] Verify..."
dd if=/dev/mtd0 bs=1 count=8 skip=7405568 2>/dev/null | hexdump -C
/usr/local/bin/web_server > /var/log/web_server.log 2>&1 &
echo "=== Done! Run: reboot ==="
