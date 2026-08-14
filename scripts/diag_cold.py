"""Diagnose why USB not connecting after cold boot."""
import paramiko, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", username="xlong", password="1234", timeout=10)
S = "echo '1234' | sudo -S"

def run(cmd):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=10)
    out = stdout.read().decode(errors="replace")
    if out.strip(): print(out.strip())

print("=== Full daemon log since boot ===")
run(S + " journalctl -u tun_nat_hub --no-pager --since '3 minutes ago' 2>&1")
print()
print("=== USB Gadget state ===")
run("cat /sys/class/udc/fc000000.usb/state 2>/dev/null || cat /sys/class/udc/*/state 2>/dev/null")
print()
print("=== ttyGS0 ===")
run("ls -la /dev/ttyGS0 2>&1")
print()
print("=== g_serial module ===")
run("lsmod | grep g_serial")
print()
print("=== dmesg USB ===")
run("dmesg 2>&1 | grep -iE 'g_serial|gs_tty|gadget|udc' | tail -8")
print()
print("=== Recent daemon stats ===")
run(S + " journalctl -u tun_nat_hub --no-pager -n 3 2>&1")
c.close()
