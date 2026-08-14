"""Deploy UDP echo server on RK3588 for tunnel latency testing."""
import paramiko, base64, time, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HOST = "192.168.144.66"
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username="xlong", password="1234", timeout=10)

def run(cmd, timeout=10):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    if out.strip(): print(out.strip())

S = "echo '1234' | sudo -S"

# Kill old
run("killall -9 python3 2>/dev/null; true")
time.sleep(0.3)

# Upload echo server
server_code = """import socket, time
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("10.0.0.1", 9999))
print("ECHO_READY", flush=True)
while True:
    data, addr = s.recvfrom(2048)
    s.sendto(data, addr)
"""

b64 = base64.b64encode(server_code.encode()).decode()
cmd = "python3 -c 'import base64,sys; data=base64.b64decode(sys.stdin.read()); open(\"/home/xlong/echo_srv.py\",\"w\").write(data.decode()); print(\"OK\")'"

transport = c.get_transport()
chan = transport.open_session()
chan.exec_command(cmd)
chan.sendall(b64.encode())
chan.shutdown_write()
chan.recv_exit_status()
chan.close()

# Start
run("nohup python3 /home/xlong/echo_srv.py > /home/xlong/echo_out.txt 2>&1 & echo STARTED")
time.sleep(1)
run("ss -tulnp 2>/dev/null | grep 9999")

print("\n=== UDP Echo Server Ready ===")
print("Address: 10.0.0.1:9999")
print("")
print("=== Test from DJI RC ===")
print("adb shell 'for i in 1 2 3 4 5; do echo PING | nc -u -w 1 10.0.0.1 9999 2>/dev/null; done'")
print("")
print("=== Test camera from RK3588 ===")
run("ping -c 5 192.168.144.101 2>&1")

c.close()
