"""部署 bridge 版 dji_rc 到 /tmp 手动跑 (UART0 ↔ 网口 UDP 65532)"""
import paramiko, time, base64

V3S = "192.168.144.66"
LOCAL = r"c:\my_project\TUN_NAT_HUB\ubuntu\build_v3s\dji_rc"
REMOTE = "/tmp/dji_rc_bridge"
LOG = "/var/log/dji_rc_bridge.log"

data = open(LOCAL, "rb").read()
b64 = base64.b64encode(data).decode()
print("bridge 版大小:", len(data))

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

print("\n=== 1. 停旧 dji_rc ===")
print(r("killall dji_rc 2>/dev/null; sleep 2; echo ok"))

print("\n=== 2. 传输 bridge 版 ===")
print(r("base64 -d > " + REMOTE, wait=3.0, stdin_data=b64))
print("md5:", r("chmod +x " + REMOTE + "; md5sum " + REMOTE))

print("\n=== 3. 启动 bridge 模式 ===")
# rcmsg-host 用电脑 IP? 但 bridge 监听 0.0.0.0, 转发目标用任意。bridge 收 UART0 帧转发到 crsfbr_host
# crsfbr_host 默认 10.0.0.2, 需要改。用 --crsfbr-host 指定电脑可达 IP
print(r(REMOTE + " --interval 20 --out-dev /dev/ttyS0 --out-baud auto --crsf-telem 1 --rcmsg-host 10.0.0.2 --rcmsg-port 65530 --crsf-bridge --crsfbr-host 10.0.0.2 --crsfbr-port 65532 > " + LOG + " 2>&1 & echo PID=$!"))

print("\n=== 4. 等 6 秒, 启动日志 ===")
time.sleep(6)
print(r("head -20 " + LOG))
print("\n=== 5. 进程 + fd ===")
print(r("ps w | grep dji_rc_bridge | grep -v grep | head -1"))
pid = r("ps w | grep dji_rc_bridge | grep -v grep | awk '{print $1}'")
print("fd:", r("ls -la /proc/" + pid + "/fd/ 2>/dev/null | grep -E 'ttyS|socket'"))
c.close()
print("\n[done]")
