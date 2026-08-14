#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ELRS Lua 参数完整读取 (最终版): 顺序读 + 分块续读 + 重试 + 解析
   参考 elrsV3.lua: 必须从 param 0 开始; 无响应时 ping 重试; chunk 流式返回"""
import serial
import time
import sys

PORT = "COM37"
BAUD = 115200

def crc8(d):
    c = 0
    for b in d:
        c ^= b
        for _ in range(8):
            c = ((c << 1) ^ 0xD5) & 0xFF if (c & 0x80) else (c << 1) & 0xFF
    return c

def ext(t, dst, org, data):
    ln = len(data) + 4
    f = bytearray([0xEE, ln, t, dst, org]) + data
    f.append(crc8(f[2:2 + ln]))
    return bytes(f)

def extract(buf):
    out = []
    i = 0
    while i < len(buf) - 3:
        ln = buf[i + 1]
        if 2 <= ln <= 58 and i + 2 + ln <= len(buf):
            f = bytes(buf[i:i + 2 + ln])
            if crc8(f[2:-1]) == f[-1]:
                out.append(f)
                del buf[i:i + 2 + ln]
                continue
        i += 1
    del buf[:i]
    return out

def parse(data):
    if len(data) < 2:
        return f"<太短 {len(data)}B>"
    parent, t = data[0], data[1] & 0x7F
    n0 = data.find(b"\0", 2)
    name = data[2:n0].decode("ascii", "replace") if n0 >= 0 else "?"
    rest = data[n0 + 1:] if n0 >= 0 else b""
    s = f"parent={parent:#04x} type={t} name={name!r}"
    if t == 9 and rest:
        s += f" opts={rest.decode('ascii','replace')!r}"
    elif t in (0, 1, 2, 3) and len(rest) >= 3:
        w = 2 if t in (2, 3) else 1
        if len(rest) >= w * 3:
            toi = lambda b: int.from_bytes(b, "little", signed=(t in (1, 3)))
            s += f" min={toi(rest[0:w])} max={toi(rest[w:2*w])} def={toi(rest[2*w:3*w])}"
    elif t in (10, 12) and rest:
        s += f" value={rest.decode('ascii','replace')!r}"
    return s

def main(max_param=40):
    s = serial.Serial(PORT, BAUD, timeout=0.1)
    s.dtr = False; s.rts = False
    buf = bytearray()
    ping = ext(0x28, 0x00, 0xEA, b"")

    dev = None
    for i in range(15):
        s.write(ping); time.sleep(0.9)
        d = s.read(512)
        if d:
            buf.extend(d)
            for f in extract(buf):
                if f[2] == 0x29:
                    dev = f[4]
                    print(f"Device_Info: dev=0x{dev:02X}")
        if dev: break
    if not dev:
        print("未锁定 ELRS"); s.close(); return

    def get_entry(idx, chunk):
        s.write(ext(0x2C, dev, 0xEA, bytes([idx, chunk])))
        end = time.time() + 0.5
        while time.time() < end:
            d = s.read(256)
            if d:
                buf.extend(d)
                for f in extract(buf):
                    if f[2] == 0x2B and f[3:-1][2] == idx:
                        return f
        # 重试: ping 保持 + 再等
        s.write(ping)
        end2 = time.time() + 0.5
        while time.time() < end2:
            d = s.read(256)
            if d:
                buf.extend(d)
                for f in extract(buf):
                    if f[2] == 0x2B and f[3:-1][2] == idx:
                        return f
        return None

    print("\n== 顺序读全部参数 (含分块) ==")
    idx = 0
    while idx < max_param:
        f = get_entry(idx, 0)
        if f is None:
            print(f"param[{idx}] 无响应, 停止")
            break
        pl = f[3:-1]
        remain = pl[3]
        data = bytearray(pl[4:])
        chunk = 0
        while remain > 0:
            chunk += 1
            f2 = get_entry(idx, chunk)
            if f2 is None:
                print(f"  param[{idx}] chunk{chunk} 无响应, 中断")
                break
            pl2 = f2[3:-1]
            remain = pl2[3]
            data.extend(pl2[4:])
        print(f"param[{idx}] ({len(data)}B, {chunk+1}块): {parse(bytes(data))}")
        idx += 1
    s.close()
    print(f"\n== 共 {idx} 个参数 ==")

if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 40)
