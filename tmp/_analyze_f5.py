# -*- coding: utf-8 -*-
# 分析 f5 64 记录流 —— 疑似摇杆承载记录 (之前完全漏掉的记录头)
import collections

BASE = r"c:\my_project\TUN_NAT_HUB\tmp\_8902_baseline.raw"
ACT  = r"c:\my_project\TUN_NAT_HUB\tmp\_8902_action.raw"

def split_f5(raw):
    """按 f5 64 <len> 切分变长记录"""
    recs = []
    i = 0
    while i < len(raw) - 3:
        if raw[i] == 0xf5 and raw[i+1] == 0x64:
            L = raw[i+2]
            # f5 64 <len> 00: len 是记录负载长, 总长约 L+? 用下一个 f5 64 或 f6 64 锚定
            if 4 <= L <= 40:
                recs.append((L, bytes(raw[i:i+4+L])))
                i += 4 + L
                continue
        i += 1
    return recs

def int16(v):
    return v - 65536 if v >= 32768 else v

ba = split_f5(open(BASE, "rb").read())
bb = split_f5(open(ACT, "rb").read())
print(f"baseline f5-64 记录 {len(ba)} 条, action {len(bb)} 条")

# 长度分布
print("\n长度分布 baseline vs action:")
ca = collections.Counter(l for l, _ in ba)
cb = collections.Counter(l for l, _ in bb)
for l in sorted(set(ca) | set(cb)):
    print(f"  len={l:2d}: {ca.get(l,0):6d} -> {cb.get(l,0):6d}")

# 每条记录内容抽样（action 前 20 条）
print("\naction 前 20 条 f5-64 记录内容:")
for L, r in bb[:20]:
    print(f"  [{L:2d}B] " + r.hex(" "))

# 按 (len, off) 收集字段，比较静止 vs 动杆
def fields(recs):
    d = collections.defaultdict(list)
    for L, r in recs:
        for off in range(4, len(r) - 1, 2):
            d[(L, off)].append(int16(r[off] | (r[off+1] << 8)))
    return d

fa = fields(ba)
fb = fields(bb)
print("\n==== f5-64 字段: 静止稳定 + 动杆摆动 (摇杆候选) ====")
n = 0
for key in fa:
    if key not in fb:
        continue
    va, vb = fa[key], fb[key]
    if len(va) < 10 or len(vb) < 10:
        continue
    sa, sb = sorted(va), sorted(vb)
    a_span, b_span = sa[-1] - sa[0], sb[-1] - sb[0]
    a_mid = sa[len(sa)//2]
    if a_span <= 150 and b_span >= 400:
        print(f"  len={key[0]:2d} off={key[1]:2d}  静止[{sa[0]:6d}..{sa[-1]:6d}]mid={a_mid:6d}  "
              f"动杆[{sb[0]:6d}..{sb[-1]:6d}]  波动{a_span}->{b_span}")
        n += 1
print(f"  (共 {n} 个)")
