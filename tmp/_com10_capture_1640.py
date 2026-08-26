"""COM10 监听 v1.6.40 启动日志, 验证 login 提示 + 无 \0 卡死"""
import serial, time, sys

PORT = "COM10"
DUR = 60
LOG = r"c:\my_project\TUN_NAT_HUB\tmp\_com10_boot_1640.txt"

s = serial.Serial(PORT, 115200, timeout=0.2)
t0 = time.time()
buf = b""
while time.time() - t0 < DUR:
    d = s.read(1024)
    if d: buf += d
s.close()
with open(LOG, "wb") as f:
    f.write(buf)
text = buf.decode("utf-8", "replace")
print(f"共收 {len(buf)}B, 已存 {LOG}")

# 关键检查
checks = {
    "login 提示出现": ("login:" in text),
    "Welcome 提示": ("Welcome to" in text),
    "S99 dji_rc 启动": ("dji_rc: started" in text),
    "S99 无双 getty respawn": ("uart0 getty: respawn" not in text),
    "有 \\0 卡死(NUL)": (buf.count(b"\x00") > 0),
}
for k, v in checks.items():
    print(f"  {'✅' if v else '❌'} {k}")

# 最后 30 行
lines = text.rstrip().split("\n")
print("\n=== 最后 25 行 ===")
print("\n".join(lines[-25:]))
