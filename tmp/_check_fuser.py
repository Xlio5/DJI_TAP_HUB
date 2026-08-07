"""确认设备上 fuser 来源 + busybox killall 是否支持 -t"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 1. which fuser ===")
print(r("which fuser; ls -la /usr/bin/fuser /bin/fuser 2>/dev/null"))
print("\n=== 2. busybox killall -t 支持? ===")
print(r("busybox killall --help 2>&1 | head -15"))
print("\n=== 3. busybox applet 列表 fuser/killall ===")
print(r("busybox 2>/dev/null | tr ',' '\\n' | grep -iE 'fuser|killall'"))
print("\n=== 4. 当前 ttyS0 占用 ===")
print(r("fuser /dev/ttyS0 2>&1"))
c.close()
print("\n[done]")
