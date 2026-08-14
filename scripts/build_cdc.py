"""Build and deploy cdc branch daemon on RK3588."""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", username="xlong", password="1234", timeout=15)

def ssh(cmd, timeout=15):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = b""
    while not stdout.channel.exit_status_ready():
        if stdout.channel.recv_ready():
            out += stdout.channel.recv(4096)
        time.sleep(0.1)
    out += stdout.read()
    text = out.decode(errors="replace")
    for line in text.split("\n"):
        line = line.strip()
        if line and "password" not in line.lower():
            print(line)
    return text

def sudossh(cmd, timeout=10):
    esc = cmd.replace('"', '\\"')
    return ssh('echo 1234 | sudo -S bash -c "' + esc + '" 2>&1', timeout)

# Stop
print("=== Stop current services ===")
sudossh("systemctl stop tun_nat_hub 2>&1 || true")
ssh("killall -9 python3 usb_tund 2>/dev/null; true")
time.sleep(1)

# Build
print()
print("=== cmake configure ===")
ssh("cd /home/xlong/tun_cdc && export TMPDIR=/home/xlong/tmp && cmake -B build -DCMAKE_BUILD_TYPE=Release 2>&1", timeout=30)

print()
print("=== cmake build ===")
ssh("cd /home/xlong/tun_cdc && export TMPDIR=/home/xlong/tmp && cmake --build build 2>&1", timeout=30)

# Check binary
print()
print("=== Binary info ===")
ssh("ls -la /home/xlong/tun_cdc/build/usb_tund 2>&1")
ssh("file /home/xlong/tun_cdc/build/usb_tund 2>&1")

# Check version string
print()
print("=== Version check ===")
ssh("strings /home/xlong/tun_cdc/build/usb_tund 2>&1 | grep -i tun 2>&1 || true")
ssh("strings /home/xlong/tun_cdc/build/usb_tund 2>&1 | grep -i v5 2>&1 || true")

# Deploy binary
print()
print("=== Deploy binary ===")
sudossh("cp /home/xlong/tun_cdc/build/usb_tund /usr/local/bin/usb_tund")
sudossh("chmod 755 /usr/local/bin/usb_tund")
print("Binary deployed")

# Start
print()
print("=== Start tun_nat_hub ===")
sudossh("systemctl start tun_nat_hub 2>&1")
time.sleep(3)

# Verify
print()
print("=== Verification ===")
ssh("systemctl is-active tun_nat_hub 2>&1")
ssh("ls -la /dev/ttyGS0 2>&1")
ssh("ip -br addr show tun_hub 2>&1")

print()
print("=== Daemon startup log ===")
ssh("journalctl -u tun_nat_hub --no-pager -n 10 2>&1")

print()
print("=== Key differences (cdc vs master) ===")
ssh("echo 'VTIME check (1=cdc old, 0=master new):'")
ssh("strings /usr/local/bin/usb_tund 2>&1 | grep -c TUN_NAT_HUB 2>&1 || true")

c.close()
print()
print("cdc branch build and deploy complete.")
