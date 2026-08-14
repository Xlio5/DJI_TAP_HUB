# -*- coding: utf-8 -*-
"""同步 V3s uart_bridge 到统一 magic 版本 (彻底清旧进程 + 分块重传)"""
import paramiko, socket, time, base64, hashlib

def connect():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)
    return c

def run(c, cmd, t=20):
    try:
        _, o, e = c.exec_command(cmd, timeout=t)
        return (o.read() + e.read()).decode(errors="replace").strip()
    except Exception as ex:
        return f"ERR: {ex}"

# 1. 彻底杀旧进程
print("=== 1. 彻底杀旧进程 ===")
c = connect()
print(run(c, "killall -9 uart_bridge 2>/dev/null; kill -9 $(ps -ef | grep uart_bridge | grep -v grep | awk '{print $2}') 2>/dev/null; sleep 3; ps -ef | grep uart_bridge | grep -v grep || echo ALL_STOPPED"))
c.close()

# 2. 重传 (分块 exec, 每块独立连接)
print("\n=== 2. 上传统一 magic 版 ===")
b64 = base64.b64encode(open(r"c:\my_project\TUN_NAT_HUB\tmp\uart_bridge", "rb").read()).decode()
CHUNK = 4096
want_md5 = hashlib.md5(open(r"c:\my_project\TUN_NAT_HUB\tmp\uart_bridge","rb").read()).hexdigest()
print(f"b64 长度 {len(b64)}, 目标 md5 {want_md5}")

c = connect()
run(c, "rm -f /tmp/ub.b64; echo cleared")
c.close()
for i in range(0, len(b64), CHUNK):
    chunk = b64[i:i+CHUNK]
    c = connect()
    r = run(c, f"echo -n '{chunk}' >> /tmp/ub.b64", t=10)
    c.close()
    if r and "ERR" in r:
        print(f"chunk {i//CHUNK} 失败: {r}")
        break
    if i % (CHUNK*50) == 0:
        print(f"  ... {i}/{len(b64)}")

# 3. 解码 + 校验
print("\n=== 3. 解码 + 校验 ===")
c = connect()
print("解码+md5:", run(c, "base64 -d /tmp/ub.b64 > /tmp/uart_bridge && chmod +x /tmp/uart_bridge && md5sum /tmp/uart_bridge | awk '{print $1}'"))
c.close()

# 4. 启动
print("\n=== 4. 启动统一 magic 版 ===")
c = connect()
print(run(c, "/tmp/uart_bridge 115200 10.0.0.2 > /tmp/ub.txt 2>&1 & sleep 3; ps -ef | grep uart_bridge | grep -v grep | awk '{print \"PID:\", $2}'; head -3 /tmp/ub.txt"))
print("65532:", run(c, "grep FFFC /proc/net/udp"))
c.close()
print("完成")
