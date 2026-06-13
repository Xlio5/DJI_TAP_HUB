#!/bin/sh
# Deploy to RK3588: measure USB tunnel latency using nc TCP echo
# Approach: start TCP echo on RK3588 10.0.0.1, DJI RC connects + sends + closes
# Each connect/disconnect = 1 RTT

PORT=9999
echo "=== USB Tunnel Latency Test ==="

# Start TCP echo server in background
python3 -c "
import socket
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(('10.0.0.1', $PORT))
s.listen(5)
print('READY', flush=True)
while True:
    c, a = s.accept()
    data = c.recv(4096)
    if data:
        c.send(data)
    c.close()
" &
SERVER_PID=$!
sleep 1

# Wait for DJI RC to connect (triggered externally via ADB)
echo "Server PID=$SERVER_PID on 10.0.0.1:$PORT"
echo "Run from DJI RC: for i in \$(seq 1 20); do time echo PING | nc -w 2 10.0.0.1 $PORT; done"

# Keep running until killed
wait $SERVER_PID
