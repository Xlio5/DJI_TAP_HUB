# -*- coding: utf-8 -*-
# 8902 离线深挖：动杆 vs 静止，int16 有符号解读，找真摇杆字段
# 数据: tmp/_8902_baseline.raw (静止) vs tmp/_8902_action.raw (动杆)
import collections

BASE = r"c:\my_project\TUN_NAT_HUB\tmp\_8902_baseline.raw"
ACT  = r"c:\my_project\TUN_NAT_HUB\tmp\_8902_action.raw"
MAIN_LEN = {0x56:86, 0x60:96, 0x32:50, 0x50:80, 0x22:34, 0x38:56,
            0x00:76, 0x48:72, 0x54:84, 0x34:52}

def split_records(raw):
    """锚点 + 主长度 + 下一个锚点校验，防漂移"""
    recs = []
    i = 0
    while i < len(raw) - 1:
        if raw[i] == 0xf6 and raw[i+1] == 0x64 and i + 2 < len(raw):
            t = raw[i+2]
            L = MAIN_LEN.get(t)
            if L and i + L <= len(raw):
                # 校验下一条锚点位置：允许记录尾部就是下一条 f6 64
                if raw[i+L] == 0xf6 and raw[i+L+1] == 0x64:
                    recs.append((t, bytes(raw[i:i+L])))
                    i += L
                    continue
        i += 1
    return recs

def int16(v):
    return v - 65536 if v >= 32768 else v

a = split_records(open(BASE, "rb").read())
b = split_records(open(ACT, "rb").read())
print(f"baseline {len(a)} 条, action {len(b)} 条")

# 1) 各 type 记录数对比（动杆时暴涨的 type = 摇杆承载者）
print("\n==== 各 type 记录数: 静止 vs 动杆 ====")
ta = collections.Counter(t for t, _ in a)
tb = collections.Counter(t for t, _ in b)
for t in sorted(set(ta) | set(tb)):
    na, nb = ta.get(t, 0), tb.get(t, 0)
    d = nb - na
    mark = "  <-- 暴涨" if d > 500 and na > 0 else ""
    print(f"  type=0x{t:02x}  {na:7d} -> {nb:7d}  (Δ{d:+7d}){mark}")

# 2) 字段级 int16 对比（聚焦暴涨 type + 全部 type）
def fields(recs, kind):
    """(type,off) -> 值列表（int16），按时间顺序"""
    d = collections.defaultdict(list)
    for t, r in recs:
        for off in range(6, len(r) - 1, 2):
            d[(t, off)].append(int16(r[off] | (r[off+1] << 8)))
    return d

fa = fields(a, "base")
fb = fields(b, "act")

print("\n==== 摇杆候选: 基线稳定(波动<80) 且 动杆大幅变化(>500) ====")
n = 0
for key in fa:
    if key not in fb:
        continue
    va, vb = fa[key], fb[key]
    if len(va) < 5 or len(vb) < 5:
        continue
    ba = sorted(va); bb = sorted(vb)
    amid, bmid = ba[len(ba)//2], bb[len(bb)//2]
    a_spread = ba[-1] - ba[0]
    b_spread = bb[-1] - bb[0]
    # 基线稳定且动作变化
    if a_spread <= 80 and b_spread >= 500:
        # 摇杆应该是有意义的连续值，排除满量程跳变（<10000）
        if abs(bmid - amid) < 10000 or b_spread < 20000:
            print(f"  type=0x{key[0]:02x} off={key[1]:2d}  基线[{ba[0]:6d}..{ba[-1]:6d}]中位{amid:6d}  "
                  f"动作[{bb[0]:6d}..{bb[-1]:6d}]中位{bmid:6d}  波动{a_spread}->{b_spread}")
            n += 1
print(f"  (共 {n} 个)")
