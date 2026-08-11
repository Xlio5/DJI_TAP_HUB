"""从 V3s 拷贝 dropbear ed25519 host key 到本地"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

# 读 key 内容 (base64 传回)
_, o, e = c.exec_command("cat /etc/dropbear/dropbear_ed25519_host_key | base64")
time.sleep(2)
b64 = (o.read() + e.read()).decode().strip()
c.close()

import base64
key = base64.b64decode(b64)
local = r"c:\my_project\TUN_NAT_HUB\tmp\dropbear_ed25519_host_key"
with open(local, "wb") as f:
    f.write(key)
print(f"已保存 {local}: {len(key)} bytes")
print("内容:", key.decode(errors="replace"))
