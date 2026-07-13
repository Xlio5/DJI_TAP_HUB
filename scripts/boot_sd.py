import serial, time

ser = serial.Serial("COM10", 115200, timeout=0.5)
time.sleep(0.3)
ser.read(ser.in_waiting)

steps = [
    ("zImage", "fatload mmc 0:1 0x41000000 zImage", 3),
    ("DTB", "fatload mmc 0:1 0x42000000 sun8i-v3s-licheepi-zero-dock.dtb", 1),
    ("bootargs", "setenv bootargs console=ttyS0,115200 root=/dev/mmcblk0p2 rootfstype=squashfs rootwait g_serial.idVendor=0x0BDA g_serial.idProduct=0x8812 g_serial.use_acm=0", 0.5),
    ("bootcmd", "setenv bootcmd fatload mmc 0:1 0x41000000 zImage; fatload mmc 0:1 0x42000000 sun8i-v3s-licheepi-zero-dock.dtb; bootz 0x41000000 - 0x42000000", 0.5),
    ("saveenv", "saveenv", 1.5),
    ("BOOT", "bootz 0x41000000 - 0x42000000", 2),
]

for label, cmd, wait in steps:
    ser.write((cmd + "\r\n").encode())
    time.sleep(wait)
    out = ser.read(ser.in_waiting).decode(errors="replace")
    ok = "bytes read" in out or "done" in out or "Starting kernel" in out
    print(f"{label}: {'OK' if ok else out.strip()[-60:]}")

time.sleep(12)
out = ser.read(ser.in_waiting).decode(errors="replace")
print(out[-600:] if len(out) > 600 else out)
ser.close()
