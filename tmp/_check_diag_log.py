"""查诊断版日志文件状态 + 进程"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 1. 日志文件存在? 大小? ===")
print(r("ls -la /var/log/dji_rc_diag.log"))
print("\n=== 2. 日志尾 5 行 ===")
print(r("tail -5 /var/log/dji_rc_diag.log"))
print("\n=== 3. dji_rc_diag 进程 ===")
print(r("ps w | grep dji_rc_diag | grep -v grep || echo '无进程!'"))
print("\n=== 4. 进程 fd (stdout 指向哪?) ===")
print(r("ls -la /proc/$(pgrep -f dji_rc_diag | head -1)/fd/1 2>/dev/null || echo '查 fd1'"))
print("\n=== 5. 等 5 秒日志是否增长 ===")
s1 = r("wc -c < /var/log/dji_rc_diag.log")
time.sleep(5)
s2 = r("wc -c < /var/log/dji_rc_diag.log")
print(f"5秒前: {s1} → 5秒后: {s2} {'增长 ✓' if s1 != s2 else '未增长 ✗'}")
print("\n=== 6. 当前 PB6 (devmem) ===")
print(r("devmem 0x01C20834 32"))
c.close()
print("\n[done]")
