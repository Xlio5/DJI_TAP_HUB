"""Reboot V3s and verify SPI boot with VID/PID fix"""
import serial, time

ser = serial.Serial("COM10", 115200, timeout=0.5)
time.sleep(0.3)
ser.read(ser.in_waiting)

# Login and reboot
ser.write(b"root\n")
time.sleep(1.5)
out = ser.read(ser.in_waiting).decode(errors="replace")
if "Password" in out:
    ser.write(b"root\n")
    time.sleep(1)
    ser.read(ser.in_waiting)

ser.write(b"reboot -f\n")
time.sleep(1)
ser.read(ser.in_waiting)
print("Rebooting... waiting for SPI boot")

# Wait and read boot log
time.sleep(20)
boot_log = ser.read(ser.in_waiting).decode(errors="replace")

checks = [
    ("SPI SPL", "Trying to boot from sunxi SPI"),
    ("squashfs", "Mounted root (squashfs"),
    ("login", "login:"),
    ("g_serial", "g_serial"),
]
for label, pattern in checks:
    found = pattern in boot_log
    print(f"[{'OK' if found else 'FAIL'}] {label}")

# Login and check VID/PID
if "login:" in boot_log:
    ser.write(b"root\n")
    time.sleep(1.5)
    out = ser.read(ser.in_waiting).decode(errors="replace")
    if "Password" in out:
        ser.write(b"root\n")
        time.sleep(1)
        ser.read(ser.in_waiting)

    for cmd, label in [
        ("cat /sys/module/g_serial/parameters/idVendor", "idVendor"),
        ("cat /sys/module/g_serial/parameters/idProduct", "idProduct"),
        ("cat /sys/class/udc/*/state 2>/dev/null", "USB state"),
        ("iptables -t nat -L POSTROUTING -n 2>&1 | grep MASQ", "NAT"),
        ("ip route | grep default", "GW"),
    ]:
        ser.write((cmd + "\n").encode())
        time.sleep(0.8)
        out = ser.read(ser.in_waiting).decode(errors="replace").strip()
        print(f"  {label}: {out[:80]}")

ser.close()
