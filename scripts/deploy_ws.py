#!/usr/bin/env python3
"""单会话 stty raw → cat → base64 → 解码"""
import paramiko, base64, time

LOCAL = r"c:\my_project\TUN_NAT_HUB\ubuntu\build_v3s\web_server"

with open(LOCAL, "rb") as f:
    data = f.read()
print(f"File: {len(data)} bytes")

b64 = base64.b64encode(data).decode()

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("192.168.144.66", username="root", password="root", timeout=15)

chan = ssh.invoke_shell(width=200, height=50)
time.sleep(0.5)
chan.recv(8192)  # banner

# Turn off echo and line buffering
chan.send("stty raw -echo 2>/dev/null\n")
time.sleep(0.2)
chan.recv(2048)

print("Sending base64 via cat...")

# Use cat to receive raw data with a delimiter
chan.send("cat > /tmp/ws_b64\n")
time.sleep(0.1)

# Send all base64 at once (no echo to worry about with raw mode)
chan.send(b64)

# Signal end with a unique marker that won't appear in base64
chan.send("\n_EOF_B64_\n")
time.sleep(2)

# Send Ctrl+C to stop cat if needed, then restore terminal
chan.send("\x03")
time.sleep(0.3)
chan.send("stty sane 2>/dev/null\n")
time.sleep(0.2)
chan.recv(4096)

# Check size
chan.send("wc -c /tmp/ws_b64\n")
time.sleep(0.5)
out = chan.recv(2048).decode(errors="replace")
print(f"B64 size: {out.strip()}")

if str(len(b64)) not in out:
    # Try removing the _EOF_B64_ marker
    chan.send("sed -i '/_EOF_B64_/d' /tmp/ws_b64 2>/dev/null; wc -c /tmp/ws_b64\n")
    time.sleep(0.5)
    out = chan.recv(2048).decode(errors="replace")
    print(f"B64 size (cleaned): {out.strip()}")

# Decode
chan.send("base64 -d /tmp/ws_b64 > /tmp/ws_new 2>&1; echo RC=$?; wc -c /tmp/ws_new\n")
time.sleep(1)
out = chan.recv(4096).decode(errors="replace")
print(f"Decode: {out.strip()}")

if str(len(data)) not in out:
    chan.send("cat /var/log/web_server.log 2>/dev/null | tail -5\n")
    time.sleep(0.3)
    out = chan.recv(2048).decode(errors="replace")
    print("Log:", out)

# Install
chan.send("cp /tmp/ws_new /usr/local/bin/web_server && chmod +x /usr/local/bin/web_server && killall web_server 2>/dev/null; sleep 1; /usr/local/bin/web_server > /var/log/web_server.log 2>&1 & sleep 2; wget -q -O - http://127.0.0.1:8080/api/heartbeat; echo ---DONE---\n")
time.sleep(4)
out = chan.recv(8192).decode(errors="replace")
print(out[-500:])

chan.close()
ssh.close()
print("Done!")
