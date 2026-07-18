#!/usr/bin/env python3
"""netcat 直传 web_server: PC -(nc)-> V3s"""
import paramiko, socket, time

LOCAL = r"c:\my_project\TUN_NAT_HUB\ubuntu\build_v3s\web_server"
V3S = "192.168.144.66"

with open(LOCAL, "rb") as f:
    filedata = f.read()
print(f"File: {len(filedata)} bytes")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(V3S, username="root", password="root", timeout=10)
print("SSH connected")

# Step 1: Start nc listener in background on V3s
_, stdout, stderr = ssh.exec_command("killall nc 2>/dev/null; rm -f /tmp/ws_new; nc -l -p 19999 > /tmp/ws_new & echo NC_STARTED")
print(stdout.read().decode())
time.sleep(1)

# Step 2: Send file from PC via direct TCP
print(f"Connecting to {V3S}:19999...")
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(10)
sock.connect((V3S, 19999))
sock.sendall(filedata)
sock.close()
print(f"Sent {len(filedata)} bytes")
time.sleep(1)

# Step 3: Verify and install
_, stdout, stderr = ssh.exec_command(
    "wc -c /tmp/ws_new && "
    "cp /tmp/ws_new /usr/local/bin/web_server && "
    "chmod +x /usr/local/bin/web_server && "
    "ls -la /usr/local/bin/web_server"
)
print(stdout.read().decode())
e = stderr.read().decode()
if e: print("E:", e)

# Step 4: Start web_server
_, stdout, stderr = ssh.exec_command(
    "killall python3 2>/dev/null; killall web_server 2>/dev/null; "
    "sleep 1; /usr/local/bin/web_server > /var/log/web_server.log 2>&1 & "
    "sleep 2; wget -q -O - http://127.0.0.1:8080/api/heartbeat"
)
print(stdout.read().decode())
e = stderr.read().decode()
if e: print("E:", e)

ssh.close()
print("Done!")
