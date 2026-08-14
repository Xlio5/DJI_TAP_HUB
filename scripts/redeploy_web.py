"""Quick redeploy web_panel.py to RK3588."""
import paramiko, base64, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", username="xlong", password="1234", timeout=10)

with open(r"c:\my_project\TUN_NAT_HUB\ubuntu\web_panel.py", "rb") as f:
    data = f.read().replace(b"\r\n", b"\n")
b64 = base64.b64encode(data).decode()
ch = c.get_transport().open_session()
ch.exec_command("base64 -d > /home/xlong/web_panel.py")
ch.sendall(b64.encode())
ch.shutdown_write()
ch.recv_exit_status()
ch.close()

# Syntax check
s1, s2, s3 = c.exec_command(
    "python3 -c 'import py_compile; py_compile.compile(\"/home/xlong/web_panel.py\", doraise=True); print(\"SYNTAX_OK\")' 2>&1",
    timeout=5)
time.sleep(1)
print(s2.read().decode(errors="replace").strip()[:200])

# Restart web
s1, s2, s3 = c.exec_command("echo 1234 | sudo -S systemctl restart tun_web 2>&1", timeout=5, get_pty=True)
time.sleep(3)
s2.read()

# Verify
s1, s2, s3 = c.exec_command("systemctl is-active tun_web 2>&1")
print("Web:", s2.read().decode(errors="replace").strip())

s1, s2, s3 = c.exec_command("curl -s http://127.0.0.1:8080/api/version 2>&1")
print("Version:", s2.read().decode(errors="replace").strip())

s1, s2, s3 = c.exec_command("curl -s http://127.0.0.1:8080/api/heartbeat 2>&1")
print("Heartbeat:", s2.read().decode(errors="replace").strip()[:400])

c.close()
