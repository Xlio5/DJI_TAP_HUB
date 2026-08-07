"""看 bridge 启动完整日志 + 检查 bind 失败"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 1. bridge 日志头 25 行 ===")
print(r("head -25 /var/log/dji_rc_bridge.log 2>/dev/null"))
print("\n=== 2. bind/监听/失败 关键词 ===")
print(r("grep -iE 'bind|监听|失败|fail|socket|65532' /var/log/dji_rc_bridge.log 2>/dev/null | head -10"))
print("\n=== 3. 当前所有 UDP 端口 ===")
print(r("cat /proc/net/udp 2>/dev/null | head -10"))
print("\n=== 4. 重新看 fd ===")
pid = r("ps w | grep dji_rc_bridge | grep -v grep | awk '{print $1}'")
print("PID:", pid)
print(r("ls -la /proc/" + pid + "/fd/ 2>/dev/null | grep -E 'socket|ttyS0'"))
c.close()
print("\n[done]")
