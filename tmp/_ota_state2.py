"""确认当前设备状态 (循环中断点)"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)
except Exception as e:
    print("SSH 连接失败:", e)
    raise SystemExit(1)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("当前槽:", r("cat /proc/cmdline | grep -o 'root=/dev/mtdblock[0-9]'"))
print("web_server:", r("ps w | grep web_server | grep -v grep | head -1 || echo 无"))
print("dji_rc:", r("ps w | grep dji_rc | grep -v grep | head -1 || echo 无"))
print("ctl block:", r("dd if=/dev/mtdblock0 bs=1 skip=1032192 count=6 2>/dev/null | hexdump -C | head -1"))
c.close()
print("\n[done]")
