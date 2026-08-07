"""抓 UART2 数据流找 0x55 (DUML 特征) + UART1 对比"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=2.0):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

# 停 dji_rc 读原始流
print("=== 1. 停 dji_rc ===")
print(r("killall dji_rc 2>/dev/null; sleep 1; echo ok"))

# 用 cat 读 ttyS2 原始 (需要 raw mode)
print("\n=== 2. ttyS2 raw 模式读 500 字节 ===")
print(r("stty -F /dev/ttyS2 raw -echo 115200 2>/dev/null; timeout 5 dd if=/dev/ttyS2 bs=1 count=500 2>/dev/null | hexdump -C | head -20"))

print("\n=== 3. ttyS1 raw 模式读 500 字节 (对比) ===")
print(r("stty -F /dev/ttyS1 raw -echo 921600 2>/dev/null; timeout 5 dd if=/dev/ttyS1 bs=1 count=500 2>/dev/null | hexdump -C | head -20"))
c.close()
print("\n[done]")
