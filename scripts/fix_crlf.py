"""Fix CRLF and restart service on RK3588."""
import paramiko, time, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("172.24.91.28", username="xlong", password="1234", timeout=10)
S = "echo '1234' | sudo -S"

def run(cmd, timeout=10):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    if out.strip(): print(out.strip())

# Fix CRLF
run(f"file /usr/local/bin/setup_gadget.sh")
run(f"{S} sed -i 's/\\r$//' /usr/local/bin/setup_gadget.sh; echo fixed")
run(f"{S} sed -i 's/\\r$//' /usr/local/bin/setup_nat.sh; echo fixed_nat")
run(f"file /usr/local/bin/setup_gadget.sh")

# Restart
run(f"{S} systemctl restart tun_nat_hub; echo restarted")
time.sleep(2)
run(f"{S} systemctl status tun_nat_hub --no-pager 2>&1 | head -12")
run(f"{S} journalctl -u tun_nat_hub --no-pager -n 5")

print("\nDone")
c.close()
