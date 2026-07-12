import serial, time
ser = serial.Serial("COM10", 115200, timeout=1)
time.sleep(0.2)
ser.read(ser.in_waiting)

# Login
ser.write(b"root\n")
time.sleep(1.5)
out = ser.read(ser.in_waiting).decode(errors="replace")
if "Password" in out:
    ser.write(b"root\n")
    time.sleep(1)
    out += ser.read(ser.in_waiting).decode(errors="replace")
print("Login done")

# Network
ser.write(b"ip addr show eth0 2>/dev/null | grep inet\n")
time.sleep(0.5)
out = ser.read(ser.in_waiting).decode(errors="replace")
print("ETH0:", out.strip()[-80:])

# Services
ser.write(b"ps | grep usb_tund\n")
time.sleep(0.5)
out = ser.read(ser.in_waiting).decode(errors="replace")
print("daemon:", out.strip()[-80:])

ser.write(b"ps | grep web\n")
time.sleep(0.5)
out = ser.read(ser.in_waiting).decode(errors="replace")
print("web:", out.strip()[-80:])

# API
ser.write(b"wget -q -O - http://127.0.0.1:8080/api/heartbeat\n")
time.sleep(1.5)
out = ser.read(ser.in_waiting).decode(errors="replace")
print("API:", out.strip()[-200:])

# SPI
ser.write(b"cat /proc/mtd\n")
time.sleep(0.5)
out = ser.read(ser.in_waiting).decode(errors="replace")
print("MTD:", out.strip()[-80:])

ser.close()
