"""确认当前运行槽位 + 目标槽"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 当前运行槽 ===")
print(r("cat /proc/cmdline | grep -o 'root=/dev/mtdblock[0-9]'"))
print("\n=== 当前槽 rootfs magic ===")
print(r("dd if=/dev/mtdblock3 bs=1 count=4 2>/dev/null; echo; dd if=/dev/mtdblock4 bs=1 count=4 2>/dev/null"))
print("\n=== A/B ctl block @0xFC000 ===")
print(r("dd if=/dev/mtdblock0 bs=1 skip=1032192 count=6 2>/dev/null | hexdump -C"))
print("\n=== inactive 槽大小 ===")
print(r("cat /proc/mtd | grep rootfs"))
c.close()
print("\n[done]")
