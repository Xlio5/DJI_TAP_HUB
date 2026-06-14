"""Upload clean files, restart services, verify everything."""
import paramiko, base64, time, os

LOCAL_BASE = r"c:\my_project\TUN_NAT_HUB"
HOST = "192.168.88.66"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username="xlong", password="1234", timeout=15)

def chan_upload(remote_path, data):
    """Upload binary data via base64 channel."""
    b64 = base64.b64encode(data).decode()
    chan = c.get_transport().open_session()
    chan.exec_command("base64 -d > " + remote_path)
    chan.sendall(b64.encode())
    chan.shutdown_write()
    return chan.recv_exit_status() == 0

def ssh(cmd, timeout=10):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    result = []
    if out.strip():
        result.append(out.strip())
    if err.strip():
        for line in err.strip().split("\n"):
            if "password" not in line.lower():
                result.append("E: " + line[:200])
    return "\n".join(result)

def sudossh(cmd, timeout=10):
    return ssh("echo 1234 | sudo -S " + cmd, timeout)

def read_and_clean(path):
    with open(path, "rb") as f:
        data = f.read()
    data = data.replace(b"\r\n", b"\n").replace(b"\r", b"")
    return data.rstrip(b"\n") + b"\n"

# ── Step 1: Upload clean web_panel.py ──
print("=== Uploading web_panel.py ===")
wp_data = read_and_clean(os.path.join(LOCAL_BASE, "ubuntu", "web_panel.py"))
ok = chan_upload("/home/xlong/web_panel.py", wp_data)
print("Upload:", "OK" if ok else "FAIL", "|", len(wp_data), "bytes")

# Verify syntax
print()
print("=== Checking syntax ===")
print(ssh("python3 -c 'import py_compile; py_compile.compile(\"/home/xlong/web_panel.py\", doraise=True); print(\"Syntax OK\")' 2>&1"))

# ── Step 2: Upload clean echo_srv.py ──
print()
print("=== Uploading echo_srv.py ===")
ec_data = read_and_clean(os.path.join(LOCAL_BASE, "tun_nat_hub_pkg", "web", "echo_srv.py"))
ok = chan_upload("/home/xlong/echo_srv.py", ec_data)
print("Upload:", "OK" if ok else "FAIL", "|", len(ec_data), "bytes")

# ── Step 3: Restart everything ──
print()
print("=== Restarting services ===")

# Kill old python3 processes first
ssh("killall -9 python3 2>/dev/null; true")
time.sleep(0.5)

# Restart systemd services
sudossh("systemctl restart tun_web 2>&1")
time.sleep(2)

# Start echo server
ssh("nohup python3 /home/xlong/echo_srv.py > /home/xlong/echo_out.txt 2>&1 &")
time.sleep(1)
echo_status = ssh("cat /home/xlong/echo_out.txt 2>&1")
print("Echo server:", echo_status)

# ── Step 4: Verify ──
print()
print("=== Service Status ===")
print(ssh("systemctl is-active tun_nat_hub tun_web 2>&1"))

print()
print("=== Listening Ports ===")
print(ssh("ss -tlnp 2>&1 | grep -E '8080|9999'"))

print()
print("=== Web HTTP Test ===")
print(ssh("curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/ 2>&1"))

print()
print("=== TCP Echo Test ===")
echo_test = (
    "import socket;"
    "s = socket.socket();"
    "s.settimeout(2);"
    "s.connect(('10.0.0.1', 9999));"
    "s.send(b'ping');"
    "r = s.recv(256);"
    "print('ECHO_OK:', r.decode());"
    "s.close()"
)
print(ssh("python3 -c '{}'".format(echo_test)))

print()
print("=== Daemon Stats ===")
print(ssh("journalctl -u tun_nat_hub --no-pager -n 2 2>&1"))

print()
print("=== Summary ===")
print(ssh("echo 'tun_nat_hub:' $(systemctl is-active tun_nat_hub)"))
print(ssh("echo 'tun_web:' $(systemctl is-active tun_web)"))
print(ssh("echo 'ttyGS0:' $(ls /dev/ttyGS0 2>&1)"))
print(ssh("echo 'tun_hub:' $(ip -br addr show tun_hub | awk '{print $3}')"))

c.close()
print()
print("Done! Web panel: http://192.168.88.66:8080")
