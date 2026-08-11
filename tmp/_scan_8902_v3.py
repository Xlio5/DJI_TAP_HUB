# -*- coding: utf-8 -*-
# 8902 摇杆扫描 v3：固定长度切分 + int16 符号 + 跨阶段响应矩阵
import socket, time, collections

HOST = "10.169.25.112"
PORT = 8902
DURATION = 30
SAVE = r"c:\my_project\TUN_NAT_HUB\tmp\_8902_scan.raw"

PHASES = [
    (0,  "全居中"),
    (5,  "左杆上下"),
    (10, "左杆左右"),
    (15, "右杆上下"),
    (20, "右杆左右"),
    (25, "全居中复验"),
]

# 固定主记录长度（来自 v2 长度分布）
MAIN_LEN = {0x56:86, 0x60:96, 0x32:50, 0x50:80, 0x22:34, 0x38:56,
            0x00:76, 0x48:72, 0x54:84, 0x34:52}

print(f"[v3] 连接抓 {DURATION}s ...", flush=True)
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
with open(SAVE, "wb") as f:
    f.write(raw)
print(f"[v3] 存 {len(raw)} bytes -> {SAVE}", flush=True)

# ---- 固定长度切分 ----
recs = []  # (t, bytes)
i = 0
n_skipped = 0
while i < len(raw):
    if i + 2 < len(raw) and raw[i] == 0xf6 and raw[i+1] == 0x64:
        t = raw[i+2]
        L = MAIN_LEN.get(t)
        if L and i + L <= len(raw):
            recs.append((t, bytes(raw[i:i+L])))
            i += L
            continue
    i += 1
print(f"[v3] 切出 {len(recs)} 条主长度记录", flush=True)
if not recs:
    print("[v3] 无记录！", flush=True); raise SystemExit

R = len(recs) / DURATION
def phase_of(ri):
    t = ri / R
    for i in range(len(PHASES) - 1, -1, -1):
        if t >= PHASES[i][0]:
            return i
    return 0

# 每个 (type,off) 按阶段收集 int16 值
seq = collections.defaultdict(lambda: collections.defaultdict(list))
for ri, (t, r) in enumerate(recs):
    ph = phase_of(ri)
    for off in range(6, len(r) - 1, 2):
        v = r[off] | (r[off+1] << 8)
        if v >= 32768:
            v -= 65536  # int16
        seq[(t, off)][ph].append(v)

print("\n==== 跨阶段响应矩阵：只在单一阶段大幅动的字段 ====\n", flush=True)
axis_names = {1:"左杆上下", 2:"左杆左右", 3:"右杆上下", 4:"右杆左右"}
strong = {1: [], 2: [], 3: [], 4: []}
for key, byph in seq.items():
    base = byph.get(0, [])
    if len(base) < 3:
        continue
    br = max(base) - min(base)
    if br > 60:
        continue  # 基线不稳定 → 排除
    # 每阶段响应
    resp = {}
    for k in range(1, 5):
        vals = byph.get(k, [])
        if len(vals) >= 2:
            resp[k] = max(vals) - min(vals)
        else:
            resp[k] = 0
    # 主响应阶段
    if not resp:
        continue
    maink = max(resp, key=resp.get)
    if resp[maink] > 300 and all(resp[k2] < 120 for k2 in resp if k2 != maink):
        bmid = sorted(base)[len(base)//2]
        amax = max(byph.get(maink, []))
        amin = min(byph.get(maink, []))
        strong[maink].append((key[0], key[1], bmid, amin, amax, resp[maink]))

for k in range(1, 5):
    print(f"【{axis_names[k]}】响应字段 {len(strong[k])} 个:", flush=True)
    for t, off, bmid, amin, amax, rng in sorted(strong[k], key=lambda x: -x[5])[:12]:
        print(f"   type=0x{t:02x} off={off:2d} 基线中心={bmid:6d} 动作范围[{amin:6d}..{amax:6d}] 幅度={rng:5d}", flush=True)
    if not strong[k]:
        print("   (无)", flush=True)

print("\n[v3] 完成。", flush=True)
