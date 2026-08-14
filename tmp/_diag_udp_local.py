# -*- coding: utf-8 -*-
"""诊断: V3s 发 UDP 到 10.0.0.1:65532 是否本地投递"""
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
def run(cmd, t=15):
    _, o, e = c.exec_command(cmd, timeout=t)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== IP 配置 ===")
print(run("ip addr show | grep -E 'inet |tun_hub|eth0|wlan'"))
print("\n=== 路由 ===")
print(run("ip route show"))
print("\n=== uart_bridge 详细日志 (含时间) ===")
print(run("tr -d '\\000' < /tmp/ub.txt | tail -20"))
print("\n=== udp_send 试发一次 (看 uart_bridge 日志) ===")
run(": > /tmp/ub.txt")
print(run("/tmp/udp_send 10.0.0.1 65532"))
time.sleep(2)
print(run("tr -d '\\000' < /tmp/ub.txt | tail -8"))
c.close()
print("完成")
