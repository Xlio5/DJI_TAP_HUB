# -*- coding: utf-8 -*-
# 8902 实时观测: 只输出 type=0x56 (86B) 记录, 与上一帧差异红色高亮
# 动杆看红色聚集的字节。Ctrl+C 停止
import socket, time, sys, os

HOST = "10.169.25.112"
PORT = 8902
INTERVAL = 0.05   # 50ms
TYPE = 0x60
LEN = 96          # type=长度

if os.name == "nt":
    os.system("")  # 启用 Windows ANSI 颜色
RED_BG = "\033[41;97m"   # 红底白字 = 与上一帧不同
DIM   = "\033[2m"        # 暗色 = 相同
GRAY  = "\033[90m"       # 浅灰 = 帧头
RESET = "\033[0m"

s = socket.create_connection((HOST, PORT), timeout=5)
s.settimeout(0.05)
buf = bytearray()
prev = None          # 上一帧 0x56 记录 bytes

def find_next_56(buf):
    """找下一条 f6 64 56 00 记录(86B), 返回 (bytes, 消耗长度); 找不到返回 None"""
    i = 0
    while i < len(buf) - 4:
        if buf[i] == 0xf6 and buf[i+1] == 0x64 and buf[i+2] == 0x56 and buf[i+3] == 0x00:
            if i + LEN <= len(buf):
                return bytes(buf[i:i+LEN]), i + LEN
        i += 1
    return None, 0

def render(rec):
    """86字节渲染: 帧头浅灰, 与上一帧不同的字节红底白字, 相同暗色"""
    global prev
    out = []
    for k in range(LEN):
        if k < 4:
            out.append(GRAY + f"{rec[k]:02x}" + RESET)
        elif prev is not None and prev[k] != rec[k]:
            out.append(RED_BG + f"{rec[k]:02x}" + RESET)
        else:
            out.append(DIM + f"{rec[k]:02x}" + RESET)
        if k % 8 == 7:
            out.append(" ")
    prev = rec
    return "".join(out)

print(f"连接 8902 ... (Ctrl+C 停止)")
print(f"只输出 type=0x{TYPE:02x} (len={LEN}B); 红色 = 与上一帧不同; 动杆看红色聚集的字节\n")
t_last = time.time()
try:
    while True:
        try:
            c = s.recv(65536)
        except socket.timeout:
            c = b""
        if c:
            buf += c
        now = time.time()
        if now - t_last >= INTERVAL:
            rec, consumed = find_next_56(buf)
            if rec:
                del buf[:consumed]
                line = render(rec)
                sys.stdout.write("\r" + line + RESET + " ")
                sys.stdout.flush()
                t_last = now
            elif len(buf) > 500000:
                del buf[:250000]
except KeyboardInterrupt:
    print("\n停止")
finally:
    s.close()
