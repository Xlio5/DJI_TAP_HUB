"""Update RTSP URL via web API and verify camera."""
import paramiko, urllib.request, json, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 1. Check camera reachability from RK3588
print("=== Checking 192.168.144.101 ===")
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", username="xlong", password="1234", timeout=10)
S = "echo '1234' | sudo -S"
def run(cmd):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=10)
    out = stdout.read().decode(errors="replace")
    if out.strip(): print(out.strip())

run(f"{S} ping -c 2 -W 2 192.168.144.101 2>&1")

# 2. Update via web API
print("\n=== Updating RTSP via Web API ===")
data = json.dumps({"rtsp_url": "rtsp://192.168.144.101:554/stream1"}).encode()
r = urllib.request.urlopen(urllib.request.Request(
    "http://192.168.144.66:8080/api/config/save",
    data=data, headers={"Content-Type": "application/json"}), timeout=10)
print("API response:", r.read().decode())

# 3. Verify config
r = urllib.request.urlopen("http://192.168.144.66:8080/api/config", timeout=5)
cfg = json.loads(r.read())
print("Current RTSP:", cfg["rtsp_url"])

# 4. Clear old conntrack entries
run(f"{S} conntrack -D -d 192.168.144.100 2>/dev/null; echo cleared")

print("\nDone! Now restart DJI RC App and try playing with the new URL.")
c.close()
