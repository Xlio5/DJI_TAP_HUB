"""读 UART2 RBR (接收数据) - 看 FIFO 里是什么"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

# UART2 RBR/DLL @ 0x1C28800 (读就是 RBR)
print("=== 1. UART2 RBR 连续读 20 次 (每次读完 LSR 看 DR) ===")
# 注意: devmem 每次读 0x1C28800 会清 DR 位
data = []
for i in range(20):
    v = r("devmem 0x01C28800 32")
    data.append(v.strip())
print("RBR 值:", " ".join(data))

print("\n=== 2. 读完后再看 LSR ===")
print("LSR:", r("devmem 0x01C28814 32"))

print("\n=== 3. UART2 LCR (帧格式) ===")
print("LCR:", r("devmem 0x01C2880C 32"))

print("\n=== 4. 波特率 divisor (DLL/DLH) ===")
print("DLL @0x28800(读RBR会冲突, 用FCR先) 改读 IER/IIR")
print("IIR @0x28808:", r("devmem 0x01C28808 32"))
c.close()
print("\n[done]")
