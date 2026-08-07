"""诊断: CH 主循环是否还活着 + PB6 poll 卡在哪"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 1. CH 行是否增长 (10秒) ===")
s1 = r("grep -c 'CH1=' /var/log/dji_rc_diag.log")
time.sleep(10)
s2 = r("grep -c 'CH1=' /var/log/dji_rc_diag.log")
print(f"CH: {s1} → {s2} {'增长 ✓(主循环活)' if s1 != s2 else '停止 ✗(主循环卡)'}")

print("\n=== 2. PB6 poll 是否增长 (10秒) ===")
p1 = r("grep -c 'PB6 DATA' /var/log/dji_rc_diag.log")
time.sleep(10)
p2 = r("grep -c 'PB6 DATA' /var/log/dji_rc_diag.log")
print(f"PB6: {p1} → {p2} {'增长 ✓' if p1 != p2 else '停止 ✗(poll 不再跑)'}")

print("\n=== 3. PB6 最后 4 条 + 上下文 (看最后一次 poll 前后) ===")
print(r("grep -n 'PB6 DATA' /var/log/dji_rc_diag.log | tail -4"))
print("\n=== 4. 最后一次 PB6 poll 之后的日志 ===")
last_line = r("grep -n 'PB6 DATA' /var/log/dji_rc_diag.log | tail -1 | cut -d: -f1")
if last_line:
    print(r("sed -n '" + last_line + ",$p' /var/log/dji_rc_diag.log | head -15"))
c.close()
print("\n[done]")
