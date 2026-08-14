"""Setup: echo server on 10.0.0.1:9999 + DNAT forwarding + test."""
import paramiko, base64, time, sys, subprocess, socket
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HOST = "192.168.144.66"
DJI = "172.24.91.112:33625"
S = "echo '1234' | sudo -S"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username="xlong", password="1234", timeout=10)

def ssh(cmd, timeout=10):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    if out.strip(): print(out.strip())

# 1. Kill old + deploy echo server (binds 10.0.0.1)
print("=== Deploying echo server ===")
ssh("killall -9 python3 2>/dev/null; true")
time.sleep(0.3)

server_code = """import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("10.0.0.1", 9999))
print("READY", flush=True)
while True:
    data, addr = s.recvfrom(4096)
    s.sendto(data, addr)
"""
b64 = base64.b64encode(server_code.encode()).decode()
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
ssh("ss -tulnp 2>/dev/null | grep 9999")

# 2. Add DNAT port forwarding for UDP 9999
print("\n=== Adding DNAT for UDP 9999 ===")
ssh(f"{S} iptables -t nat -D PREROUTING -i end1 -p udp --dport 9999 -j DNAT --to-destination 10.0.0.1:9999 2>/dev/null; true")
ssh(f"{S} iptables -t nat -A PREROUTING -i end1 -p udp --dport 9999 -j DNAT --to-destination 10.0.0.1:9999")
ssh(f"{S} iptables -D FORWARD -i end1 -o tun_hub -p udp --dport 9999 -j ACCEPT 2>/dev/null; true")
ssh(f"{S} iptables -A FORWARD -i end1 -o tun_hub -p udp --dport 9999 -j ACCEPT")

# 3. Test from Windows (via WiFi to RK3588 LAN IP, DNAT -> 10.0.0.1)
print("\n=== Test from Windows -> RK3588:9999 (DNAT -> 10.0.0.1) ===")
for i in range(5):
    try:
        sock = __import__('socket').socket(__import__('socket').AF_INET, __import__('socket').SOCK_DGRAM)
        sock.settimeout(2)
        sock.sendto(b"ping", ("192.168.144.66", 9999))
        t0 = time.time()
        sock.recvfrom(256)
        elapsed = (time.time() - t0) * 1000
        sock.close()
        print(f"  Echo #{i+1}: {elapsed:.2f}ms (Windows -> RK3588 LAN -> DNAT -> 10.0.0.1 -> back)")
    except Exception as e:
        print(f"  Echo #{i+1}: FAILED ({e})")

# 4. Test from DJI RC ADB shell (via WiFi -> RK3588:9999)
print("\n=== Test from DJI RC ADB (WiFi) -> RK3588:9999 ===")
subprocess.run(["adb", "connect", DJI], capture_output=True, timeout=5)
r = subprocess.run(
    ["adb", "-s", DJI, "shell",
     "for i in 1 2 3 4 5; do echo PING | nc -u -w 2 192.168.144.66 9999 2>/dev/null && echo OK || echo FAIL; done"],
    capture_output=True, text=True, timeout=15
)
print(r.stdout.strip())

# 5. Daemon stats
print("\n=== Daemon stats ===")
ssh(f"{S} journalctl -u tun_nat_hub --no-pager -n 2 2>&1")

c.close()
print("\nDone")
