"""验证 v149 启动: 系统正常 + dji_rc 修复版 + SBUS 输出"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)
    print("SSH 连接: OK")
except Exception as e:
    print("SSH 连接失败:", e)
    raise SystemExit(1)

def r(cmd, wait=1.5):
    try:
        _, o, e = c.exec_command(cmd)
        time.sleep(wait)
        return (o.read() + e.read()).decode(errors="replace").strip()
    except Exception as ex:
        return f"<exec 异常: {ex}>"

print("=== 1. dji_rc md5 (应 68a6b7b5) ===")
print(r("md5sum /usr/local/bin/dji_rc"))
print("\n=== 2. dji_rc 进程 ===")
print(r("ps w | grep dji_rc | grep -v grep || echo 无"))
print("\n=== 3. 内核 cmdline (应 console=null, root=mtdblock3) ===")
print(r("cat /proc/cmdline"))
print("\n=== 4. inittab ttyS0 (应禁用) ===")
print(r("grep ttyS0 /etc/inittab"))
print("\n=== 5. 日志尾 15 行 ===")
print(r("tail -15 /var/log/dji_rc.log 2>/dev/null"))
print("\n=== 6. getty / ttyS0 占用 ===")
print(r("ps w | grep getty | grep -v grep || echo 无 getty; fuser /dev/ttyS0 2>&1 || echo ttyS0 无占用"))
print("\n=== 7. PB6 DATA (devmem, 应上拉 0x40) ===")
print(r("devmem 0x01C20834 2>/dev/null || echo devmem不可用"))
c.close()
print("\n[done]")
