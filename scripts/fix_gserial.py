"""Fix: switch RK3588 to g_serial and restart daemon."""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("172.24.91.28", username="xlong", password="1234", timeout=10)

S = "echo '1234' | sudo -S"

def run(cmd):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=10)
    out = stdout.read().decode(errors="replace")
    if out.strip(): print(out.strip())

run("ls -la /dev/ttyGS0 2>&1 || echo no_tty")

# Copy script
run(f"{S} cp /home/xlong/tun_nat_hub/ubuntu/scripts/setup_gadget.sh /usr/local/bin/setup_gadget.sh")
run(f"{S} chmod +x /usr/local/bin/setup_gadget.sh")

# Stop old
run(f"{S} systemctl stop tun_nat_hub 2>/dev/null; true")
run(f"{S} killall usb_tund 2>/dev/null; true")

# Clean and reload g_serial
run(f"{S} modprobe -r g_ether g_rndis g_serial 2>/dev/null; echo cleaned")
time.sleep(1)
run(f"{S} modprobe g_serial use_acm=0 use_obex=0 idVendor=0x0BDA idProduct=0x8812")
time.sleep(2)

run("ls -la /dev/ttyGS0")
run(f"{S} chmod 666 /dev/ttyGS0 2>/dev/null; echo chmod_ok")

# Restart
run(f"{S} systemctl restart tun_nat_hub")
time.sleep(3)
run(f"{S} journalctl -u tun_nat_hub --no-pager -n 10")

print("\nDone - check /dev/ttyGS0 and daemon status")
c.close()
