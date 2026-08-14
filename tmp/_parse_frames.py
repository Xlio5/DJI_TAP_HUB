#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解析桥日志里的 CRSF 帧, 确认帧类型/对齐"""
import re
import sys

CRSF_TYPES = {
    0x16: "RC_CHANNELS_PACKED(摇杆)",
    0x28: "DEVICE_PING",
    0x29: "DEVICE_INFO",
    0x2A: "PARAMETER_SETTINGS_ENTRY",
    0x2B: "PARAMETER_SETTINGS_ENTRY",
    0x2C: "PARAMETER_READ",
    0x2D: "PARAMETER_WRITE",
    0x3A: "ELRS_STATUS",
    0x0E: "LINK_STATISTICS",
}

def main(path):
    text = open(path, encoding="latin-1", errors="ignore").read()
    # 提取 V3s->ELRS 的帧 hex (箭头在文件里是 GBK 乱码, 用宽松前缀匹配)
    v3s = re.findall(r"\[V3s.*?\]\s*\d+B: ([0-9a-f]+)", text)
    elrs = re.findall(r"\[ELRS.*?\]\s*\d+B: ([0-9a-f]+)", text)
    print(f"V3s->ELRS 段: {len(v3s)} 条, ELRS->V3s 段: {len(elrs)} 条")
    if not v3s:
        print("无 V3s->ELRS 数据"); return

    # 分析每条段的字节, 尝试 CRSF 对齐
    def scan(hexs, label, n):
        print(f"\n=== {label} 前 {n} 条 ===")
        for h in hexs[:n]:
            b = bytes.fromhex(h)
            # 尝试多种起始偏移找 [addr][len] 且 len 合理 (1..58)
            found = []
            for off in range(min(3, len(b))):
                if len(b) < off + 2: break
                a = b[off]
                ln = b[off + 1]
                if a in (0xC8, 0xEE, 0xEA, 0x00, 0x88, 0xEC) and 2 <= ln <= 58:
                    total = 2 + ln
                    typ = b[off + 2] if off + 2 < len(b) else -1
                    found.append(f"off={off} addr=0x{a:02x} len={ln}(0x{ln:02x}) type=0x{typ:02x}({CRSF_TYPES.get(typ,'?')}) total={total} 实际={len(b)}B")
            print(f"  {h[:32]}... ({len(b)}B): {found if found else '无法对齐'}")

    scan(v3s, "V3s→ELRS", 3)
    scan(elrs, "ELRS→V3s", 3)

    # 统计 type 分布 (尝试从字节流里找 addr 帧)
    print("\n=== V3s→ELRS type 分布 (滑动找 0xC8/0xEE 起始) ===")
    from collections import Counter
    cnt = Counter()
    for h in v3s:
        b = bytes.fromhex(h)
        for i in range(len(b) - 3):
            if b[i] in (0xC8, 0xEE, 0xEA, 0x00, 0x88) and 2 <= b[i+1] <= 58 and i+2 < len(b):
                cnt[b[i+2]] += 1
    for t, c in cnt.most_common(6):
        print(f"  type=0x{t:02x} {CRSF_TYPES.get(t,'?')}: {c} 次")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else
         r"C:\Users\xlong\AppData\Local\Temp\claude\c--work-tun--nat--hub\1b656529-1022-45b4-8bea-8a7b1ab1f9c8\tasks\bkw6ejua5.output")
