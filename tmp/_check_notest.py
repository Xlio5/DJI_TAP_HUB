"""查无对调版日志"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 无对调版日志尾 8 行 ===")
print(r("tail -8 /var/log/dji_rc_notest.log 2>/dev/null"))
print("\n=== 20秒后 rx 计数 ===")
time.sleep(20)
print(r("tail -3 /var/log/dji_rc_notest.log 2>/dev/null | grep -oE 'rx1=[0-9]* rx2=[0-9]*|g1=[0-9]* g2=[0-9]*'"))
c.close()
print("\n[done]")
