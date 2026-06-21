"""Diagnose why end1 wired network lost IP after cold boot."""
import paramiko, base64, time

HOST = "172.24.91.129"  # WiFi IP

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username="xlong", password="1234", timeout=10)

script = """#!/bin/bash
echo '=== interfaces ==='
ip -br addr show

echo ''
echo '=== routes ==='
ip route

echo ''
echo '=== NM connections ==='
nmcli -t -f NAME,DEVICE,TYPE,AUTOCONNECT,STATE connection show 2>&1

echo ''
echo '=== NM end1 detail ==='
nmcli -t connection show 'Profile 1' 2>&1 | head -20
nmcli -t connection show 'Wired connection 1' 2>/dev/null | head -20

echo ''
echo '=== journalctl network boot ==='
journalctl -b --no-pager 2>&1 | grep -iE 'NetworkManager.*end1|dhcp.*end1|end1.*up|end1.*carrier|end1.*link' | head -15

echo ''
echo '=== dmesg end1 ==='
dmesg 2>&1 | grep -iE 'end1|dwmac|rk_gmac' | head -10
"""

b64 = base64.b64encode(script.encode()).decode()
ch = c.get_transport().open_session()
ch.exec_command("base64 -d > /tmp/netdiag.sh")
ch.sendall(b64.encode())
ch.shutdown_write()
ch.recv_exit_status()
ch.close()

stdin, stdout, stderr = c.exec_command("bash /tmp/netdiag.sh", timeout=10, get_pty=True)
out = b""
while not stdout.channel.exit_status_ready():
    if stdout.channel.recv_ready(): out += stdout.channel.recv(4096)
    time.sleep(0.1)
out += stdout.read()
print(out.decode(errors="replace"))
c.close()
