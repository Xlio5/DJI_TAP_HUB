"""SD boot -> flash rootfs via mtd0 seek=1808"""
import paramiko, time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("192.168.144.66", username="root", password="root", timeout=10)
print("SSH OK")

# Upload rootfs
sq = open(r"c:\my_project\TUN_NAT_HUB\backup\rootfs.squashfs", "rb").read()
sq_kb = len(sq) // 1024
print("Uploading " + str(sq_kb) + " KB...")
chan = ssh.get_transport().open_session()
chan.exec_command("cat > /tmp/rf.sq && echo UP_OK")
time.sleep(0.2)
for i in range(0, len(sq), 65536):
    chan.sendall(sq[i:i+65536])
chan.shutdown_write()
time.sleep(1)
out = chan.recv(4096).decode(errors="replace")
chan.close()
print("Upload:", "OK" if "UP_OK" in out else "FAIL")

# Verify
_, o, _ = ssh.exec_command("wc -c /tmp/rf.sq", timeout=5)
sz = o.read().decode(errors="replace").strip()
if str(len(sq)) not in sz:
    print("SIZE MISMATCH! " + sz + " vs " + str(len(sq)))
    ssh.close()
    exit(1)
print("Size OK: " + sz)

# Flash via raw mtd0 (handles NOR erase)
print("Flashing via /dev/mtd0 seek=1808...")
_, o, e = ssh.exec_command(
    "dd if=/tmp/rf.sq of=/dev/mtd0 bs=4096 seek=1808 2>&1; echo FLASH_DONE",
    timeout=120
)
out = o.read().decode(errors="replace")
err = e.read().decode(errors="replace")
print(out.strip()[-120:])
if err and "FLASH_DONE" not in out:
    print("ERR:", err[:100])

# Verify
time.sleep(1)
_, o, _ = ssh.exec_command(
    "hexdump -C -n 16 /dev/mtd0 2>&1",
    timeout=5
)
print("SPI header:", o.read().decode(errors="replace").strip()[:80])

_, o, _ = ssh.exec_command(
    "dd if=/dev/mtd0 bs=1 skip=7405568 count=16 2>/dev/null | od -A x -t x1z",
    timeout=5
)
print("squashfs @0x710000:", o.read().decode(errors="replace").strip())

# Verify the new web_server has firmware endpoint
_, o, _ = ssh.exec_command(
    "dd if=/dev/mtd0 bs=1 skip=7405568 count=262144 2>/dev/null | strings | grep -c 'mtd0'",
    timeout=10
)
c = o.read().decode(errors="replace").strip()
print("mtd0 reference in binary:", c, "-", "FIXED" if int(c) >= 1 else "OLD CODE")

ssh.close()
print("\nDone! Remove SD card, reboot to test.")
