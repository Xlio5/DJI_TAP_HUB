# -*- coding: utf-8 -*-
"""直连 COM10 发 5x 单次 ping, 看是否响应 (模拟 V3s 的 5 帧行为)
   对照组: 参考程序是持续 ping + wait, 这里发 5 帧即停"""
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
print(f"ping = {ping.hex()}")

ser = serial.Serial(PORT, BAUD, timeout=0.2)
ser.dtr = False
ser.rts = False
time.sleep(0.5)
parser = crsf.FrameParser()
ser.reset_input_buffer()

# 发 5 帧 (间隔 300ms), 与 V3s udp_send 一致
for i in range(5):
    ser.write(ping); ser.flush()
    print(f"[{i}] sent {ping.hex()}")
    time.sleep(0.3)

# 等 3s 收响应
deadline = time.time() + 3
got = []
while time.time() < deadline:
    n = ser.in_waiting
    data = ser.read(n) if n else ser.read(1)
    if data:
        for f in parser.feed(data):
            got.append(repr(f))
            print(f"  <- {f!r}")
    time.sleep(0.02)

print(f"\n总响应帧: {len(got)}")
ser.close()
print("完成")
