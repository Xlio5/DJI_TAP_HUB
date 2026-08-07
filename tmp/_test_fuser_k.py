"""测试 fuser -k /dev/ttyS0 能否释放 ttyS0 (验证 getty_stop 增强方案)"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 1. 当前 ttyS0 占用 ===")
print(r("fuser /dev/ttyS0 2>&1 || echo '无占用'"))
print("\n=== 2. 执行 fuser -k /dev/ttyS0 ===")
print(r("fuser -k /dev/ttyS0 2>&1; echo 'exit:' $?"))
print("\n=== 3. 杀后 ttyS0 占用 ===")
print(r("fuser /dev/ttyS0 2>&1 || echo '已释放 ✓'"))
print("\n=== 4. PID 174 还在吗 ===")
print(r("cat /proc/174/cmdline 2>&1 | tr '\\0' ' '; echo"))
print("\n=== 5. SSH 仍正常? ===")
print(r("echo 'SSH alive'"))
c.close()
print("\n[done]")
