"""flash_erase + dd 正确烧写 SPI NOR — 一次性搞定"""
import paramiko, time, sys

SPI_FILE = r"c:\my_project\TUN_NAT_HUB\backup\spi_image.bin"

with open(SPI_FILE, "rb") as f:
    spi_data = f.read()
print(f"SPI: {len(spi_data)} bytes ({len(spi_data)/1024/1024:.1f}MB)")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("192.168.144.66", username="root", password="root", timeout=15)

# Upload (separate calls to avoid timeouts)
print("Uploading...")
chan = ssh.get_transport().open_session()
chan.exec_command("cat > /tmp/spi.bin && echo UP_OK")
time.sleep(0.2)

total = len(spi_data)
pos = 0
while pos < total:
    chunk = spi_data[pos:pos+65536]
    chan.sendall(chunk)
    pos += 65536
    if pos % (4*1024*1024) < 65536:
        print(f"  {pos//1024//1024}MB / {total//1024//1024}MB")

chan.shutdown_write()
time.sleep(3)
out = chan.recv(4096).decode(errors="replace")
chan.close()
print(f"Upload: {'OK' if 'UP_OK' in out else 'FAIL'}")

# Verify size
_, o, _ = ssh.exec_command("wc -c /tmp/spi.bin", timeout=10)
size = o.read().decode().strip()
print(f"Size check: {size}")
if str(total) not in size:
    print("SIZE MISMATCH!")
    ssh.close()
    sys.exit(1)

# CRITICAL: flash_erase first, then dd
print("Step 1: flash_erase /dev/mtd0 0 0 ...")
_, o, e = ssh.exec_command("flash_erase /dev/mtd0 0 0 2>&1; echo ERASE_DONE", timeout=120)
out = o.read().decode()
err = e.read().decode()
print(out.strip())
if err:
    print("Erase err:", err[:200])

print("Step 2: dd if=/tmp/spi.bin of=/dev/mtd0 bs=4096 ...")
_, o, e = ssh.exec_command("dd if=/tmp/spi.bin of=/dev/mtd0 bs=4096 2>&1; echo WRITE_DONE", timeout=60)
out = o.read().decode()
err = e.read().decode()
print(out.strip())
if err:
    print("Write err:", err[:200])

# Verify first 64 bytes
print("Step 3: Verify...")
_, o, e = ssh.exec_command("dd if=/dev/mtd0 bs=1 count=64 2>/dev/null | od -A x -t x1 2>/dev/null", timeout=10)
out = o.read().decode().strip()
err = e.read().decode().strip()
if err:
    print("Verify err:", err[:200])
if out:
    print("SPI[0:64]:")
    print(out)
else:
    # Try alternate read
    _, o, _ = ssh.exec_command("hexdump -C -n 64 /dev/mtd0 2>&1", timeout=5)
    print(o.read().decode())

ssh.close()
print("\n=== DONE ===\nRemove SD card, reboot V3s.")
