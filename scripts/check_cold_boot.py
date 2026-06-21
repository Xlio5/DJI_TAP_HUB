"""Check RK3588 state after cold boot."""
import paramiko, base64, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("172.24.91.129", username="xlong", password="1234", timeout=10)

script = b"""#!/bin/bash
echo "=== IP ==="
ip -br addr show

echo ""
echo "=== Routes ==="
ip route | head -5

echo ""
echo "=== Services ==="
systemctl is-active tun_nat_hub tun_web 2>&1
systemctl is-enabled tun_nat_hub tun_web 2>&1

echo ""
echo "=== USB Gadget ==="
cat /sys/module/g_serial/parameters/idVendor 2>&1
cat /sys/module/g_serial/parameters/idProduct 2>&1
ls -la /dev/ttyGS0 2>&1
lsmod | grep g_serial 2>&1

echo ""
echo "=== TUN ==="
ip -br addr show tun_hub 2>&1

echo ""
echo "=== NAT ==="
echo '1234' | sudo -S iptables -t nat -L POSTROUTING -n 2>&1 | grep MASQUERADE

echo ""
echo "=== NM autoconnect ==="
nmcli -t -f NAME,AUTOCONNECT,STATE connection show 2>&1

echo ""
echo "=== Boot log (last 3 daemon lines) ==="
journalctl -u tun_nat_hub --no-pager -n 3 2>&1
"""

b64 = base64.b64encode(script).decode()
ch = c.get_transport().open_session()
ch.exec_command("base64 -d > /tmp/ckboot.sh")
ch.sendall(b64.encode())
ch.shutdown_write()
ch.recv_exit_status()
ch.close()

stdin, stdout, stderr = c.exec_command("bash /tmp/ckboot.sh", timeout=15, get_pty=True)
out = b""
while not stdout.channel.exit_status_ready():
    if stdout.channel.recv_ready():
        out += stdout.channel.recv(4096)
    time.sleep(0.1)
out += stdout.read()
print(out.decode(errors="replace"))
c.close()
