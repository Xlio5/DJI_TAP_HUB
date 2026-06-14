"""Build daemon on RK3588 and create deployment package."""
import paramiko, base64, time, os, sys

HOST = "192.168.88.66"
USER = "xlong"
PW = "1234"
LOCAL_BASE = r"c:\my_project\TUN_NAT_HUB"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PW, timeout=15)

def ssh(cmd, timeout=15):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    if out.strip(): print(out.strip())
    if err.strip(): print("ERR:", err.strip()[:300])

def upload_via_channel(local_path, remote_path):
    """Upload file using SSH channel (handles binary content safely)."""
    with open(local_path, "rb") as f:
        data = f.read()
    b64 = base64.b64encode(data).decode()
    cmd = f"base64 -d > {remote_path}"
    transport = c.get_transport()
    chan = transport.open_session()
    chan.exec_command(cmd)
    chan.sendall(b64.encode())
    chan.shutdown_write()
    code = chan.recv_exit_status()
    chan.close()
    if code != 0:
        print(f"  WARN: {remote_path} exit code {code}")
    return code == 0

print("=== Step 1: Prepare build directory ===")
ssh("mkdir -p /home/xlong/tun_build/src /home/xlong/tun_build/protocol")

print("\n=== Step 2: Upload source files ===")
files = [
    (os.path.join(LOCAL_BASE, "protocol", "frame.h"), "/home/xlong/tun_build/protocol/frame.h"),
    (os.path.join(LOCAL_BASE, "ubuntu", "src", "main.cpp"), "/home/xlong/tun_build/src/main.cpp"),
    (os.path.join(LOCAL_BASE, "ubuntu", "src", "tun_iface.cpp"), "/home/xlong/tun_build/src/tun_iface.cpp"),
    (os.path.join(LOCAL_BASE, "ubuntu", "src", "tun_iface.h"), "/home/xlong/tun_build/src/tun_iface.h"),
    (os.path.join(LOCAL_BASE, "ubuntu", "CMakeLists.txt"), "/home/xlong/tun_build/CMakeLists.txt"),
]
for local, remote in files:
    ok = upload_via_channel(local, remote)
    print(f"  {os.path.basename(local)} {'OK' if ok else 'FAILED'}")

print("\n=== Step 3: Build ===")
ssh("cd /home/xlong/tun_build && export TMPDIR=/home/xlong/tmp && cmake -B build -DCMAKE_BUILD_TYPE=Release 2>&1")
ssh("cd /home/xlong/tun_build && export TMPDIR=/home/xlong/tmp && cmake --build build 2>&1")

print("\n=== Step 4: Verify binary ===")
ssh("ls -la /home/xlong/tun_build/build/usb_tund")
ssh("file /home/xlong/tun_build/build/usb_tund")

print("\n=== Step 5: Create package directory ===")
pkg = "/home/xlong/tun_nat_hub_pkg"
ssh(f"rm -rf {pkg}")
ssh(f"mkdir -p {pkg}/bin {pkg}/scripts {pkg}/config {pkg}/web")

# Copy binary
ssh(f"cp /home/xlong/tun_build/build/usb_tund {pkg}/bin/")

# Copy scripts from installed locations
ssh(f"cp /usr/local/bin/setup_gadget.sh {pkg}/scripts/")
ssh(f"cp /usr/local/bin/setup_nat.sh {pkg}/scripts/")

# Copy config
ssh(f"cp /etc/systemd/system/tun_nat_hub.service {pkg}/config/")
ssh(f"cp /etc/systemd/system/tun_web.service {pkg}/config/")

# Copy web panel
ssh(f"cp /home/xlong/web_panel.py {pkg}/web/")
ssh(f"cp /home/xlong/echo_srv.py {pkg}/web/")

print("\n=== Step 6: Create install.sh ===")
install_script = """#!/bin/bash
# TUN_NAT_HUB One-Click Install Script
# For RK3588 (Rock 5C) Ubuntu / ARM64
set -e

echo "========================================="
echo " TUN_NAT_HUB Installer"
echo " Target: RK3588 (ARM64)"
echo "========================================="

SCRIPT_DIR=\"$(cd \"$(dirname \"$0\")\" && pwd)\"

# 1. Stop existing services
echo \"[1/5] Stopping existing services...\"
systemctl stop tun_nat_hub 2>/dev/null || true
systemctl stop tun_web 2>/dev/null || true

# 2. Install binary
echo \"[2/5] Installing usb_tund daemon...\"
cp \"$SCRIPT_DIR/bin/usb_tund\" /usr/local/bin/usb_tund
chmod 755 /usr/local/bin/usb_tund

# 3. Install scripts
echo \"[3/5] Installing gadget/nat scripts...\"
cp \"$SCRIPT_DIR/scripts/setup_gadget.sh\" /usr/local/bin/setup_gadget.sh
cp \"$SCRIPT_DIR/scripts/setup_nat.sh\" /usr/local/bin/setup_nat.sh
chmod 755 /usr/local/bin/setup_gadget.sh /usr/local/bin/setup_nat.sh

# Fix line endings (CRLF -> LF)
sed -i 's/\\\\r$//' /usr/local/bin/setup_gadget.sh
sed -i 's/\\\\r$//' /usr/local/bin/setup_nat.sh

# 4. Install systemd services
echo \"[4/5] Installing systemd services...\"
cp \"$SCRIPT_DIR/config/tun_nat_hub.service\" /etc/systemd/system/tun_nat_hub.service
cp \"$SCRIPT_DIR/config/tun_web.service\" /etc/systemd/system/tun_web.service
systemctl daemon-reload

# 5. Install web panel and echo server
echo \"[5/5] Installing web panel + echo server...\"
cp \"$SCRIPT_DIR/web/web_panel.py\" /home/xlong/web_panel.py
cp \"$SCRIPT_DIR/web/echo_srv.py\" /home/xlong/echo_srv.py
chmod 644 /home/xlong/web_panel.py /home/xlong/echo_srv.py

# Fix line endings for Python files
sed -i 's/\\\\r$//' /home/xlong/web_panel.py
sed -i 's/\\\\r$//' /home/xlong/echo_srv.py

# Enable and start services
echo \"\"
echo \"Starting services...\"
systemctl enable tun_nat_hub
systemctl enable tun_web
systemctl start tun_nat_hub
sleep 2
systemctl start tun_web

echo \"\"
echo \"=========================================\"
echo \" Installation Complete!\"
echo \"=========================================\"
echo \"\"
echo \"Services:\"
echo \"  tun_nat_hub: USB tunnel daemon\"
echo \"  tun_web:     Web config panel (port 8080)\"
echo \"\"
echo \"Check status:\"
echo \"  systemctl status tun_nat_hub\"
echo \"  systemctl status tun_web\"
echo \"  journalctl -u tun_nat_hub -f\"
echo \"\"
echo \"Web panel: http://$(hostname -I | awk '{print $1}'):8080\"
echo \"=========================================\"
"""
# Upload install.sh via channel
b64 = base64.b64encode(install_script.encode()).decode()
cmd = f"base64 -d > {pkg}/install.sh"
transport = c.get_transport()
chan = transport.open_session()
chan.exec_command(cmd)
chan.sendall(b64.encode())
chan.shutdown_write()
chan.recv_exit_status()
chan.close()

ssh(f"chmod 755 {pkg}/install.sh")
print("install.sh created")

print("\n=== Step 7: Verify package ===")
ssh(f"ls -laR {pkg}")

print("\n=== Step 8: Create tarball ===")
ssh(f"cd /home/xlong && tar czvf tun_nat_hub_rk3588.tar.gz tun_nat_hub_pkg/")
ssh("ls -lh /home/xlong/tun_nat_hub_rk3588.tar.gz")

print("\n=== Done! Package ready on RK3588: /home/xlong/tun_nat_hub_rk3588.tar.gz ===")
c.close()
