#!/usr/bin/env python3
"""通过 SSH 部署 web_panel.py 到 V3s"""

import paramiko
import os
import sys

LOCAL_PATH = r"c:\my_project\TUN_NAT_HUB\ubuntu\web_panel.py"
REMOTE_PATH = "/usr/local/bin/web_panel.py"
V3S_IP = "192.168.144.66"
USER = "root"
PASS = "root"

try:
    with open(LOCAL_PATH, "rb") as f:
        content = f.read()
    print(f"Read {len(content)} bytes from {LOCAL_PATH}")
except Exception as e:
    print(f"ERROR reading local file: {e}")
    sys.exit(1)

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(V3S_IP, username=USER, password=PASS, timeout=10)
    print(f"SSH connected to {V3S_IP}")

    sftp = ssh.open_sftp()
    sftp.putfo(open(LOCAL_PATH, "rb"), REMOTE_PATH)
    sftp.chmod(REMOTE_PATH, 0o755)
    sftp.close()
    print(f"Uploaded to {REMOTE_PATH}")

    # Restart web_panel
    stdin, stdout, stderr = ssh.exec_command("killall python3; sleep 1; python3 /usr/local/bin/web_panel.py > /var/log/web_panel.log 2>&1 &")
    print("web_panel restarted")

    # Verify new config
    stdin, stdout, stderr = ssh.exec_command("sleep 2; wget -q -O - http://127.0.0.1:8080/api/config")
    out = stdout.read().decode()
    print(f"Config: {out}")

    ssh.close()
    print("Done!")
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)
