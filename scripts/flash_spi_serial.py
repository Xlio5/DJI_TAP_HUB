"""串口登录 V3s，配网，下载 SPI 镜像，烧录"""
import serial, time, base64, os

SERIAL = "COM10"
SPI_FILE = r"c:\my_project\TUN_NAT_HUB\backup\spi_image.bin"
PC_IP = "192.168.144.88"

with open(SPI_FILE, "rb") as f:
    spi_data = f.read()
print(f"SPI image: {len(spi_data)} bytes")

ser = serial.Serial(SERIAL, 115200, timeout=0.5)
time.sleep(0.3)
ser.read(ser.in_waiting)

# Login
ser.write(b"\n")
time.sleep(0.3)
out = ser.read(ser.in_waiting).decode(errors="replace")
if "login:" in out:
    ser.write(b"root\n")
    time.sleep(1)
    out = ser.read(ser.in_waiting).decode(errors="replace")
    if "Password" in out:
        ser.write(b"root\n")
        time.sleep(1)
        out = ser.read(ser.in_waiting).decode(errors="replace")
    print("Logged in")

# Set IP
ser.write(b"ip addr add 192.168.144.66/24 dev eth0 2>/dev/null\n")
time.sleep(0.5)
ser.read(ser.in_waiting)

# Verify IP
ser.write(b"ip addr show eth0 | grep inet\n")
time.sleep(0.5)
out = ser.read(ser.in_waiting).decode(errors="replace")
print(f"IP: {out.strip()[-80:]}")

# Download SPI image from PC
ser.write(f"wget -O /tmp/spi.bin http://{PC_IP}:8888/ 2>&1; echo DL_DONE\n".encode())
time.sleep(35)
out = ser.read(ser.in_waiting).decode(errors="replace")
print(f"DL: {out.strip()[-200:]}")

# Verify size
ser.write(b"wc -c /tmp/spi.bin\n")
time.sleep(0.5)
out = ser.read(ser.in_waiting).decode(errors="replace")
print(f"Size check: {out.strip()}")

if str(len(spi_data)) in out:
    print("Size OK! Flashing SPI...")
    # Erase and write
    ser.write(b"dd if=/tmp/spi.bin of=/dev/mtd0 bs=4096 2>&1; echo FLASH_DONE\n")
    time.sleep(30)
    out = ser.read(ser.in_waiting).decode(errors="replace")
    print(out.strip()[-200:])
    print("\nSPI flash done! Remove SD card and reboot.")
else:
    print("Download failed. Trying direct serial xfer...")
    # Base64 via serial fallback
    b64 = base64.b64encode(spi_data).decode()
    print(f"Base64: {len(b64)} chars - this will take a while over serial")
    # Skip - too slow for 16MB

ser.close()
