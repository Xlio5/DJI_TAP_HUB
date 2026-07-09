#!/usr/bin/env python3
"""通过 SSH exec + base64 部署 web_panel.py"""

import paramiko
import base64

LOCAL_PATH = r"c:\my_project\TUN_NAT_HUB\ubuntu\web_panel.py"
V3S_IP = "192.168.144.66"

with open(LOCAL_PATH, "rb") as f:
    raw = f.read()
b64 = base64.b64encode(raw).decode("ascii")
print(f"Read {len(raw)} bytes, base64: {len(b64)} chars")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(V3S_IP, username="root", password="root", timeout=10)
print(f"SSH connected")

# Write base64 to V3s via cat
channel = ssh.get_transport().open_session()
channel.exec_command(f"cat > /tmp/wp_b64 << 'EOF64'\n{b64}\nEOF64\n")
channel.recv_exit_status()
print("Base64 uploaded. Decoding & deploying...")

_, stdout, stderr = ssh.exec_command(
    "base64 -d /tmp/wp_b64 > /tmp/wp_new.py && "
    "wc -c /tmp/wp_new.py && "
    "cp /tmp/wp_new.py /usr/local/bin/web_panel.py && "
    "chmod +x /usr/local/bin/web_panel.py && "
    "killall python3 2>/dev/null; sleep 1; "
    "python3 /usr/local/bin/web_panel.py > /var/log/web_panel.log 2>&1 & "
    "sleep 2; wget -q -O - http://127.0.0.1:8080/api/config"
)
print(stdout.read().decode())
err = stderr.read().decode()
if err:
    print(f"STDERR: {err}")

ssh.close()
print("Done!")
