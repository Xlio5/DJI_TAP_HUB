"""paramiko 验证设备连通 + 读 PB6 电平"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    c.connect("192.168.144.66", 22, "root", "root", timeout=10, allow_agent=False, look_for_keys=False)
    print("SSH OK")
except Exception as e:
    print("SSH 失败:", e)
    raise SystemExit(1)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("PB6 DATA:", r("devmem 0x01C20834 32"))
print("dji_rc:", r("ps w | grep dji_rc | grep -v grep | head -1 || echo 无"))
c.close()
