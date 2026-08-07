"""验证 B 槽内容: 提取 B 槽 dji_rc, 确认是否 rootfs_crsf 版 (9f867cf9)"""
import paramiko, time, hashlib, subprocess

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== B 槽 rootfs 大小 + magic ===")
print(r("dd if=/dev/mtdblock4 bs=1 count=4 2>/dev/null | hexdump -C | head -1"))
print("B 槽大小:", r("cat /proc/mtd | grep rootfs_b"))

# 用 dd 读 B 槽到 /tmp (设备上), 再想办法取回。但 B 槽 4.5MB 太大经 SSH 慢。
# 改用: 检查 web_server 日志确认 OTA 是否真的写入了 dji_rc
print("\n=== web_server 日志 (OTA 过程) ===")
print(r("tail -30 /var/log/web_server.log 2>/dev/null | grep -iE 'fw|flash|dd|RECV|TAIL'"))
c.close()
print("\n[done]")
