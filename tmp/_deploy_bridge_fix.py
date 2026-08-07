"""部署 bridge 热重配修复版 + 验证线程/socket"""
import paramiko, time, base64

V3S = "192.168.144.66"
LOCAL = r"c:\my_project\TUN_NAT_HUB\ubuntu\build_v3s\dji_rc"
REMOTE = "/tmp/dji_rc_bridge"
LOG = "/var/log/dji_rc_bridge3.log"

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

print("停旧:", r("killall dji_rc_bridge 2>/dev/null; sleep 2; echo ok"))
print("传输:", r("base64 -d > " + REMOTE, wait=3.0, stdin_data=b64))
print("md5:", r("chmod +x " + REMOTE + "; md5sum " + REMOTE))
print("启动:", r(REMOTE + " --interval 20 --out-dev /dev/ttyS0 --out-baud auto --crsf-telem 1 --rcmsg-host 10.0.0.2 --rcmsg-port 65530 --crsf-bridge --crsfbr-host 192.168.144.88 --crsfbr-port 65532 > " + LOG + " 2>&1 & echo PID=$!"))
time.sleep(8)
pid = r("ps w | grep dji_rc_bridge | grep -v grep | awk '{print $1}'")
print("\nPID:", pid)
print("线程数:", r("cat /proc/" + pid + "/status 2>/dev/null | grep Threads"))
print("fd:", r("ls -la /proc/" + pid + "/fd/ 2>/dev/null | grep -E 'socket|ttyS0'"))
print("热重配? :", r("grep -c '热重配' " + LOG + " || echo 0"))
print("监听? :", r("grep '监听' " + LOG + " | head -1"))
print("udp 端口:", r("cat /proc/net/udp | grep -i ':ffdc' || echo '无 ffdc'"))
c.close()
print("\n[done]")
