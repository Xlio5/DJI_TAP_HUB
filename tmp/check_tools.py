"""检查 V3s busybox 可用工具 (确定传输方式)"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=10, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("base64:", r("which base64; base64 --help 2>&1 | head -1"))
print("uudecode:", r("which uudecode; which uuencode"))
print("cat:", r("which cat"))
print("dropbear/ssh:", r("which dropbear sshd 2>/dev/null; ps w | grep -iE 'dropbear|sshd' | grep -v grep | head -3"))
c.close()
print("[done]")
