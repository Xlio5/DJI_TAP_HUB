"""Deep USB diagnostic on DJI RC via RK3588 ADB."""
import paramiko, base64, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", username="xlong", password="1234", timeout=10)

# Write diagnostic script to RK3588
script = r"""#!/bin/bash
echo '=== USB bus scan ==='
adbt=$(timeout 5 adb -s 10.248.133.209:5555 shell 'ls -laR /dev/bus/usb/' 2>&1 || true)
echo "$adbt" | head -20

echo ''
echo '=== host_manager devices ==='
adbt=$(timeout 5 adb -s 10.248.133.209:5555 shell 'dumpsys usb' 2>&1 || true)
echo "$adbt" | grep -A1 '"devices"' | head -5
echo "$adbt" | grep 'vendor_id\|product_id\|0bda\|0x0bda\|8812\|3034\|34834' | head -10

echo ''
echo '=== App logcat ==='
timeout 3 adb -s 10.248.133.209:5555 logcat -d 2>&1 | grep -i 'UsbBridge\|TunNatHub\|tunnathub' | tail -10 || true

echo ''
echo '=== Check if ADB is alive ==='
adb devices 2>&1
"""

b64 = base64.b64encode(script.encode()).decode()
ch = c.get_transport().open_session()
ch.exec_command("base64 -d > /tmp/diag_dji.sh")
ch.sendall(b64.encode())
ch.shutdown_write()
ch.recv_exit_status()
ch.close()

s1, s2, s3 = c.exec_command("bash /tmp/diag_dji.sh", timeout=15, get_pty=True)
time.sleep(4)
out = b""
while s2.channel.recv_ready():
    out += s2.channel.recv(4096)
try:
    out += s2.read()
except:
    pass
print(out.decode(errors="replace"))
c.close()
