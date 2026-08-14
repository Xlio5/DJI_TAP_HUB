#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""COM5(V3s) ↔ COM37(高频头) 双向透明桥 + 帧监测, 波特率 400000
   链路: V3s(COM5) ⇄ 电脑桥 ⇄ COM37(高频头 ELRS)
   关键: 两侧 drop DTR/RTS (CP210x/CH340 在 DTR/RTS assert 时可能复位 MCU)
   用法: python _com_bridge.py [--a COM5 --b COM37 --baud 400000]"""
import argparse
import serial
import threading
import time

stop = threading.Event()


def bridge(src, dst, name, other):
    while not stop.is_set():
        n = src.in_waiting
        if n:
            data = src.read(n)
            print(f"[{name}→{other}] {len(data)}B: {data[:48].hex()}", flush=True)
            dst.write(data)
        else:
            time.sleep(0.01)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="COM5", help="A 端口 (V3s UART0)")
    ap.add_argument("--b", default="COM37", help="B 端口 (高频头 ELRS)")
    ap.add_argument("--baud", type=int, default=400000, help="波特率")
    args = ap.parse_args()

    sa = serial.Serial(args.a, args.baud, timeout=0.2)
    sa.dtr = False
    sa.rts = False
    print(f"{args.a} (V3s) @{args.baud} dtr/rts=False", flush=True)

    sb = serial.Serial(args.b, args.baud, timeout=0.2)
    sb.dtr = False
    sb.rts = False
    print(f"{args.b} (高频头) @{args.baud} dtr/rts=False", flush=True)

    t1 = threading.Thread(target=bridge, args=(sa, sb, "V3s", "ELRS"), daemon=True)
    t2 = threading.Thread(target=bridge, args=(sb, sa, "ELRS", "V3s"), daemon=True)
    t1.start()
    t2.start()
    print("启动双向桥 (Ctrl+C 停止)...", flush=True)

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n停止", flush=True)
    finally:
        stop.set()
        sa.close()
        sb.close()


if __name__ == "__main__":
    main()
