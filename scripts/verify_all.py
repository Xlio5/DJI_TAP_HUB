"""Quick verify all services on RK3588."""
import paramiko, base64, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", username="xlong", password="1234", timeout=10)

script = b"""#!/bin/bash
echo "tun_nat_hub: $(systemctl is-active tun_nat_hub)"
echo "tun_web: $(systemctl is-active tun_web)"
echo "ttyGS0: $(ls -la /dev/ttyGS0 2>&1)"
echo "end1: $(ip -br addr show end1)"
echo "tun_hub: $(ip -br addr show tun_hub)"
"""

b64 = base64.b64encode(script).decode()
ch = c.get_transport().open_session()
ch.exec_command("base64 -d > /tmp/vfy.sh")
ch.sendall(b64.encode())
ch.shutdown_write()
ch.recv_exit_status()
ch.close()

stdin, stdout, stderr = c.exec_command("bash /tmp/vfy.sh", timeout=10, get_pty=True)
out = b""
while not stdout.channel.exit_status_ready():
    if stdout.channel.recv_ready():
        out += stdout.channel.recv(4096)
    time.sleep(0.1)
out += stdout.read()
print(out.decode(errors="replace"))
c.close()
