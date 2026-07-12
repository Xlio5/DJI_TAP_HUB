import serial, time

ser = serial.Serial("COM10", 115200, timeout=0.5)

ser.read(ser.in_waiting)
ser.write(b"\n")
time.sleep(0.3)

out = ser.read(ser.in_waiting).decode(errors="replace")
print("Prompt:", out.strip()[-60:])

# Login
if "login:" in out:
    ser.write(b"root\n")
    time.sleep(1)
    out = ser.read(ser.in_waiting).decode(errors="replace")
    if "Password" in out:
        ser.write(b"root\n")
        time.sleep(1)
        out = ser.read(ser.in_waiting).decode(errors="replace")
    print("Login:", out[-100:])

# Tests
tests = [
    ("MTD", "cat /proc/mtd"),
    ("Mount", "mount | grep squash"),
    ("PS", "ps | grep usb_tund"),
    ("PS2", "ps | grep web_server"),
    ("API", "wget -q -O - http://127.0.0.1:8080/api/heartbeat"),
]

for name, cmd in tests:
    ser.write((cmd + "\n").encode())
    time.sleep(1)
    out = ser.read(ser.in_waiting).decode(errors="replace")
    print(f"{name}: {out.strip()[-150:]}")

ser.close()
