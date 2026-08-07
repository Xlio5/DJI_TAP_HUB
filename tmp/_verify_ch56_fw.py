"""验证固化固件: dji_rc 86f48284 + CH5/CH6 对调 + PB6 状态"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 1. dji_rc md5 (应 86f48284) ===")
print(r("md5sum /usr/local/bin/dji_rc"))
print("\n=== 2. 运行槽 ===")
print(r("cat /proc/cmdline | grep -o 'root=/dev/mtdblock[0-9]'"))
print("\n=== 3. PB6 状态 + 输出模式 ===")
print(r("devmem 0x01C20834 32"))
print(r("head -3 /var/log/dji_rc.log"))
print("\n=== 4. CH 行 (CH5/CH6 对调生效) ===")
print(r("grep 'CH1=' /var/log/dji_rc.log | tail -3"))
print("\n=== 5. 进程 ===")
print(r("ps w | grep dji_rc | grep -v grep | head -1 || echo 无"))
c.close()
print("\n[done]")
