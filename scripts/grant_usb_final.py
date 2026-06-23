"""Fix USB permission on DJI RC."""
import paramiko, base64, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.88.66", username="xlong", password="1234", timeout=10)

script = r"""#!/bin/bash
echo '=== Our app UID ==='
adb -s 10.248.133.209:5555 shell 'dumpsys package com.tunnathub.app' 2>&1 | grep 'userId=' | head -3

echo ''
echo '=== Clear USB permissions cache ==='
adb -s 10.248.133.209:5555 shell 'pm clear com.tunnathub.app' 2>&1 || true

echo ''
echo '=== Re-install APK ==='
adb -s 10.248.133.209:5555 install -r /tmp/app-debug.apk 2>&1

echo ''
echo '=== Re-launch app ==='
adb -s 10.248.133.209:5555 shell 'am start -n com.tunnathub.app/.MainActivity' 2>&1

sleep 3

echo ''
echo '=== Check permissions again ==='
adb -s 10.248.133.209:5555 shell 'dumpsys usb' 2>&1 | grep -A10 'permissions_manager' | head -20

echo ''
echo '=== Check our app logcat ==='
adb -s 10.248.133.209:5555 logcat -d 2>&1 | grep -i 'tunnathub\|UsbBridge\|MainActivity' | tail -15 || echo 'NO LOGS'
"""

b64 = base64.b64encode(script.encode()).decode()
ch = c.get_transport().open_session()
ch.exec_command("base64 -d > /tmp/grant2.sh")
ch.sendall(b64.encode())
ch.shutdown_write()
ch.recv_exit_status()
ch.close()

s1, s2, s3 = c.exec_command("bash /tmp/grant2.sh", timeout=60, get_pty=True)
time.sleep(8)
out = b""
while s2.channel.recv_ready():
    out += s2.channel.recv(4096)
try:
    out += s2.read()
except:
    pass
print(out.decode(errors="replace"))
c.close()
