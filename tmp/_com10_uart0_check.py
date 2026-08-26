"""COM10 验证 V3s UART0 debug: 发回车触发 getty, 观察 login 提示 + 串口不卡死"""
import serial, time, sys

PORT = "COM10"
BAUD = 115200

def drain(s, seconds):
    end = time.time() + seconds
    out = b""
    while time.time() < end:
        n = s.in_waiting
        if n:
            out += s.read(n)
        else:
            time.sleep(0.05)
    return out

print(f"打开 {PORT} @{BAUD} 8N1 ...")
s = serial.Serial(PORT, BAUD, timeout=0.5, write_timeout=1)
time.sleep(0.3)
s.reset_input_buffer()

print("--- 1. 静置读 2s (看现存输出/心跳) ---")
d = drain(s, 2)
print(repr(d[:200]) if d else "(静默)")

print("--- 2. 发回车 x1, 读 2s (应触发 login 提示) ---")
s.write(b"\r\n")
d = drain(s, 2)
print(repr(d[:300]) if d else "(无响应)")

print("--- 3. 再发回车 x1, 读 2s (确认持续响应不卡死) ---")
s.write(b"\r\n")
d = drain(s, 2)
print(repr(d[:300]) if d else "(无响应)")

# 判断
all_out = b""
s.reset_input_buffer()
print("--- 4. 主动发 'root' + 回车看 password 流程 (不送密码, 只确认链路) ---")
s.write(b"root\r\n")
d = drain(s, 3)
print(repr(d[:300]) if d else "(无响应)")
ok = b"login" in d.lower() or b"password" in d.lower() or b"welcome" in d.lower()
print(f"\n结果: {'✅ COM10 UART0 debug 正常 (getty 响应 login 流程)' if ok else '❌ 未观察到 getty 响应'}")
s.close()
