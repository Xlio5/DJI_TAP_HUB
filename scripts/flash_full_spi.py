"""最终SPI烧录 - boot without mtdparts, full device write"""
import serial, time, paramiko

SERIAL = "COM10"
SPI_FILE = r"c:\my_project\TUN_NAT_HUB\backup\spi_image.bin"

print("=== Step 1: Boot from SD without mtdparts ===")
ser = serial.Serial(SERIAL, 115200, timeout=0.5)
time.sleep(0.3)
ser.read(ser.in_waiting)

# Check state
ser.write(b"\r\n")
time.sleep(0.5)
out = ser.read(ser.in_waiting).decode(errors="replace")
print(f"State: {out.strip()[-50:]}")

if "=>" in out:
    # In U-Boot, boot without mtdparts
    print("In U-Boot, booting without mtdparts...")
    for cmd, wait in [
        ("fatload mmc 0:1 0x41000000 zImage", 3),
        ("fatload mmc 0:1 0x42000000 sun8i-v3s-licheepi-zero-dock.dtb", 1),
        ("setenv bootargs console=ttyS0,115200 root=/dev/mmcblk0p2 rootfstype=squashfs rootwait g_serial.idVendor=0x0BDA g_serial.idProduct=0x8812 g_serial.use_acm=0", 0.5),
        ("bootz 0x41000000 - 0x42000000", 2),
    ]:
        ser.write((cmd + "\r\n").encode())
        time.sleep(wait)
        out = ser.read(ser.in_waiting).decode(errors="replace")
        ok = "bytes read" in out or "Starting kernel" in out
        print(f"  {cmd[:50]}... {'OK' if ok else out.strip()[-50:]}")

elif "login:" in out:
    print("Already in Linux!")
elif not out.strip():
    print("No response - V3s may need power cycle!")
    ser.close()
    exit(1)

# Wait for boot
time.sleep(12)
out = ser.read(ser.in_waiting).decode(errors="replace")
if "login:" not in out:
    print("Did not reach login:", out[-200:] if len(out) > 200 else out)
    ser.close()
    exit(1)

# Login
ser.write(b"root\r\n")
time.sleep(1.5)
out = ser.read(ser.in_waiting).decode(errors="replace")
if "Password" in out:
    ser.write(b"root\r\n")
    time.sleep(1)
    ser.read(ser.in_waiting)

# Set IP
ser.write(b"ip addr add 192.168.144.66/24 dev eth0 2>/dev/null; ip link set eth0 up; echo OK\r\n")
time.sleep(1)
out = ser.read(ser.in_waiting).decode(errors="replace")
if "OK" not in out:
    print("Failed to set IP!")
    ser.close()
    exit(1)
print("Network OK")
ser.close()

print("\n=== Step 2: Check MTD and flash ===")
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("192.168.144.66", username="root", password="root", timeout=10)

# Check MTD state
_, o, _ = ssh.exec_command("cat /proc/mtd", timeout=5)
mtd = o.read().decode().strip()
print(f"MTD:\n{mtd}")

# Upload
with open(SPI_FILE, "rb") as f:
    spi_data = f.read()
print(f"Uploading {len(spi_data)} bytes...")

chan = ssh.get_transport().open_session()
chan.exec_command("cat > /tmp/spi.bin && echo UP_OK")
time.sleep(0.2)
for i in range(0, len(spi_data), 65536):
    chan.sendall(spi_data[i:i+65536])
chan.shutdown_write()
time.sleep(2)
chan.recv(4096)
chan.close()

_, o, _ = ssh.exec_command("wc -c /tmp/spi.bin", timeout=5)
if str(len(spi_data)) not in o.read().decode():
    print("Upload FAILED")
    ssh.close()
    exit(1)
print("Upload OK")

# If single mtd0 device (no partitions), write directly
# If partitioned, write to each partition at correct skip
if "mtd1" in mtd:
    print("Partitioned - writing per-partition...")
    partitions = {
        "mtd0": (0, 256),      # uboot 1MB
        "mtd1": (256, 16),     # dtb 64KB
        "mtd2": (272, 1536),   # kernel 6MB
        "mtd3": (1808, 2288),  # rootfs ~9MB
    }
    for part, (skip, count) in partitions.items():
        cmd = f"dd if=/tmp/spi.bin of=/dev/{part} bs=4096 skip={skip} count={count} 2>&1; echo {part}_OK"
        _, o, e = ssh.exec_command(cmd, timeout=30)
        out = o.read().decode()
        print(f"  {part}: {'OK' if f'{part}_OK' in out else out.strip()[-50:]}")
else:
    print("Single device - writing full 16MB...")
    _, o, e = ssh.exec_command("dd if=/tmp/spi.bin of=/dev/mtd0 bs=4096 2>&1; echo FLASH_OK", timeout=120)
    out = o.read().decode()
    print(out.strip())

# Verify
time.sleep(2)
_, o, _ = ssh.exec_command("hexdump -C -n 16 /dev/mtd0 2>&1", timeout=5)
print("SPI[0]:", o.read().decode().strip())

_, o, _ = ssh.exec_command("hexdump -C -n 16 /dev/mtd3 2>&1", timeout=5)
print("SPI[mtd3]:", o.read().decode().strip())

ssh.close()
print("\nDone! Remove SD card, power cycle, test SPI boot.")
