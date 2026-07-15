"""Deploy web_server with version and verify"""
import paramiko, time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("192.168.144.66", username="root", password="root", timeout=10)

# Upload
chan = ssh.get_transport().open_session()
chan.exec_command("cat > /tmp/ws_new && chmod +x /tmp/ws_new && echo UP_OK")
time.sleep(0.2)
with open(r"c:\my_project\TUN_NAT_HUB\ubuntu\build_v3s\web_server", "rb") as f:
    ws = f.read()
for i in range(0, len(ws), 65536):
    chan.sendall(ws[i:i+65536])
chan.shutdown_write()
time.sleep(1)
out = chan.recv(4096).decode(errors="replace")
chan.close()
print("Upload:", "OK" if "UP_OK" in out else "FAIL")

# Restart
_, o, e = ssh.exec_command(
    "killall web_server 2>/dev/null; sleep 1; "
    "/tmp/ws_new > /var/log/ws.log 2>&1 & sleep 2; "
    "wget -q -O - http://127.0.0.1:8080/api/version 2>&1",
    timeout=10)
out = o.read().decode(errors="replace").strip()
print("Version API:", out)

# Check HTML header
_, o, e = ssh.exec_command(
    "wget -q -O - http://127.0.0.1:8080/ 2>&1 | grep 'hdr-ver'",
    timeout=5)
out = o.read().decode(errors="replace").strip()
print("HTML header:", out[:120])

ssh.close()
print("Done!")
