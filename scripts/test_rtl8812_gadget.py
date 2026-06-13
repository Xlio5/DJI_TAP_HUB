"""Quick test: switch RK3588 g_serial to RTL8812AU VID/PID and check DJI RC."""
import paramiko, time, subprocess

S = "echo '1234' | sudo -S"

print("=== 1. SSH to RK3588, switch gadget ===")
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("172.24.91.28", username="xlong", password="1234", timeout=10)

def ssh(cmd):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=10)
    out = stdout.read().decode(errors='replace')
    err = stderr.read().decode(errors='replace')
    if out.strip(): print(out.strip())
    if err.strip(): print("[e]", err.strip())

# Stop old
ssh(f"{S} systemctl stop tun_nat_hub 2>/dev/null; true")
ssh(f"{S} killall usb_tund 2>/dev/null; true")

# Clean old modules
ssh(f"{S} modprobe -r g_ether g_rndis g_serial 2>/dev/null; echo cleaned")
time.sleep(1)

# Load g_serial with RTL8812AU VID/PID
ssh(f"{S} modprobe g_serial use_acm=0 idVendor=0x0BDA idProduct=0x8812")
time.sleep(2)

# Verify
ssh("ls -la /dev/ttyGS0")
ssh("cat /sys/class/udc/*/state 2>/dev/null || echo no udc state")
ssh("ls /sys/class/tty/ttyGS0/device/driver 2>/dev/null || echo no tty driver")

c.close()

print("\n=== 2. Check DJI RC USB devices ===")
adb = "adb"
dev = "172.24.91.112:46561"
# Reconnect first
subprocess.run([adb, "connect", dev], capture_output=True, timeout=5)
result = subprocess.run([adb, "-s", dev, "shell", "dumpsys usb 2>&1 | grep -A5 'name=/dev/bus/usb' | head -40"],
                       capture_output=True, text=True, timeout=10)
print(result.stdout)
if result.stderr: print("[e]", result.stderr)

# Check specific device
result = subprocess.run([adb, "-s", dev, "shell", "ls /dev/bus/usb/004/ 2>&1"],
                       capture_output=True, text=True, timeout=5)
print("USB bus 004:", result.stdout.strip())

print("\nDone - check if VID=0x0BDA PID=0x8812 appears in dumpsys above")
