"""Pure Python TCP throughput test over USB tunnel (no iperf3 / nc dependency)."""
import paramiko, subprocess, time, sys, threading, socket, struct
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HOST = "172.24.91.28"
DJI = "172.24.91.112:46561"
PORT = 9997
TEST_MB = 50
TEST_BYTES = TEST_MB * 1024 * 1024

# ---- Server on RK3588 via SSH ----
print(f"=== Starting Python TCP server on RK3588 port {PORT} ===")
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username="xlong", password="1234", timeout=10)

server_script = f'''
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("0.0.0.0", {PORT}))
s.listen(1)
print("LISTENING", flush=True)
conn, addr = s.accept()
print(f"ACCEPTED from {{addr}}", flush=True)
total = 0
while total < {TEST_BYTES}:
    data = conn.recv(65536)
    if not data: break
    total += len(data)
conn.close()
s.close()
print(f"RECEIVED {{total}} bytes", flush=True)
'''

stdin, stdout, stderr = c.exec_command(
    f"python3 -c '{server_script}' 2>&1 &", timeout=5
)
time.sleep(1.5)
ssh_chan = stdout.channel

# Verify server is listening
stdin2, stdout2, stderr2 = c.exec_command(
    f"echo 1234 | sudo -S ss -tlnp 2>&1 | grep {PORT} || echo not_listening",
    timeout=5
)
ver = stdout2.read().decode(errors="replace")
print("Server check:", ver.strip())

if "not_listening" in ver or "LISTEN" not in ver:
    print("Server didn't start. Trying inline start...")
    # Try starting in foreground with timeout handling
    c2 = paramiko.SSHClient()
    c2.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c2.connect(HOST, username="xlong", password="1234", timeout=10)
    # Use threaded approach
    pass

# ---- TEST 1: DJI RC -> RK3588 (UPLOAD) ----
print(f"\n{'='*60}")
print(f"TEST 1: UPLOAD - DJI RC -> RK3588 via USB tunnel ({TEST_MB}MB)")
print(f"{'='*60}")

client_script = f"""
import socket, time, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(10)
try:
    s.connect(("10.0.0.1", {PORT}))
    data = bytearray(65536)
    sent = 0
    target = {TEST_BYTES}
    t0 = time.time()
    while sent < target:
        n = s.send(data[:min(65536, target - sent)])
        if n <= 0: break
        sent += n
    t1 = time.time()
    elapsed = t1 - t0
    mbps = (sent * 8 / 1_000_000) / elapsed if elapsed > 0 else 0
    print(f"SENT {{sent}} bytes in {{elapsed:.2f}}s = {{mbps:.1f}} Mbps", flush=True)
except Exception as e:
    print(f"ERROR: {{e}}", flush=True)
finally:
    s.close()
"""

print(f"\nSending {TEST_MB}MB through USB tunnel (this takes a few seconds)...")
t0 = time.time()
r = subprocess.run(
    ["adb", "-s", DJI, "shell", f"python3 -c '{client_script}' 2>&1"],
    capture_output=True, text=True, timeout=60
)
t1 = time.time()
print(r.stdout.strip())
if r.stderr.strip():
    print("[stderr]", r.stderr.strip())

# ---- Cleanup ----
c.exec_command("echo 1234 | sudo -S killall python3 2>/dev/null; true", timeout=5)
c.close()

# ---- Daemon stats ----
print(f"\n{'='*60}")
print("Daemon stats after test:")
print(f"{'='*60}")
c3 = paramiko.SSHClient()
c3.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c3.connect(HOST, username="xlong", password="1234", timeout=10)
stdin, stdout, stderr = c3.exec_command(
    "echo 1234 | sudo -S journalctl -u tun_nat_hub --no-pager -n 4 2>&1",
    timeout=10
)
print(stdout.read().decode(errors="replace"))
c3.close()
print("\nDone!")
