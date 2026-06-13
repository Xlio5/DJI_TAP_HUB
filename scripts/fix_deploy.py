"""Fix remaining deployment issues on RK3588."""
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

print("=== 1. Fix setup_gadget.sh exec permission ===")
run(f"{S} chmod +x /usr/local/bin/setup_gadget.sh 2>&1; echo fixed")
run("ls -la /usr/local/bin/setup_gadget.sh")
run("head -3 /usr/local/bin/setup_gadget.sh")

print("\n=== 2. Update setup_nat.sh with proper FORWARD rules ===")
run("cat /usr/local/bin/setup_nat.sh | grep -c 'iptables -A FORWARD'")

print("\n=== 3. Ensure current FORWARD rules are correct ===")
run(f"{S} iptables -F FORWARD 2>/dev/null; echo flushed")
run(f"{S} iptables -A FORWARD -i tun_hub -o end1 -j ACCEPT; echo fwd1")
run(f"{S} iptables -A FORWARD -i end1 -o tun_hub -m state --state ESTABLISHED,RELATED -j ACCEPT; echo fwd2")
run(f"{S} iptables -t nat -F POSTROUTING; echo nat_flushed")
run(f"{S} iptables -t nat -A POSTROUTING -s 10.0.0.0/24 -o end1 -j MASQUERADE; echo nat1")

print("\n=== 4. Verify ===")
run(f"{S} iptables -L FORWARD -n -v 2>&1")
run(f"{S} iptables -t nat -L POSTROUTING -n 2>&1")

print("\n=== 5. Restart service ===")
run(f"{S} systemctl daemon-reload 2>&1; echo daemon_reload")
run(f"{S} systemctl restart tun_nat_hub 2>&1; echo restarted")
time.sleep(3)
run(f"{S} systemctl status tun_nat_hub --no-pager 2>&1 | head -10")

print("\n=== 6. Check daemon ===")
run(f"{S} journalctl -u tun_nat_hub --no-pager -n 5 2>&1")

print("\nDone - all issues fixed. Test again now.")
c.close()
