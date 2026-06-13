"""Final throughput test: Python server on RK3588, nc client on DJI RC."""
import paramiko, subprocess, time, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HOST = "172.24.91.28"
DJI = "172.24.91.112:46561"
PORT = 9995
TEST_MB = 50

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username="xlong", password="1234", timeout=10)

# Kill old
c.exec_command("killall -9 python3 2>/dev/null; true", timeout=5)
time.sleep(0.5)

# Start Python TCP server on RK3588 that receives and counts
server_code = f"""
import socket
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(('0.0.0.0', {PORT}))
s.listen(1)
print('READY', flush=True)
conn, addr = s.accept()
total = 0
while True:
    data = conn.recv(65536)
    if not data:
        break
    total += len(data)
conn.close()
s.close()
print(f'TOTAL_BYTES={{total}}', flush=True)
"""

# Start server in background via shell
stdin, stdout, stderr = c.exec_command(
    f"python3 -c '{server_code}' &",
    timeout=5
)
time.sleep(1.5)

# Verify
stdin, stdout, stderr = c.exec_command("ss -tlnp 2>/dev/null | grep 9995", timeout=5)
out = stdout.read().decode(errors="replace")
print("Server:", out.strip() or "checking...")

# Send from DJI RC with timing
print(f"\n{'='*60}")
print(f"UPLOAD: DJI RC -> RK3588 ({TEST_MB}MB via USB tunnel)")
print(f"{'='*60}")
print(f"Sending {TEST_MB}MB...")

t0 = time.time()
r = subprocess.run(
    ["adb", "-s", DJI, "shell",
     f"dd if=/dev/zero bs=1M count={TEST_MB} 2>&1 | nc -w 20 10.0.0.1 {PORT} 2>&1; echo NC_EXIT=\$?"],
    capture_output=True, text=True, timeout=40
)
t1 = time.time()
elapsed = t1 - t0

# Parse dd output
dd_out = r.stdout.strip()
print(dd_out)

if elapsed > 0 and elapsed < 30:  # Only if it actually transferred
    mbps = (TEST_MB * 8) / elapsed
    print(f"\n>>> UPLOAD: {TEST_MB}MB in {elapsed:.1f}s = {mbps:.1f} Mbps <<<")
else:
    print(f"\n>>> Transfer failed or too fast to measure (elapsed={elapsed:.1f}s) <<<")

# Check what server received
time.sleep(1)
stdin, stdout, stderr = c.exec_command("jobs -l 2>/dev/null; ps aux | grep python3 | grep -v grep | head -3", timeout=5)
print("\nServer process:", stdout.read().decode(errors="replace").strip()[:300])

# Clean
c.exec_command("killall -9 python3 2>/dev/null; true", timeout=5)

# Daemon stats
stdin, stdout, stderr = c.exec_command(
    "echo 1234 | sudo -S journalctl -u tun_nat_hub --no-pager -n 2 2>&1",
    timeout=10
)
print("\nDaemon:", stdout.read().decode(errors="replace").strip()[-200:])

c.close()
print("\n---")
print(f"If the dd output shows '{TEST_MB}+0 records', the transfer succeeded.")
print(f"If it shows '0+0 records', nc connection failed.")
