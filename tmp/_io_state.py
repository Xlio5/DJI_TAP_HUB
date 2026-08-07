"""抓当前 PB6/UART0 相关 IO 状态 (devmem 直接读寄存器)"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

# pinctrl base 0x01C20800
# PB CFG1 @0x28, PB DATA @0x34, PB PU0 @0x40
print("=== 1. PB6 相关寄存器 ===")
print("CFG1 @0x1C20828:", r("devmem 0x01C20828 32 2>/dev/null || devmem 0x01C20828"))
print("DATA @0x1C20834:", r("devmem 0x01C20834 32 2>/dev/null || devmem 0x01C20834"))
print("PU0  @0x1C20840:", r("devmem 0x01C20840 32 2>/dev/null || devmem 0x01C20840"))

print("\n=== 2. dji_rc 进程 ===")
print(r("ps w | grep dji_rc | grep -v grep || echo 无"))

print("\n=== 3. dji_rc 固化 md5 ===")
print(r("md5sum /usr/local/bin/dji_rc"))

print("\n=== 4. 日志尾 25 行 ===")
print(r("tail -25 /var/log/dji_rc.log 2>/dev/null"))

print("\n=== 5. getty / ttyS0 占用 ===")
print(r("ps w | grep -E 'getty' | grep -v grep || echo 无 getty"))
print(r("fuser /dev/ttyS0 2>&1 || echo ttyS0 无占用"))

print("\n=== 6. UART0 输出 fd (lsof) ===")
print(r("ls -la /proc/$(pgrep dji_rc | head -1)/fd/ 2>/dev/null | grep -E 'ttyS' || echo 无"))
c.close()
print("\n[done]")
