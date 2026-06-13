"""Simple latency test: UDP echo via shell tools on DJI RC."""
import paramiko, subprocess, time, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HOST = "172.24.91.28"
DJI = "172.24.91.112:46495"

# 1. Ensure server is running on RK3588
print("=== Checking echo server on RK3588 ===")
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username="xlong", password="1234", timeout=10)

stdin,stdout,stderr = c.exec_command("ss -tulnp 2>/dev/null | grep 9999", timeout=5)
print(stdout.read().decode(errors="replace").strip())

print("\n=== Test 1: Single UDP echo via nc ===")
# Send a timestamped packet from DJI RC, get echo back, measure
# The trick: send a packet with "PING", server echoes "PING" back
test_cmd = """end=$(($(date +%s%N)+5000000000)); while [ $(date +%s%N) -lt $end ]; do echo PING | nc -u -w 1 10.0.0.1 9999 2>/dev/null; done; echo DONE"""
r = subprocess.run(["adb", "-s", DJI, "shell", test_cmd], capture_output=True, text=True, timeout=15)
print(r.stdout[:200])

print("\n=== Test 2: Measure round-trip via shell timing ===")
# Use a tighter loop with individual measurements
script = """
for i in $(seq 1 30); do
    t0=$(date +%s%N)
    echo PING | nc -u -w 2 10.0.0.1 9999 2>/dev/null
    t1=$(date +%s%N)
    echo "$(( ($t1 - $t0) / 1000000 ))"
done
"""
r = subprocess.run(["adb", "-s", DJI, "shell", script], capture_output=True, text=True, timeout=60)
lines = [l.strip() for l in r.stdout.strip().split("\n") if l.strip().isdigit()]
if lines:
    vals = [int(l) for l in lines]
    vals.sort()
    avg = sum(vals)/len(vals)
    print(f"  Samples: {len(vals)}")
    print(f"  Min: {vals[0]}ms  Max: {vals[-1]}ms")
    print(f"  Avg: {avg:.1f}ms  P50: {vals[len(vals)//2]}ms")
    print(f"  P95: {vals[int(len(vals)*0.95)]}ms")
else:
    print(f"  No valid measurements. Raw output: {r.stdout[:300]}")

c.close()
