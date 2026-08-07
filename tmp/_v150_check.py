"""验证 v150 启动: dji_rc 正式版 + 主循环健康 + PB6"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)
    print("SSH 连接: OK")
except Exception as e:
    print("SSH 连接失败:", e)
    raise SystemExit(1)

def r(cmd, wait=1.5):
    try:
        _, o, e = c.exec_command(cmd)
        time.sleep(wait)
        return (o.read() + e.read()).decode(errors="replace").strip()
    except Exception as ex:
        return f"<exec 异常: {ex}>"

print("=== 1. dji_rc md5 (应 fad8b8f2) ===")
print(r("md5sum /usr/local/bin/dji_rc"))
print("\n=== 2. dji_rc 进程 ===")
print(r("ps w | grep dji_rc | grep -v grep || echo 无"))
print("\n=== 3. 内核 cmdline ===")
print(r("cat /proc/cmdline"))
print("\n=== 4. 主循环健康 (10秒内 CH 行增长) ===")
s1 = r("grep -c 'CH1=' /var/log/dji_rc.log")
time.sleep(10)
s2 = r("grep -c 'CH1=' /var/log/dji_rc.log")
print(f"CH: {s1} → {s2} {'增长 ✓(主循环活)' if s1 != s2 else '停止 ✗(卡死)'}")
print("\n=== 5. out ok (SBUS 输出) 计数 ===")
print(r("grep -c 'out ok' /var/log/dji_rc.log"))
print("\n=== 6. rcmsg fail (应 0 或很少) ===")
print(r("grep -c 'rcmsg send fail' /var/log/dji_rc.log || echo 0"))
print("\n=== 7. PB6 当前 (devmem) ===")
print(r("devmem 0x01C20834 32"))
print("\n=== 8. 日志头 20 行 (PB6 检测/输出) ===")
print(r("head -20 /var/log/dji_rc.log"))
c.close()
print("\n[done]")
