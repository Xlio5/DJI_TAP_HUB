"""深入查 PID 174: 父进程链 + 是否 getty 登录遗留"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 1. PID 174 完整 cmdline + ppid ===")
print(r("cat /proc/174/cmdline 2>&1 | tr '\\0' ' '; echo; echo 'PPID:'; awk '/PPid/{print $2}' /proc/174/status"))
print("\n=== 2. 父进程链 (174 -> ppid -> ...) ===")
print(r("p=174; for i in 1 2 3 4; do echo -n \"$p: \"; cat /proc/$p/cmdline 2>/dev/null | tr '\\0' ' '; echo; p=$(awk '/PPid/{print $2}' /proc/$p/status 2>/dev/null); [ -z \"$p\" ] && break; done"))
print("\n=== 3. 全部 tty 进程 (找 getty/login/agetty) ===")
print(r("ps w | grep -iE 'getty|login|agetty|tinylogin|tty' | grep -v grep"))
print("\n=== 4. 所有挂 ttyS0 的进程 ===")
print(r("ls -la /proc/[0-9]*/fd/ 2>/dev/null | grep ttyS0 | awk '{print $3, $9, $10, $11}' | head"))
print("\n=== 5. inittab ttyS0 配置 ===")
print(r("grep -n 'ttyS0' /etc/inittab 2>/dev/null || echo 无 ttyS0 in inittab"))
c.close()
print("\n[done]")
