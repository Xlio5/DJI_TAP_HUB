# -*- coding: utf-8 -*-
# 1) 列出 action.raw 里所有 f6 64 type（含非主长度）
# 2) 候选字段时间序列波形采样（看摆动/静止）
import collections

ACT  = r"c:\my_project\TUN_NAT_HUB\tmp\_8902_action.raw"
BASE = r"c:\my_project\TUN_NAT_HUB\tmp\_8902_baseline.raw"
MAIN_LEN = {0x56:86, 0x60:96, 0x32:50, 0x50:80, 0x22:34, 0x38:56,
            0x00:76, 0x48:72, 0x54:84, 0x34:52}

raw = open(ACT, "rb").read()
# 所有 f6 64 type 分布
types = collections.Counter()
i = 0
while i < len(raw) - 2:
    if raw[i] == 0xf6 and raw[i+1] == 0x64:
        types[raw[i+2]] += 1
        i += 2
    else:
        i += 1
print("action.raw 所有 f6 64 type 分布:")
for t, c in types.most_common(25):
    mark = "  (主长度覆盖)" if t in MAIN_LEN else "  <-- 未覆盖!"
    print(f"  type=0x{t:02x}: {c}{mark}")

# 候选字段时间序列
def int16(v):
    return v - 65536 if v >= 32768 else v

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

ba = split_records(open(BASE, "rb").read())
bb = split_records(open(ACT, "rb").read())

print("\n候选字段时间序列采样 (每 500 条取 1, 显示摆动):")
for t, off in [(0x60,26), (0x60,30), (0x60,32), (0x60,54), (0x50,24), (0x38,30)]:
    def seq(recs):
        vals = []
        for tt, r in recs:
            if tt == t and off + 1 < len(r):
                vals.append(int16(r[off] | (r[off+1] << 8)))
        return vals
    va, vb = seq(ba), seq(bb)
    print(f"\n0x{t:02x}@{off}  静止波形(采样10点): {va[::max(1,len(va)//10)][:10]}")
    print(f"0x{t:02x}@{off}  动杆波形(采样20点): {vb[::max(1,len(vb)//20)][:20]}")
