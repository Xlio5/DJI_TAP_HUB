"""Throughput benchmark over USB tunnel."""
import paramiko, subprocess, time, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HOST = "172.24.91.28"
DJI = "172.24.91.112:46561"
PORT = 9995
TEST_MB = 50
S = "echo '1234' | sudo -S"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username="xlong", password="1234", timeout=10)

def ssh(cmd, timeout=15):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    if err.strip():
        print("[stderr]", err.strip()[:200])
    return out

# ---- Write server to /tmp via heredoc (avoids all quoting) ----
print("Uploading server script...")
server = """cat > /home/xlong/speed_srv.py << 'PYEOF'
import socket
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("0.0.0.0", 9995))
s.listen(1)
print("READY", flush=True)
conn, addr = s.accept()
total = 0
while True:
    data = conn.recv(65536)
    if not data:
        break
    total += len(data)
conn.close()
s.close()
print("TOTAL_BYTES=" + str(total), flush=True)
PYEOF
echo "WRITTEN"
"""

ssh(server, timeout=10)
ssh("wc -c < /home/xlong/speed_srv.py", timeout=5)

# Start server
ssh("killall -9 python3 2>/dev/null; true", timeout=5)
time.sleep(0.3)
# Clean /tmp first
ssh(f"{S} rm -rf /tmp/* 2>/dev/null; true", timeout=5)
ssh("nohup python3 /home/xlong/speed_srv.py > /home/xlong/speed_out.txt 2>&1 &", timeout=5)
time.sleep(1.5)

out = ssh(f"{S} ss -tlnp 2>/dev/null | grep {PORT}; echo '---'; cat /home/xlong/speed_out.txt 2>/dev/null", timeout=5)
print(f"Server: {out.strip()[:200]}")

if "READY" not in out and "LISTEN" not in out:
    print("ERROR: Server did not start!")
    c.close()
    sys.exit(1)

# ---- UPLOAD test ----
print(f"\n{'='*60}")
print(f"UPLOAD: DJI RC -> RK3588 via USB tunnel ({TEST_MB}MB)")
print(f"{'='*60}")

t0 = time.time()
r = subprocess.run(
    ["adb", "-s", DJI, "shell",
     f"dd if=/dev/zero bs=1M count={TEST_MB} 2>&1 | nc -w 20 10.0.0.1 {PORT} 2>&1; echo EXIT=$?"],
    capture_output=True, text=True, timeout=45
)
t1 = time.time()
elapsed = t1 - t0
print(r.stdout.strip())

if elapsed > 1:
    mbps = (TEST_MB * 8) / elapsed
    print(f"\n>>> Wall-clock: {TEST_MB}MB in {elapsed:.1f}s = {mbps:.1f} Mbps <<<")

# Server output
time.sleep(1)
out = ssh("cat /home/xlong/speed_out.txt 2>/dev/null", timeout=5)
print(f"\nServer output: {out.strip()}")

# Parse actual bytes
if "TOTAL_BYTES=" in out:
    try:
        received = int(out.split("TOTAL_BYTES=")[1].split()[0])
        actual_mbps = (received * 8 / 1_000_000) / elapsed if elapsed > 0 else 0
        print(f"  Actual: {received/1024/1024:.1f}MB received = {actual_mbps:.1f} Mbps")
    except:
        pass

# Daemon
out = ssh(f"{S} journalctl -u tun_nat_hub --no-pager -n 1 2>&1", timeout=10)
print(f"\nDaemon: {out.strip()[-200:]}")

# Cleanup
ssh("killall -9 python3 2>/dev/null; true", timeout=5)
c.close()
print("\nDone!")
