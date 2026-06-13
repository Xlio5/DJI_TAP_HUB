#!/bin/bash
# Test: Write to ttyGS0, then try to read response
echo "=== Writing to ttyGS0 ==="
echo "HELLO_FROM_RK3588" > /dev/ttyGS0
echo "Wrote 18 bytes"

echo "=== Reading from ttyGS0 (3 sec timeout) ==="
timeout 3 dd if=/dev/ttyGS0 bs=64 count=1 2>&1 || echo "no data received"

echo "=== TTY settings ==="
stty -F /dev/ttyGS0 -a 2>&1 | head -5

echo "=== g_serial module params ==="
cat /sys/module/g_serial/parameters/use_acm 2>/dev/null || echo "n/a"
