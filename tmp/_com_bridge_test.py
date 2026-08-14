# -*- coding: utf-8 -*-
"""一体测试: 电脑桥 + V3s 持续 ping → 验证完整回传链路
   前台运行, 实时输出转发内容"""
import serial, time, threading, sys, subprocess, paramiko

COM10 = "COM10"; COM30 = "COM30"; BAUD = 115200
s10 = serial.Serial(COM10, BAUD, timeout=0.2)
s10.dtr = False; s10.rts = False
print(f"{COM10} (ELRS) @{BAUD} dtr/rts=False", flush=True)
s30 = serial.Serial(COM30, BAUD, timeout=0.2)
s30.dtr = False; s30.rts = False
print(f"{COM30} (V3s UART0) @{BAUD}", flush=True)

stop = threading.Event()
logs = []
def bridge(src, dst, name, other):
    while not stop.is_set():
        n = src.in_waiting
        if n:
            data = src.read(n)
            line = f"[{name}→{other}] {len(data)}B: {data[:40].hex()}"
            print(line, flush=True)
            logs.append(line)
            dst.write(data)
        else:
            time.sleep(0.005)

t1 = threading.Thread(target=bridge, args=(s10, s30, "ELRS", "V3s"), daemon=True)
t2 = threading.Thread(target=bridge, args=(s30, s10, "V3s", "ELRS"), daemon=True)
t1.start(); t2.start()
print("桥启动, 触发 V3s ping...", flush=True)

# 触发 V3s 持续 ping (后台 ssh)
def ssh_ping():
    try:
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect("192.168.144.66", 22, "root", "root", timeout=10, allow_agent=False, look_for_keys=False)
        _, o, e = c.exec_command("/tmp/udp_ping 10.0.0.1 65532 10", timeout=20)
        out = (o.read()+e.read()).decode(errors="replace")
        print(f"  V3s: {out.strip()}", flush=True)
        c.close()
    except Exception as ex:
        print(f"  V3s ERR: {ex}", flush=True)
t3 = threading.Thread(target=ssh_ping, daemon=True)
t3.start()

# 等待 15s 收集
try:
    time.sleep(15)
finally:
    stop.set()
    s10.close(); s30.close()

print("\n===== 转发记录 =====")
for l in logs: print(l)
print(f"\n总记录 {len(logs)} 条")
