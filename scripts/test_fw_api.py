"""Test firmware API on V3s"""
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("192.168.144.66", username="root", password="root", timeout=5)

# Check firmware page
_, o, _ = ssh.exec_command(
    "wget -q -O - http://127.0.0.1:8080/ 2>&1 | grep -c rootfs.squashfs",
    timeout=5)
c = o.read().decode(errors="replace").strip()
print("HTML fw page:", "FOUND" if c == "1" else "MISSING")

# Create a fake 3MB file with hsqs header
_, o, _ = ssh.exec_command(
    "dd if=/dev/zero of=/tmp/fake3m.sq bs=1M count=3 2>/dev/null; "
    "wc -c /tmp/fake3m.sq",
    timeout=5)
print(o.read().decode(errors="replace").strip())

# Write hsqs magic to first 4 bytes
_, o, _ = ssh.exec_command(
    "printf 'hsqs' > /tmp/hdr.bin; "
    "dd if=/tmp/hdr.bin of=/tmp/fake3m.sq bs=1 count=4 conv=notrunc 2>/dev/null; "
    "od -A x -t x1z -N 4 /tmp/fake3m.sq",
    timeout=5)
print(o.read().decode(errors="replace").strip())

# Test firmware upload
_, o, _ = ssh.exec_command(
    "wget -q -O - --post-file=/tmp/fake3m.sq "
    "--header=Content-Type:application/octet-stream "
    "http://127.0.0.1:8080/api/firmware/upload 2>&1",
    timeout=15)
out = o.read().decode(errors="replace").strip()
print("API response:", out[:200])

ssh.close()
