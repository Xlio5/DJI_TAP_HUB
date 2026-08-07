"""诊断: dji_rc 内部 mmap 读 PB6 vs devmem 一致性 + mmap 失败痕迹"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 1. /dev/mem 权限 ===")
print(r("ls -la /dev/mem"))
print("\n=== 2. dmesg 有无 mmap/fault 相关 ===")
print(r("dmesg 2>/dev/null | grep -iE 'mmap|segfault|fault|dji' | tail -8 || echo 无"))
print("\n=== 3. 当前 dji_rc 完整日志 (含 stderr, 找 mmap/open 失败) ===")
print(r("grep -iE 'mmap|无法打开|失败|PB6' /var/log/dji_rc.log 2>/dev/null | head -10"))
print("\n=== 4. 当前 PB6 DATA (devmem, 应接地=0) ===")
print(r("devmem 0x01C20834 32 2>/dev/null || devmem 0x01C20834"))
print("\n=== 5. dji_rc 进程状态 (是否 D/S) ===")
print(r("cat /proc/110/status 2>/dev/null | grep -E 'State|Threads'"))
print("\n=== 6. dji_rc 启动参数 + 当前时间 ===")
print(r("cat /proc/110/cmdline 2>/dev/null | tr '\\0' ' '; echo; date; uptime"))
c.close()
print("\n[done]")
