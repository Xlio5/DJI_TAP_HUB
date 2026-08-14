#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证 ELRS 分块: 读 param 1 (Packet Rate) 全部分块并拼接解析"""
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

    # ping 拿 Device_Info
    dev = None
    for i in range(15):
        s.write(ext(0x28, 0x00, 0xEA, b""))
        time.sleep(0.9)
        d = s.read(512)
        if d:
            buf.extend(d)
            for f in extract(buf):
                if f[2] == 0x29:
                    dev = f[4]
                    print(f"ping{i}: Device_Info dev=0x{dev:02X}")
        if dev: break
    if not dev:
        print("未锁定 ELRS"); s.close(); return

    def send(type_, dst, org, data, wait=0.5, expect_idx=None):
        # 清缓冲, 丢弃残留/Device_Info 重发
        while s.in_waiting:
            s.read(s.in_waiting)
        s.write(ext(type_, dst, org, data))
        end = time.time() + wait
        while time.time() < end:
            d = s.read(256)
            if d:
                buf.extend(d)
                for f in extract(buf):
                    if f[2] == 0x2B:
                        pl = f[3:-1]
                        if expect_idx is None or pl[2] == expect_idx:
                            return f
        return None

    # 完整读一个参数 (分块到 remain=0)
    def read_param(idx):
        full = b""
        chunk = 1
        while chunk < 20:
            f = send(0x2C, dev, 0xEA, bytes([idx, chunk]), 0.6, expect_idx=idx)
            if f is None:
                print(f"  param{idx} chunk{chunk} 无响应, 中断")
                break
            pl = f[3:-1]
            full += pl[4:]
            print(f"  param{idx} chunk{chunk}: remain={pl[3]} +{len(pl[4:])}B (累计{len(full)}B)")
            if pl[3] == 0:
                break
            chunk += 1
        return full

    # 先完整读 param 0 (folder, 初始化 + 清队列)
    print("== 读 param 0 ==")
    p0 = read_param(0)

    # 读 param 1 完整分块
    print("\n== 读 param 1 (Packet Rate) ==")
    full = read_param(1)

    print(f"\n== Packet Rate 完整数据 ({len(full)}B) ==")
    if len(full) >= 2:
        parent, t = full[0], full[1] & 0x7F
        n0 = full.find(b"\0", 2)
        name = full[2:n0].decode("ascii", "replace") if n0 >= 0 else "?"
        opts = full[n0 + 1:].decode("ascii", "replace") if n0 >= 0 else "?"
        print(f"parent={parent:#04x} type={t} name={name!r}")
        print(f"options={opts!r}")
    else:
        print(full.hex())
    s.close()

if __name__ == "__main__":
    main()
