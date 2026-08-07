"""45 秒窗口监控 PB6 接地/断开切换 (需老大配合物理操作)"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=10, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

start = int(r("wc -c < /var/log/dji_rc_poll.log"))
print("监控开始, 日志起点字节:", start)
time.sleep(45)
newlog = r("tail -c +" + str(start + 1) + " /var/log/dji_rc_poll.log")
lines = [l for l in newlog.splitlines() if ("PB6" in l or "pb6-poll" in l or "变化" in l or "getty" in l)]
print("=== 45 秒窗口内 PB6 相关日志 ===")
for l in lines:
    print(l)
print("=== 进程存活 ===")
print(r("ps w | grep /tmp/dji_rc | grep -v grep || echo 进程挂了!"))
c.close()
print("\n[监控结束]")
