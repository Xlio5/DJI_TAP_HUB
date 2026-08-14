# -*- coding: utf-8 -*-
"""COM10(ELRS) ↔ COM30(V3s UART0) 双向透明桥 + 监测
   链路: ELRS(COM10) ⇄ 电脑桥 ⇄ COM30 ⇄ V3s UART0 ⇄ V3s bridge(UDP65532) ⇄ 安卓App
   CRSF 波特率 420000"""
import serial, time, threading, sys

COM10 = "COM10"   # ELRS 设备
COM30 = "COM30"   # V3s UART0
BAUD = 115200

s10 = serial.Serial(COM10, BAUD, timeout=0.2)
# 关键: ELRS 模块 (CP210x) 在 DTR/RTS assert 时 MCU 复位不响应, 必须 drop
s10.dtr = False
s10.rts = False
print(f"{COM10} (ELRS) 打开 @{BAUD} dtr/rts=False")
s30 = serial.Serial(COM30, BAUD, timeout=0.2)
s30.dtr = False
s30.rts = False
print(f"{COM30} (V3s UART0) 打开 @{BAUD}")

stop = threading.Event()

def bridge(src, dst, name, other):
    while not stop.is_set():
        n = src.in_waiting
        if n:
            data = src.read(n)
            print(f"[{name}→{other}] {len(data)}B: {data[:40].hex()}", flush=True)
            dst.write(data)
        else:
            time.sleep(0.01)

print("启动双向桥 (Ctrl+C 停止)...")
t1 = threading.Thread(target=bridge, args=(s10, s30, "ELRS", "V3s"), daemon=True)
t2 = threading.Thread(target=bridge, args=(s30, s10, "V3s", "ELRS"), daemon=True)
t1.start(); t2.start()

try:
    while True:
        time.sleep(0.5)
except KeyboardInterrupt:
    print("\n停止")
finally:
    stop.set()
    s10.close(); s30.close()
