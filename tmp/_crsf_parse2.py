#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""精确解析桥日志里的 CRSF 帧: 按 [addr][len] + CRC8(poly 0xD5) 校验"""
import re
import sys
from collections import Counter

TYPES = {
    0x00: "GPS", 0x14: "BATTERY", 0x16: "RC_CHANNELS(摇杆)",
    0x0E: "LINK_STATS", 0x28: "DEVICE_PING", 0x29: "DEVICE_INFO",
    0x2A: "SETTINGS_ENTRY", 0x2B: "SETTINGS_ENTRY", 0x2C: "PARAM_READ",
    0x2D: "PARAM_WRITE", 0x3A: "ELRS_STATUS",
}
ADDRS = (0xC8, 0xEE, 0xEA, 0x00, 0xEC)

def crc8(data):
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ 0xD5) & 0xFF if (crc & 0x80) else (crc << 1) & 0xFF
    return crc

def extract_frames(stream, src):
    """在字节流里滑窗找 [addr][len] + crc 校验通过的帧"""
    frames = []
    i = 0
    while i < len(stream) - 3:
        addr, ln = stream[i], stream[i + 1]
        if addr in ADDRS and 2 <= ln <= 58 and i + 1 + ln < len(stream):
            total = 2 + ln
            f = stream[i:i + total]
            if crc8(f[:-1]) == f[-1]:
                frames.append(f)
                i += total
                continue
        i += 1
    return frames

def main(path):
    text = open(path, encoding="latin-1", errors="ignore").read()
    v3s = re.findall(r"\[V3s.*?\]\s*\d+B: ([0-9a-f]+)", text)
    elrs = re.findall(r"\[ELRS.*?\]\s*\d+B: ([0-9a-f]+)", text)
    print(f"段: V3s→ELRS {len(v3s)}, ELRS→V3s {len(elrs)}")

    for label, hexs in [("V3s→ELRS", v3s), ("ELRS→V3s", elrs)]:
        stream = b"".join(bytes.fromhex(h) for h in hexs)
        frames = extract_frames(stream, label)
        cnt = Counter()
        samples = {}
        for f in frames:
            typ = f[2]
            cnt[typ] += 1
            samples.setdefault(typ, f)
        print(f"\n=== {label}: 解析出 {len(frames)} 个有效 CRSF 帧 ===")
        if not frames:
            print("  !! 无有效帧 (crc 不通过/格式不对)")
            # 展示前2段原始
            for h in hexs[:2]:
                b = bytes.fromhex(h)
                print(f"  原始 {len(b)}B: {b.hex()}")
            continue
        for t, n in cnt.most_common():
            f = samples[t]
            print(f"  type=0x{t:02x} {TYPES.get(t,'?')}: {n} 次 | 帧[{len(f)}B]: {f.hex()[:40]}")
        # crc 拒绝率
        total_parsed = sum(1 for _ in [1])
        print(f"  首帧地址: 0x{frames[0][0]:02x} len=0x{frames[0][1]:02x}")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else r"tmp\bridge_out.log")
