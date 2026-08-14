"""Deploy web panel to RK3588 and start as systemd service."""
import paramiko, time, sys, base64
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HOST = "172.24.91.28"
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username="xlong", password="1234", timeout=10)

def run(cmd, timeout=10):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    if out.strip(): print(out.strip())

S = "echo '1234' | sudo -S"

# 1. Upload web_panel.py
print("=== Uploading web_panel.py ===")
with open("c:/my_project/TUN_NAT_HUB/ubuntu/web_panel.py", "rb") as f:
    data = f.read()
b64 = base64.b64encode(data).decode()

# Upload via stdin pipe
cmd_py = "python3 -c \"import base64,sys; open('/home/xlong/web_panel.py','wb').write(base64.b64decode(sys.stdin.read()))\""
transport = c.get_transport()
chan = transport.open_session()
chan.exec_command(cmd_py)
chan.sendall(b64.encode())
chan.shutdown_write()
code = chan.recv_exit_status()
chan.close()
print(f"Upload exit={code}")

# Verify
run("wc -c < /home/xlong/web_panel.py")

# 2. Add shebang line, make executable
run(f"{S} sed -i '1s|^|#!/usr/bin/env python3\\n|' /home/xlong/web_panel.py; echo fixed")
run(f"{S} chmod +x /home/xlong/web_panel.py")

# 3. Kill old instance
run(f"{S} killall python3 2>/dev/null; true")
time.sleep(0.5)

# 4. Install as systemd service
service_unit = """[Unit]
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

# Upload service unit
svc_b64 = base64.b64encode(service_unit.encode()).decode()
cmd_svc = "python3 -c \"import base64,sys; open('/tmp/tun_web.service','wb').write(base64.b64decode(sys.stdin.read()))\""
chan2 = transport.open_session()
chan2.exec_command(cmd_svc)
chan2.sendall(svc_b64.encode())
chan2.shutdown_write()
chan2.recv_exit_status()
chan2.close()

run(f"{S} cp /tmp/tun_web.service /etc/systemd/system/tun_web.service")
run(f"{S} systemctl daemon-reload")
run(f"{S} systemctl enable tun_web")

# 5. Start
print("\n=== Starting web panel ===")
run(f"{S} systemctl restart tun_web")
time.sleep(2)
run(f"{S} systemctl status tun_web --no-pager 2>&1 | head -10")

# 6. Check port
run("ss -tlnp 2>/dev/null | grep 8080")

# 7. Also restart tun_nat_hub if needed
run(f"{S} systemctl status tun_nat_hub --no-pager 2>&1 | head -3")

print("\n" + "=" * 60)
print("Web panel deployed!")
print("Access: http://192.168.144.66:8080")
print("=" * 60)

c.close()
