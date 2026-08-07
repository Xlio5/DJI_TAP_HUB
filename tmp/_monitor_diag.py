"""监控诊断版 poll 日志: 观察接地/断开时 DATA 是否变化"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

start = int(r("wc -c < /var/log/dji_rc_diag.log"))
print("监控开始(90s), 日志起点:", start)
print("=== 请在 90 秒窗口内: 接地 10s -> 断开 10s -> 接地 10s ===")
t0 = time.time()
last_pos = start
while time.time() - t0 < 90:
    time.sleep(5)
    now = int(r("wc -c < /var/log/dji_rc_diag.log"))
    if now > last_pos:
        seg = r("tail -c +" + str(last_pos + 1) + " /var/log/dji_rc_diag.log")
        pb6 = [l for l in seg.splitlines() if "PB6 DATA" in l]
        if pb6:
            print(f"[t+{time.time()-t0:.0f}s] {pb6[-1].strip()}")
        last_pos = now
print("\n=== 进程 ===")
print(r("ps w | grep dji_rc_diag | grep -v grep || echo '进程挂了!'"))
c.close()
print("\n[监控结束]")
