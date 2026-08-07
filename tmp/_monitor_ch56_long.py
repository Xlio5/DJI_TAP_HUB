"""长时间监控 CH5/CH6 (60s, 0.5s 采样) - 抓偶发跳动"""
import paramiko, time, re

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.0):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 60s 监控 CH5/CH6 (请操作遥控器) ===")
t0 = time.time()
last5 = last6 = None
while time.time() - t0 < 60:
    line = r("grep 'CH1=' /var/log/dji_rc.log 2>/dev/null | tail -1")
    m = re.search(r'CH5=([+-]?\d+) CH6=([+-]?\d+)', line)
    rx = re.search(r'rx1=(\d+) rx2=(\d+)', line)
    g = re.search(r'g1=(\d+) g2=(\d+)', line)
    if m:
        c5, c6 = int(m.group(1)), int(m.group(2))
        # 只在 CH5/CH6 非零或变化时打印
        if c5 != 0 or c6 != 0:
            print(f"[t+{time.time()-t0:.0f}s] CH5={c5} CH6={c6}" +
                  (f" rx1={rx.group(1)} rx2={rx.group(2)}" if rx else "") +
                  (f" g1={g.group(1)} g2={g.group(2)}" if g else ""), flush=True)
    time.sleep(0.5)
print("=== 监控结束 ===")
c.close()
