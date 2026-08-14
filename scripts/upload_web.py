"""Re-upload web_panel.py to RK3588."""
import paramiko, base64, time, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", username="xlong", password="1234", timeout=10)
S = "echo '1234' | sudo -S"

def run(cmd, timeout=10):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    if out.strip(): print(out.strip())

# Read local file
with open("c:/my_project/TUN_NAT_HUB/ubuntu/web_panel.py", "rb") as f:
    data = f.read()
print(f"Local file: {len(data)} bytes")

# Upload via stdin pipe
b64 = base64.b64encode(data).decode()
cmd = "python3 -c 'import base64,sys; data=base64.b64decode(sys.stdin.read()); open(\"/home/xlong/web_panel.py\",\"wb\").write(data); print(\"OK\")'"

transport = c.get_transport()
chan = transport.open_session()
chan.exec_command(cmd)
chan.sendall(b64.encode())
chan.shutdown_write()
code = chan.recv_exit_status()
chan.close()
print(f"Upload exit: {code}")

# Verify
run("wc -c < /home/xlong/web_panel.py")
run("file /home/xlong/web_panel.py")

# Fix line endings and make executable
run(f"{S} chmod +x /home/xlong/web_panel.py")
run(f"{S} systemctl reset-failed tun_web 2>/dev/null; true")
run(f"{S} systemctl restart tun_web")
time.sleep(2)

# Verify running
run(f"{S} systemctl status tun_web --no-pager 2>&1 | head -8")
run("ss -tlnp 2>/dev/null | grep 8080")

print("Done. Web panel at http://192.168.144.66:8080")
c.close()
