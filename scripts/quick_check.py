"""Quick check RK3588 daemon state."""
import paramiko, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("172.24.91.28", username="xlong", password="1234", timeout=10)

def run(cmd):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=10)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    if out.strip(): print(out.strip())
    if err.strip(): print("[e]", err.strip())

run("echo 1234 | sudo -S journalctl -u tun_nat_hub --no-pager -n 10 2>&1")
print("---")
run("ip addr show tun_hub | grep -E 'inet|state'")
run("ls -la /dev/ttyGS0 2>&1")
run("lsmod | grep g_serial")
run("echo 1234 | sudo -S systemctl status tun_nat_hub --no-pager | head -5")
c.close()
