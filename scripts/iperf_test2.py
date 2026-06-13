"""Reliable throughput test using nc + dd + timer."""
import paramiko, subprocess, time, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HOST = "172.24.91.28"
DJI = "172.24.91.112:46561"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username="xlong", password="1234", timeout=10)
S = "echo '1234' | sudo -S"

def ssh(cmd, timeout=10):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    return out

# Kill everything
ssh(f"{S} killall -9 iperf3 python3 nc 2>/dev/null; true")
time.sleep(0.5)

# ---- UPLOAD test: DJI -> RK3588 ----
print("=" * 60)
print("UPLOAD: DJI RC -> RK3588 (50MB via USB tunnel)")
print("=" * 60)

# Start nc listener on RK3588, pipe to /dev/null, count bytes with wc
# The key: keep nc running and accept ONE connection
ssh("""
nohup sh -c '
  nc -l -p 9998 2>&1 | dd of=/dev/null bs=1M status=progress 2>/tmp/dd_out.txt
  echo "DD_EXIT=\$?" > /tmp/dd_exit.txt
' > /tmp/nc_bg.log 2>&1 &
echo "NC_PID=\$!"
""", timeout=5)
time.sleep(0.5)

# Verify listener
out = ssh(f"{S} ss -tlnp 2>&1 | grep 9998; echo '---'; ps aux | grep 'nc -l' | grep -v grep")
print("Listener status:", out.strip()[:200])

# Send from DJI RC
print("\nSending 50MB...")
t0 = time.time()
r = subprocess.run(
    ["adb", "-s", DJI, "shell",
     "dd if=/dev/zero bs=1M count=50 2>&1 | nc -w 20 10.0.0.1 9998 2>&1; echo NC_EXIT=\$?"],
    capture_output=True, text=True, timeout=30
)
t1 = time.time()
elapsed = t1 - t0

print(r.stdout.strip())
if elapsed > 0:
    mbps = (50 * 8) / elapsed
    print(f">>> UPLOAD: 50MB in {elapsed:.1f}s = {mbps:.1f} Mbps <<<")

# Check what RK3588 received
time.sleep(1)
out = ssh("cat /tmp/dd_out.txt 2>/dev/null; echo '---'; cat /tmp/dd_exit.txt 2>/dev/null")
print("\nRK3588 receiver output:", out.strip()[:500])

# Check daemon stats
out = ssh(f"{S} journalctl -u tun_nat_hub --no-pager -n 1 2>&1")
print("\nDaemon:", out.strip()[-120:])

# Clean
ssh(f"{S} killall nc 2>/dev/null; true")

# ---- DOWNLOAD test: RK3588 -> DJI ----
print("\n" + "=" * 60)
print("DOWNLOAD: RK3588 -> DJI RC (10MB via USB tunnel)")
print("=" * 60)

# Start nc listener on DJI RC (pipe to /dev/null)
subprocess.Popen(
    ["adb", "-s", DJI, "shell", "nc -l -p 9996 > /dev/null &"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
time.sleep(0.5)

# Send from RK3588 to DJI RC through tunnel
print("Sending 10MB...")
t0 = time.time()
stdin, stdout, stderr = c.exec_command(
    "sh -c 'dd if=/dev/zero bs=1M count=10 2>/tmp/dd_send.txt | nc -w 15 10.0.0.2 9996 2>&1; echo SEND_DONE'",
    timeout=25
)
out = stdout.read().decode(errors="replace")
t1 = time.time()
elapsed = t1 - t0

print(out.strip())
# Get dd output
out2 = ssh("cat /tmp/dd_send.txt 2>/dev/null")
print(out2.strip())

if elapsed > 0:
    mbps = (10 * 8) / elapsed
    print(f">>> DOWNLOAD: 10MB in {elapsed:.1f}s = {mbps:.1f} Mbps <<<")

# Cleanup
subprocess.run(["adb", "-s", DJI, "shell", "killall nc 2>/dev/null; true"], capture_output=True, timeout=3)
ssh(f"{S} killall nc 2>/dev/null; true")

# Final daemon stats
print("\n" + "=" * 60)
out = ssh(f"{S} journalctl -u tun_nat_hub --no-pager -n 1 2>&1")
print("Final daemon stats:", out.strip()[-150:])

c.close()
print("\nDone!")
