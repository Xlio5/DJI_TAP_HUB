"""Systematic USB diagnostic - figure out why App shows 'USB 未连接'"""
import paramiko, base64, time, re

HOST = "192.168.144.66"
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username="xlong", password="1234", timeout=10)

# Upload a comprehensive diagnostic script to RK3588
script = """#!/bin/bash
ADB="adb -s 10.248.133.209:5555"

echo "=== 1. Device node permissions ==="
$ADB shell 'ls -la /dev/bus/usb/002/' 2>&1

echo ""
echo "=== 2. Our app UID ==="
$ADB shell 'dumpsys package com.tunnathub.app' 2>&1 | grep 'userId='

echo ""
echo "=== 3. USB device permissions ==="
$ADB shell 'dumpsys usb' 2>&1 | grep -A5 'device_permissions' | head -10

echo ""
echo "=== 4. Can app open device node? ==="
$ADB shell 'run-as com.tunnathub.app ls /dev/bus/usb/002/ 2>&1 || echo "run-as FAILED"'

echo ""
echo "=== 5. USB host devices list ==="
$ADB shell 'dumpsys usb' 2>&1 | grep -B1 -A3 'vendor_id=3034' | head -20

echo ""
echo "=== 6. Check if device is in UsbManager list ==="
# This is the key - does Java API see it?
# Use 'cmd' to query USB service
$ADB shell 'cmd usb get-devices 2>&1 || dumpsys usb | grep -c "vendor_id=3034"'

echo ""
echo "=== 7. Any SELinux denials? ==="
$ADB shell 'dmesg 2>&1' | grep -i 'usb.*denied\\|avc.*usb' | tail -5 || echo "no selinux denials"

echo ""
echo "=== 8. Last USB connect events ==="
$ADB shell 'dumpsys usb' 2>&1 | grep -A2 'num_connects\|device_address.*002' | head -10

echo ""
echo "=== 9. Compare with a known-good USB device ==="
$ADB shell 'lsusb' 2>&1
"""

b64 = base64.b64encode(script.encode()).decode()
ch = c.get_transport().open_session()
ch.exec_command("base64 -d > /tmp/usb_root_cause.sh")
ch.sendall(b64.encode())
ch.shutdown_write()
ch.recv_exit_status()
ch.close()

s1, s2, s3 = c.exec_command("bash /tmp/usb_root_cause.sh", timeout=15, get_pty=True)
time.sleep(5)
out = b""
while s2.channel.recv_ready():
    out += s2.channel.recv(4096)
try:
    out += s2.read()
except:
    pass
print(out.decode(errors="replace"))
c.close()
