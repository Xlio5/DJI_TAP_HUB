"""Deploy new web_server with firmware upgrade support"""
import paramiko, time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("192.168.144.66", username="root", password="root", timeout=10)

# Upload
chan = ssh.get_transport().open_session()
chan.exec_command("cat > /tmp/ws_new && chmod +x /tmp/ws_new && echo UP_OK")
time.sleep(0.2)
with open(r"c:\my_project\TUN_NAT_HUB\ubuntu\build_v3s\web_server", "rb") as f:
    d = f.read()
print("Uploading " + str(len(d)) + " bytes...")
for i in range(0, len(d), 65536):
    chan.sendall(d[i:i+65536])
chan.shutdown_write()
time.sleep(1)
out = chan.recv(4096).decode(errors="replace")
chan.close()
print("Upload: " + ("OK" if "UP_OK" in out else "FAIL"))

# Restart with new binary
_, o, e = ssh.exec_command(
    "killall web_server 2>/dev/null; sleep 1; "
    "/tmp/ws_new > /var/log/web_server.log 2>&1 & sleep 2; "
    "wget -q -O - http://127.0.0.1:8080/ 2>&1 | grep -c hsqs",
    timeout=10
)
out = o.read().decode(errors="replace").strip()
err = e.read().decode(errors="replace").strip()
print("HTML check (hsqs count): " + out + " - " + ("PASS" if out == "1" else "FAIL"))
if err:
    print("ERR: " + err[:100])

# Test firmware API
_, o, e = ssh.exec_command(
    "echo 'test' > /tmp/test_fw.sq; "
    "wget -q -O - --post-file=/tmp/test_fw.sq "
    "--header='Content-Type: application/octet-stream' "
    "http://127.0.0.1:8080/api/firmware/upload 2>&1",
    timeout=5
)
out = o.read().decode(errors="replace").strip()
err = e.read().decode(errors="replace").strip()
print("API test: " + out)

ssh.close()
print("Done!")
