"""检查设备 OTA 能力: web_server OTA 端点 + 分区大小 + 当前槽位"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 1. web_server 进程 + 端口 ===")
print(r("ps w | grep web_server | grep -v grep; echo '---'; netstat -tlnp 2>/dev/null | grep -E '80|8080' || echo '查端口'"))
print("\n=== 2. 当前 rootfs 槽位 ===")
print(r("cat /proc/cmdline | grep -o 'mtdblock[0-9]'"))
print("\n=== 3. SPI 分区 (rootfs_a/b 大小) ===")
print(r("cat /proc/mtd"))
print("\n=== 4. rootfs 当前占用 ===")
print(r("df -h / | tail -1"))
print("\n=== 5. 是否能写 inactive 分区 (mtdblock4?) ===")
print(r("ls -la /dev/mtdblock3 /dev/mtdblock4 2>&1"))
print("\n=== 6. /var/log 可写 (tmpfs)? ===")
print(r("mount | grep -E 'var/log|tmpfs' | head -3"))
c.close()
print("\n[done]")
