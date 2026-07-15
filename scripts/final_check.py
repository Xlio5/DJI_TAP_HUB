import serial, time

ser = serial.Serial("COM10", 115200, timeout=0.5)
time.sleep(0.2)
ser.read(ser.in_waiting)

# Login
ser.write(b"root\n")
time.sleep(1.5)
out = ser.read(ser.in_waiting).decode(errors="replace")
if "Password" in out:
    ser.write(b"root\n")
    time.sleep(1)
    ser.read(ser.in_waiting)

tests = [
    ("VID/PID", "cat /sys/module/g_serial/parameters/idVendor /sys/module/g_serial/parameters/idProduct 2>/dev/null"),
    ("USB state", "cat /sys/class/udc/*/state 2>/dev/null"),
    ("NAT", "iptables -t nat -L POSTROUTING -n 2>&1 | grep -E 'MASQ|10\\.0'"),
    ("GW", "ip route | grep default"),
    ("IP forward", "cat /proc/sys/net/ipv4/ip_forward"),
    ("daemon", "ps | grep usb_tund"),
    ("web", "ps | grep web_server"),
    ("MTD", "cat /proc/mtd | head -3"),
]

for label, cmd in tests:
    ser.write((cmd + "\n").encode())
    time.sleep(0.8)
    out = ser.read(ser.in_waiting).decode(errors="replace").strip()
    lines = out.split("\n")
    best = [l for l in lines if l.strip() and "#" not in l]
    print(f"{label}:")
    for l in best[:3]:
        print(f"  {l.strip()[:100]}")

ser.close()
