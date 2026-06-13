"""Precision latency test: UDP echo through USB tunnel, no video/codec overhead."""
import paramiko, subprocess, time, sys, struct, socket, threading
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HOST = "172.24.91.28"
DJI = "172.24.91.112:46495"
SERVER_IP = "10.0.0.1"   # RK3588 tun_hub
CLIENT_IP = "10.0.0.2"   # Android TUN

# ============================================================
# Step 1: Upload and start UDP echo server on RK3588
# ============================================================
print("=" * 60)
print("Step 1: Start UDP echo server on RK3588 (10.0.0.1:9999)")
print("=" * 60)

echo_server = """import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind(("10.0.0.1", 9999))
print("ECHO_READY", flush=True)
while True:
    data, addr = s.recvfrom(2048)
    s.sendto(data, addr)
"""

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username="xlong", password="1234", timeout=10)

# Upload server
server_upload = f"cat > /home/xlong/echo_srv.py << 'PYEOF'\n{echo_server}\nPYEOF\necho WRITTEN"
stdin, stdout, stderr = c.exec_command(server_upload, timeout=10)
print(stdout.read().decode(errors="replace").strip())

# Kill old, start new
c.exec_command("killall -9 python3 2>/dev/null; true", timeout=5)
time.sleep(0.3)
stdin, stdout, stderr = c.exec_command(
    "nohup python3 /home/xlong/echo_srv.py > /home/xlong/echo_out.txt 2>&1 & echo STARTED",
    timeout=5
)
time.sleep(1)

# Verify
stdin, stdout, stderr = c.exec_command("cat /home/xlong/echo_out.txt 2>/dev/null; ss -tulnp 2>/dev/null | grep 9999", timeout=5)
print("Server:", stdout.read().decode(errors="replace").strip())

# ============================================================
# Step 2: Upload and run UDP ping client on DJI RC
# ============================================================
print("\n" + "=" * 60)
print("Step 2: UDP ping from DJI RC through USB tunnel")
print("Each round: send 100 packets, measure RTT")
print("=" * 60)

client_script = """import socket, time, struct
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.settimeout(3)
s.bind(("0.0.0.0", 0))

server = ("10.0.0.1", 9999)
rtts, drp = [], 0
n = 100

for seq in range(n):
    payload = struct.pack("!Qd", seq, time.time())
    s.sendto(payload, server)
    try:
        data, addr = s.recvfrom(256)
        recv = time.time()
        _, sent = struct.unpack("!Qd", data[:16])
        rtts.append((recv - sent) * 1000)
    except:
        drp += 1

s.close()

if rtts:
    rtts.sort()
    a = sum(rtts) / len(rtts)
    i50 = len(rtts)//2
    i95 = int(len(rtts)*0.95)
    i99 = int(len(rtts)*0.99) if len(rtts)>50 else len(rtts)-1
    print("RESULT n=%d drp=%d avg=%.2f p50=%.2f p95=%.2f p99=%.2f min=%.2f max=%.2f" % (n, drp, a, rtts[i50], rtts[i95], rtts[i99], rtts[0], rtts[-1]))
else:
    print("RESULT ALL_DROPPED n=%d drp=%d" % (n, drp))
"""

# Upload client to DJI RC: write locally then adb push
import tempfile, os
tmpf = os.path.join(tempfile.gettempdir(), "ping_test.py")
with open(tmpf, "w") as f:
    f.write(client_script)
subprocess.run(
    ["adb", "-s", DJI, "push", tmpf, "/sdcard/ping_test.py"],
    capture_output=True, text=True, timeout=10
)

# Verify
r = subprocess.run(
    ["adb", "-s", DJI, "shell", "wc -c < /sdcard/ping_test.py"],
    capture_output=True, text=True, timeout=5
)
print(f"Client uploaded: {r.stdout.strip()} bytes")
os.remove(tmpf)

# ============================================================
# Step 3: Run test
# ============================================================
print("\n" + "=" * 60)
print("Running test (100 UDP echo packets through USB tunnel)...")
print("=" * 60)

t0 = time.time()
r = subprocess.run(
    ["adb", "-s", DJI, "shell", "python3 /sdcard/ping_test.py 2>&1"],
    capture_output=True, text=True, timeout=120
)
t1 = time.time()

print(r.stdout.strip())
if r.stderr.strip():
    print("[stderr]", r.stderr.strip()[:500])

# ============================================================
# Step 4: Cleanup + daemon stats
# ============================================================
c.exec_command("killall -9 python3 2>/dev/null; true", timeout=5)
stdin, stdout, stderr = c.exec_command(
    "echo 1234 | sudo -S journalctl -u tun_nat_hub --no-pager -n 2 2>&1",
    timeout=10
)
print("\nDaemon:", stdout.read().decode(errors="replace").strip()[-200:])
c.close()

print("\n" + "=" * 60)
print("Done!")
print("=" * 60)
