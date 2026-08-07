"""读 UART0 寄存器反推实际波特率 (SPL/U-Boot 段乱码根因)"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

# V3s UART0 @ 0x01C28000 (sun8i-v3s)
# RBR/THR/DLL @ +0, IER @+4, IIR/FCR @+8, LCR @+0x0C, MCR@+0x10, LSR@+0x14, MSR@+0x18, SCR@+0x1C, DLL@+0x00, DLH@+0x04
print("=== UART0 寄存器 (0x01C28000) ===")
print("LCR  @+0x0C:", r("devmem 0x01C2800C 32"))
print("DLL  @+0x00:", r("devmem 0x01C28000 32"))
print("DLH  @+0x04:", r("devmem 0x01C28004 32"))
print("\n=== UART0 时钟基址 (APB2 div) ===")
# CCM 0x01C20000: APB2 div @ 0x58
print("CCM APB2 div @0x1C20058:", r("devmem 0x01C20058 32"))
print("\n=== UART0 物理地址确认 (mmap 区) ===")
print(r("cat /proc/iomem | grep -i uart || echo 无"))
c.close()
print("\n[done]")
