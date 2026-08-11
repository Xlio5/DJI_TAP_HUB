# -*- coding: utf-8 -*-
# 验证紧凑值域候选字段：baseline 静止分布 vs action 动杆分布
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

# 候选字段: (type, off)
CAND = [(0x60, 26), (0x60, 30), (0x60, 32),
        (0x60, 54), (0x60, 56), (0x60, 58),
        (0x50, 24), (0x50, 78),
        (0x54, 28), (0x38, 30), (0x22, 26)]

def getvals(recs, t, off):
    vals = []
    for tt, r in recs:
        if tt == t and off + 1 < len(r):
            vals.append(int16(r[off] | (r[off+1] << 8)))
    return vals

print(f"{'字段':<20} {'静止: n/中位/范围':<32} {'动杆: n/中位/范围':<32}")
print("-" * 90)
for t, off in CAND:
    va = getvals(a, t, off)
    vb = getvals(b, t, off)
    if not va or not vb:
        print(f"0x{t:02x}@{off:2d}  (数据不足)")
        continue
    sa, sb = sorted(va), sorted(vb)
    a_mid, b_mid = sa[len(sa)//2], sb[len(sb)//2]
    print(f"0x{t:02x}@{off:2d}   "
          f"n={len(va):5d} mid={a_mid:6d} [{sa[0]:6d}..{sa[-1]:6d}]   "
          f"n={len(vb):5d} mid={b_mid:6d} [{sb[0]:6d}..{sb[-1]:6d}]")
