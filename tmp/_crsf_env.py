"""确认设备 CRSF 验证环境"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)
except Exception as e:
    print("SSH 失败:", e)
    raise SystemExit(1)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 1. 当前 dji_rc md5 (v150=fad8b8f2) ===")
print(r("md5sum /usr/local/bin/dji_rc"))
print("\n=== 2. 当前输出模式配置 (SPI flash) ===")
print(r("dd if=/dev/mtdblock0 bs=1 skip=$((0xFD000)) count=128 2>/dev/null | strings | head -5 || echo 无"))
print("\n=== 3. 当前槽位 ===")
print(r("cat /proc/cmdline | grep -o 'root=/dev/mtdblock[0-9]'"))
print("\n=== 4. dji_rc 进程 + 模式 ===")
print(r("ps w | grep dji_rc | grep -v grep | head -1"))
print(r("grep '输出' /var/log/dji_rc.log | head -3"))
print("\n=== 5. web_server 在线 ===")
print(r("ps w | grep web_server | grep -v grep | head -1 || echo 无"))
c.close()
print("\n[done]")
