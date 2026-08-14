"""Deploy cdc branch (old baseline) to RK3588 for latency comparison."""
import paramiko, base64, time, os

HOST = "192.168.144.66"
LOCAL_BASE = r"c:\my_project\TUN_NAT_HUB"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username="xlong", password="1234", timeout=15)

def chan_upload(remote_path, data):
    b64 = base64.b64encode(data).decode()
    chan = c.get_transport().open_session()
    chan.exec_command("base64 -d > " + remote_path)
    chan.sendall(b64.encode())
    chan.shutdown_write()
    return chan.recv_exit_status() == 0

def read_clean(path):
    with open(path, "rb") as f:
        data = f.read()
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"")

def sudossh(cmd, timeout=10):
    full = "echo 1234 | sudo -S bash -c '%s' 2>&1" % cmd.replace("'", "'\"'\"'")
    stdin, stdout, stderr = c.exec_command(full, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    for line in (out + err).strip().split("\n"):
        if "password" not in line.lower():
            print("  ", line)

def ssh(cmd, timeout=10):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    if out.strip():
        print(out.strip())

# ── 1. Stop current services ──
print("=== [1/4] Stopping services ===")
sudossh("systemctl stop tun_nat_hub tun_web 2>&1 || true")
ssh("killall -9 python3 usb_tund 2>/dev/null; true")
time.sleep(1)
print("Services stopped")

# ── 2. Upload cdc branch source ──
print()
print("=== [2/4] Uploading cdc source ===")
src_files = {
    "protocol/frame.h": "/home/xlong/tun_cdc/protocol/frame.h",
    "ubuntu/src/main.cpp": "/home/xlong/tun_cdc/src/main.cpp",
    "ubuntu/src/tun_iface.cpp": "/home/xlong/tun_cdc/src/tun_iface.cpp",
    "ubuntu/src/tun_iface.h": "/home/xlong/tun_cdc/src/tun_iface.h",
    "ubuntu/CMakeLists.txt": "/home/xlong/tun_cdc/CMakeLists.txt",
}

# Create dirs
ssh("mkdir -p /home/xlong/tun_cdc/src /home/xlong/tun_cdc/protocol /home/xlong/protocol")

for local_rel, remote in src_files.items():
    local_path = os.path.join(LOCAL_BASE, local_rel)
    data = read_clean(local_path).rstrip(b"\n") + b"\n"
    ok = chan_upload(remote, data)
    print("  {} {} ({} bytes)".format(os.path.basename(local_rel), "OK" if ok else "FAIL", len(data)))

# Also copy frame.h to /home/xlong/protocol/ for build
ssh("cp /home/xlong/tun_cdc/protocol/frame.h /home/xlong/protocol/frame.h")

# ── 3. Build ──
print()
print("=== [3/4] Building cdc daemon ===")
# Remove old build
ssh("rm -rf /home/xlong/tun_cdc/build")
# CMake configure
ssh("cd /home/xlong/tun_cdc && export TMPDIR=/home/xlong/tmp && cmake -B build -DCMAKE_BUILD_TYPE=Release 2>&1")
# Build
ssh("cd /home/xlong/tun_cdc && export TMPDIR=/home/xlong/tmp && cmake --build build 2>&1")

# Verify binary
print()
ssh("ls -la /home/xlong/tun_cdc/build/usb_tund")
ssh("file /home/xlong/tun_cdc/build/usb_tund")

# ── 4. Deploy cdc version ──
print()
print("=== [4/4] Deploying cdc version ===")

# Copy binary
sudossh("cp /home/xlong/tun_cdc/build/usb_tund /usr/local/bin/usb_tund")

# Upload cdc scripts (with old VID 0x2207)
for script_name in ["setup_gadget.sh", "setup_nat.sh"]:
    local_path = os.path.join(LOCAL_BASE, "ubuntu", "scripts", script_name)
    data = read_clean(local_path).rstrip(b"\n") + b"\n"
    # Upload to /home/xlong first
    ok = chan_upload("/home/xlong/" + script_name, data)
    # Copy with sudo
    sudossh("cp /home/xlong/{} /usr/local/bin/{}".format(script_name, script_name))
    sudossh("sed -i 's/\\r$//' /usr/local/bin/{}".format(script_name))
    sudossh("chmod 755 /usr/local/bin/{}".format(script_name))
    print("  {} installed".format(script_name))

# Fix systemd unit (cdc has StartLimitIntervalSec in wrong section)
svc_content = b"""[Unit]
Description=TUN NAT Hub USB Bridge (cdc baseline)
After=network.target systemd-udev-settle.service
Wants=systemd-udev-settle.service
Requires=network.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=simple
User=root
Group=root
ExecStartPre=-/usr/local/bin/setup_gadget.sh
ExecStartPre=/usr/local/bin/setup_nat.sh
ExecStart=/usr/local/bin/usb_tund
Restart=always
RestartSec=5
LimitNOFILE=65536
LimitNPROC=256
StandardOutput=journal
StandardError=journal
SyslogIdentifier=tun_nat_hub

[Install]
WantedBy=multi-user.target
"""
chan_upload("/home/xlong/tun_nat_hub_cdc.service", svc_content)
sudossh("cp /home/xlong/tun_nat_hub_cdc.service /etc/systemd/system/tun_nat_hub.service")
sudossh("systemctl daemon-reload")
time.sleep(0.5)

# Start service
print()
print("Starting tun_nat_hub...")
sudossh("systemctl start tun_nat_hub 2>&1")
time.sleep(3)

# ── Verify ──
print()
print("=== Verification ===")
ssh("systemctl is-active tun_nat_hub 2>&1")
ssh("ls -la /dev/ttyGS0 2>&1")
ssh("ip -br addr show tun_hub 2>&1")
print()
ssh("journalctl -u tun_nat_hub --no-pager -n 8 2>&1")

# Show key differences
print()
print("=== Key differences (cdc vs master) ===")
print("  VTIME: 1 (100ms timer) vs 0 (instant)")
print("  VID:   0x2207 vs 0x0BDA (RTL8812AU)")
print("  usleep: see main.cpp for exact values")

c.close()
print()
print("cdc branch deployed. Ready for latency comparison.")
