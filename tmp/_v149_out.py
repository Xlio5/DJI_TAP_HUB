"""确认 v149 dji_rc 是否真的在输出 SBUS (out fd + out ok 日志)"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 1. dji_rc fd (看 ttyS0 输出 fd) ===")
print(r("ls -la /proc/110/fd/ 2>/dev/null | grep -E 'ttyS|socket'"))
print("\n=== 2. 日志头 25 行 (找 PB6 检测/输出模式) ===")
print(r("head -25 /var/log/dji_rc.log 2>/dev/null"))
print("\n=== 3. out ok 出现次数 ===")
print(r("grep -c 'out ok' /var/log/dji_rc.log 2>/dev/null || echo 0"))
print("\n=== 4. 最近 out ok 日志 ===")
print(r("grep 'out ok' /var/log/dji_rc.log 2>/dev/null | tail -3"))
print("\n=== 5. RC 输入状态 (rx1/rx2) ===")
print(r("tail -5 /var/log/dji_rc.log 2>/dev/null | grep -o 'rx1=[0-9]* rx2=[0-9]*' | tail -3"))
c.close()
print("\n[done]")
