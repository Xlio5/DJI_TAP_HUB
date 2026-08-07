"""查 PID 174 (占用 ttyS0) 是谁 + dji_rc 为何没输出"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 1. PID 174 身份 ===")
print(r("cat /proc/174/cmdline 2>&1 | tr '\\0' ' '; echo; cat /proc/174/status 2>/dev/null | head -4"))
print("\n=== 2. 全部 dji_rc / getty 相关进程 ===")
print(r("ps w | grep -E 'dji|getty|login' | grep -v grep"))
print("\n=== 3. dji_rc fd 列表 (看 ttyS0 fd) ===")
print(r("ls -la /proc/112/fd/ 2>/dev/null | grep -E 'ttyS|pipe|tty'"))
print("\n=== 4. dji_rc 日志头 30 行 (找 PB6 检测/切换记录) ===")
print(r("head -30 /var/log/dji_rc.log 2>/dev/null"))
print("\n=== 5. 启动时间对比 ===")
print(r("ps -o pid,lstart,cmd -p 112,174 2>/dev/null; cat /proc/uptime"))
c.close()
print("\n[done]")
