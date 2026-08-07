"""OTA 上传后验证: B 槽内容 + ctl block"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 1. B 槽 magic (应 hsqs) ===")
print(r("dd if=/dev/mtdblock4 bs=1 count=4 2>/dev/null | hexdump -C | head -1"))
print("\n=== 2. A/B ctl block (应 target=B=0x00, trial=3) ===")
print(r("dd if=/dev/mtdblock0 bs=1 skip=1032192 count=6 2>/dev/null | hexdump -C"))
print("\n=== 3. web_server 日志尾 15 行 (OTA 过程) ===")
print(r("tail -15 /var/log/web_server.log 2>/dev/null"))
print("\n=== 4. 当前仍 A 槽? ===")
print(r("cat /proc/cmdline | grep -o 'root=/dev/mtdblock[0-9]'"))
c.close()
print("\n[done]")
