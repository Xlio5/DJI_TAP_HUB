"""Permanently fix CRLF + cold boot issues on RK3588."""
import paramiko, base64, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HOST = "192.168.144.66"
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username="xlong", password="1234", timeout=10)
S = "echo '1234' | sudo -S"

def run(cmd, timeout=10):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    if out.strip(): print(out.strip())

# ---- Step 1: Strip CR from existing files ----
print("=== 1. Strip CR from existing scripts ===")
run(f"{S} tr -d '\\r' < /usr/local/bin/setup_gadget.sh > /tmp/gadget_clean.sh")
run(f"{S} cp /tmp/gadget_clean.sh /usr/local/bin/setup_gadget.sh")
run(f"{S} tr -d '\\r' < /usr/local/bin/setup_nat.sh > /tmp/nat_clean.sh")
run(f"{S} cp /tmp/nat_clean.sh /usr/local/bin/setup_nat.sh")
run(f"{S} chmod +x /usr/local/bin/setup_gadget.sh /usr/local/bin/setup_nat.sh")
print("---")
run("file /usr/local/bin/setup_gadget.sh")
run("file /usr/local/bin/setup_nat.sh")

# ---- Step 2: Verify scripts run ----
print("\n=== 2. Verify script execution ===")
run(f"{S} /usr/local/bin/setup_gadget.sh 2>&1")

# ---- Step 3: Also upload clean scripts from local ----
print("\n=== 3. Upload clean scripts (LF) from local copy ===")
# Read local file, ensure LF
with open("c:/my_project/TUN_NAT_HUB/ubuntu/scripts/setup_gadget.sh", "rb") as f:
    content = f.read().decode().replace("\r\n", "\n").replace("\r", "\n")

# Write via base64 pipe
b64 = base64.b64encode(content.encode()).decode()
cmd = "python3 -c \"import base64,sys; data=base64.b64decode(sys.stdin.read()); open('/tmp/gadget_new.sh','wb').write(data)\""
transport = c.get_transport()
chan = transport.open_session()
chan.exec_command(cmd)
chan.sendall(b64.encode())
chan.shutdown_write()
rc = chan.recv_exit_status()
chan.close()
print(f"Upload setup_gadget.sh: exit={rc}")

if rc == 0:
    run(f"{S} cp /tmp/gadget_new.sh /usr/local/bin/setup_gadget.sh")
    run(f"{S} chmod +x /usr/local/bin/setup_gadget.sh")

# Upload setup_nat.sh same way
with open("c:/my_project/TUN_NAT_HUB/ubuntu/scripts/setup_nat.sh", "rb") as f:
    nat_content = f.read().decode().replace("\r\n", "\n").replace("\r", "\n")
nat_b64 = base64.b64encode(nat_content.encode()).decode()
chan2 = transport.open_session()
chan2.exec_command("python3 -c \"import base64,sys; data=base64.b64decode(sys.stdin.read()); open('/tmp/nat_new.sh','wb').write(data)\"")
chan2.sendall(nat_b64.encode())
chan2.shutdown_write()
chan2.recv_exit_status()
chan2.close()

run(f"{S} cp /tmp/nat_new.sh /usr/local/bin/setup_nat.sh")
run(f"{S} chmod +x /usr/local/bin/setup_nat.sh")

# ---- Step 4: Final verification ----
print("\n=== 4. Final verification ===")
run("file /usr/local/bin/setup_gadget.sh")
run("file /usr/local/bin/setup_nat.sh")
run("wc -l /usr/local/bin/setup_gadget.sh /usr/local/bin/setup_nat.sh")

# Test execution
print("\n=== 5. Test gadget script ===")
run(f"{S} /usr/local/bin/setup_gadget.sh 2>&1")

# Reload systemd and restart
print("\n=== 6. Restart daemon ===")
run(f"{S} systemctl daemon-reload")
run(f"{S} systemctl restart tun_nat_hub")
import time; time.sleep(3)

run(f"{S} systemctl status tun_nat_hub --no-pager 2>&1 | head -12")
run("ls -la /dev/ttyGS0 2>&1")
run(f"{S} journalctl -u tun_nat_hub --no-pager -n 5 2>&1")

# Also fix tun_web service script CRLF
run(f"{S} tr -d '\\r' < /home/xlong/web_panel.py > /tmp/web_clean.py")
run(f"{S} cp /tmp/web_clean.py /home/xlong/web_panel.py")
run(f"{S} chmod +x /home/xlong/web_panel.py")
run(f"{S} systemctl restart tun_web")

print("\n=== Done - Should survive reboot now ===")
c.close()
