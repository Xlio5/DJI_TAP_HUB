# -*- coding: utf-8 -*-
"""验证统一 magic 后完整回传链路: V3s 持续 ping → ELRS → 响应回传"""
import paramiko, socket, time

def ws():
    for i in range(15):
        try:
            s=socket.create_connection(("192.168.144.66",22),timeout=4); s.close(); return True
        except Exception: time.sleep(4)
    return False
assert ws()

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)
def run(cmd, t=25):
    _, o, e = c.exec_command(cmd, timeout=t)
    return (o.read() + e.read()).decode(errors="replace").strip()

# 清日志
run(": > /tmp/ub.txt 2>/dev/null")

# 确认 udp_ping 存在
print("udp_ping:", run("ls -la /tmp/udp_ping 2>/dev/null | awk '{print $5}' || echo MISSING"))

# 持续 ping 15s (覆盖 ELRS 波特率轮换)
print("=== V3s 持续 ping 15s ===")
print(run("/tmp/udp_ping 10.0.0.1 65532 15", t=25))
time.sleep(2)

# 检查回传
print("\n=== uart_bridge 日志 (应出现 [uart→net]) ===")
print(run("tr -d '\\000' < /tmp/ub.txt | tail -12"))
c.close()
print("\n完成 - 看电脑桥监测 [ELRS→V3s]")
