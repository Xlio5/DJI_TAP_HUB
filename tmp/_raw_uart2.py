"""抓 UART2(ttyS2) 原始数据流分析 (前 64 字节 hex)"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=2.0):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 1. UART2 原始数据 (dd 读 200 字节 hex) ===")
print(r("dd if=/dev/ttyS2 bs=1 count=200 2>/dev/null | hexdump -C | head -15"))
print("\n=== 2. UART1 原始数据对比 ===")
print(r("dd if=/dev/ttyS1 bs=1 count=200 2>/dev/null | hexdump -C | head -15"))
print("\n=== 3. 当前 ttyS 波特率配置 ===")
print(r("stty -F /dev/ttyS1 speed 2>/dev/null; stty -F /dev/ttyS2 speed 2>/dev/null"))
print("\n=== 4. UART2 是否有数据持续流入 ===")
s1 = r("wc -c < /var/log/dji_rc.log")
time.sleep(5)
# rx2 计数
print(r("tail -1 /var/log/dji_rc.log | grep -oE 'rx2=[0-9]*'"))
c.close()
print("\n[done]")
