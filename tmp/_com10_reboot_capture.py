"""COM10 全程监听 + SSH reboot V3s, 定位 UART0 boot 输出断点"""
import serial, paramiko, threading, time, sys

PORT = "COM10"
DUR = 75
LOG = r"c:\my_project\TUN_NAT_HUB\tmp\_com10_reboot_log.txt"

records = []
def listen():
    try:
        s = serial.Serial(PORT, 115200, timeout=0.2)
    except Exception as e:
        records.append(("OPEN_FAIL", str(e).encode()))
        return
    t0 = time.time()
    while time.time() - t0 < DUR:
        try:
            d = s.read(1024)
        except Exception as e:
            break
        if d:
            records.append((time.time() - t0, d))
    s.close()

th = threading.Thread(target=listen)
th.start()
time.sleep(0.5)

print("SSH 连接并发送 reboot ...")
try:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect("192.168.144.66", 22, "root", "root", timeout=10,
              allow_agent=False, look_for_keys=False, banner_timeout=10)
    c.exec_command("sync; reboot")
    time.sleep(1.5)
    c.close()
    print("reboot 已发出, 开始监听 %d s ..." % DUR)
except Exception as e:
    print("SSH 失败:", e)

th.join()
data = b"".join(d for _, d in records if isinstance(d, bytes))
with open(LOG, "wb") as f:
    f.write(data)
print(f"\n=== COM10 共收 {len(data)}B, 已存 {LOG} ===")

# 断点分析
if not data:
    print("❌ COM10 全程 0 字节 —— 物理链路完全不通 (USB-TTL 未连 V3s UART0 / 接反 / 未共地)")
    sys.exit(0)

# 找启动里程碑时刻
import re
text = data.decode("utf-8", "replace")
marks = [
    ("U-Boot SPL", "SPL 阶段"),
    ("U-Boot 20", "U-Boot proper"),
    ("Starting kernel", "kernel 解压前"),
    ("Booting Linux", "kernel boot"),
    ("Run /linuxrc", "busybox init"),
    ("Welcome to", "getty/login"),
    ("login:", "login 提示"),
]
# 按时间顺序打印每个里程碑前后
last_end = 0
for pat, name in marks:
    idx = text.find(pat, last_end)
    if idx >= 0:
        start = max(0, idx-40)
        ctx = text[start:idx+80].replace("\n", "\\n")
        print(f"[里程碑] {name}: ...{ctx[:150]}...")
        last_end = idx + 80

# 找最后一个非空输出位置
last_line = text.rstrip().split("\n")[-1][-160:]
print(f"\n=== 最后一段输出 ===\n{last_line}")
