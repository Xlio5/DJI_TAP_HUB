#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ELRS Lua 参数完整读取: 分块续读(chunks_remain)+解析参数结构
   参考 elrsV3.lua: Settings_Entry data[1..]=[dest][orig][param_index][chunks_rem][data...]"""
import serial
import time

PORT = "COM37"
BAUD = 115200
HANDSET_ID = 0xEA

TYPE_NAMES = {0:"UINT8",1:"INT8",2:"UINT16",3:"INT16",8:"FLOAT",9:"SELECT",
              10:"STRING",11:"FOLDER",12:"INFO",13:"COMMAND"}

def crc8(d):
    c = 0
    for b in d:
        c ^= b
        for _ in range(8):
            c = ((c << 1) ^ 0xD5) & 0xFF if (c & 0x80) else (c << 1) & 0xFF
    return c

def build_ext(type_, dest, orig, data):
    ln = len(data) + 4
    frame = bytearray([0xEE, ln, type_, dest, orig]) + data
    frame.append(crc8(frame[2:2 + ln]))
    return bytes(frame)

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

def cstr(b):
    return b.split(b'\0')[0].decode('ascii', 'replace')

def parse_param(data):
    if len(data) < 2:
        return f"data太短({len(data)}B)"
    parent, t = data[0], data[1] & 0x7F
    # name 从 data[2] 起 NUL 终止
    n0 = data.find(b'\0', 2)
    name = cstr(data[2:n0]) if n0 >= 0 else cstr(data[2:])
    rest = data[n0 + 1:] if n0 >= 0 else b''
    s = f"parent={parent:#04x} type={t}({TYPE_NAMES.get(t,'?')}) name='{name}'"
    if t == 9 and rest:  # SELECT: options
        s += f" opts=[{cstr(rest)}]"
    elif t in (0,1,2,3) and len(rest) >= 3:  # 数值: min/max/def
        w = 2 if t in (2,3) else 1
        if len(rest) >= w*3:
            def toint(b): return int.from_bytes(b, 'little', signed=(t in (1,3)))
            mn, mx, dv = toint(rest[0:w]), toint(rest[w:2*w]), toint(rest[2*w:3*w])
            s += f" min={mn} max={mx} def={dv}"
            if len(rest) > 3*w: s += f" unit='{cstr(rest[3*w:])}'"
    elif t in (12,10) and rest:  # INFO/STRING: value
        s += f" value='{cstr(rest)}'"
    return s

def main(max_param=40):
    s = serial.Serial(PORT, BAUD, timeout=0.1)
    s.dtr = False; s.rts = False
    buf = bytearray()
    ping = build_ext(0x28, 0x00, HANDSET_ID, b"")

    # 等 Device_Info
    dev = None
    end = time.time() + 12
    while time.time() < end:
        s.write(ping); time.sleep(0.9)
        d = s.read(512)
        if d:
            buf.extend(d)
            for f in extract(buf):
                if f[2] == 0x29:
                    pl = f[3:-1]
                    dev = pl[1]
                    print(f"Device_Info: deviceId=0x{dev:02X}")
                    break
        if dev: break
    if not dev:
        print("没收到 Device_Info"); s.close(); return

    def send_get(type_, data, wait=0.4):
        s.write(build_ext(type_, dev, HANDSET_ID, data))
        end2 = time.time() + wait
        while time.time() < end2:
            d = s.read(256)
            if d:
                buf.extend(d)
                for f in extract(buf):
                    if f[2] == 0x2B:
                        return f
        return None

    print("\n== 分块续读全部参数 ==")
    idx = 0
    while idx < max_param:
        # chunk 从 1 开始 (ELRS: chunk0 无效, chunk>=1 按序)
        f = send_get(0x2C, bytes([idx, 1]))
        if f is None:
            # 预热重试
            s.write(ping); time.sleep(0.4)
            d = s.read(256)
            if d:
                buf.extend(d)
                for f in extract(buf):
                    if f[2] == 0x2B: break
        if f is None:
            print(f"param[{idx}] 无响应, 停止")
            break
        pl = f[3:-1]
        pidx = pl[2]
        remain = pl[3]
        data = bytearray(pl[4:])
        chunk = 1
        while remain > 0:
            chunk += 1
            f2 = send_get(0x2C, bytes([pidx, chunk]))
            if f2 is None:
                print(f"  param[{pidx}] chunk{chunk} 无响应, 中断")
                break
            pl2 = f2[3:-1]
            remain = pl2[3]
            data.extend(pl2[4:])
        print(f"param[{pidx}] ({len(data)}B, {chunk}块): {parse_param(bytes(data))}")
        idx += 1
    s.close()
    print(f"\n== 共 {idx} 个参数 ==")

if __name__ == "__main__":
    import sys
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 40)
