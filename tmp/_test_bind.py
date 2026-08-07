"""测试 V3s 65532 端口能否 bind + 排查占用"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 1. 测试 bind 65532 (busybox nc / python) ===")
print(r("python3 -c 'import socket; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.bind((\"0.0.0.0\",65532)); print(\"bind OK\")' 2>&1 || echo 'python bind 失败'"))
print("\n=== 2. 哪个进程占 65532 ===")
print(r("fuser -n udp 65532 2>&1 || echo '无占用'"))
print(r("cat /proc/net/udp 2>/dev/null | grep -i ':ffdc' || echo '无 :ffdc'"))
print("\n=== 3. 重启 bridge 看 stderr (日志同时捕获 stderr) ===")
print(r("killall dji_rc_bridge 2>/dev/null; sleep 1; /tmp/dji_rc_bridge --interval 20 --out-dev /dev/ttyS0 --out-baud auto --crsf-telem 1 --rcmsg-host 10.0.0.2 --rcmsg-port 65530 --crsf-bridge --crsfbr-host 192.168.144.88 --crsfbr-port 65532 > /var/log/dji_rc_bridge2.log 2>&1 & echo PID=$!"))
time.sleep(5)
print("\n=== 4. 完整日志 (含 stderr) ===")
print(r("cat /var/log/dji_rc_bridge2.log 2>/dev/null | head -30"))
print("\n=== 5. 线程数 ===")
pid = r("ps w | grep dji_rc_bridge | grep -v grep | awk '{print $1}'")
print("PID:", pid)
print(r("cat /proc/" + pid + "/status 2>/dev/null | grep Threads"))
c.close()
print("\n[done]")
