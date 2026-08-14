"""Upload latency test script to RK3588 and run it."""
import paramiko, base64, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", username="xlong", password="1234", timeout=10)

def run(cmd, timeout=10):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    if out.strip(): print(out.strip())

# The test script that runs on RK3588
test_script = r"""#!/usr/bin/env python3
import socket, time, struct, subprocess, sys

N = 30

print("=" * 50)
print("TEST 1: Local loopback echo (reference)")
print("=" * 50)
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.settimeout(2)
rtts = []
for i in range(N):
    payload = struct.pack("!Qd", i, time.time())
    s.sendto(payload, ("10.0.0.1", 9999))
    try:
        data, addr = s.recvfrom(256)
        recv = time.time()
        _, sent = struct.unpack("!Qd", data[:16])
        rtts.append((recv - sent) * 1000)
    except socket.timeout:
        pass
s.close()

if rtts:
    rtts.sort()
    valid = len(rtts)
    avg = sum(rtts) / valid
    print(f"  Local echo RTT: avg={avg:.2f}ms p50={rtts[valid//2]:.2f}ms min={rtts[0]:.2f}ms max={rtts[-1]:.2f}ms")
    print(f"  (This is RK3588 -> local kernel -> echo. Should be ~0.05ms)")
else:
    print("  FAILED")

print()
print("=" * 50)
print("TEST 2: Camera ping (LAN)")
print("=" * 50)
r = subprocess.run(["ping", "-c", "10", "192.168.144.101"], capture_output=True, text=True, timeout=15)
for line in r.stdout.split("\n"):
    if "rtt" in line.lower() or "packet" in line.lower() or "avg" in line.lower():
        print("  " + line.strip())

print()
print("=" * 50)
print("TEST 3: Camera TCP connect time (port 554)")
print("=" * 50)
connects = []
for i in range(10):
    try:
        t0 = time.time()
        sock = socket.socket()
        sock.settimeout(3)
        sock.connect(("192.168.144.101", 554))
        t1 = time.time()
        sock.close()
        connects.append((t1 - t0) * 1000)
    except:
        pass
if connects:
    connects.sort()
    avg = sum(connects) / len(connects)
    print(f"  TCP connect RTT: avg={avg:.2f}ms min={connects[0]:.2f}ms max={connects[-1]:.2f}ms")
else:
    print("  FAILED")

print()
print("=" * 50)
print("TEST 4: Daemon stats snapshot")
print("=" * 50)
r = subprocess.run(
    "echo '1234' | sudo -S journalctl -u tun_nat_hub --no-pager -n 2 2>/dev/null",
    shell=True, capture_output=True, text=True, timeout=5
)
for line in r.stdout.strip().split("\n"):
    if "TX=" in line:
        print("  " + line.strip())

print()
print("=" * 50)
print("SUMMARY")
print("=" * 50)
print("USB Tunnel RTT  = (your 330ms total) - (camera encode ~80-150ms) - (decode ~10-20ms)")
print("To isolate further: measure glass-to-glass with a stopwatch app")
"""

b64 = base64.b64encode(test_script.encode()).decode()
cmd = "python3 -c 'import base64,sys; d=base64.b64decode(sys.stdin.read()); open(\"/home/xlong/latency_test.py\",\"w\").write(d.decode()); print(\"OK\")'"

transport = c.get_transport()
chan = transport.open_session()
chan.exec_command(cmd)
chan.sendall(b64.encode())
chan.shutdown_write()
chan.recv_exit_status()
chan.close()

# Run the test
print("=== Running latency tests on RK3588 ===\n")
stdin, stdout, stderr = c.exec_command("python3 /home/xlong/latency_test.py", timeout=30)
print(stdout.read().decode(errors="replace"))
c.close()
