"""诊断: 主循环是否活着 (CH 打印) vs rx_thread (out ok)"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 1. 日志里 CH 行 (主循环) vs out ok (rx_thread) 计数 ===")
print("CH 行数:", r("grep -c 'CH1=' /var/log/dji_rc_diag.log"))
print("out ok 行数:", r("grep -c 'out ok' /var/log/dji_rc_diag.log"))
print("PB6 行数:", r("grep -c 'PB6 DATA' /var/log/dji_rc_diag.log"))
print("\n=== 2. 日志里最后 3 种行各自最后时间 ===")
print(r("tail -20 /var/log/dji_rc_diag.log | grep -c 'CH1='"))
print(r("tail -20 /var/log/dji_rc_diag.log | grep -c 'out ok'"))
print("\n=== 3. 线程数 ===")
print(r("cat /proc/292/status 2>/dev/null | grep Threads"))
print("\n=== 4. 进程 CPU 时间 (判断是否活) ===")
print(r("ps -o pid,stat,time,cmd -p 292 2>/dev/null || cat /proc/292/stat | awk '{print \"utime=\", $14, \"stime=\", $15}'"))
print("\n=== 5. 是否 out ok 还在增长 (10秒) ===")
s1 = r("grep -c 'out ok' /var/log/dji_rc_diag.log")
time.sleep(10)
s2 = r("grep -c 'out ok' /var/log/dji_rc_diag.log")
print(f"out ok: {s1} → {s2} {'增长 ✓' if s1 != s2 else '停止 ✗'}")
c.close()
print("\n[done]")
