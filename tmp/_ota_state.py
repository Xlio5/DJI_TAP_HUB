"""确认当前 OTA 槽位 + 固件版本"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 1. 当前运行槽 ===")
print(r("cat /proc/cmdline | grep -o 'root=/dev/mtdblock[0-9]'"))
print("\n=== 2. dji_rc md5 (v150=fad8b8f2) ===")
print(r("md5sum /usr/local/bin/dji_rc"))
print("\n=== 3. A/B ctl block ===")
print(r("dd if=/dev/mtdblock0 bs=1 skip=1032192 count=6 2>/dev/null | hexdump -C"))
print("\n=== 4. 两个槽 magic ===")
print("A:", r("dd if=/dev/mtdblock3 bs=1 count=4 2>/dev/null | hexdump -C | head -1"))
print("B:", r("dd if=/dev/mtdblock4 bs=1 count=4 2>/dev/null | hexdump -C | head -1"))
print("\n=== 5. dji_rc 运行正常? ===")
print(r("ps w | grep dji_rc | grep -v grep | head -1 || echo 无"))
print(r("grep -c 'out ok' /var/log/dji_rc.log 2>/dev/null || echo 0"))
c.close()
print("\n[done]")
