"""诊断: 当前 dji_rc 版本 + PB6 接地为何没触发切换"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=2.0):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 1. 固化 dji_rc md5 (对照: 修复版=54e2a723, 旧mmap=1a249a11) ===")
print(r("md5sum /usr/local/bin/dji_rc; ls -la /usr/local/bin/dji_rc"))
print("\n=== 2. 当前运行 dji_rc 进程 ===")
print(r("ps w | grep dji_rc | grep -v grep || echo 无"))
print("\n=== 3. dji_rc 日志尾 15 行 ===")
print(r("tail -15 /var/log/dji_rc.log 2>/dev/null"))
print("\n=== 4. devmem 手动读 PB6 DATA (0x01C20834) ===")
print(r("devmem 0x01C20834 2>/dev/null || echo 'devmem 不可用'"))
print("\n=== 5. 内核启动 console (dmesg 头) ===")
print(r("dmesg 2>/dev/null | head -3; echo '---'; cat /proc/cmdline"))
print("\n=== 6. getty 状态 ===")
print(r("ps w | grep getty | grep -v grep || echo 无 getty"))
c.close()
print("\n[done]")
