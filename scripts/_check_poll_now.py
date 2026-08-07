"""当前未接地, 查 pb6-poll 是否误判 grounded=1"""
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

print("=== 1. 物理 PB6 DATA (devmem, 上拉=0x40) ===")
print("DATA 0x34:", ssh_r("devmem 0x01C20834 2>/dev/null"))

print("\n=== 2. dji_rc pb6-poll 最新 (应 grounded=0 若检测正确) ===")
print(ssh_r("grep 'pb6-poll' /var/log/dji_rc.log | tail -8"))

print("\n=== 3. 首次 PB6 检测日志 ===")
print(ssh_r("grep 'PB6 检测' /var/log/dji_rc.log | tail -2"))

print("\n=== 4. 当前 getty (误判 debug 应有) ===")
print(ssh_r("ps w | grep getty | grep -v grep || echo '无 getty'"))
c.close()
print("\n[done]")
