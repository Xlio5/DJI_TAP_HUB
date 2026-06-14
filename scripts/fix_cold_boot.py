"""Fix RK3588 after cold boot: load g_serial + fix CRLF + restart daemon."""
import paramiko, time, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.88.66", username="xlong", password="1234", timeout=10)
S = "echo '1234' | sudo -S"

def run(cmd, timeout=10):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    if out.strip(): print(out.strip().replace("\\n","\n")[:300])

# 1. Load g_serial NOW
print("=== Loading g_serial ===")
run(f"{S} modprobe g_serial use_acm=0 use_obex=0 idVendor=0x0BDA idProduct=0x8812")
time.sleep(2)
run("ls -la /dev/ttyGS0 2>&1")
run(f"{S} chmod 666 /dev/ttyGS0; echo tty_ok")

# 2. Fix setup_gadget.sh permanently (CRLF issue)
print("\n=== Fixing setup_gadget.sh ===")
run(f"{S} cp /home/xlong/tun_nat_hub/ubuntu/scripts/setup_gadget.sh /usr/local/bin/setup_gadget.sh")
# Use python to strip CR from the file on RK3588
strip_cr_cmd = "python3 -c \"data=open('/usr/local/bin/setup_gadget.sh','rb').read(); open('/usr/local/bin/setup_gadget.sh','wb').write(data.replace(b'\\r\\n',b'\\n'))\""
run(strip_cr_cmd)
run(f"{S} chmod +x /usr/local/bin/setup_gadget.sh")
run("file /usr/local/bin/setup_gadget.sh 2>&1")

# Verify it runs
run(f"{S} /usr/local/bin/setup_gadget.sh 2>&1 || echo SCRIPT_FAILED")

# 3. Also fix setup_nat.sh CRLF
strip_nat_cmd = "python3 -c \"data=open('/usr/local/bin/setup_nat.sh','rb').read(); open('/usr/local/bin/setup_nat.sh','wb').write(data.replace(b'\\r\\n',b'\\n'))\""
run(strip_nat_cmd)
run(f"{S} chmod +x /usr/local/bin/setup_nat.sh")

# 4. Restart daemon
print("\n=== Restarting daemon ===")
run(f"{S} systemctl restart tun_nat_hub")
time.sleep(3)

# 5. Final check
print("\n=== Final state ===")
run(f"{S} systemctl status tun_nat_hub --no-pager 2>&1 | head -15")
run("ls -la /dev/ttyGS0 2>&1")
run(f"{S} journalctl -u tun_nat_hub --no-pager -n 6 2>&1")

print("\n=== Done ===")
c.close()
