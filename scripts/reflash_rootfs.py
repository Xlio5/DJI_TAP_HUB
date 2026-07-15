"""Upload fixed squashfs and write to mtdblock3"""
import paramiko, time, os

SQ_FILE = r"c:\my_project\TUN_NAT_HUB\backup\rootfs.squashfs"
V3S = "192.168.144.66"

with open(SQ_FILE, "rb") as f:
    sq_data = f.read()
print(f"Squashfs: {len(sq_data)} bytes ({len(sq_data)/1024/1024:.1f}MB)")

# Check magic
magic = sq_data[:4]
print(f"Magic: {magic.hex()}")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(V3S, username="root", password="root", timeout=10)
print("SSH OK")

# Upload
chan = ssh.get_transport().open_session()
chan.exec_command("cat > /tmp/rootsq && echo UP_OK")
time.sleep(0.2)
for i in range(0, len(sq_data), 65536):
    chan.sendall(sq_data[i:i+65536])
chan.shutdown_write()
time.sleep(2)
result = chan.recv(4096).decode()
chan.close()
print("Upload:", "OK" if "UP_OK" in result else "FAIL")

# Verify
_, o, _ = ssh.exec_command("wc -c /tmp/rootsq", timeout=5)
sz = o.read().decode().strip()
print("Size check:", sz)

if str(len(sq_data)) in sz:
    print("Writing to /dev/mtdblock3 (rootfs partition)...")
    _, o, e = ssh.exec_command(
        "dd if=/tmp/rootsq of=/dev/mtdblock3 bs=4096 2>&1; echo FLASH_DONE",
        timeout=60
    )
    out = o.read().decode()
    err = e.read().decode()
    print(out.strip())
    if err:
        print("E:", err[:200])

    # Verify magic
    _, o, _ = ssh.exec_command("hexdump -C -n 16 /dev/mtdblock3 2>&1 | head -3", timeout=5)
    print("mtdblock3 verify:")
    print(o.read().decode().strip())

    print("\nDone! Remove SD card, power cycle, and test.")
else:
    print("SIZE MISMATCH")

ssh.close()
