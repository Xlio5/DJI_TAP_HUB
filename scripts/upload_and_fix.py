"""Upload fix scripts and execute via WiFi on RK3588."""
import paramiko, base64, time, os

HOST = "172.24.91.129"
BASE = r"c:\my_project\TUN_NAT_HUB"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username="xlong", password="1234", timeout=10)

def upload_file(local, remote):
    with open(local, "rb") as f:
        data = f.read().replace(b"\r\n", b"\n")
    b64 = base64.b64encode(data).decode()
    ch = c.get_transport().open_session()
    ch.exec_command("base64 -d > " + remote)
    ch.sendall(b64.encode())
    ch.shutdown_write()
    code = ch.recv_exit_status()
    ch.close()
    return code == 0

# Upload all fix files
files_to_upload = [
    ("scripts/fix_cold_boot.sh", "/home/xlong/fix_cold_boot.sh"),
    ("ubuntu/scripts/setup_gadget.sh", "/home/xlong/setup_gadget.sh"),
    ("ubuntu/scripts/setup_nat.sh", "/home/xlong/setup_nat.sh"),
]

for local_rel, remote in files_to_upload:
    ok = upload_file(os.path.join(BASE, local_rel), remote)
    print("{} -> {} {}".format(local_rel, remote, "OK" if ok else "FAIL"))

# Execute fix script
print()
print("=== Running fix_cold_boot.sh ===")
stdin, stdout, stderr = c.exec_command("bash /home/xlong/fix_cold_boot.sh", timeout=30, get_pty=True)
out = b""
t0 = time.time()
while time.time() - t0 < 25:
    if stdout.channel.recv_ready():
        out += stdout.channel.recv(4096)
    if stdout.channel.exit_status_ready():
        break
    time.sleep(0.2)
try:
    out += stdout.read()
except:
    pass

text = out.decode(errors="replace")
for line in text.split("\n"):
    if line.strip() and "password" not in line.lower():
        print(line)

c.close()
