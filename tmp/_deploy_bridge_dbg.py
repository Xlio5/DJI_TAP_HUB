"""部署带日志 bridge + 跑双向验证 + 看日志"""
import paramiko, time, base64, serial, socket, struct, threading

V3S = "192.168.144.66"
LOCAL = r"c:\my_project\TUN_NAT_HUB\ubuntu\build_v3s\dji_rc"
REMOTE = "/tmp/dji_rc_bridge"
LOG = "/var/log/dji_rc_bridge4.log"
CRSFBR_MAGIC = 0x46534352

data = open(LOCAL, "rb").read()
b64 = base64.b64encode(data).decode()

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(V3S, 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=2.0, stdin_data=None):
    stdin, out, err = c.exec_command(cmd)
    if stdin_data is not None:
        stdin.write(stdin_data)
        stdin.channel.shutdown_write()
    time.sleep(wait)
    return (out.read() + err.read()).decode(errors="replace").strip()

print("=== 部署 ===")
r("killall dji_rc_bridge 2>/dev/null; sleep 2")
r("base64 -d > " + REMOTE, wait=3.0, stdin_data=b64)
r("chmod +x " + REMOTE)
print("md5:", r("md5sum " + REMOTE))
r(REMOTE + " --interval 20 --out-dev /dev/ttyS0 --out-baud auto --crsf-telem 1 --rcmsg-host 10.0.0.2 --rcmsg-port 65530 --crsf-bridge --crsfbr-host 192.168.144.88 --crsfbr-port 65532 > " + LOG + " 2>&1 & echo PID=$!")
time.sleep(6)
pid = r("ps w | grep dji_rc_bridge | grep -v grep | awk '{print $1}'")
print("PID:", pid, "线程:", r(f"cat /proc/{pid}/status 2>/dev/null | grep Threads"))

print("\n=== 电脑 COM10 打开 ===")
try:
    ser = serial.Serial("COM10", 115200, timeout=1)
    print("COM10 OK")
except Exception as e:
    print("COM10 失败:", e); c.close(); raise SystemExit(1)

print("\n=== 测试 A: 电脑 UDP → V3s → COM10 ===")
udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
frame = bytes([0xC8, 0x06, 0x2C, 0xEE, 0xEA, 0x01, 0x00, 0x66])  # Parameter_Read
pkt = struct.pack("<I", CRSFBR_MAGIC) + frame
udp.sendto(pkt, (V3S, 65532))
print("已发 UDP:", frame.hex())
time.sleep(1)
got = ser.read(64)
print("COM10 收到:", got.hex() if got else "(空)")

print("\n=== 测试 B: COM10 → V3s → 电脑 UDP ===")
recv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
recv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
recv.bind(("0.0.0.0", 65532))
recv.settimeout(3)
ping = bytes([0xC8, 0x04, 0x28, 0xEE, 0xEA, 0x0D])
ser.write(ping)
print("COM10 已发:", ping.hex())
try:
    d, a = recv.recvfrom(128)
    print("UDP 收到:", d.hex() if d else "(空)")
except socket.timeout:
    print("UDP 超时")

print("\n=== V3s 日志 (bridge 相关) ===")
print(r(f"grep -E 'bridge|UART0 rx|监听|热重配' {LOG} | tail -15"))

ser.close(); udp.close(); recv.close(); c.close()
print("\n[done]")
