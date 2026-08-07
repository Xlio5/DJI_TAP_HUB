"""重启 bridge 模式: crsfbr_host=192.168.144.88 (电脑)"""
import paramiko, time

V3S = "192.168.144.66"
LOG = "/var/log/dji_rc_bridge.log"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(V3S, 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=2.0):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("停旧 bridge:", r("killall dji_rc_bridge 2>/dev/null; sleep 2; echo ok"))
print("\n启动 bridge (crsfbr-host=192.168.144.88):")
print(r("/tmp/dji_rc_bridge --interval 20 --out-dev /dev/ttyS0 --out-baud auto --crsf-telem 1 --rcmsg-host 10.0.0.2 --rcmsg-port 65530 --crsf-bridge --crsfbr-host 192.168.144.88 --crsfbr-port 65532 > " + LOG + " 2>&1 & echo PID=$!"))
time.sleep(5)
print("\nbridge 监听确认:")
print(r("grep -E 'crsf-bridge|输出 c|监听' " + LOG + " | head -5"))
print("\n进程 fd:")
pid = r("ps w | grep dji_rc_bridge | grep -v grep | awk '{print $1}'")
print("PID:", pid)
print(r("ls -la /proc/" + pid + "/fd/ 2>/dev/null | grep -E 'ttyS0|socket'"))
c.close()
print("\n[done]")
