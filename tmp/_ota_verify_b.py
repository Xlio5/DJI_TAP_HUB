"""写后读回: 验证 B 槽 (mtdblock4) 已写入 v149 rootfs"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 1. B 槽 magic (应 hsqs) ===")
print(r("dd if=/dev/mtdblock4 bs=1 count=4 2>/dev/null; echo"))
print("\n=== 2. B 槽大小/尾部 ===")
print(r("dd if=/dev/mtdblock4 bs=1 skip=4599800 count=8 2>/dev/null | hexdump -C"))
print("\n=== 3. A/B ctl block (应 target=B, trial=3) ===")
print(r("dd if=/dev/mtdblock0 bs=1 skip=1032192 count=6 2>/dev/null | hexdump -C"))
print("\n=== 4. B 槽 dji_rc 提取校验 ===")
print(r("dd if=/dev/mtdblock4 of=/tmp/b_root.sq bs=1 count=4599808 2>/dev/null && rm -rf /tmp/b_x && unsquashfs -q -d /tmp/b_x /tmp/b_root.sq 2>&1 | tail -1; md5sum /tmp/b_x/usr/local/bin/dji_rc 2>/dev/null"))
c.close()
print("\n[done]")
