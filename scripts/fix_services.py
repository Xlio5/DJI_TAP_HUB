"""Fix remaining services on new RK3588."""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", username="xlong", password="1234", timeout=10)

def ssh(cmd, timeout=10):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    merged = (out + err).strip()
    if merged:
        for line in merged.split("\n"):
            if "password" not in line.lower():
                print(line)

# Check tun_web
print("=== tun_web status ===")
ssh("systemctl status tun_web --no-pager -l 2>&1 | head -15")

# Check web_panel.py first line (shebang)
print()
print("=== web_panel.py shebang ===")
ssh("head -1 /home/xlong/web_panel.py")
ssh("which python3")

# Start echo server
print()
print("=== Starting TCP echo server ===")
ssh("killall -9 python3 2>/dev/null; true")
time.sleep(0.5)
ssh("nohup python3 /home/xlong/echo_srv.py > /home/xlong/echo_out.txt 2>&1 &")
time.sleep(1.5)
ssh("cat /home/xlong/echo_out.txt")

# Restart web
print()
print("=== Restarting tun_web ===")
ssh("echo 1234 | sudo -S systemctl restart tun_web 2>&1")
time.sleep(3)
ssh("systemctl is-active tun_web tun_nat_hub 2>&1")

# Port check
print()
print("=== Listening ports ===")
ssh("ss -tlnp 2>&1 | grep -E '8080|9999'")

# Web test
print()
print("=== Web HTTP test ===")
ssh("curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/ 2>&1")

# Echo test using separate Python script
print()
print("=== TCP echo test ===")
test_script = (
    "import socket; "
    "s = socket.socket(); "
    "s.settimeout(2); "
    "s.connect(('10.0.0.1', 9999)); "
    "s.send(b'ping'); "
    "r = s.recv(256); "
    "print('ECHO:', r); "
    "s.close()"
)
ssh("python3 -c '{}'".format(test_script))

print()
print("=== Final summary ===")
ssh("echo '--- tun_nat_hub:' && systemctl is-active tun_nat_hub")
ssh("echo '--- tun_web:' && systemctl is-active tun_web")
ssh("echo '--- ttyGS0:' && ls -la /dev/ttyGS0")
ssh("echo '--- tun_hub:' && ip -br addr show tun_hub")

c.close()
