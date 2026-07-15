"""V3s 诊断 + 修复 USB/路由"""
import paramiko, sys

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect("192.168.144.66", username="root", password="root", timeout=5)
except Exception as e:
    print("SSH FAIL:", e)
    sys.exit(1)

# Check USB OTG mode (critical for DJI RC connection)
_, o, _ = ssh.exec_command("cat /sys/devices/platform/soc/1c19000.usb/musb-hdrc.2.auto/mode 2>&1", timeout=5)
print("USB MODE:", o.read().decode().strip())

# Check DTB dr_mode
_, o, _ = ssh.exec_command("cat /sys/kernel/debug/usb/musb-hdrc.2.auto/testmode 2>&1; dmesg | grep -i 'dr_mode\|peripheral\|otg\|host mode' | tail -5", timeout=5)
print(o.read().decode().strip())

# Check if default route exists
_, o, _ = ssh.exec_command("ip route | grep default", timeout=5)
gw = o.read().decode().strip()
print("DEFAULT GW:", gw or "MISSING")

# Fix 1: Add default gateway (V3s needs this to route packets)
print("\n=== FIXING ===")
_, o, e = ssh.exec_command(
    "ip route add default via 192.168.144.1 dev eth0 2>&1; "
    "echo 'GW fixed'; "
    "ip route | grep default",
    timeout=5
)
print(o.read().decode().strip())

# Fix 2: Switch USB to peripheral mode (required for DJI RC connection)
_, o, e = ssh.exec_command(
    "echo peripheral > /sys/devices/platform/soc/1c19000.usb/musb-hdrc.2.auto/mode 2>&1; "
    "sleep 1; cat /sys/devices/platform/soc/1c19000.usb/musb-hdrc.2.auto/mode; "
    "echo '---'; cat /sys/class/udc/*/state 2>&1",
    timeout=5
)
print("USB after switch:", o.read().decode().strip())
err = e.read().decode().strip()
if err: print("USB err:", err[:100])

# Fix 3: Verify FORWARD works
_, o, e = ssh.exec_command(
    "iptables -L FORWARD -n -v 2>&1 | grep -E 'tun_hub|eth0'",
    timeout=5
)
print("\nFORWARD check:", o.read().decode().strip())

ssh.close()
