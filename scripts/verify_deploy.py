"""Final verification of new RK3588 deployment."""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.88.66", username="xlong", password="1234", timeout=10)

def ssh(cmd, timeout=10):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    if out.strip():
        print(out.strip())
    if err.strip():
        for line in err.strip().split("\n"):
            if "password" not in line.lower():
                print("E:", line[:200])

time.sleep(2)
print("=== Service Status ===")
ssh("systemctl is-active tun_nat_hub tun_web 2>&1")

print()
print("=== /dev/ttyGS0 ===")
ssh("ls -la /dev/ttyGS0")

print()
print("=== tun_hub ===")
ssh("ip -br addr show tun_hub")

print()
print("=== NAT ===")
ssh("echo 1234 | sudo -S iptables -t nat -L POSTROUTING -n 2>&1")

print()
print("=== Listening ports ===")
ssh("ss -tlnp | grep -E '8080|9999'")

print()
print("=== Web panel HTTP test ===")
ssh("curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/ 2>&1")

print()
print("=== TCP Echo test ===")
# Use Python on RK3588 for echo test
ssh("python3 -c \"import socket; s=socket.socket(); s.settimeout(2); s.connect(('10.0.0.1', 9999)); s.send(b'ping'); d=s.recv(256); print('ECHO:', d); s.close()\" 2>&1")

print()
print("=== Daemon running stats ===")
ssh("journalctl -u tun_nat_hub --no-pager -n 1 2>&1")

c.close()
print()
print("All checks complete!")
