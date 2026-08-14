"""Fix and deploy on new RK3588."""
import paramiko, base64, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", username="xlong", password="1234", timeout=15)

def chan_write(remote_path, content_bytes):
    b64 = base64.b64encode(content_bytes).decode()
    chan = c.get_transport().open_session()
    chan.exec_command("base64 -d > " + remote_path)
    chan.sendall(b64.encode())
    chan.shutdown_write()
    return chan.recv_exit_status() == 0

def sudossh(cmd, timeout=15):
    """Run command with sudo password (via pipe)."""
    full_cmd = "echo 1234 | sudo -S bash -c '%s' 2>&1" % cmd.replace("'", "'\"'\"'")
    stdin, stdout, stderr = c.exec_command(full_cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    result = (out + err).strip()
    # Only print if there's content beyond password prompt
    if result:
        for line in result.split("\n"):
            if "password" not in line.lower():
                print(line)
    return result

def normalsh(cmd, timeout=15):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    if out.strip():
        print(out.strip())
    if err.strip():
        print("E:", err.strip()[:300])

# ── 1. Write clean service files ──
print("=== [1/6] Writing clean systemd service files ===")

tun_nat_hub_svc = """[Unit]
Description=TUN NAT Hub USB Bridge (g_serial Pure Bulk)
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

tun_web_svc = """[Unit]
Description=TUN NAT Hub Web Config Panel
After=network.target tun_nat_hub.service
Wants=tun_nat_hub.service

[Service]
Type=simple
User=root
ExecStart=/usr/bin/python3 /home/xlong/web_panel.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""

chan_write("/home/xlong/tun_nat_hub.service.fixed", tun_nat_hub_svc.encode())
chan_write("/home/xlong/tun_web.service.fixed", tun_web_svc.encode())

# Verify clean content
normalsh("cat -A /home/xlong/tun_nat_hub.service.fixed")

# ── 2. Fix CRLF in all text files ──
print()
print("=== [2/6] Fixing CRLF line endings ===")
sudossh("sed -i 's/\\r$//' /usr/local/bin/setup_gadget.sh")
sudossh("sed -i 's/\\r$//' /usr/local/bin/setup_nat.sh")
sudossh("sed -i 's/\\r$//' /home/xlong/web_panel.py")
sudossh("sed -i 's/\\r$//' /home/xlong/echo_srv.py")
print("CRLF fixed for all files")

# ── 3. Copy service files (with sudo) ──
print()
print("=== [3/6] Installing service files ===")
sudossh("cp /home/xlong/tun_nat_hub.service.fixed /etc/systemd/system/tun_nat_hub.service")
sudossh("cp /home/xlong/tun_web.service.fixed /etc/systemd/system/tun_web.service")

# Verify installed files
normalsh("cat -A /etc/systemd/system/tun_nat_hub.service")

# ── 4. Reload systemd ──
print()
print("=== [4/6] Reloading systemd ===")
sudossh("systemctl daemon-reload")
time.sleep(1)
print("daemon-reload done")

# ── 5. Verify syntax ──
print()
print("=== [5/6] Verifying service syntax ===")
normalsh("systemd-analyze verify /etc/systemd/system/tun_nat_hub.service 2>&1 || true")

# ── 6. Enable and start ──
print()
print("=== [6/6] Starting services ===")
sudossh("systemctl enable tun_nat_hub 2>&1 || true")
sudossh("systemctl enable tun_web 2>&1 || true")
sudossh("systemctl start tun_nat_hub 2>&1 || true")
time.sleep(2)
sudossh("systemctl start tun_web 2>&1 || true")
time.sleep(1)

# ── Final verification ──
print()
print("=== Final Status ===")
normalsh("systemctl is-active tun_nat_hub tun_web 2>&1")
print()
normalsh("ls -la /dev/ttyGS0 2>&1")
print()
normalsh("ip addr show tun_hub 2>&1")
print()
print("=== Daemon log ===")
normalsh("journalctl -u tun_nat_hub --no-pager -n 10 2>&1")

c.close()
print()
print("=== Deployment complete! ===")
