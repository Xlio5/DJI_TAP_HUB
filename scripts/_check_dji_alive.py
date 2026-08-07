"""确认 dji_rc 是否存活 + 崩溃原因"""
import paramiko, time

V3S = "192.168.144.66"

def ssh_r(cmd, wait=2.0):
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(V3S, 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)
    _, out, err = c.exec_command(cmd)
    time.sleep(wait)
    r = (out.read() + err.read()).decode(errors="replace").strip()
    c.close()
    return r

print("=== 1. dji_rc 进程 ===")
print(ssh_r("ps w | grep -E 'dji' | grep -v grep || echo '无 dji_rc'"))

print("\n=== 2. dji_rc 日志尾 15 行 ===")
print(ssh_r("tail -15 /var/log/dji_rc.log"))

print("\n=== 3. dmesg 崩溃? ===")
print(ssh_r("dmesg | grep -iE 'segfault|dji_rc|killed' | tail -5"))

print("\n=== 4. getty ===")
print(ssh_r("ps w | grep getty | grep -v grep || echo '无 getty'"))
c.close()
print("\n[done]")
