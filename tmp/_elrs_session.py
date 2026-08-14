#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ELRS CRSF Lua 会话: 持续 Device_Ping, 收集 ELRS 响应 (Device_Info/Settings_Entry/Status)
   参考 elrsV3.lua 交互: ping -> Device_Info -> Parameter_Read -> Settings_Entry"""
import serial
import time
import sys

PORT = "COM37"
BAUD = 115200

TYPES = {
    0x16: "RC_CHANNELS", 0x0E: "LINK_STATS", 0x28: "DEVICE_PING",
    0x29: "DEVICE_INFO", 0x2A: "SETTINGS_ENTRY", 0x2B: "SETTINGS_ENTRY",
    0x2C: "PARAM_READ", 0x2D: "PARAM_WRITE", 0x3A: "ELRS_STATUS",
}

def crc8(d):
    c = 0
    for b in d:
        c ^= b
        for _ in range(8):
            c = ((c << 1) ^ 0xD5) & 0xFF if (c & 0x80) else (c << 1) & 0xFF
    return c

def extract(buf):
    """从缓冲提取完整 CRSF 帧 (addr+len+crc 校验), 返回帧列表"""
    out = []
    i = 0
    while i < len(buf) - 3:
        ln = buf[i + 1]
        if 2 <= ln <= 58 and i + 2 + ln <= len(buf):
            f = bytes(buf[i:i + 2 + ln])
            if crc8(f[:-1]) == f[-1]:
                out.append(f)
                del buf[i:i + 2 + ln]
                continue
        i += 1
    del buf[:i]
    return out

def main(dur=15):
    s = serial.Serial(PORT, BAUD, timeout=0.05)
    s.dtr = False; s.rts = False
    ping = bytes.fromhex("ee042800ea54")  # 广播 Device_Ping
    print(f"连接 {PORT}@{BAUD}, 持续 ping {dur}s...", flush=True)

    buf = bytearray()
    last_ping = 0
    end = time.time() + dur
    seen = {}
    while time.time() < end:
        if time.time() - last_ping > 0.15:
            s.write(ping)
            last_ping = time.time()
        d = s.read(512)
        if d:
            buf.extend(d)
            for f in extract(buf):
                t = f[2]
                seen.setdefault(t, [0, f])
                seen[t][0] += 1
                if t in (0x29, 0x2A, 0x2B):
                    print(f"[{time.time():.1f}] 0x{t:02X} {TYPES.get(t,'?')} {len(f)}B: {f.hex()}", flush=True)
    s.close()

    print("\n== 响应统计 ==")
    for t, (n, f) in seen.items():
        print(f"  0x{t:02X} {TYPES.get(t,'?')}: {n} 次 | 样例: {f.hex()}")
    if 0x29 in seen:
        print("\n== Device_Info 完整解析 ==")
        f = seen[0x29][1]
        print("  ", f.hex())
        print(f"  addr=0x{f[0]:02X} len={f[1]} type=0x{f[2]:02X} dest=0x{f[3]:02X} orig=0x{f[4]:02X}")
        print(f"  payload(从dest起): {f[3:-1].hex()}")
        # ELRS V2: [dest][orig][proto][name\0][serial_hi][serial_lo][flags][param_count]
        pl = f[3:-1]
        if len(pl) >= 4:
            proto = pl[2]
            rest = pl[3:]
            n0 = rest.find(0)
            name = rest[:n0] if n0 >= 0 else rest[:16]
            after = rest[n0 + 1:] if n0 >= 0 else b""
            try:
                nm = name.decode("ascii")
            except Exception:
                nm = name.hex()
            print(f"  proto={proto} name='{nm}' 剩余: {after.hex()}")

if __name__ == "__main__":
    dur = float(sys.argv[1]) if len(sys.argv) > 1 else 15
    main(dur)
