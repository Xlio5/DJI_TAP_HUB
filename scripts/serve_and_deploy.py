#!/usr/bin/env python3
"""在 Windows 上启动临时 HTTP 服务器，让 V3s 拉取 web_panel.py 并部署"""

import subprocess, time, os

LOCAL_FILE = r"c:\my_project\TUN_NAT_HUB\ubuntu\web_panel.py"
SERVE_DIR = r"c:\my_project\TUN_NAT_HUB\ubuntu"
V3S_IP = "192.168.144.66"
WIN_IP = "192.168.144.88"   # Windows Ethernet IP on same switch as V3s
HTTP_PORT = 9990

# Start HTTP server
server = subprocess.Popen(
    ["python", "-m", "http.server", str(HTTP_PORT)],
    cwd=SERVE_DIR,
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
time.sleep(1)
print(f"HTTP server on http://{WIN_IP}:{HTTP_PORT}")

try:
    subprocess.run(["python", "-c", f"""
import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("{V3S_IP}", username="root", password="root", timeout=10)
print("SSH connected")
cmd = (
    "wget -q -O /tmp/web_panel.py http://{WIN_IP}:{HTTP_PORT}/web_panel.py && "
    "echo 'DOWNLOAD_OK '$(wc -c < /tmp/web_panel.py) && "
    "cp /tmp/web_panel.py /usr/local/bin/web_panel.py && "
    "chmod +x /usr/local/bin/web_panel.py && "
    "killall python3 2>/dev/null; sleep 1; "
    "python3 /usr/local/bin/web_panel.py > /var/log/web_panel.log 2>&1 & "
    "sleep 2; "
    "echo '---CONFIG---'; wget -q -O - http://127.0.0.1:8080/api/config; "
    "echo; echo '---DONE---'"
)
_, stdout, stderr = ssh.exec_command(cmd)
print(stdout.read().decode())
err = stderr.read().decode()
if err:
    print(f'STDERR: {err}')
ssh.close()
"""], check=True, timeout=30)
except subprocess.CalledProcessError as e:
    print(f"Failed: {e}")
finally:
    server.terminate()
    print("Done!")
