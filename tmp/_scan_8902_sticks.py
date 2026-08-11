# -*- coding: utf-8 -*-
# 8902 摇杆字段扫描：分段对比字节差分，找出摇杆轴/旋钮/按键偏移
# 配合方式：老大按 PHASES 口令表掐表做动作，45 秒后自动出映射表
import socket, time, collections

HOST = "10.169.25.112"
PORT = 8902
DURATION = 45  # 秒

PHASES = [
    (0,  "全居中不动"),
    (5,  "左摇杆 上下"),
    (10, "左摇杆 左右"),
    (15, "右摇杆 上下"),
    (20, "右摇杆 左右"),
    (25, "依次拨旋钮"),
    (32, "依次按按键"),
    (39, "全居中复验"),
]

print(f"[scan] 连接 {HOST}:{PORT}，抓 {DURATION}s ...", flush=True)
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
print(f"[scan] 抓到 {len(raw)} bytes / {DURATION}s", flush=True)

# ---- 切分记录：f6 64 锚点 ----
marks = []
i = 0
while True:
    i = raw.find(b"\xf6\x64", i)
    if i < 0:
        break
    marks.append(i)
    i += 2
print(f"[scan] f6-64 记录 {len(marks)} 条 (~{len(marks)/DURATION:.0f}/s)", flush=True)

# ---- 收集 (type, off) 字段值序列（u16 LE + 单字节） ----
recs = []          # (type, record_bytes)
for k in range(len(marks)):
    st = marks[k]
    en = marks[k+1] if k+1 < len(marks) else len(raw)
    r = bytes(raw[st:en])
    if len(r) >= 6 and r[2] != 0xFF:
        recs.append((r[2], r))

# 每秒记录数，用于时间对齐
R = len(recs) / DURATION

def phase_of(rec_idx):
    t = rec_idx / R
    for i in range(len(PHASES) - 1, -1, -1):
        if t >= PHASES[i][0]:
            return i
    return 0

# u16 字段: (type, off) -> list[(rec_idx, value)]
u16seq = collections.defaultdict(list)
# 单字节字段
byseq = collections.defaultdict(list)
for ri, (t, r) in enumerate(recs):
    ph = phase_of(ri)
    for off in range(6, min(len(r), 48), 2):
        if off + 1 < len(r):
            v = r[off] | (r[off+1] << 8)
            u16seq[(t, off)].append((ri, ph, v))
    for off in range(6, min(len(r), 48)):
        byseq[(t, off)].append((ri, ph, r[off]))

# ---- 分析：每阶段 vs 基线(阶段0) ----
def analyze(seqmap, name, dev_thresh, newval_min_count):
    print(f"\n==== {name} 差分结果 ====", flush=True)
    # 基线字段值集
    baseline = {}
    for (t, off), seq in seqmap.items():
        bset = set(v for _, ph, v in seq if ph == 0)
        if len(bset) <= 4:   # 基线稳定字段才关注
            baseline[(t, off)] = bset
    if not baseline:
        print("  (无稳定基线字段)", flush=True)
        return
    for k in range(1, len(PHASES) - 1):
        ph_start = PHASES[k][0]
        ph_name = PHASES[k][1]
        hits = []
        for (t, off), bset in baseline.items():
            aseq = [(v) for _, ph, v in u16seq.get((t, off), []) if ph == k]
            if not aseq:
                continue
            amax = max(aseq)
            amin = min(aseq)
            b = next(iter(bset)) if bset else 0
            # 摇杆：动作期出现明显偏离基线的值
            far = [v for v in aseq if v > b + dev_thresh or v < b - dev_thresh]
            if far and (amax - amin) > dev_thresh:
                hits.append((t, off, amin, amax, b, len(far)))
        if hits:
            hits.sort(key=lambda h: -(h[5]))
            print(f"\n  阶段{k} [{ph_start}s 起, {ph_name}] 活跃字段 {len(hits)} 个:", flush=True)
            for t, off, amin, amax, b, nfar in hits[:8]:
                print(f"    type=0x{t:02x} off={off:2d}  基线={b}  范围[{amin}..{amax}]  偏离{nfar}点", flush=True)
        else:
            print(f"\n  阶段{k} [{ph_start}s 起, {ph_name}] 无活跃字段", flush=True)

analyze(u16seq, "16bit字段", 60, 3)
analyze(byseq, "单字节字段", 0, 3)

print("\n[scan] 完成。", flush=True)
