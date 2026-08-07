"""从 V3s 获取 dropbear host key (固化用)"""
import paramiko, time, base64

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 1. dropbear key 位置 ===")
print(r("ls -la /etc/dropbear/ /var/run/dropbear/ 2>/dev/null"))
print("\n=== 2. key 文件内容 (base64) ===")
keys = r("ls /etc/dropbear/* /var/run/dropbear/* 2>/dev/null | head -5")
print("keys:", keys)
c.close()
print("\n[done]")
