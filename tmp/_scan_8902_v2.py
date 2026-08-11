# -*- coding: utf-8 -*-
# 8902 摇杆扫描 v2：严格基线排除持续变化字段，锁定跟手摇杆字段
import socket, time, collections

HOST = "10.169.25.112"
PORT = 8902
DURATION = 30

PHASES = [
    (0,  "全居中"),
    (5,  "左杆上下"),
    (10, "左杆左右"),
    (15, "右杆上下"),
    (20, "右杆左右"),
    (25, "全居中复验"),
]

print(f"[scan] 连接 {HOST}:{PORT} 抓 {DURATION}s ...", flush=True)
s = socket.create_connection((HOST, PORT), timeout=5)
s.settimeout(0.5)
raw = bytearray()
t0 = time.time()
try:
    while time.time() - t0 < DURATION:
        try:
            c = s.recv(65536)
        except socket.timeout:
            c = b""
        if c:
            raw += c
finally:
    s.close()
print(f"[scan] {len(raw)} bytes / {DURATION}s", flush=True)

# 切记录
marks = []
i = 0
while True:
    i = raw.find(b"\xf6\x64", i)
    if i < 0:
        break
    marks.append(i)
    i += 2
print(f"[scan] {len(marks)} 条记录", flush=True)

recs = []
for k in range(len(marks)):
    st = marks[k]
    en = marks[k+1] if k+1 < len(marks) else len(raw)
    r = bytes(raw[st:en])
    if len(r) >= 6 and r[2] != 0xFF:
        recs.append((r[2], r))
R = len(recs) / DURATION

def phase_of(ri):
    t = ri / R
    for i in range(len(PHASES) - 1, -1, -1):
        if t >= PHASES[i][0]:
            return i
    return 0

u16seq = collections.defaultdict(list)  # (type,off) -> [(ri,ph,v)]
for ri, (t, r) in enumerate(recs):
    ph = phase_of(ri)
    for off in range(6, min(len(r), 48), 2):
        if off + 1 < len(r):
            v = r[off] | (r[off+1] << 8)
            u16seq[(t, off)].append((ri, ph, v))

# 基线幅度排除
base_range = {}
for key, seq in u16seq.items():
    bvals = [v for _, ph, v in seq if ph == 0]
    if len(bvals) >= 3:
        base_range[key] = max(bvals) - min(bvals)
    else:
        base_range[key] = -1

print("\n==== 16bit 摇杆候选（基线稳定 + 动作期显著偏离） ====", flush=True)
found_any = False
for k in range(1, len(PHASES) - 1):
    ph_start = PHASES[k][0]
    ph_name = PHASES[k][1]
    hits = []
    for key, br in base_range.items():
        if br < 0 or br > 100:
            continue  # 基线不稳定或样本不足 → 排除
        aseq = [v for _, ph, v in u16seq[key] if ph == k]
        if len(aseq) < 3:
            continue
        ar = max(aseq) - min(aseq)
        if ar > br + 300:  # 动作期变化显著大于基线
            bvals = [v for _, ph, v in u16seq[key] if ph == 0]
            bmid = sorted(bvals)[len(bvals)//2]
            avs = sorted(set(aseq))
            hits.append((key[0], key[1], bmid, min(avs), max(avs), len(avs)))
    if hits:
        found_any = True
        print(f"\n阶段{k} [{ph_start}s, {ph_name}] —— 摇杆候选 {len(hits)} 个:", flush=True)
        for t, off, bmid, amin, amax, nd in hits:
            print(f"  type=0x{t:02x} off={off:2d} 中心={bmid} 动作范围[{amin}..{amax}] ({nd}值)", flush=True)
if not found_any:
    print("  (无满足条件的字段)", flush=True)

# 打印各高频 type 典型长度，辅助确认记录结构
print("\n==== 高频 type 记录长度分布 ====", flush=True)
lens = collections.defaultdict(list)
for t, r in recs:
    lens[t].append(len(r))
for t, ls in sorted(lens.items(), key=lambda x: -len(x[1]))[:10]:
    from collections import Counter
    c = Counter(ls)
    common = c.most_common(3)
    print(f"  type=0x{t:02x} 记录数={len(ls)} 典型长度: " + ", ".join(f"{l}B×{n}" for l, n in common), flush=True)

print("\n[scan] 完成。", flush=True)
