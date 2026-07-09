#!/usr/bin/env python3
"""通过 UART (COM24) 传输 web_panel.py 到 V3s，使用 base64 编码"""

import serial
import base64
import os
import time

LOCAL_PATH = r"c:\my_project\TUN_NAT_HUB\ubuntu\web_panel.py"
PORT = "COM24"
BAUD = 115200

with open(LOCAL_PATH, "rb") as f:
    raw = f.read()

b64 = base64.b64encode(raw).decode("ascii")
print(f"File size: {len(raw)} bytes, base64: {len(b64)} chars")

ser = serial.Serial(PORT, BAUD, timeout=1)
ser.reset_input_buffer()
ser.reset_output_buffer()

# Login
ser.write(b"root\r\n")
time.sleep(0.5)
ser.write(b"root\r\n")
time.sleep(1)
ser.read(ser.in_waiting)

# Send base64 data in chunks
CHUNK = 100
chunks = [b64[i:i+CHUNK] for i in range(0, len(b64), CHUNK)]
print(f"Sending {len(chunks)} chunks...")

# Clear existing target file and start writing
ser.write(b"cat > /tmp/wp_b64 << 'ENDOFDATA'\r\n")
time.sleep(0.5)
ser.read(ser.in_waiting)

for i, chunk in enumerate(chunks):
    ser.write(chunk.encode() + b"\r\n")
    if i < 3 or i % 50 == 0:
        time.sleep(0.02)  # Small delay to prevent buffer overrun
    if (i + 1) % 100 == 0:
        print(f"  {i+1}/{len(chunks)} chunks sent")
        time.sleep(0.1)  # Let V3s catch up

ser.write(b"ENDOFDATA\r\n")
time.sleep(1)
print("Base64 data sent. Decoding...")

# Decode and install
cmds = [
    "base64 -d /tmp/wp_b64 > /tmp/wp_new.py 2>/dev/null && echo DECODE_OK || echo DECODE_FAIL",
    "wc -c /tmp/wp_new.py",
    "cp /tmp/wp_new.py /usr/local/bin/web_panel.py && chmod +x /usr/local/bin/web_panel.py && echo INSTALL_OK",
    "killall python3 2>/dev/null; sleep 1; python3 /usr/local/bin/web_panel.py > /var/log/web_panel.log 2>&1 &",
    "sleep 2; wget -q -O - http://127.0.0.1:8080/api/config",
]

for cmd in cmds:
    ser.write((cmd + "\r\n").encode())
    time.sleep(1 if "sleep" in cmd else 2)

time.sleep(2)
result = ser.read(ser.in_waiting).decode("ascii", errors="replace")
print(result[-2000:])
ser.close()
print("Done!")
