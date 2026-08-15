# -*- coding: utf-8 -*-
"""上传 get_baudbase 到 V3s 并运行, 读权威 uartclk"""
import paramiko, socket, time, base64

def ws():
    for i in range(15):
        try:
            s = socket.create_connection(("192.168.144.66", 22), timeout=4); s.close(); return True
        except Exception:
            time.sleep(3)
    return False
assert ws()

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=10, allow_agent=False, look_for_keys=False)
def run(cmd, t=15):
    _, o, e = c.exec_command(cmd, timeout=t)
    return (o.read() + e.read()).decode(errors="replace").strip()

# 上传 (base64 分块)
data = open(r"c:\my_project\TUN_NAT_HUB\tmp\get_baudbase", "rb").read()
b64 = base64.b64encode(data).decode()
run("rm -f /tmp/get_baudbase.b64")
for i in range(0, len(b64), 4096):
    run(f"echo -n '{b64[i:i+4096]}' >> /tmp/get_baudbase.b64")
run("echo '' >> /tmp/get_baudbase.b64")
print("上传:", run("base64 -d /tmp/get_baudbase.b64 > /tmp/get_baudbase && chmod +x /tmp/get_baudbase && ls -la /tmp/get_baudbase | awk '{print $5}'"))

# 运行 (三个 UART)
print("\n=== 权威 baud_base (uartclk/16) ===")
print("ttyS0:", run("/tmp/get_baudbase /dev/ttyS0"))
print("ttyS1:", run("/tmp/get_baudbase /dev/ttyS1"))
print("ttyS2:", run("/tmp/get_baudbase /dev/ttyS2"))
c.close()
print("完成")
