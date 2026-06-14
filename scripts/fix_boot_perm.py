"""Fix setup scripts on RK3588 with clean LF."""
import paramiko, base64, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HOST = "192.168.88.66"
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username="xlong", password="1234", timeout=10)

def upload_clean(remote_path, content):
    b64 = base64.b64encode(content.encode()).decode()
    cmd = "python3 -c \"import base64,sys; open('" + remote_path + "','w').write(base64.b64decode(sys.stdin.read()).decode())\""
    transport = c.get_transport()
    if transport is None:
        print("No transport")
        return False
    chan = transport.open_session()
    chan.exec_command(cmd)
    chan.sendall(b64.encode())
    chan.shutdown_write()
    code = chan.recv_exit_status()
    chan.close()
    return code == 0

def run(cmd):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=10)
    out = stdout.read().decode(errors="replace")
    if out.strip(): print(out.strip())
    return out

# Upload clean setup_gadget.sh
gadget_script = """#!/bin/bash
set -e
if [ -c /dev/ttyGS0 ]; then
    echo "g_serial ready"
    exit 0
fi
modprobe -r g_serial 2>/dev/null || true
sleep 1
modprobe g_serial use_acm=0 use_obex=0 idVendor=0x0BDA idProduct=0x8812
sleep 2
if [ -c /dev/ttyGS0 ]; then
    chmod 666 /dev/ttyGS0 2>/dev/null || true
    echo "g_serial loaded"
else
    echo "WARNING: ttyGS0 not found"
fi
"""

print("=== Uploading clean setup_gadget.sh ===")
if upload_clean("/usr/local/bin/setup_gadget.sh", gadget_script):
    print("OK")
else:
    print("FAILED")

# Upload clean setup_nat.sh
with open("c:/my_project/TUN_NAT_HUB/ubuntu/scripts/setup_nat.sh", "rb") as f:
    nat_content = f.read().decode().replace("\r\n", "\n").replace("\r", "\n")

print("=== Uploading clean setup_nat.sh ===")
if upload_clean("/usr/local/bin/setup_nat.sh", nat_content):
    print("OK")
else:
    print("FAILED")

# Make executable
run("echo 1234 | sudo -S chmod +x /usr/local/bin/setup_gadget.sh /usr/local/bin/setup_nat.sh")

# Verify
print("\n=== Verification ===")
run("file /usr/local/bin/setup_gadget.sh")
run("file /usr/local/bin/setup_nat.sh")
run("echo 1234 | sudo -S /usr/local/bin/setup_gadget.sh 2>&1")

# Restart daemon
print("\n=== Restart daemon ===")
run("echo 1234 | sudo -S systemctl restart tun_nat_hub")
import time; time.sleep(3)
run("echo 1234 | sudo -S systemctl status tun_nat_hub --no-pager 2>&1 | head -15")
run("echo 1234 | sudo -S journalctl -u tun_nat_hub --no-pager -n 6 2>&1")

print("\n=== Done ===")
c.close()
