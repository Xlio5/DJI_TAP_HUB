# -*- coding: utf-8 -*-
# 参考 8902 数据抓取流程-阶段四：直接连 TCP 端口抓数据
import socket, time

HOST = "10.169.25.112"   # 当前 adb 设备 (rc701)
TCP_PORTS = [8901, 8902, 40007, 40008, 40009]
UDP_PORTS = [6698]
CAP = 4.0                 # 每个端口抓 4 秒

def probe_tcp(host, port):
    try:
        s = socket.create_connection((host, port), timeout=3)
    except Exception as e:
        print(f"[TCP {port}]  CONNECT FAIL: {e}")
        return
    s.settimeout(0.3)
    data = b""
    t0 = time.time()
    n_chunks = 0
    try:
        while time.time() - t0 < CAP:
            try:
                chunk = s.recv(65536)
            except socket.timeout:
                continue
            if not chunk:
                break
            data += chunk
            n_chunks += 1
    except Exception as e:
        print(f"[TCP {port}]  recv err: {e}")
    s.close()
    dt = time.time() - t0
    print(f"[TCP {port}]  {len(data)} bytes in {dt:.1f}s  ({n_chunks} recv, {len(data)/max(dt,0.001):.0f} B/s)")
    print("   head64: " + data[:64].hex(" ") + "  ascii: " + repr(data[:40]))
    # 记录类型统计：按 f6 64 头切分（参考流程-阶段六 用 f6 64 记录头）
    if b"\xf6\x64" in data[:2000]:
        print("   f6-64 记录头出现 -> 8902 风格高频流")
    print()

def probe_udp(host, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(2.0)
    try:
        s.sendto(b"\x00" * 8, (host, port))
        data, _ = s.recvfrom(65536)
        print(f"[UDP {port}]  response {len(data)} bytes: " + data[:64].hex(" "))
    except socket.timeout:
        print(f"[UDP {port}]  sent 8B, no response")
    except Exception as e:
        print(f"[UDP {port}]  err: {e}")
    s.close()

for p in TCP_PORTS:
    probe_tcp(HOST, p)
for p in UDP_PORTS:
    probe_udp(HOST, p)
