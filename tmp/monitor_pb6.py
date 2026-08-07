"""观察 PB6 poll 日志基线 (8秒)"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=10, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 等 8 秒收集 poll 基线 ===")
time.sleep(8)
print(r("grep -E 'PB6|pb6-poll' /var/log/dji_rc_poll.log | tail -8"))
print("\n=== 进程存活 ===")
print(r("ps w | grep /tmp/dji_rc | grep -v grep || echo 进程挂了!"))
c.close()
print("\n[done]")
