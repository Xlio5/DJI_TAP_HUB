"""Rebuild squashfs with fixed S99 + g_serial.ko"""
import subprocess, os, time

script = r"""
#!/bin/bash
set -e

# Extract rootfs
rm -rf /tmp/sq_final
mkdir -p /tmp/sq_final/usr/local/bin /tmp/sq_final/etc/init.d /tmp/sq_final/lib/modules/7.1.0
tar xf /home/xlong/v3s/buildroot-2024.02/output/images/rootfs.tar -C /tmp/sq_final/

# Copy TUN_NAT_HUB binaries
cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/build_v3s/web_server /tmp/sq_final/usr/local/bin/
cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/build_v3s/usb_tund /tmp/sq_final/usr/local/bin/
chmod +x /tmp/sq_final/usr/local/bin/web_server /tmp/sq_final/usr/local/bin/usb_tund

# Copy g_serial module
cp /home/xlong/v3s/linux/drivers/usb/gadget/legacy/g_serial.ko /tmp/sq_final/lib/modules/7.1.0/

# Copy fixed init and setup scripts
cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/scripts/S99tun_nat_hub_final /tmp/sq_final/etc/init.d/S99tun_nat_hub
cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/scripts/setup_v3s_fixed.sh /tmp/sq_final/usr/local/bin/setup_v3s.sh
chmod +x /tmp/sq_final/etc/init.d/S99tun_nat_hub /tmp/sq_final/usr/local/bin/setup_v3s.sh

# Remove python3
rm -rf /tmp/sq_final/usr/lib/python3* 2>/dev/null || true

# Depmod
cd /tmp/sq_final
depmod -b . 7.1.0 2>/dev/null || true

echo "Building squashfs..."
mksquashfs /tmp/sq_final /tmp/rootfs_final.squashfs -comp xz -b 128K -noappend 2>&1 | tail -3

ls -lh /tmp/rootfs_final.squashfs
cp /tmp/rootfs_final.squashfs /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs.squashfs
echo "SQUASHFS_DONE"
"""

# Write script to WSL temp file via stdin pipe
result = subprocess.run(
    ["wsl", "-u", "root", "-e", "bash", "-c", "cat > /tmp/build_sq.sh && bash /tmp/build_sq.sh"],
    input=script.encode(), capture_output=True, timeout=120
)
stdout_text = result.stdout.decode(errors="replace") if result.stdout else ""
stderr_text = result.stderr.decode(errors="replace") if result.stderr else ""
print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr[:300])
print(f"Exit: {result.returncode}")

# Verify local copy
sq_path = r"c:\my_project\TUN_NAT_HUB\backup\rootfs.squashfs"
if os.path.exists(sq_path):
    print(f"Local squashfs: {os.path.getsize(sq_path)} bytes")

# Also rebuild SPI image
print("\n=== Rebuilding SPI image ===")
r2 = subprocess.run(
    ["wsl", "-u", "root", "-e", "bash", "-c",
     "python3 /mnt/c/my_project/TUN_NAT_HUB/scripts/build_spi_final.py"],
    capture_output=True, text=True, timeout=30
)
print(r2.stdout[-500:] if len(r2.stdout) > 500 else r2.stdout)
