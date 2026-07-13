#!/usr/bin/env python3
"""TCP文件服务 + SSH远程部署 web_server"""
import paramiko, threading, socket, time, struct, os
import subprocess

LOCAL = r"c:\my_project\TUN_NAT_HUB\ubuntu\build_v3s\web_server"
V3S = "192.168.144.66"
PORT = 9898

with open(LOCAL, "rb") as f:
    filedata = f.read()
print(f"File: {len(filedata)} bytes")

# --- TCP file server thread ---
def serve_file():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", PORT))
    srv.listen(1)
    srv.settimeout(30)
    print(f"TCP server: :{PORT}")
    try:
        conn, addr = srv.accept()
        print(f"Client: {addr}")
        # send size header + data
        conn.sendall(struct.pack("!I", len(filedata)))
        conn.sendall(filedata)
        conn.close()
        print("Sent")
    except socket.timeout:
        print("Timeout - no client")
    finally:
        srv.close()

t = threading.Thread(target=serve_file, daemon=True)
t.start()
time.sleep(0.3)

# --- SSH to trigger download ---
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(V3S, username="root", password="root", timeout=10)
print("SSH connected")

# V3s runs: wget from PC, then install, then restart
script = """
killall python3 2>/dev/null
killall web_server 2>/dev/null
rm -f /tmp/ws_new
wget -q -O /tmp/ws_new http://<PC>:<PORT>/web_server
if [ -s /tmp/ws_new ]; then
  cp /tmp/ws_new /usr/local/bin/web_server
  chmod +x /usr/local/bin/web_server
  ls -la /usr/local/bin/web_server
  sleep 1
  /usr/local/bin/web_server > /var/log/web_server.log 2>&1 &
  sleep 2
  wget -q -O - http://127.0.0.1:8080/api/heartbeat || echo "HEARTBEAT_FAIL"
else
  echo "DOWNLOAD_FAILED"
fi
""".replace("<PC>", "192.168.144.88").replace("<PORT>", str(PORT))

# Write to temp file on V3s and execute
channel = ssh.get_transport().open_session()
channel.exec_command("cat > /tmp/install_ws.sh && sh /tmp/install_ws.sh")
time.sleep(0.5)
channel.sendall(script.encode())
channel.shutdown_write()
time.sleep(8)

result = channel.recv(4096).decode(errors="replace")
print(f"Result:\n{result}")

channel.close()
ssh.close()
t.join(timeout=30)
print("Done!")
