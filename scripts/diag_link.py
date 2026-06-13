"""Diagnose USB link between RK3588 and DJI RC."""
import paramiko, subprocess, sys

print("=" * 50)
print("=== DJI RC side (ADB) ===")
print("=" * 50)

def adb(cmd):
    r = subprocess.run(["adb", "-s", "172.24.91.112:43081", "shell"] + cmd.split(),
                       capture_output=True, text=True, timeout=10)
    print(f"$ {cmd}")
    print(r.stdout.strip())
    if r.stderr.strip(): print("[e]", r.stderr.strip())
    return r.stdout

adb("ip addr show usb0")
adb("ip route show | grep usb0")
adb("cat /proc/net/arp")

print()
print("=" * 50)
print("=== RK3588 side (SSH) ===")
print("=" * 50)

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("172.24.91.28", username="xlong", password="1234", timeout=10)

S = "echo '1234' | sudo -S"

def ssh(cmd):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=10)
    out = stdout.read().decode()
    err = stderr.read().decode()
    print(f"$ {cmd}")
    if out.strip(): print(out.strip())
    if err.strip(): print("[e]", err.strip())

ssh("ip addr show usb0")
ssh("ip route show | grep usb0")
ssh(f"{S} ip neigh show usb0")
ssh(f"{S} conntrack -L 2>/dev/null | grep usb0 | head -5")
# Check if iptables might be blocking
ssh(f"{S} iptables -L INPUT -n -v 2>&1 | grep -E 'Chain|usb0|DROP|REJECT|192.168'")
ssh(f"{S} iptables -L FORWARD -n -v 2>&1 | grep -E 'Chain|usb0|DROP|REJECT'")

c.close()
print("\nDone")
