"""Restart echo server with TCP support on 10.0.0.1:9999 + DNAT."""
import paramiko, base64, time, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HOST = "192.168.88.66"
S = "echo '1234' | sudo -S"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username="xlong", password="1234", timeout=10)

def ssh(cmd, timeout=10):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    if out.strip(): print(out.strip())

# Kill old
ssh("killall -9 python3 2>/dev/null; true")
time.sleep(0.3)

# TCP echo server (bind 10.0.0.1:9999)
server = """import socket, threading

def handle(conn):
    try:
        data = conn.recv(4096)
        if data:
            conn.send(data)
        conn.close()
    except:
        pass

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("10.0.0.1", 9999))
s.listen(5)
print("TCP_ECHO_READY", flush=True)
while True:
    conn, addr = s.accept()
    threading.Thread(target=handle, args=(conn,)).start()
"""

b64 = base64.b64encode(server.encode()).decode()
cmd = "python3 -c 'import base64,sys; open(\"/home/xlong/echo_srv.py\",\"w\").write(base64.b64decode(sys.stdin.read()).decode()); print(\"OK\")'"
transport = c.get_transport()
chan = transport.open_session()
chan.exec_command(cmd)
chan.sendall(b64.encode())
chan.shutdown_write()
chan.recv_exit_status()
chan.close()

ssh("nohup python3 /home/xlong/echo_srv.py > /home/xlong/echo_out.txt 2>&1 & echo STARTED")
time.sleep(1)

# Verify
ssh(f"{S} ss -tlnp 2>/dev/null | grep 9999")
print()

# Add DNAT for TCP 9999
ssh(f"{S} iptables -t nat -D PREROUTING -i end1 -p tcp --dport 9999 -j DNAT --to-destination 10.0.0.1:9999 2>/dev/null; true")
ssh(f"{S} iptables -t nat -A PREROUTING -i end1 -p tcp --dport 9999 -j DNAT --to-destination 10.0.0.1:9999")
ssh(f"{S} iptables -D FORWARD -i end1 -o tun_hub -p tcp --dport 9999 -j ACCEPT 2>/dev/null; true")
ssh(f"{S} iptables -A FORWARD -i end1 -o tun_hub -p tcp --dport 9999 -j ACCEPT")

# Test from Windows
print("=== Test from Windows ===")
for i in range(3):
    try:
        import socket
        s = socket.socket()
        s.settimeout(2)
        t0 = time.time()
        s.connect(("192.168.88.66", 9999))
        t1 = time.time()
        s.send(b"hello")
        s.recv(256)
        s.close()
        print(f"  TCP #{i+1}: {(t1-t0)*1000:.1f}ms connect, echo OK")
    except Exception as e:
        print(f"  TCP #{i+1}: FAILED ({e})")

print("\nDone - TCP echo ready on 10.0.0.1:9999")
c.close()
