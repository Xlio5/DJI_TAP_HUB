"""诊断 V3s bridge: 端口监听 + 日志 + UDP 到达"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 1. bridge 日志尾 20 行 ===")
print(r("tail -20 /var/log/dji_rc_bridge.log 2>/dev/null"))
print("\n=== 2. 端口 65532 监听? ===")
print(r("netstat -tulnp 2>/dev/null | grep 65532 || echo '无 netstat 输出'; ss -ulnp 2>/dev/null | grep 65532 || echo '无 ss'"))
print("\n=== 3. UDP 65532 是否收到包 (测试前) ===")
print(r("cat /proc/net/udp 2>/dev/null | grep ':FFDC' || echo '查不到'"))
print("\n=== 4. bridge 进程状态 ===")
print(r("ps w | grep dji_rc_bridge | grep -v grep | head -1"))
print("\n=== 5. 电脑 ping V3s / V3s ping 电脑 ===")
print(r("ping -c 2 -W 1 192.168.144.88 2>&1 | tail -2"))
c.close()
print("\n[done]")
