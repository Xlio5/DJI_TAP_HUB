"""确认设备上线 + 状态"""
import paramiko, time, socket

HOST = "192.168.144.66"
try:
    s = socket.create_connection((HOST, 22), timeout=5); s.close()
    print("SSH 可达")
except Exception as e:
    print("SSH 不可达:", e); raise SystemExit(1)

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("槽位:", r("cat /proc/cmdline | grep -o 'root=/dev/mtdblock[0-9]'"))
print("dji_rc:", r("md5sum /usr/local/bin/dji_rc"))
print("web_server:", r("ps w | grep web_server | grep -v grep | head -1 || echo 无"))
print("dji_rc 进程:", r("ps w | grep dji_rc | grep -v grep | head -1 || echo 无"))
print("当前模式:", r("head -3 /var/log/dji_rc.log 2>/dev/null | tail -1"))
print("PB6:", r("devmem 0x01C20834 32"))
c.close()
print("\n[done]")
