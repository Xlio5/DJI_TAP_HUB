# -*- coding: utf-8 -*-
"""验证: ELRS 波特率轮换 ~7s, 需持续 ping + 等待响应
   参考 elrs_serial.py find_baud: 每 0.25s ping, 等 DEVICE_INFO"""
import sys, time
sys.path.insert(0, r"c:\my_project\elrs_lua_python")
import serial
import crsf

PORT = "COM10"
BAUD = 115200

ping = crsf.build_extended_frame(crsf.FRAMETYPE_DEVICE_PING,
                                 crsf.ADDR_BROADCAST,
                                 crsf.ADDR_RADIO_TRANSMITTER,
                                 [], addr=crsf.ADDR_CRSF_TRANSMITTER)
print(f"ping = {ping.hex()}   (持续 ping, 每 0.2s, 共 12s)")

ser = serial.Serial(PORT, BAUD, timeout=0.2)
ser.dtr = False
ser.rts = False
time.sleep(0.5)  # 模块复位重启
parser = crsf.FrameParser()
ser.reset_input_buffer()

start = time.time()
got_info = False
while time.time() - start < 12:
    ser.write(ping); ser.flush()
    # 读并解析
    deadline = time.time() + 0.2
    while time.time() < deadline:
        n = ser.in_waiting
        data = ser.read(n) if n else ser.read(1)
        if data:
            for f in parser.feed(data):
                elapsed = time.time() - start
                print(f"  [{elapsed:.1f}s] <- {f!r}")
                if f.frame_type == crsf.FRAMETYPE_DEVICE_INFO:
                    got_info = True
        time.sleep(0.01)
    if got_info:
        # 已收到, 再等 2s 看是否还有 (完整会话)
        extra = time.time() + 2
        while time.time() < extra:
            n = ser.in_waiting
            data = ser.read(n) if n else ser.read(1)
            if data:
                for f in parser.feed(data):
                    print(f"  [+]{f!r}")
            time.sleep(0.01)
        break

print(f"\nDEVICE_INFO 收到: {got_info}")
ser.close()
print("完成")
