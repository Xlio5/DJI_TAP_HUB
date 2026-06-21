"""Configure static IP 192.168.88.66/24 on end1 via NM."""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("172.24.91.129", username="xlong", password="1234", timeout=10)

def sh(cmd, timeout=10):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = b""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if stdout.channel.recv_ready():
            out += stdout.channel.recv(4096)
        if stdout.channel.exit_status_ready():
            break
        time.sleep(0.2)
    try: out += stdout.read()
    except: pass
    for line in out.decode(errors="replace").strip().split("\n"):
        if line.strip() and "password" not in line.lower():
            print(line)

# Delete all old end1 connections
print("=== Clean old connections ===")
sh("echo 1234 | sudo -S nmcli connection delete end1-dhcp 2>&1 || true")
sh("echo 1234 | sudo -S nmcli connection delete netplan-end1 2>&1 || true")

# Create static connection
print()
print("=== Create static connection ===")
sh('echo 1234 | sudo -S nmcli connection add type ethernet ifname end1 con-name end1-static connection.autoconnect yes ipv4.method manual ipv4.addresses 192.168.88.66/24 ipv4.gateway 192.168.88.1 ipv4.dns 192.168.88.1 ipv6.method disabled 2>&1')
time.sleep(1)

# Bring it up
print()
print("=== Bring up ===")
sh("echo 1234 | sudo -S nmcli connection up end1-static 2>&1")
time.sleep(3)

# Verify
print()
print("=== Verify ===")
sh("ip -br addr show end1 2>&1")
sh("ip route | grep end1 2>&1")
sh("nmcli -t -f NAME,AUTOCONNECT,STATE connection show end1-static 2>&1")

# Ensure setup_nat.sh has static fallback
print()
print("=== Update setup_nat.sh ===")
sh("grep -c 'static fallback' /usr/local/bin/setup_nat.sh 2>&1 || echo 'not patched yet'")

c.close()
