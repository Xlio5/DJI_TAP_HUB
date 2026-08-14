#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ELRS Parameter_Write (0x2D) 验证: 写 Switch Mode(param3) 并读回确认
   elrs.lua: crossfireTelemetryPush(0x2D,{deviceId,handsetId,field.id,value})"""
import serial
import time

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

def main():
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
        if dev: break
    if not dev:
        print("未锁定 ELRS"); s.close(); return
    print(f"Device_Info dev=0x{dev:02X}")

    def get_entry(idx, chunk=0):
        s.write(ext(0x2C, dev, 0xEA, bytes([idx, chunk])))
        end = time.time() + 0.5
        while time.time() < end:
            d = s.read(256)
            if d:
                buf.extend(d)
                for f in extract(buf):
                    if f[2] == 0x2B and f[3:-1][2] == idx:
                        return f
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

    def parse_value(data):
        """SELECT 参数: opts 后提取当前值(尾部第?字节)"""
        n0 = data.find(b"\0", 2)
        rest = data[n0 + 1:] if n0 >= 0 else b""
        # opts 分号分隔, 尾部 [min][max][def] 或 [value]
        return rest

    # 读 param 3 当前定义
    f = get_entry(3)
    if f is None:
        print("读 param3 失败"); s.close(); return
    pl = f[3:-1]
    data = bytes(pl[4:])
    n0 = data.find(b"\0", 2)
    name = data[2:n0].decode("ascii", "replace")
    rest = data[n0 + 1:]
    opts_end = rest.find(b"\0")
    opts = rest[:opts_end].decode("ascii", "replace") if opts_end >= 0 else rest.hex()
    tail = rest[opts_end:] if opts_end >= 0 else b""
    print(f"param3: name={name!r} opts={opts!r}")
    print(f"  opts后 tail: {tail.hex()} (当前值区域)")

    # 写 value=0 (Wide), 然后读回
    for value, label in [(0, "0/Wide"), (1, "1/Hybrid")]:
        print(f"\n== 写 param3 value={value} ({label}) ==")
        s.write(ext(0x2D, dev, 0xEA, bytes([3, value])))
        time.sleep(0.4)
        # 读回确认
        f = get_entry(3)
        if f:
            d2 = bytes(f[3:-1][4:])
            n02 = d2.find(b"\0", 2)
            tail2 = d2[n02 + 1:]
            print(f"  写后 Settings_Entry tail: {tail2.hex()}")
        else:
            print("  读回失败")
    s.close()

if __name__ == "__main__":
    main()
