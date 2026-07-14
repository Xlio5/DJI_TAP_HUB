import serial, time

s = serial.Serial("COM10", 115200, timeout=0.5)
time.sleep(0.2)
s.read(s.in_waiting)

# Login
s.write(b"root\n")
time.sleep(1.5)
out = s.read(s.in_waiting).decode(errors="replace")
if "Password" in out:
    s.write(b"root\n")
    time.sleep(1)
    s.read(s.in_waiting)

# Verify
tests = [
    ("mount | head -3", "Mount"),
    ("ps | grep usb_tund", "daemon"),
    ("ps | grep web_server", "web"),
    ("cat /proc/mtd", "MTD"),
    ("df -h / | tail -1", "Disk"),
]

for cmd, label in tests:
    s.write((cmd + "\n").encode())
    time.sleep(1)
    out = s.read(s.in_waiting).decode(errors="replace")
    print(f"{label}: {out.strip()[-80:]}")

s.close()
print("\n=== SPI FLASH BOOT: COMPLETE ===")
