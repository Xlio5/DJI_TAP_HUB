#!/usr/bin/env python3
"""Final deploy steps: stop, install, start."""
import paramiko
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

HOST = "172.24.91.28"
USER = "xlong"
PWD = "1234"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, port=22, username=USER, password=PWD, timeout=15)

def run(cmd, timeout=15):
    print(f"$ {cmd}")
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode()
    err = stderr.read().decode()
    if out.strip(): print(out.strip())
    if err.strip(): print(f"[e] {err.strip()}")
    return out

# 1. Kill old daemon + stop service (without get_pty)
run("echo '1234' | sudo -S killall usb_tund 2>/dev/null; echo done")
run("echo '1234' | sudo -S systemctl stop tun_nat_hub 2>/dev/null; echo done")

# 2. Copy binary (now not busy)
run("echo '1234' | sudo -S cp /home/xlong/tun_nat_hub/ubuntu/build/usb_tund /usr/local/bin/usb_tund")
run("echo '1234' | sudo -S chmod +x /usr/local/bin/usb_tund")

# 3. Copy scripts
run("echo '1234' | sudo -S cp /home/xlong/tun_nat_hub/ubuntu/scripts/setup_gadget.sh /usr/local/bin/")
run("echo '1234' | sudo -S cp /home/xlong/tun_nat_hub/ubuntu/scripts/setup_nat.sh /usr/local/bin/")
run("echo '1234' | sudo -S chmod +x /usr/local/bin/setup_gadget.sh /usr/local/bin/setup_nat.sh")
run("echo '1234' | sudo -S cp /home/xlong/tun_nat_hub/ubuntu/config/tun_nat_hub.service /etc/systemd/system/")
run("echo '1234' | sudo -S systemctl daemon-reload")

# 4. Setup gadget
print("\n--- Gadget Setup ---")
run("echo '1234' | sudo -S modprobe -r g_serial g_ether g_rndis 2>/dev/null; echo cleaned", timeout=10)
run("echo '1234' | sudo -S modprobe g_ether dev_addr=02:00:00:00:00:01 host_addr=02:00:00:00:00:02", timeout=10)

# 5. Show usb0
import time; time.sleep(2)
print("\n--- Network Interfaces ---")
run("ip link show 2>&1 | grep -E 'usb|rndis|tun'")

# 6. Run NAT setup
print("\n--- NAT Setup ---")
run("echo '1234' | sudo -S /usr/local/bin/setup_nat.sh", timeout=30)

# 7. Start service
print("\n--- Starting Service ---")
run("echo '1234' | sudo -S systemctl enable tun_nat_hub", timeout=10)
run("echo '1234' | sudo -S systemctl restart tun_nat_hub", timeout=10)
time.sleep(2)

# 8. Status
print("\n=== Service Status ===")
run("echo '1234' | sudo -S systemctl status tun_nat_hub --no-pager -l 2>&1 | head -20", timeout=15)
print("\n=== usb0 ===")
run("ip addr show usb0 2>&1 | head -10")
print("\n=== Journal ===")
run("echo '1234' | sudo -S journalctl -u tun_nat_hub --no-pager -n 15 2>&1", timeout=15)

c.close()
print("\n=== Done ===")
