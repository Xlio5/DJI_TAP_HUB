"""复盘前确认当前状态"""
import paramiko, time

V3S = "192.168.144.66"

def ssh_r(cmd, wait=2.0):
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(V3S, 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)
    _, out, err = c.exec_command(cmd)
    time.sleep(wait)
    r = (out.read() + err.read()).decode(errors="replace").strip()
    c.close()
    return r

print("=== 1. PB6 DATA (断开=0x40) ===")
print("DATA:", ssh_r("devmem 0x01C20834 2>/dev/null"))

print("\n=== 2. dji_rc 日志 (切换?) ===")
print(ssh_r("grep -E 'PB6 检测|接地|debug|协议|输出 /dev' /var/log/dji_rc.log | tail -8"))

print("\n=== 3. getty + out ===")
print("getty:", ssh_r("ps w | grep getty | grep -v grep || echo '无'"))
print("out:", ssh_r("grep -cE 'out ok' /var/log/dji_rc.log 2>/dev/null || echo 0"))

print("\n=== 4. 当前 dji_rc ===")
print(ssh_r("ps w | grep dji_rc | grep -v grep | head -1"))
c.close()
print("\n[done]")
