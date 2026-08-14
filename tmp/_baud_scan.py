#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扫描 COM5(V3s) 实际波特率: 试多档, 看哪个能解析出有效 CRSF 摇杆帧"""
import serial
import time
from collections import Counter

BAUDS = [100000, 115200, 230400, 250000, 300000, 333333, 375000, 384000, 400000, 420000, 460800, 500000, 576000, 600000, 921600]
PORT = "COM5"
DURATION = 2.0

def crc8(data):
    c = 0
    for b in data:
        c ^= b
        for _ in range(8):
            c = ((c << 1) ^ 0xD5) & 0xFF if (c & 0x80) else (c << 1) & 0xFF
    return c

def count_frames(stream):
    """找 [0xC8/0xEE][len] + crc 通过的帧, 返回帧数 + type 分布"""
    n = 0
    types = Counter()
    i = 0
    while i < len(stream) - 3:
        a, ln = stream[i], stream[i + 1]
        if a in (0xC8, 0xEE, 0xEA, 0x00) and 2 <= ln <= 58 and i + 1 + ln < len(stream):
            f = stream[i:i + 2 + ln]
            if crc8(f[:-1]) == f[-1]:
                n += 1
                types[f[2]] += 1
                i += 2 + ln
                continue
        i += 1
    return n, types

print(f"扫描 {PORT}, 每档读 {DURATION}s...")
for bd in BAUDS:
    try:
        s = serial.Serial(PORT, bd, timeout=0.1)
        s.dtr = False; s.rts = False
        buf = bytearray()
        end = time.time() + DURATION
        while time.time() < end:
            d = s.read(256)
            if d:
                buf.extend(d)
        s.close()
        n, types = count_frames(bytes(buf))
        total = len(buf)
        marker = " <<<" if n > 5 else ""
        print(f"  {bd:>7}: 收到 {total}B, 有效CRSF帧 {n} 个{marker}"
              + (f"  types={dict(types)}" if n else ""))
    except Exception as e:
        print(f"  {bd:>7}: 打开/设置失败 ({e})")
