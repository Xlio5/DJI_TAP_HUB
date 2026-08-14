"""Grant USB permission to our app on DJI RC."""
import paramiko, base64, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", username="xlong", password="1234", timeout=10)

script = r"""#!/bin/bash
echo '=== Force stop and restart app ==='
adb -s 10.248.133.209:5555 shell 'am force-stop com.tunnathub.app' 2>&1

echo '=== Check device_filter.xml in app ==='
adb -s 10.248.133.209:5555 shell 'dumpsys package com.tunnathub.app' 2>&1 | grep -i 'usb\|device_filter\|intent' | head -10

echo ''
echo '=== Launch app to trigger USB permission flow ==='
adb -s 10.248.133.209:5555 shell 'am start -n com.tunnathub.app/.MainActivity' 2>&1

sleep 3

echo ''
echo '=== Check USB permissions after app start ==='
adb -s 10.248.133.209:5555 shell 'dumpsys usb' 2>&1 | grep -A10 'permissions_manager' | head -15

echo ''
echo '=== App logcat ==='
adb -s 10.248.133.209:5555 logcat -d 2>&1 | grep -i 'UsbBridge\|TunNatHub\|USB\|Permission' | tail -15 || echo 'NO LOGS'
"""

b64 = base64.b64encode(script.encode()).decode()
ch = c.get_transport().open_session()
ch.exec_command("base64 -d > /tmp/grant.sh")
ch.sendall(b64.encode())
ch.shutdown_write()
ch.recv_exit_status()
ch.close()

s1, s2, s3 = c.exec_command("bash /tmp/grant.sh", timeout=20, get_pty=True)
time.sleep(5)
out = b""
while s2.channel.recv_ready():
    out += s2.channel.recv(4096)
try:
    out += s2.read()
except:
    pass
print(out.decode(errors="replace"))
c.close()
