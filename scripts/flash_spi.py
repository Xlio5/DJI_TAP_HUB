#!/usr/bin/env python3
"""SSH channel 直传 SPI 镜像 → /tmp/spi.bin → flash_erase → dd"""
import paramiko, time, os

SPI_FILE = r"c:\my_project\TUN_NAT_HUB\backup\spi_image.bin"
V3S = "192.168.144.66"

with open(SPI_FILE, "rb") as f:
    spi_data = f.read()
print(f"SPI image: {len(spi_data)} bytes ({len(spi_data)/1024/1024:.1f} MB)")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(V3S, username="root", password="root", timeout=10)
print("SSH OK")

# Step 1: open session for "cat > file" and pipe binary data
print("Uploading via SSH stdin pipe...")
chan = ssh.get_transport().open_session()
chan.exec_command("cat > /tmp/spi.bin && echo WRITE_OK")
time.sleep(0.2)

# Send in 64KB chunks
CHUNK = 65536
for i in range(0, len(spi_data), CHUNK):
    chunk = spi_data[i:i+CHUNK]
    chan.sendall(chunk)
    if i % (1024*1024) == 0:
        print(f"  {i//1024//1024}MB / {len(spi_data)//1024//1024}MB")
chan.shutdown_write()
print("Upload complete, waiting for shell response...")

time.sleep(3)
result = chan.recv(4096).decode(errors="replace")
print(f"Result: {result.strip()}")
chan.close()

# Step 2: Verify
_, stdout, stderr = ssh.exec_command("ls -la /tmp/spi.bin && wc -c /tmp/spi.bin", timeout=5)
out = stdout.read().decode().strip()
print(f"Verify: {out}")
err = stderr.read().decode()
if err: print("Err:", err[:200])

expected = str(len(spi_data))
if expected in out:
    print("Size OK! Flashing SPI...")
    _, stdout, stderr = ssh.exec_command(
        "flash_erase /dev/mtd0 0 0 2>&1; "
        "dd if=/tmp/spi.bin of=/dev/mtd0 bs=4096 2>&1; "
        "echo FLASH_DONE",
        timeout=120)
    print(stdout.read().decode())
    err = stderr.read().decode()
    if err: print("Flash:", err[:200])
    print("\nSPI Flash done! Remove SD card, reboot - should boot from SPI.")
else:
    print("SIZE MISMATCH!")

ssh.close()
print("Done!")
