#!/usr/bin/env python3
"""串口直传 web_server 到 V3s (heredoc + base64)"""
import serial, time, base64

SERIAL = "COM11"
BAUD = 115200
LOCAL = r"c:\my_project\TUN_NAT_HUB\ubuntu\build_v3s\web_server"

with open(LOCAL, "rb") as f:
    data = f.read()
print(f"File: {len(data)} bytes")

b64 = base64.b64encode(data).decode()
print(f"Base64: {len(b64)} chars, ~{len(b64)*10//115200}s over serial")

ser = serial.Serial(SERIAL, BAUD, timeout=1)
print(f"Opened {SERIAL}")

# Clear any pending output
time.sleep(0.5)
ser.read(ser.in_waiting)

# Send newline to get a prompt
ser.write(b"\n")
time.sleep(0.3)
ser.read(ser.in_waiting)

print("Starting heredoc upload...")

# Step 1: start heredoc
ser.write(b"cat > /tmp/ws_b64 << 'HEREDOC_END'\n")
time.sleep(0.3)
ser.read(ser.in_waiting)

# Step 2: send base64 in chunks (with small delays to avoid buffer overrun)
LINE_LEN = 76  # standard base64 line length
for i in range(0, len(b64), LINE_LEN):
    line = b64[i:i+LINE_LEN]
    ser.write((line + "\n").encode())
    # Small delay every few lines to let V3s process
    if i % 4096 == 0:
        time.sleep(0.01)
        # Flush any echo (don't let buffer fill up)
        ser.read(ser.in_waiting)

ser.write(b"HEREDOC_END\n")
print("Base64 uploaded. Waiting for shell...")
time.sleep(1)
out = ser.read(ser.in_waiting).decode(errors="replace")
print(out[-200:] if len(out) > 200 else out)

# Step 3: Decode, install, test
commands = [
    "echo DECODING...",
    "base64 -d /tmp/ws_b64 > /tmp/ws_new 2>&1",
    "echo DECODE_RC=$? SIZE=$(wc -c < /tmp/ws_new)",
    "cp /tmp/ws_new /usr/local/bin/web_server",
    "chmod +x /usr/local/bin/web_server",
    "ls -la /usr/local/bin/web_server",
    "killall python3 2>/dev/null",
    "killall web_server 2>/dev/null",
    "sleep 1",
    "/usr/local/bin/web_server > /var/log/web_server.log 2>&1 &",
    "sleep 2",
    "wget -q -O - http://127.0.0.1:8080/api/heartbeat",
    "echo DONE",
]

for cmd in commands:
    ser.write((cmd + "\n").encode())
    time.sleep(0.4)
    out = ser.read(ser.in_waiting).decode(errors="replace")
    if out.strip():
        print(out.rstrip())

ser.close()
print("Done!")
