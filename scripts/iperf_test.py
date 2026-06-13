"""Run iperf3 throughput test over USB tunnel."""
import paramiko, subprocess, time, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RK = "172.24.91.28"
DJI = "172.24.91.112:46561"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(RK, username="xlong", password="1234", timeout=10)
S = "echo '1234' | sudo -S"

def ssh(cmd, timeout=10):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    if out.strip(): print(out.strip())

def adb(cmd, timeout=15):
    # kill old and restart
    r = subprocess.run(["adb", "-s", DJI, "shell"] + cmd.split(),
                       capture_output=True, text=True, timeout=timeout)
    if r.stdout.strip(): print(r.stdout.strip())
    if r.stderr.strip(): print("[e]", r.stderr.strip())
    return r.stdout

# Clean
ssh(f"{S} killall iperf3 2>/dev/null; true")
time.sleep(0.5)

# Start iperf3 server on RK3588
print("=" * 50)
print("Starting iperf3 server on RK3588...")
print("=" * 50)
ssh("iperf3 -s -p 5201 -1 --json 2>&1 &", timeout=3)
time.sleep(1.5)
ssh("ps aux | grep iperf3 | grep -v grep")

# --- Test 1: DJI -> RK3588 TUN (10.0.0.1) ---
print("\n" + "=" * 50)
print("Test 1: DJI RC -> RK3588 TUN (10.0.0.1) via USB")
print("Direction: UPLOAD (Android -> RK3588)")
print("=" * 50)
adb("iperf3 -c 10.0.0.1 -p 5201 -t 10 -i 2 -P 1 2>&1", timeout=25)

# Restart server
ssh(f"{S} killall iperf3 2>/dev/null; true")
time.sleep(0.5)
ssh("iperf3 -s -p 5201 -1 --json 2>&1 &", timeout=3)
time.sleep(1.5)

# --- Test 2: Reverse direction (RK3588 -> DJI) ---
print("\n" + "=" * 50)
print("Test 2: RK3588 -> DJI RC (Reverse)")
print("Direction: DOWNLOAD (RK3588 -> Android)")
print("=" * 50)
adb("iperf3 -c 10.0.0.1 -p 5201 -t 10 -i 2 -P 1 -R 2>&1", timeout=25)

ssh(f"{S} killall iperf3 2>/dev/null; true")
c.close()

# --- Test 3: nc simple throughput ---
print("\n" + "=" * 50)
print("Test 3: Netcat /dev/zero throughput test")
print("Receive side: DJI RC nc -> /dev/null")
print("Send side: RK3588 dd -> nc")
print("=" * 50)

# Start nc listener on DJI RC (background)
subprocess.Popen(["adb", "-s", DJI, "shell", "nc -l -p 9999 > /dev/null &"],
                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(0.5)

c2 = paramiko.SSHClient()
c2.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c2.connect(RK, username="xlong", password="1234", timeout=10)

# Send from RK3588 to DJI RC via tunnel
print("Sending 10MB via nc through tunnel (10.0.0.2:9999)...")
stdin, stdout, stderr = c2.exec_command(
    "dd if=/dev/zero bs=1M count=10 2>&1 | timeout 10 nc 10.0.0.2 9999 2>&1; echo DONE",
    timeout=25)
out = stdout.read().decode(errors="replace")
print(out)
c2.close()

# Cleanup
subprocess.run(["adb", "-s", DJI, "shell", "killall nc 2>/dev/null"],
              capture_output=True, timeout=3)

print("\n=== All tests done ===")
