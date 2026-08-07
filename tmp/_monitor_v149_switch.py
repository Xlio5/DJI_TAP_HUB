"""60 秒监控 v149 PB6 运行中切换 (需老大配合接地/断开)"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

start = int(r("wc -c < /var/log/dji_rc.log"))
print("监控开始, 日志起点字节:", start)
print("=== 请在 60 秒窗口内: 接地 8s -> 断开 8s ===")
time.sleep(60)
newlog = r("tail -c +" + str(start + 1) + " /var/log/dji_rc.log")
lines = [l for l in newlog.splitlines()
         if ("PB6" in l or "变化" in l or "getty" in l or "输出" in l or "打开失败" in l or "out ok" in l)]
print("\n=== 60 秒窗口 PB6/切换相关日志 ===")
for l in lines:
    print(l)
print("\n=== 当前 ttyS0 占用 ===")
print(r("fuser /dev/ttyS0 2>&1 || echo '无占用'"))
print("=== dji_rc 进程 ===")
print(r("ps w | grep dji_rc | grep -v grep || echo '进程挂了!'"))
c.close()
print("\n[监控结束]")
