"""Restart echo server on RK3588 (0.0.0.0:9999)."""
import paramiko, base64, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.88.66", username="xlong", password="1234", timeout=10)

# Kill old
c.exec_command("killall -9 python3 2>/dev/null; true", timeout=5)
time.sleep(0.3)

# Upload
server = "import socket\ns = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)\ns.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)\ns.bind(('0.0.0.0', 9999))\nprint('READY', flush=True)\nwhile True:\n    data, addr = s.recvfrom(4096)\n    s.sendto(data, addr)\n"
b64 = base64.b64encode(server.encode()).decode()

transport = c.get_transport()
cmd = "python3 -c 'import base64,sys; d=base64.b64decode(sys.stdin.read()); open(\"/home/xlong/echo_srv.py\",\"w\").write(d.decode()); print(\"OK\")'"
chan = transport.open_session()
chan.exec_command(cmd)
chan.sendall(b64.encode())
chan.shutdown_write()
chan.recv_exit_status()
chan.close()

# Start
c.exec_command("nohup python3 /home/xlong/echo_srv.py > /home/xlong/echo_out.txt 2>&1 & echo STARTED", timeout=5)
time.sleep(1)

stdin, stdout, stderr = c.exec_command("ss -tulnp 2>/dev/null | grep 9999", timeout=5)
print(stdout.read().decode(errors="replace").strip())
c.close()
print("Echo ready on 0.0.0.0:9999")
