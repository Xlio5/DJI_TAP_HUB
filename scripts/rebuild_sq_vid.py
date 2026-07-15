#!/usr/bin/env python3
"""Rebuild squashfs with g_serial.ko for correct VID/PID"""
import subprocess, os, time

print("=== Step 1: Rebuild squashfs with g_serial module ===")

script = r"""
rm -rf /tmp/sq_vid
mkdir -p /tmp/sq_vid/usr/local/bin /tmp/sq_vid/etc/init.d /tmp/sq_vid/lib/modules/7.1.0
tar xf /home/xlong/v3s/buildroot-2024.02/output/images/rootfs.tar -C /tmp/sq_vid/

# Copy TUN_NAT_HUB binaries
cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/build_v3s/web_server /tmp/sq_vid/usr/local/bin/
cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/build_v3s/usb_tund /tmp/sq_vid/usr/local/bin/
chmod +x /tmp/sq_vid/usr/local/bin/web_server /tmp/sq_vid/usr/local/bin/usb_tund

# Copy g_serial module
cp /home/xlong/v3s/linux/drivers/usb/gadget/legacy/g_serial.ko /tmp/sq_vid/lib/modules/7.1.0/
cp /home/xlong/v3s/linux/drivers/usb/gadget/function/usb_f_obex.ko /tmp/sq_vid/lib/modules/7.1.0/ 2>/dev/null || true

# Run depmod
cd /tmp/sq_vid
depmod -b . 7.1.0 2>/dev/null || true

# Copy S99 and setup scripts
cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/scripts/S99tun_nat_hub_clean /tmp/sq_vid/etc/init.d/S99tun_nat_hub
cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/scripts/setup_v3s_fixed.sh /tmp/sq_vid/usr/local/bin/setup_v3s.sh
chmod +x /tmp/sq_vid/etc/init.d/S99tun_nat_hub /tmp/sq_vid/usr/local/bin/setup_v3s.sh

# Remove python3
rm -rf /tmp/sq_vid/usr/lib/python3* 2>/dev/null || true

echo "Building squashfs..."
ls -la /tmp/sq_vid/lib/modules/7.1.0/g_serial.ko
mksquashfs /tmp/sq_vid /tmp/rootfs_vid.squashfs -comp xz -b 128K -noappend 2>&1 | tail -5
ls -lh /tmp/rootfs_vid.squashfs
cp /tmp/rootfs_vid.squashfs /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs.squashfs
echo "SQUASHFS_READY"
"""

result = subprocess.run(["wsl", "-u", "root", "-e", "bash", "-c", script],
                       capture_output=True, text=True, timeout=120)
print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr[:300])
print(f"Exit: {result.returncode}")

# Verify the local file
sq_path = r"c:\my_project\TUN_NAT_HUB\backup\rootfs.squashfs"
if os.path.exists(sq_path):
    print(f"Local squashfs: {os.path.getsize(sq_path)} bytes")
else:
    print("Squashfs not found locally!")
