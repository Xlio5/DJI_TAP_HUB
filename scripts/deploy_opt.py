"""Deploy optimized master daemon to RK3588."""
import paramiko, base64, time, os

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", username="xlong", password="1234", timeout=15)
BASE = r"c:\my_project\TUN_NAT_HUB"

def chan_upload(remote, data):
    b64 = base64.b64encode(data).decode()
    ch = c.get_transport().open_session()
    ch.exec_command("base64 -d > " + remote)
    ch.sendall(b64.encode())
    ch.shutdown_write()
    return ch.recv_exit_status() == 0

def read_clean(path):
    with open(path, "rb") as f:
        return f.read().replace(b"\r\n", b"\n").replace(b"\r", b"")

def sh(cmd, timeout=15):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = b""
    while not stdout.channel.exit_status_ready():
        if stdout.channel.recv_ready(): out += stdout.channel.recv(4096)
        time.sleep(0.1)
    out += stdout.read()
    for line in out.decode(errors="replace").strip().split("\n"):
        if line.strip() and "password" not in line.lower(): print(line)
    return out.decode(errors="replace")

def su(cmd, timeout=10):
    esc = cmd.replace('"', '\\"')
    return sh('echo 1234 | sudo -S bash -c "' + esc + '" 2>&1', timeout)

print("=== Stop ===")
su("systemctl stop tun_nat_hub 2>&1; true")
sh("killall -9 python3 usb_tund 2>/dev/null; true")
time.sleep(1)

print()
print("=== Upload ===")
sh("mkdir -p /home/xlong/tun_opt/src /home/xlong/tun_opt/protocol /home/xlong/protocol")
for rel, remote in [
    ("ubuntu/src/main.cpp", "/home/xlong/tun_opt/src/main.cpp"),
    ("ubuntu/src/tun_iface.cpp", "/home/xlong/tun_opt/src/tun_iface.cpp"),
    ("ubuntu/src/tun_iface.h", "/home/xlong/tun_opt/src/tun_iface.h"),
    ("ubuntu/CMakeLists.txt", "/home/xlong/tun_opt/CMakeLists.txt"),
    ("protocol/frame.h", "/home/xlong/tun_opt/protocol/frame.h"),
]:
    data = read_clean(os.path.join(BASE, rel)).rstrip(b"\n") + b"\n"
    ok = chan_upload(remote, data)
    print("  {} {}".format(os.path.basename(rel), "OK" if ok else "FAIL"))
sh("cp /home/xlong/tun_opt/protocol/frame.h /home/xlong/protocol/frame.h")

print()
print("=== Build ===")
sh("cd /home/xlong/tun_opt && export TMPDIR=/home/xlong/tmp && cmake -B build -DCMAKE_BUILD_TYPE=Release 2>&1", timeout=30)
sh("cd /home/xlong/tun_opt && export TMPDIR=/home/xlong/tmp && cmake --build build 2>&1", timeout=30)

print()
print("=== Deploy binary + scripts ===")
su("cp /home/xlong/tun_opt/build/usb_tund /usr/local/bin/usb_tund")
su("chmod 755 /usr/local/bin/usb_tund")
data = read_clean(os.path.join(BASE, "ubuntu", "scripts", "setup_nat.sh")).rstrip(b"\n") + b"\n"
chan_upload("/home/xlong/setup_nat.sh", data)
su("cp /home/xlong/setup_nat.sh /usr/local/bin/setup_nat.sh")
su("sed -i 's/\\r$//' /usr/local/bin/setup_nat.sh")
su("chmod 755 /usr/local/bin/setup_nat.sh")
print("  setup_nat.sh (qlen=100)")

print()
print("=== VID=0x0BDA ===")
su("modprobe -r g_serial 2>&1; true")
time.sleep(1)
su("modprobe g_serial use_acm=0 use_obex=0 idVendor=0x0BDA idProduct=0x8812 2>&1")
time.sleep(1.5)
su("chmod 666 /dev/ttyGS0 2>&1")

print()
print("=== Start ===")
su("systemctl start tun_nat_hub 2>&1")
time.sleep(2)

print()
print("=== Verify ===")
sh("echo tun_nat_hub: $(systemctl is-active tun_nat_hub)")
sh("ls -la /dev/ttyGS0")
sh("ip -br addr show tun_hub")
sh("/usr/local/bin/usb_tund 2>&1; true")

print()
print("Optimized master: usleep 100, qlen 100, VID=0x0BDA")
c.close()
