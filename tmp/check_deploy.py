"""检查 V3s 设备状态, 确定 dji_rc 部署路径"""
import paramiko, time

V3S = "192.168.144.66"

def r(c, cmd):
    _, o, e = c.exec_command(cmd)
    time.sleep(1.5)
    return (o.read() + e.read()).decode(errors="replace").strip()

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    c.connect(V3S, 22, "root", "root", timeout=10, allow_agent=False, look_for_keys=False)
except Exception as e:
    print("SSH连接失败:", e)
    raise SystemExit(1)

print("=== 1. 挂载状态 (是否只读) ===")
print(r(c, "mount | grep -E ' on / | on /usr ' | head -5"))
print("\n=== 2. dji_rc 位置 ===")
print(r(c, "ls -la /usr/local/bin/dji_rc 2>/dev/null; which dji_rc 2>/dev/null"))
print("\n=== 3. 当前 dji_rc 进程 ===")
print(r(c, "ps w | grep dji_rc | grep -v grep || echo 无"))
print("\n=== 4. 日志尾 8 行 ===")
print(r(c, "tail -8 /var/log/dji_rc.log 2>/dev/null || echo 无日志"))
print("\n=== 5. /tmp 可写? ===")
print(r(c, "echo ok > /tmp/.wt && cat /tmp/.wt && unlink /tmp/.wt && echo tmp可写"))
print("\n=== 6. rootfs 分区类型 ===")
print(r(c, "cat /proc/mounts | grep -E ' / ' | head -2"))
c.close()
print("\n[done]")
