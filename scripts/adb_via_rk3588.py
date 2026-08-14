"""Scan DJI RC ADB ports from RK3588 and install APK."""
import paramiko, time

DJI_IP = "10.248.133.209"
RK3588 = "192.168.144.66"
APK_REMOTE = "/tmp/app-debug.apk"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(RK3588, username="xlong", password="1234", timeout=10)

# Verify APK exists
s1, s2, s3 = c.exec_command("ls -la " + APK_REMOTE)
out = s2.read().decode(errors="replace").strip()
print("APK:", out[:100])

# Scan ports using Python on RK3588 (avoids bash /dev/tcp issues)
scan_script = """
import socket
ports = [5555, 43319, 40333, 46405, 46495, 33625]
for port in ports:
    s = socket.socket()
    s.settimeout(2)
    try:
        s.connect(('""" + DJI_IP + """', port))
        print('PORT_OPEN:' + str(port))
        s.close()
    except:
        pass
"""

import base64
b64 = base64.b64encode(scan_script.encode()).decode()
ch = c.get_transport().open_session()
ch.exec_command("base64 -d > /tmp/scan.py")
ch.sendall(b64.encode())
ch.shutdown_write()
ch.recv_exit_status()
ch.close()

s1, s2, s3 = c.exec_command("python3 /tmp/scan.py", timeout=15)
scan_result = s2.read().decode(errors="replace").strip()
print("Scan:", scan_result)

# Try ADB on open ports
for line in scan_result.split("\n"):
    line = line.strip()
    if line.startswith("PORT_OPEN:"):
        port = line.split(":")[1]
        print("Trying ADB on port", port)
        s1, s2, s3 = c.exec_command(
            "timeout 8 adb connect " + DJI_IP + ":" + port + " 2>&1",
            timeout=12)
        result = s2.read().decode(errors="replace").strip()
        print("  ADB:", result)

        if "connected" in result.lower():
            # Install APK
            print("  Installing APK...")
            s1, s2, s3 = c.exec_command(
                "adb -s " + DJI_IP + ":" + port + " install -r " + APK_REMOTE + " 2>&1",
                timeout=120)
            install = s2.read().decode(errors="replace").strip()
            print("  Install:", install)
            break

c.close()
