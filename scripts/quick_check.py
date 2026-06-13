"""Quick check RK3588 daemon state."""
import paramiko
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("172.24.91.28", username="xlong", password="1234", timeout=10)

def run(cmd):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=10)
    out = stdout.read().decode()
    err = stderr.read().decode()
    if out.strip(): print(out.strip())
    if err.strip(): print("[e]", err.strip())

run("echo 1234 | sudo -S ss -tunlp 2>&1 | grep 8899")
run("echo ---")
run("echo 1234 | sudo -S journalctl -u tun_nat_hub --no-pager -n 8 2>&1")
print("\n--- TUN state ---")
run("ip addr show tun_hub 2>&1 | head -8")
c.close()
