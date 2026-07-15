#!/usr/bin/env python3
"""
V3s 完整修复脚本
1. 从 SD 卡启动 Linux
2. 上传并擦写 SPI rootfs 分区
3. 验证 NAT/USB/daemon 自动启动
"""
import serial, time, paramiko, os, sys, struct, binascii

SERIAL_PORT = "COM10"
SQ_FILE = r"c:\my_project\TUN_NAT_HUB\backup\rootfs.squashfs"

# ============================================================
# Step 1: SD 卡启动
# ============================================================
print("=" * 60)
print("Step 1: Boot from SD card")
print("=" * 60)

ser = serial.Serial(SERIAL_PORT, 115200, timeout=0.5)
time.sleep(0.3)
ser.read(ser.in_waiting)

# Send enter to get U-Boot prompt
ser.write(b"\r\n")
time.sleep(0.5)
out = ser.read(ser.in_waiting).decode(errors="replace")

if "=>" not in out:
    # Might be at login already
    ser.write(b"\r\n")
    time.sleep(0.5)
    out = ser.read(ser.in_waiting).decode(errors="replace")

if "=>" in out:
    print("In U-Boot, loading from SD...")

    cmds = [
        ("zImage", "fatload mmc 0:1 0x41000000 zImage", 3),
        ("DTB", "fatload mmc 0:1 0x42000000 sun8i-v3s-licheepi-zero-dock.dtb", 1),
        ("bootargs", "setenv bootargs console=ttyS0,115200 root=/dev/mmcblk0p2 rootfstype=squashfs rootwait", 0.5),
        ("bootz", "bootz 0x41000000 - 0x42000000", 2),
    ]
    for label, cmd, wait in cmds:
        ser.write((cmd + "\r\n").encode())
        time.sleep(wait)
        out = ser.read(ser.in_waiting).decode(errors="replace")
        print(f"  {label}: {'OK' if 'bytes read' in out or 'Starting kernel' in out else out.strip()[-50:]}")

    # Wait for kernel
    time.sleep(15)
    out = ser.read(ser.in_waiting).decode(errors="replace")
    if "login:" not in out:
        print("ERROR: Did not reach login prompt!")
        print(out[-300:] if len(out) > 300 else out)
        ser.close()
        sys.exit(1)
    print("Reached login prompt")

# ============================================================
# Step 2: Login + set IP
# ============================================================
print("\n" + "=" * 60)
print("Step 2: Login and network setup")
print("=" * 60)

ser.write(b"root\r\n")
time.sleep(1.5)
out = ser.read(ser.in_waiting).decode(errors="replace")
if "Password" in out:
    ser.write(b"root\r\n")
    time.sleep(1)
    ser.read(ser.in_waiting)

ser.write(b"ip addr add 192.168.144.66/24 dev eth0 2>/dev/null; ip link set eth0 up; echo OK\r\n")
time.sleep(1)
out = ser.read(ser.in_waiting).decode(errors="replace")
if "OK" not in out:
    print("ERROR: Failed to set IP!")
    ser.close()
    sys.exit(1)
print("Network OK")
ser.close()

# ============================================================
# Step 3: Upload + flash squashfs via mtd0 raw offset
# ============================================================
print("\n" + "=" * 60)
print("Step 3: Flash squashfs to SPI (raw mtd0)")
print("=" * 60)

with open(SQ_FILE, "rb") as f:
    sq_data = f.read()
print(f"Squashfs: {len(sq_data)} bytes ({len(sq_data)/1024/1024:.1f}MB)")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("192.168.144.66", username="root", password="root", timeout=10)
print("SSH connected")

# Upload
chan = ssh.get_transport().open_session()
chan.exec_command("cat > /tmp/rootsq && echo UP_OK")
time.sleep(0.2)
for i in range(0, len(sq_data), 65536):
    chan.sendall(sq_data[i:i+65536])
chan.shutdown_write()
time.sleep(2)
result = chan.recv(4096).decode()
chan.close()
print("Upload:", "OK" if "UP_OK" in result else "FAIL")

# Verify upload
_, o, _ = ssh.exec_command("wc -c /tmp/rootsq", timeout=5)
sz = o.read().decode().strip()
print(f"Uploaded size: {sz}")
if str(len(sq_data)) not in sz:
    print("SIZE MISMATCH!")
    ssh.close()
    sys.exit(1)

# ============================================================
# Step 4: ERASE rootfs area of SPI NOR, then write
# Write via mtdchar device with seek (bypasses mtdblock issue)
# ============================================================
print("\n" + "=" * 60)
print("Step 4: Erase + write SPI rootfs partition")
print("=" * 60)

# rootfs partition: mtd3, starts at 0x710000, size 0x8F0000
# mtdchar device supports seek

# First erase by writing zeros to rootfs area
ROOTFS_OFFSET_KB = 0x710000 // 1024  # = 7232
ROOTFS_SIZE_KB = 0x8F0000 // 1024   # = 9152
SQ_SIZE_KB = (len(sq_data) + 1023) // 1024

print(f"Erasing {ROOTFS_SIZE_KB}KB at offset {ROOTFS_OFFSET_KB}KB...")
_, o, e = ssh.exec_command(
    f"dd if=/dev/zero of=/dev/mtd0 bs=1024 seek={ROOTFS_OFFSET_KB} count={ROOTFS_SIZE_KB} 2>&1; echo ERASE_DONE",
    timeout=120
)
out = o.read().decode()
err = e.read().decode()
if err:
    print("Erase warning:", err[:100])

print(f"Writing {len(sq_data)} bytes squashfs...")
_, o, e = ssh.exec_command(
    f"dd if=/tmp/rootsq of=/dev/mtd0 bs=1024 seek={ROOTFS_OFFSET_KB} 2>&1; echo WRITE_DONE",
    timeout=60
)
out = o.read().decode()
err = e.read().decode()
print(out.strip()[-100:])
if err and "WRITE_DONE" not in out:
    print("Write error:", err[:100])

# ============================================================
# Step 5: Verify squashfs magic on SPI
# ============================================================
print("\n" + "=" * 60)
print("Step 5: Verify SPI rootfs content")
print("=" * 60)

_, o, e = ssh.exec_command("hexdump -C -n 32 /dev/mtdblock3 2>&1 | head -4", timeout=5)
verify = o.read().decode().strip()
print(verify)

if "hsqsk" not in verify:
    print("WARNING: squashfs magic not found on mtdblock3!")
    # Try raw mtd0 read
    _, o, _ = ssh.exec_command(
        "dd if=/dev/mtd0 bs=1 skip=$((0x710000)) count=16 2>/dev/null | od -A x -t x1z",
        timeout=5
    )
    print("Raw mtd0 check:", o.read().decode().strip())
else:
    print("Squashfs verified OK!")

# ============================================================
# Step 6: Verify setup_v3s.sh is the fixed version
# ============================================================
print("\n" + "=" * 60)
print("Step 6: Verify setup_v3s.sh with fixes")
print("=" * 60)

# Mount squashfs from SPI and check the script
_, o, e = ssh.exec_command(
    "mkdir -p /tmp/sq_mnt 2>/dev/null; "
    "mount -t squashfs /dev/mtdblock3 /tmp/sq_mnt 2>&1; "
    "grep -c 'Waiting for DHCP' /tmp/sq_mnt/usr/local/bin/setup_v3s.sh 2>/dev/null || echo 'NOT_FOUND'; "
    "grep -c 'default via' /tmp/sq_mnt/usr/local/bin/setup_v3s.sh 2>/dev/null || echo 'NOT_FOUND'; "
    "grep -c 'echo peripheral' /tmp/sq_mnt/usr/local/bin/setup_v3s.sh 2>/dev/null || echo 'NOT_FOUND'; "
    "umount /tmp/sq_mnt 2>/dev/null",
    timeout=10
)
out = o.read().decode().strip()
print("setup_v3s.sh checks (DHCP_wait/GW/USB_mode):", out)

# ============================================================
# Step 7: Reboot pure SPI test
# ============================================================
print("\n" + "=" * 60)
print("Step 7: Reboot to test pure SPI boot")
print("=" * 60)

print("Removing SD card and rebooting...")
_, o, e = ssh.exec_command("reboot -f", timeout=5)
ssh.close()

# Wait and read boot log
ser2 = serial.Serial(SERIAL_PORT, 115200, timeout=1)
time.sleep(8)
boot_log = ser2.read(ser2.in_waiting).decode(errors="replace")

# Check key success indicators
checks = {
    "SPL SPI boot": "Trying to boot from sunxi SPI",
    "Kernel started": "Starting kernel",
    "squashfs root": "Mounted root (squashfs filesystem)",
    "DHCP wait": "Waiting for DHCP",
    "TUN created": "TUN: 10.0.0.1",
    "NAT configured": "MASQUERADE",
    "USB peripheral": "USB: peripheral mode",
    "login prompt": "login:",
}

print("\nSPI Boot Results:")
for label, pattern in checks.items():
    found = pattern in boot_log
    print(f"  {'✅' if found else '❌'} {label}")

# Try to login and verify
if "login:" in boot_log:
    ser2.write(b"root\r\n")
    time.sleep(1.5)
    out = ser2.read(ser2.in_waiting).decode(errors="replace")
    if "Password" in out:
        ser2.write(b"root\r\n")
        time.sleep(1)
        ser2.read(ser2.in_waiting)

    # Set IP and check final status
    ser2.write(b"ip addr add 192.168.144.66/24 dev eth0 2>/dev/null; ip link set eth0 up; echo OK\r\n")
    time.sleep(1)
    ser2.read(ser2.in_waiting)

    for cmd, label in [
        ("iptables -t nat -L POSTROUTING -n 2>&1 | grep MASQ", "NAT"),
        ("ip route | grep default", "GW"),
        ("cat /sys/class/udc/*/state 2>&1", "USB"),
        ("ps | grep usb_tund", "daemon"),
        ("ps | grep web_server", "web"),
    ]:
        ser2.write((cmd + "\r\n").encode())
        time.sleep(1)
        out = ser2.read(ser2.in_waiting).decode(errors="replace")
        status = "OK" if ("MASQ" in out or "192.168" in out or "usb_tund" in out or "web_server" in out or "b_idle" in out) else out.strip()[-40:]
        print(f"  {label}: {status}")

ser2.close()
print("\n=== REPAIR COMPLETE ===")
