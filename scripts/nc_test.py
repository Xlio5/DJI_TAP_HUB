"""Netcat throughput test over USB tunnel."""
import paramiko, subprocess, time, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HOST = "172.24.91.28"
DJI_ADB = "172.24.91.112:46561"
S = "echo '1234' | sudo -S"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username="xlong", password="1234", timeout=10)

def ssh(cmd, timeout=10):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    if out.strip(): print(out.strip())

# Kill old
ssh(f"{S} killall nc iperf3 2>/dev/null; true")
time.sleep(0.5)

print("=" * 60)
print("TEST 1: DJI RC -> RK3588 (UPLOAD via USB tunnel)")
print("=" * 60)

# Start nc listener on RK3588
ssh(
    "nohup sh -c 'nc -l -p 9999 > /dev/null' > /tmp/nc_listen.log 2>&1 & echo STARTED",
    timeout=5
)
time.sleep(0.5)
ssh(f"{S} ss -tlnp 2>&1 | grep 9999 || echo 'nc not listening, trying alt...'", timeout=5)

# Send from DJI RC and measure time
print("\nSending 50MB from DJI RC -> RK3588 via USB tunnel (10.0.0.1:9999)...")
t0 = time.time()
r = subprocess.run(
    ["adb", "-s", DJI_ADB, "shell",
     "dd if=/dev/zero bs=4096 count=12800 2>&1 | nc -w 10 10.0.0.1 9999 2>&1; echo DONE"],
    capture_output=True, text=True, timeout=30
)
t1 = time.time()
elapsed = t1 - t0
print(r.stdout.strip())

# Calculate throughput
mb_sent = 50  # 12800 * 4096 = 52,428,800 bytes ~= 50 MB
if elapsed > 0:
    mbps = (mb_sent * 8) / elapsed
    print(f"\n>>> UPLOAD: {mb_sent}MB in {elapsed:.1f}s = {mbps:.1f} Mbps <<<")

# Check if nc received data on RK3588
time.sleep(1)
ssh(f"{S} killall nc 2>/dev/null; true")

print("\n" + "=" * 60)
print("TEST 2: RK3588 -> DJI RC (DOWNLOAD via USB tunnel)")
print("=" * 60)

# Start nc listener on DJI RC
subprocess.run(
    ["adb", "-s", DJI_ADB, "shell", "killall nc 2>/dev/null; true"],
    capture_output=True, timeout=3
)
time.sleep(0.5)
subprocess.Popen(
    ["adb", "-s", DJI_ADB, "shell", "nc -l -p 9998 > /dev/null &"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
time.sleep(1)

# Send from RK3588 to DJI RC
print("\nSending 10MB from RK3588 -> DJI RC via USB tunnel (10.0.0.2:9998)...")
t0 = time.time()
stdin, stdout, stderr = c.exec_command(
    "sh -c 'dd if=/dev/zero bs=1M count=10 2>&1 | timeout 15 nc 10.0.0.2 9998 2>&1; echo DONE'",
    timeout=25
)
out = stdout.read().decode(errors="replace")
t1 = time.time()
elapsed = t1 - t0
print(out.strip())

mb_sent = 10
if elapsed > 0:
    mbps = (mb_sent * 8) / elapsed
    print(f"\n>>> DOWNLOAD: {mb_sent}MB in {elapsed:.1f}s = {mbps:.1f} Mbps <<<")

# Cleanup
subprocess.run(["adb", "-s", DJI_ADB, "shell", "killall nc 2>/dev/null; true"], capture_output=True, timeout=3)
ssh(f"{S} killall nc iperf3 2>/dev/null; true")

# Also check daemon stats
print("\n" + "=" * 60)
print("Daemon stats after tests:")
print("=" * 60)
ssh(f"{S} journalctl -u tun_nat_hub --no-pager -n 3 2>&1", timeout=10)

c.close()
print("\nDone!")
