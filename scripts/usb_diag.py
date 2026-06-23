"""Diagnose USB on both sides."""
import paramiko, base64, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.88.66", username="xlong", password="1234", timeout=10)

# Check RK3588 side
diag = b"""#!/bin/bash
echo '=== VID:PID ==='
cat /sys/module/g_serial/parameters/idVendor 2>&1
cat /sys/module/g_serial/parameters/idProduct 2>&1
echo ''
echo '=== ttyGS0 ==='
ls -la /dev/ttyGS0 2>&1
echo ''
echo '=== daemon ==='
systemctl is-active tun_nat_hub 2>&1
echo ''
echo '=== dmesg tail ==='
dmesg 2>&1 | grep -i 'g_serial\\|ttyGS\\|gadget' | tail -5
echo ''
echo '=== lsusb ==='
lsusb 2>&1
"""

b64 = base64.b64encode(diag).decode()
ch = c.get_transport().open_session()
ch.exec_command("base64 -d > /tmp/usbdiag.sh")
ch.sendall(b64.encode())
ch.shutdown_write()
ch.recv_exit_status()
ch.close()

s1, s2, s3 = c.exec_command("bash /tmp/usbdiag.sh", timeout=10, get_pty=True)
time.sleep(2)
out = b""
while s2.channel.recv_ready(): out += s2.channel.recv(4096)
try: out += s2.read()
except: pass
print(out.decode(errors="replace")[:600])

# Check DJI RC via ADB
s1, s2, s3 = c.exec_command("adb -s 10.248.133.209:5555 shell lsusb 2>&1", timeout=10)
time.sleep(2)
out2 = b""
while s2.channel.recv_ready(): out2 += s2.channel.recv(4096)
try: out2 += s2.read()
except: pass
print("DJI lsusb:", out2.decode(errors="replace")[:500])

# Check DJI USB permissions for our app
s1, s2, s3 = c.exec_command(
    "adb -s 10.248.133.209:5555 shell dumpsys usb 2>&1 | grep -A3 -B1 '0bda\\|8812\\|permissions_manager\\|10113'",
    timeout=10)
time.sleep(2)
out3 = b""
while s2.channel.recv_ready(): out3 += s2.channel.recv(4096)
try: out3 += s2.read()
except: pass
print("DJI perms:", out3.decode(errors="replace")[:500])

c.close()
