"""OTA 预检: 设备 web_server + 当前槽 + 上传端点格式"""
import socket, paramiko, time

# 1. 确认 web_server 8080 可达
try:
    s = socket.create_connection(("192.168.144.66", 8080), timeout=5)
    s.close()
    print("web_server 8080: 可达 ✓")
except Exception as e:
    print("web_server 8080:", e)

# 2. 当前槽位
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)
def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("\n当前 cmdline root:", r("cat /proc/cmdline | grep -o 'root=/dev/mtdblock[0-9]'"))
print("当前 dji_rc md5:", r("md5sum /usr/local/bin/dji_rc"))
print("\nA/B ctl block @0xFC000:", r("dd if=/dev/mtdblock0 bs=1 skip=1032192 count=6 2>/dev/null | hexdump -C"))
print("B 槽 magic:", r("dd if=/dev/mtdblock4 bs=1 count=4 2>/dev/null | hexdump -C | head -1"))
c.close()
print("\n[done]")
