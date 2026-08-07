"""读 UART2(ttyS2) 原始数据流 - 确认硬件信号"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=2.0):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 1. 停 dji_rc (释放 ttyS2) ===")
print(r("killall dji_rc 2>/dev/null; sleep 1; echo ok"))

print("\n=== 2. 读 UART2 原始数据 (ttyS2, 5秒 200字节) ===")
print(r("timeout 5 dd if=/dev/ttyS2 bs=1 count=200 2>/dev/null | hexdump -C | head -12 || echo '无数据/读不到'"))

print("\n=== 3. 再读一次确认 ===")
print(r("timeout 3 dd if=/dev/ttyS2 bs=1 count=100 2>/dev/null | hexdump -C | head -8 || echo '无数据'"))

print("\n=== 4. UART1 对比 (确认遥控器在发) ===")
print(r("timeout 3 dd if=/dev/ttyS1 bs=1 count=100 2>/dev/null | hexdump -C | head -8 || echo '无数据'"))

print("\n=== 5. UART2 波特率/接收状态 (寄存器) ===")
print(r("devmem 0x01C28800 32 2>/dev/null; echo '--- LSR @0x14 ---'; devmem 0x01C28814 32 2>/dev/null"))
c.close()
print("\n[done]")
