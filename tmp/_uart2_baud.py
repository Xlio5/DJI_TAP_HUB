"""反推 UART2 实际波特率 (读 divisor + APB2 时钟)"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

# UART2 @0x1C28800. 要读 DLL/DLH 需先设 LCR.DLAB=1 (LCR bit7)
# LCR @0x0C. 设 DLAB, 读 DLL@0x00 DLH@0x04, 恢复
print("=== 1. 设 DLAB 读 UART2 divisor ===")
print(r("devmem 0x01C2880C 32"))   # 当前 LCR
print(r("devmem 0x01C2880C 32 0x83; echo 'LCR=0x83 (DLAB)'; devmem 0x01C28800 32; devmem 0x01C28804 32; devmem 0x01C2880C 32 0x13"))

print("\n=== 2. 设 DLAB 读 UART1 divisor (对比) ===")
print(r("devmem 0x01C2840C 32 0x83; devmem 0x01C28400 32; devmem 0x01C28404 32; devmem 0x01C2840C 32 0x13"))

print("\n=== 3. APB2 时钟 (UART 时钟源) ===")
# V3s APB2 div @ CCM 0x1C20058
print("APB2 div:", r("devmem 0x01C20058 32"))
c.close()
print("\n[done]")
