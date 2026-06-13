#!/usr/bin/env python3
"""Send UDP packet from RK3588 to Android TUN IP"""
import socket

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
msg = b"UDP_TEST_FROM_RK3588"

# Send to Android TUN IP
n = s.sendto(msg, ("10.0.0.2", 9999))
print(f"Sent {n} bytes to 10.0.0.2:9999 (UDP)")

# Try to receive echo
s.settimeout(2)
try:
    data, addr = s.recvfrom(1024)
    print(f"Got {len(data)}B reply from {addr}: {data}")
except socket.timeout:
    print("No reply within 2s (expected if no listener on Android)")

s.close()
print("UDP test complete")
