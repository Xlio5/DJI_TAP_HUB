"""90 秒监控 v149 PB6 运行中切换 (更长时间窗口)"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

# 每 5 秒采样一次当前 PB6 状态 + 日志增量
start = int(r("wc -c < /var/log/dji_rc.log"))
print("监控开始(90s), 日志起点:", start)
t0 = time.time()
while time.time() - t0 < 90:
    data = r("devmem 0x01C20834 32 2>/dev/null || devmem 0x01C20834")
    newlog = r("tail -c +" + str(start + 1) + " /var/log/dji_rc.log")
    interesting = [l for l in newlog.splitlines()
                   if ("PB6" in l or "变化" in l or "getty" in l or "打开失败" in l or "模式" in l)]
    print(f"[t+{time.time()-t0:.0f}s] DATA={data.strip()} " + (" | ".join(interesting) if interesting else ""))
    start = int(r("wc -c < /var/log/dji_rc.log"))
    time.sleep(5)
print("\n=== 最终 ttyS0 占用 ===")
print(r("fuser /dev/ttyS0 2>&1 || echo '无占用'"))
print("=== dji_rc 进程 ===")
print(r("ps w | grep dji_rc | grep -v grep || echo '进程挂了!'"))
c.close()
print("\n[监控结束]")
