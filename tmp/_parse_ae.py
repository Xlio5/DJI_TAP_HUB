# -*- coding: utf-8 -*-
# 40009 0xAE 摇杆帧解析（修正帧头判断：55 1e 04 8a a2 82 <seq> <seq2> 00 06 ae ...）
import socket, time

HOST = "10.169.25.112"

s = socket.create_connection((HOST, 40009), timeout=3)
s.settimeout(0.3)
d = b""
t0 = time.time()
try:
    while time.time() - t0 < 4.0:
        try:
            c = s.recv(65536)
        except socket.timeout:
            continue
        if not c:
            break
        d += c
finally:
    s.close()

print(f"40009 共 {len(d)} bytes / 4s")

# 逐帧: 55 <len> 04 8a a2 82 ... 命令在 offset 10
cnt = 0
i = 0
seen = []
while i < len(d) - 12:
    if d[i] == 0x55 and d[i+1] == 0x1e and d[i+2] == 0x04 and d[i+5] == 0x82 and d[i+10] == 0xae:
        seq = d[i+6]
        # 通道: 参考流程 [00 00 02 00 00] [00 04 x6] -> 6 通道 16bit 从 offset 14 起? 实测从 0x0e(14) 起连续 04 00
        # 更稳妥: 取 offset 14 起 6*2 字节
        ch = [int.from_bytes(d[i+16+j*2:i+18+j*2], "little") for j in range(6)]
        cnt += 1
        if len(seen) < 10 or cnt % 40 == 0:
            seen.append((seq, ch))
        i += 30
        continue
    i += 1

print(f"0xAE 摇杆帧: {cnt} 帧 (~20Hz 突发)")
for seq, ch in seen:
    print(f"  seq={seq:3d}  ch1-6={ch}  -> 中心值 1024, 超出即摇杆在动")
