"""诊断: 拔掉接地线后疑似卡死"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    c.connect("192.168.144.66", 22, "root", "root", timeout=10, allow_agent=False, look_for_keys=False)
    print("SSH 连接: OK")
except Exception as e:
    print("SSH 连接失败:", e)
    raise SystemExit(1)

def r(cmd, wait=2.0):
    try:
        _, o, e = c.exec_command(cmd)
        time.sleep(wait)
        return (o.read() + e.read()).decode(errors="replace").strip()
    except Exception as ex:
        return f"<exec 异常: {ex}>"

print("=== 1. 运行 dji_rc 进程 ===")
print(r("ps w | grep dji_rc | grep -v grep || echo 无"))
print("\n=== 2. dji_rc 固化 md5 (应 54e2a723) ===")
print(r("md5sum /usr/local/bin/dji_rc"))
print("\n=== 3. 日志尾 20 行 ===")
print(r("tail -20 /var/log/dji_rc.log 2>/dev/null"))
print("\n=== 4. getty ===")
print(r("ps w | grep getty | grep -v grep || echo 无 getty"))
print("\n=== 5. PB6 DATA (devmem) ===")
print(r("devmem 0x01C20834 2>/dev/null || echo devmem不可用"))
print("\n=== 6. 系统负载/内存 ===")
print(r("uptime; free | head -3"))
print("\n=== 7. dmesg 最近 ===")
print(r("dmesg 2>/dev/null | tail -8"))
c.close()
print("\n[done]")
