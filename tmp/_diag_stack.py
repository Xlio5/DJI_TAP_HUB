"""查 dji_rc 主循环卡死位置: wchan + syscall + 线程"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

pid = "292"
print("=== 1. 进程状态 + wchan (卡在哪个内核函数) ===")
print(r("cat /proc/" + pid + "/status | grep -E 'State|Threads'"))
print(r("cat /proc/" + pid + "/wchan 2>/dev/null || echo 无wchan"))
print(r("cat /proc/" + pid + "/syscall 2>/dev/null || echo 无syscall"))

print("\n=== 2. 线程列表 ===")
print(r("for t in /proc/" + pid + "/task/*; do echo -n \"$(basename $t): \"; cat $t/comm 2>/dev/null; echo -n '  wchan='; cat $t/wchan 2>/dev/null; echo -n '  syscall='; cat $t/syscall 2>/dev/null; echo; done"))

print("\n=== 3. 所有线程状态 ===")
print(r("for t in /proc/" + pid + "/task/*; do echo -n \"$(basename $t) \"; awk '/State/{print $2,$3}' $t/status 2>/dev/null; done"))

print("\n=== 4. 主线程 (Tgid) 卡在哪 ===")
print(r("awk '/State|wchan/{print}' /proc/" + pid + "/task/" + pid + "/status 2>/dev/null"))
print(r("cat /proc/" + pid + "/task/" + pid + "/wchan 2>/dev/null"))

print("\n=== 5. fd 列表 (看有无半开的 socket) ===")
print(r("ls -la /proc/" + pid + "/fd/ 2>/dev/null | grep -E 'socket|tty|pipe'"))
c.close()
print("\n[done]")
