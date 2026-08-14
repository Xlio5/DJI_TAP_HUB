# -*- coding: utf-8 -*-
"""诊断: 检查 V3s uart_bridge 状态 + 最近日志"""
import paramiko, socket, time

def ws():
    for i in range(15):
        try:
            s=socket.create_connection(("192.168.144.66",22),timeout=4); s.close(); return True
        except Exception: time.sleep(4)
    return False
assert ws(), "V3s SSH 不通"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=10, allow_agent=False, look_for_keys=False)
def run(cmd, t=10):
    _, o, e = c.exec_command(cmd, timeout=t)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== uart_bridge 进程 ===")
print(run("ps -ef | grep uart_bridge | grep -v grep || echo 'NOT RUNNING'"))
print("\n=== udp_send 工具 ===")
print(run("ls -la /tmp/udp_send 2>/dev/null || echo 'MISSING'"))
print("\n=== 65532 监听 ===")
print(run("grep -i FFFC /proc/net/udp || echo 'no udp listen'"))
print("\n=== uart_bridge 最近日志 (ub.txt) ===")
print(run("tr -d '\\000' < /tmp/ub.txt 2>/dev/null | tail -8 || echo 'no log'"))
c.close()
print("\n完成")
