"""COM10 监听 + SSH 往 V3s UART0 TX 发数据, 判断 COM10 是否物理连着 UART0"""
import serial, paramiko, threading, time

result = {}
def listen(port, key):
    s = serial.Serial(port, 115200, timeout=0.2, write_timeout=1)
    buf = b""
    end = time.time() + 8
    while time.time() < end:
        d = s.read(1024)
        if d: buf += d
    result[key] = buf
    s.close()
    print(f"[{key}] COM{port} 监听结束, 共收 {len(buf)}B")

# 1. 后台开 COM10 监听
th = threading.Thread(target=listen, args=("COM10", "com10"))
th.start()
time.sleep(0.5)

# 2. SSH 往 ttyS0 发独特测试串 (5 次)
print("SSH 往 /dev/ttyS0 发送测试数据...")
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=10,
          allow_agent=False, look_for_keys=False, banner_timeout=10)
for i in range(5):
    c.exec_command(f"echo 'UART0-TX-PROBE-{i}-ABCDEFGHIJKLMNOPQRST' > /dev/ttyS0 2>&1")
    time.sleep(0.4)
c.close()
print("SSH 发送完成")

th.join(timeout=10)
got = result.get("com10", b"")
print("\n=== COM10 收到内容 ===")
print(repr(got[:300]) if got else "(完全静默)")
if got:
    print("✅ COM10 物理链路通! V3s UART0 TX -> COM10 RX 正常")
else:
    print("❌ COM10 物理链路不通 (V3s 已发出数据但 COM10 收不到)")
