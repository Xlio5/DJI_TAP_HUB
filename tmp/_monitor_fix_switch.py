"""监控修复版 PB6 运行中切换 (接地/断开)"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

LOG = "/var/log/dji_rc_fix.log"
start = int(r("wc -c < " + LOG))
print("监控开始(75s), 日志起点:", start)
print("=== 请在 75 秒窗口: 接地 10s -> 断开 10s ===")
t0 = time.time()
last_pos = start
while time.time() - t0 < 75:
    time.sleep(3)
    now = int(r("wc -c < " + LOG))
    if now > last_pos:
        seg = r("tail -c +" + str(last_pos + 1) + " " + LOG)
        interesting = [l.strip() for l in seg.splitlines()
                       if ("PB6" in l or "变化" in l or "getty" in l or "模式" in l or "输出" in l)]
        if interesting:
            print(f"[t+{time.time()-t0:.0f}s] " + " | ".join(interesting[:3]))
        last_pos = now
print("\n=== 进程 ===")
print(r("ps w | grep dji_rc_fix | grep -v grep || echo '进程挂了!'"))
print("=== ttyS0 占用 ===")
print(r("fuser /dev/ttyS0 2>&1 || echo '无占用'"))
c.close()
print("\n[监控结束]")
