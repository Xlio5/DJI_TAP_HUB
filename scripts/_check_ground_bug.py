"""检查接地后为何还有 SBUS 输出"""
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

print("=== 1. PB6 DATA (接地=0) ===")
print(ssh_r("devmem 0x01C20834 2>/dev/null"))

print("\n=== 2. dji_rc 切换日志 ===")
print(ssh_r("grep 'PB6 变化' /var/log/dji_rc.log | tail -4"))

print("\n=== 3. 当前模式 (debug 应无 out) ===")
print(ssh_r("grep -E 'PB6 检测|输出 /dev|debug 模式|协议模式' /var/log/dji_rc.log | tail -5"))

print("\n=== 4. out ok 还在发? ===")
print(ssh_r("grep 'out ok' /var/log/dji_rc.log | tail -3"))

print("\n=== 5. getty ===")
print(ssh_r("ps w | grep getty | grep -v grep || echo '无 getty'"))

print("\n=== 6. dji_rc PID + fd ===")
print(ssh_r("pidof dji_rc; ls -la /proc/$(pidof dji_rc)/fd 2>/dev/null | grep ttyS"))
c.close()
print("\n[done]")
