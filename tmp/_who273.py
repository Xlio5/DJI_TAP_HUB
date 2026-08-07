"""查 PID 273 是否 respawn 的新 getty"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 1. PID 273 身份 ===")
print(r("cat /proc/273/cmdline 2>&1 | tr '\\0' ' '; echo; awk '/PPid/{print \"PPID:\", $2}' /proc/273/status"))
print("\n=== 2. 当前全部 ttyS0 占用 ===")
print(r("fuser /dev/ttyS0 2>&1"))
print("\n=== 3. getty 相关进程 ===")
print(r("ps w | grep -E 'getty|login' | grep -v grep || echo 无"))
print("\n=== 4. 又杀一次 fuser -k, 看是否 respawn ===")
print(r("fuser -k /dev/ttyS0 2>&1; sleep 2; fuser /dev/ttyS0 2>&1 || echo '已释放'"))
c.close()
print("\n[done]")
