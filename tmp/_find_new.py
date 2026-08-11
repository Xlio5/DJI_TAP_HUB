# -*- coding: utf-8 -*-
# 8902 离线深挖 v2：找 action 中 baseline 从未出现的新值字段
# 真摇杆: 动作时平滑扫过大量新值（连续）
# 噪声:   偶尔冒几个孤立值
import collections

BASE = r"c:\my_project\TUN_NAT_HUB\tmp\_8902_baseline.raw"
ACT  = r"c:\my_project\TUN_NAT_HUB\tmp\_8902_action.raw"
MAIN_LEN = {0x56:86, 0x60:96, 0x32:50, 0x50:80, 0x22:34, 0x38:56,
            0x00:76, 0x48:72, 0x54:84, 0x34:52}

def split_records(raw):
    recs = []
    i = 0
    while i < len(raw) - 1:
        if raw[i] == 0xf6 and raw[i+1] == 0x64 and i + 2 < len(raw):
            t = raw[i+2]
            L = MAIN_LEN.get(t)
            if L and i + L <= len(raw) and raw[i+L] == 0xf6 and raw[i+L+1] == 0x64:
                recs.append((t, bytes(raw[i:i+L])))
                i += L
                continue
        i += 1
    return recs

def int16(v):
    return v - 65536 if v >= 32768 else v

a = split_records(open(BASE, "rb").read())
b = split_records(open(ACT, "rb").read())

# 收集各 type 各字段的值集合
def collect(recs):
    d = collections.defaultdict(list)   # (type,off) -> [int16 值序列]
    for t, r in recs:
        for off in range(6, len(r) - 1, 2):
            d[(t, off)].append(int16(r[off] | (r[off+1] << 8)))
    return d

fa = collect(a)
fb = collect(b)

# 基线值集合
base_set = {k: set(v) for k, v in fa.items()}

print("==== action 中 baseline 从未出现的新值（连续摇杆字段） ====\n")
for key in fb:
    if key not in base_set:
        continue
    basevals = base_set[key]
    newvals = [v for v in fb[key] if v not in basevals]
    if len(newvals) < 10:     # 新值太少 = 噪声
        continue
    # 新值是否连续（值域覆盖广 = 平滑扫描）
    vmin, vmax = min(newvals), max(newvals)
    nd = len(set(newvals))
    span = vmax - vmin
    # 摇杆特征: 新值多 + 值域广 + 值域内基本连续
    if span >= 200 and nd >= 15:
        print(f"  type=0x{key[0]:02x} off={key[1]:2d}  "
              f"新值 {len(newvals)}个(独特{nd})  范围[{vmin:6d}..{vmax:6d}] 跨度{span:6d}")
