"""Set up DHCP on RK3588 usb0 and restart gadget to trigger fresh RNDIS negotiation."""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("172.24.91.28", username="xlong", password="1234", timeout=10)

def run(cmd, timeout=10):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode()
    err = stderr.read().decode()
    if out.strip(): print(out.strip())
    if err.strip(): print("[e]", err.strip())

S = "echo '1234' | sudo -S"

# 1. Check/install dnsmasq
print("=== Check dnsmasq ===")
run("which dnsmasq; dpkg -l dnsmasq 2>/dev/null | tail -1")

# 2. Kill any existing dnsmasq
run(f"{S} killall dnsmasq 2>/dev/null; echo done")

# 3. Stop daemon first
run(f"{S} systemctl stop tun_nat_hub 2>/dev/null; echo done")

# 4. Remove old g_ether module
run(f"{S} modprobe -r g_ether g_rndis g_serial 2>/dev/null; echo cleaned")
time.sleep(1)

# 5. Reload g_ether with host_addr set (this triggers RNDIS on DJI RC side)
run(f"{S} modprobe g_ether host_addr=02:00:00:00:00:02 dev_addr=02:00:00:00:00:01; echo loaded")
time.sleep(3)

# 6. Configure usb0 IP on RK3588
run(f"{S} ip addr flush dev usb0 2>/dev/null; echo flushed")
run(f"{S} ip addr add 192.168.50.2/24 dev usb0; echo ip_set")
run(f"{S} ip link set usb0 up; echo up")

# 7. Start dnsmasq for DHCP on usb0
# Give Android IPs in 192.168.50.100-200 range
run(f"""{S} dnsmasq --interface=usb0 --bind-interfaces --dhcp-range=192.168.50.100,192.168.50.200,255.255.255.0,1h --port=0 --no-resolv --no-hosts --dhcp-option=3,192.168.50.2 2>&1; echo dnsmasq_exit=\$?""", timeout=15)

# 8. Check
print("\n=== usb0 state ===")
run("ip addr show usb0 | grep inet")
run("ps aux | grep dnsmasq | grep -v grep")

# 9. Restart daemon
print("\n=== Restart daemon ===")
run(f"{S} systemctl restart tun_nat_hub 2>&1; echo restarted")
time.sleep(1)
run(f"{S} systemctl status tun_nat_hub --no-pager | head -10")

print("\n=== Done - check DJI RC now ===")
c.close()
