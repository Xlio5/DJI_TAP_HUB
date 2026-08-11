# -*- coding: utf-8 -*-
# 字段分类: 计数器(单调锯齿) vs 摇杆(来回摆动) vs 常量
# 检测: 静止时单调递增比例高 = 计数器; 动杆时摆动且静止稳定 = 摇杆
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

ba = split_records(open(BASE, "rb").read())
bb = split_records(open(ACT, "rb").read())

def series(recs, t, off):
    vals = []
    for tt, r in recs:
        if tt == t and off + 1 < len(r):
            vals.append(int16(r[off] | (r[off+1] << 8)))
    return vals

def mono_ratio(vals):
    """相邻单调递增比例（锯齿计数器=高, 摇杆=低）"""
    if len(vals) < 2:
        return 1.0
    pos = 0
    for i in range(1, len(vals)):
        if vals[i] > vals[i-1]:
            pos += 1
    return pos / (len(vals) - 1)

print("==== 全字段分类 (聚焦 type=0x56 主 type) ====")
t = 0x56
for off in range(6, 86, 2):
    va = series(ba, t, off)
    vb = series(bb, t, off)
    if len(va) < 20 or len(vb) < 20:
        continue
    mono_a = mono_ratio(va)
    mono_b = mono_ratio(vb)
    sa, sb = sorted(va), sorted(vb)
    span_a = sa[-1] - sa[0]
    span_b = sb[-1] - sb[0]
    amid = sa[len(sa)//2]
    # 分类
    if span_a <= 2 and span_b <= 2:
        kind = "常量"
    elif mono_a > 0.85:
        kind = "计数器(锯齿)"
    elif span_a > 2000 and span_b > 2000:
        kind = "大范围动态"
    elif span_b > span_a + 200 and span_a < 300:
        kind = "==> 疑似摇杆"
    else:
        kind = "其他"
    print(f"  off={off:2d}  mono静止={mono_a:.2f} mono动杆={mono_b:.2f}  "
          f"静止[{sa[0]:6d}..{sa[-1]:6d}]mid={amid:6d} 动杆[{sb[0]:6d}..{sb[-1]:6d}]  [{kind}]")
