"""诊断: OTA 上传后为何没切到 B 槽"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 1. 当前槽 + cmdline ===")
print(r("cat /proc/cmdline"))
print("\n=== 2. A/B ctl block (应 target=B? 之前传过) ===")
print(r("dd if=/dev/mtdblock0 bs=1 skip=1032192 count=6 2>/dev/null | hexdump -C"))
print("\n=== 3. B 槽 magic (rootfs_crsf 应 hsqs) ===")
print(r("dd if=/dev/mtdblock4 bs=1 count=4 2>/dev/null | hexdump -C | head -1"))
print("\n=== 4. A 槽 dji_rc vs B 槽 dji_rc ===")
print("A md5:", r("dd if=/dev/mtdblock3 bs=1 count=64 skip=4096 2>/dev/null | md5sum"))
print("B md5:", r("dd if=/dev/mtdblock4 bs=1 count=64 skip=4096 2>/dev/null | md5sum"))
print("\n=== 5. SPL 切槽逻辑 (上次烧的 SPL) ===")
print(r("dd if=/dev/mtdblock0 bs=1 skip=1032192 count=6 2>/dev/null | hexdump -C"))
c.close()
print("\n[done]")
