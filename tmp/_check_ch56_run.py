"""确认对调版运行正常 + CH5/CH6 行为"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 对调版日志尾 8 行 ===")
print(r("tail -8 /var/log/dji_rc_ch56.log 2>/dev/null"))
print("\n=== 进程 ===")
print(r("ps w | grep dji_rc_ch56 | grep -v grep || echo 挂了"))
print("\n=== 运行时长 ===")
print(r("ps -o etime= -p $(cat /proc/$(pgrep -f dji_rc_ch56 | head -1)/stat 2>/dev/null | awk '{print $1}' 2>/dev/null) 2>/dev/null || echo 查进程"))
c.close()
print("\n[done]")
