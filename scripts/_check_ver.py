"""检查 dji_rc 版本 + DATA 读取"""
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

print("=== 1. dji_rc md5 (应 1a249a11) ===")
print(ssh_r("md5sum /usr/local/bin/dji_rc"))

print("\n=== 2. 当前运行 dji_rc PID + 启动时间 ===")
print(ssh_r("pidof dji_rc; ls -la /proc/$(pidof dji_rc)/exe 2>/dev/null"))

print("\n=== 3. devmem 读 DATA (正确地址 0x34) vs 其他地址 ===")
print("DATA 0x34:", ssh_r("devmem 0x01C20834 2>/dev/null"))
print("DATA 0x14:", ssh_r("devmem 0x01C20814 2>/dev/null"))  # 若 dji_rc 用错地址

print("\n=== 4. dji_rc 检测日志 (DATA 值) ===")
print(ssh_r("grep 'PB6 检测' /var/log/dji_rc.log | tail -3"))
c.close()
print("\n[done]")
