#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ELRS Lua 参数读取: ping->Device_Info, 循环 Parameter_Read 收 Settings_Entry
   参考 elrsV3.lua / LuaEngine.buildCrsfFrame: [EE][len][type][dest][orig][payload][crc]"""
import serial
import time

PORT = "COM37"
BAUD = 115200
DEVICE_ID = 0xEE   # ELRS TX 模块 (Device_Info orig)
HANDSET_ID = 0xEA  # 遥控器

def crc8(d):
    c = 0
    for b in d:
        c ^= b
        for _ in range(8):
            c = ((c << 1) ^ 0xD5) & 0xFF if (c & 0x80) else (c << 1) & 0xFF
    return c

def build_ext(type_, dest, orig, data):
    """[EE][len][type][dest][orig][data][crc], crc 从 type 起 len 字节"""
    plen = len(data)
    ln = plen + 4
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

def main(max_param=60):
    s = serial.Serial(PORT, BAUD, timeout=0.1)
    s.dtr = False; s.rts = False
    buf = bytearray()
    ping = build_ext(0x28, 0x00, HANDSET_ID, b"")  # 广播 ping

    # 1. ping 直到 Device_Info
    print("== 等 Device_Info ==", flush=True)
    dev_id = None
    end = time.time() + 12
    while time.time() < end:
        s.write(ping); time.sleep(0.9)
        d = s.read(512)
        if d:
            buf.extend(d)
            for f in extract(buf):
                if f[2] == 0x29:
                    pl = f[3:-1]
                    name = b"".join(c.to_bytes(1, 'big') for c in pl[3:]).split(b'\0')[0]
                    print(f"  Device_Info: deviceId=0x{pl[1]:02X} proto={pl[2]} name={name}")
                    dev_id = pl[1]
                    break
        if dev_id: break
    if not dev_id:
        print("!! 没收到 Device_Info"); s.close(); return
    if dev_id != DEVICE_ID:
        print(f"!! deviceId={dev_id} 非预期 {DEVICE_ID}, 用实际值")

    # 2. 循环 Parameter_Read
    print(f"\n== 读参数 (deviceId=0x{dev_id:02X}) ==", flush=True)
    params = []
    last_activity = time.time()
    idx = 0
    while idx < max_param:
        s.write(build_ext(0x2C, dev_id, HANDSET_ID, bytes([idx, 0])))
        # 等待 Settings_Entry
        got = False
        wait_end = time.time() + 0.5
        while time.time() < wait_end:
            d = s.read(256)
            if d:
                buf.extend(d)
                for f in extract(buf):
                    if f[2] == 0x2B:
                        pl = f[3:-1]
                        # [dest][orig][param_index][chunks_remain][data...]
                        pidx = pl[2]
                        remain = pl[3]
                        data = pl[4:]
                        params.append((pidx, remain, data))
                        print(f"  param[{pidx}] chunks_rem={remain} data({len(data)}B): {data.hex()}", flush=True)
                        got = True
                        last_activity = time.time()
            if got: break
        if not got:
            # 无响应: 可能没更多参数或需要 ping 保持
            s.write(ping); time.sleep(0.3)
            d = s.read(256)
            if d:
                buf.extend(d)
                for f in extract(buf):
                    if f[2] == 0x2B:
                        pl = f[3:-1]
                        params.append((pl[2], pl[3], pl[4:]))
                        print(f"  param[{pl[2]}] (重试) chunks_rem={pl[3]} data: {pl[4:].hex()}", flush=True)
                        got = True
            if not got:
                print(f"  param[{idx}] 无响应, 停止", flush=True)
                break
        idx += 1
    s.close()
    print(f"\n== 共读 {len(params)} 个参数 ==")

if __name__ == "__main__":
    import sys
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 60)
