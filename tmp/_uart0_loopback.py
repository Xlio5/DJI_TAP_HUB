"""测试 V3s UART0 是否正常 (发数据后读回, 需 TX-RX 短接或看寄存器)"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 1. UART0 寄存器状态 ===")
# UART0 @0x1C28000, LSR @+0x14
print("LSR:", r("devmem 0x01C28014 32"))
print("LCR:", r("devmem 0x01C2800C 32"))

print("\n=== 2. 当前 bridge 是否还占用 UART0 ===")
print(r("fuser /dev/ttyS0 2>&1 || echo 无占用"))

print("\n=== 3. 停 bridge, 用 echo 测 UART0 ===")
r("killall dji_rc_bridge 2>/dev/null; sleep 2")
print("已停 bridge")
# 用 python 测 UART0: 发 0x55, 看 LSR DR 是否置位 (TX 正常)
print(r("devmem 0x01C28000 32 0x55; sleep 1; echo '--- 写后 LSR ---'; devmem 0x01C28014 32"))

print("\n=== 4. UART0 读测试 (看 RX 有无数据) ===")
print("读 RBR:", r("devmem 0x01C28000 32"))
print("读后 LSR:", r("devmem 0x01C28014 32"))
c.close()
print("\n[done]")
