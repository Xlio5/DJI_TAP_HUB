# -*- coding: utf-8 -*-
# 8902 记录分类 + 40009 0xAE 摇杆解析（参考流程-阶段五/六）
import socket, time, collections

HOST = "10.169.25.112"

def grab_tcp(port, secs):
    s = socket.create_connection((HOST, port), timeout=3)
    s.settimeout(0.3)
    data = b""
    t0 = time.time()
    try:
        while time.time() - t0 < secs:
            try:
                c = s.recv(65536)
            except socket.timeout:
                continue
            if not c:
                break
            data += c
    finally:
        s.close()
    return data

# ---------- 8902 记录分类 ----------
print("==== 8902 主流记录分类 (f6 64 头切分) ====")
d = grab_tcp(8902, 3.0)
print(f"8902 共 {len(d)} bytes / 3s")
idx = 0
types = collections.Counter()
seqs = {}
samples = {}
n = 0
while True:
    i = d.find(b"\xf6\x64", idx)
    if i < 0:
        break
    n += 1
    if i + 4 <= len(d):
        t = d[i+2]
        types[t] += 1
        if t not in samples and i + 32 <= len(d):
            samples[t] = d[i:i+32]
    idx = i + 1
print(f"f6-64 记录总数: {n}")
print("记录类型分布 (type: 数量):")
for t, c in types.most_common(12):
    print(f"  type 0x{t:02x} ({t:3d}): {c}")
print("\n各类型前 32 字节样例:")
for t in list(types.keys())[:6]:
    print(f"  0x{t:02x}: {samples.get(t, b'').hex(' ')}")

# ---------- 40009 0xAE 摇杆 ----------
print("\n==== 40009 0xAE 摇杆帧解析 ====")
d9 = grab_tcp(40009, 4.0)
print(f"40009 共 {len(d9)} bytes / 4s")
ae = d9.find(b"\x06\xae")  # 找 00 06 ae 命令
if ae >= 0:
    # 回溯到 55 帧头
    start = d9.rfind(b"\x55", max(0, ae - 16), ae)
    print(f"首帧 0xAE @ 0x{start:x} 命令偏移 {ae-start}")
    # 逐个解析 55 1e 04 8a a2 82 帧
    cnt = 0
    i = 0
    seqs_seen = []
    while i < len(d9) - 8:
        if d9[i] == 0x55 and d9[i+1] == 0x1e and d9[i+4] == 0x82:
            seq = d9[i+6]
            cmd = d9[i+10] if i+10 < len(d9) else 0
            if cmd == 0xae:
                ch = [int.from_bytes(d9[i+14+j*2:i+16+j*2], "little") for j in range(6)]
                cnt += 1
                if len(seqs_seen) < 12 or cnt % 30 == 0:
                    seqs_seen.append((seq, ch))
                i += 30  # 0x1e = 30 字节帧
                continue
        i += 1
    print(f"0xAE 摇杆帧数: {cnt}")
    for seq, ch in seqs_seen[:12]:
        print(f"  seq={seq:3d} 6通道16bit: {ch}")
