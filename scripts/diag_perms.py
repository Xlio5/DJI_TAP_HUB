"""Check USB permissions on DJI RC."""
import paramiko, base64, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", username="xlong", password="1234", timeout=10)

script = r"""#!/bin/bash
echo '=== USB device node perms ==='
adb -s 10.248.133.209:5555 shell 'ls -laR /dev/bus/usb/' 2>&1

echo ''
echo '=== dumpsys permissions_manager ==='
adb -s 10.248.133.209:5555 shell 'dumpsys usb' 2>&1 | grep -A20 'permissions_manager' | head -25

echo ''
echo '=== our app uid ==='
adb -s 10.248.133.209:5555 shell 'dumpsys package com.tunnathub.app' 2>&1 | grep 'userId=' | head -3

echo ''
echo '=== USB device preferences ==='
adb -s 10.248.133.209:5555 shell 'dumpsys usb' 2>&1 | grep -A5 'device_preferences' | head -10
"""

b64 = base64.b64encode(script.encode()).decode()
ch = c.get_transport().open_session()
ch.exec_command("base64 -d > /tmp/diag_perms.sh")
ch.sendall(b64.encode())
ch.shutdown_write()
ch.recv_exit_status()
ch.close()

s1, s2, s3 = c.exec_command("bash /tmp/diag_perms.sh", timeout=15, get_pty=True)
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
