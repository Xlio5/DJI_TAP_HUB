"""精确诊断 bridge socket 状态"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

pid = r("ps w | grep dji_rc_bridge | grep -v grep | awk '{print $1}'")
print("PID:", pid)
print("\n=== 1. /proc/net/udp 完整 ===")
print(r("cat /proc/net/udp"))
print("\n=== 2. fd 全部 ===")
print(r("ls -la /proc/" + pid + "/fd/ 2>/dev/null"))
print("\n=== 3. 线程数 + 线程列表 ===")
print(r("cat /proc/" + pid + "/status 2>/dev/null | grep Threads"))
print(r("ls /proc/" + pid + "/task/ 2>/dev/null"))
print("\n=== 4. 每个线程 wchan (看 t4 是否在 recvfrom) ===")
print(r("for t in /proc/" + pid + "/task/*; do echo -n \"$(basename $t): \"; cat $t/wchan 2>/dev/null; echo; done"))
print("\n=== 5. bind 失败日志? ===")
print(r("grep -iE 'bind|失败|fail' /var/log/dji_rc_bridge.log | head -5"))
c.close()
print("\n[done]")
