# -*- coding: utf-8 -*-
# 8902 完整协议解析: 验证 len=type 假说 + 真实帧表 + 逐字段行为分类
import collections

BASE = r"c:\my_project\TUN_NAT_HUB\tmp\_8902_baseline.raw"
ACT  = r"c:\my_project\TUN_NAT_HUB\tmp\_8902_action.raw"

def int16(v):
    return v - 65536 if v >= 32768 else v

def anchors(raw):
    a = []
    i = 0
    n = len(raw)
    while i < n - 3:
        if (raw[i] == 0xf6 or raw[i] == 0xf5) and raw[i+1] == 0x64:
            a.append((i, raw[i], raw[i+2]))
            i += 2
        else:
            i += 1
    return a

# 真实类型: 出现次数高(>500) 的 f6 类型
def real_types(raw):
    cnt = collections.Counter()
    for pos, fb, tl in anchors(raw):
        if fb == 0xf6:
            cnt[tl] += 1
    return {t: c for t, c in cnt.items() if c > 300}

ra = open(BASE, "rb").read()
rb = open(ACT, "rb").read()
ta = real_types(ra)
tb = real_types(rb)
top_types = sorted(set(ta) | set(tb))
print(f"真实 f6 记录类型: {[f'0x{t:02x}' for t in top_types]}")

# 验证 len=type 假说: 对每个真实 type, 检查锚点+type 处是否正好是下一条记录
def validate_len(raw, t):
    a = anchors(raw)
    ok = bad = 0
    L = t  # 假说: 长度 = type 数值
    for k in range(len(a)):
        pos, fb, tl = a[k]
        if fb == 0xf6 and tl == t:
            nxt = a[k+1][0] if k+1 < len(a) else len(raw)
            # 期望下一条锚点正好在 pos+L (若最后一条则到 EOF)
            exp = pos + L
            if exp <= len(raw):
                if nxt == exp or (k+1 >= len(a) and exp == len(raw)):
                    ok += 1
                elif nxt > exp:
                    bad += 1
    return ok, bad, L

print(f"\n{'type':<8}{'长度':<6}{'验证通过':<10}{'不符':<8}  len=type假说")
for t in top_types:
    ok, bad, L = validate_len(rb, t)
    print(f"0x{t:02x}    {L:<6}{ok:<10}{bad:<8}{'✓' if bad==0 else '✗'}")

# 逐字段分类: 用真实类型切分(长度=type), 只统计 id=action
def split_records(raw, types):
    a = anchors(raw)
    recs = []
    for k in range(len(a)):
        pos, fb, tl = a[k]
        if fb == 0xf6 and tl in types:
            L = tl
            if pos + L <= len(raw):
                recs.append((tl, bytes(raw[pos:pos+L])))
    return recs

def series(recs, t, off):
    return [int16(r[off] | (r[off+1] << 8)) for tt, r in recs if tt == t and off + 1 < len(r)]

def mono_ratio(vals):
    if len(vals) < 2:
        return 1.0
    pos = 0
    for i in range(1, len(vals)):
        if vals[i] > vals[i-1]:
            pos += 1
    return pos / (len(vals) - 1)

ra_recs = split_records(ra, top_types)
rb_recs = split_records(rb, top_types)

# 只深入 5 个最高频 type
order = sorted(top_types, key=lambda t: -(tb.get(t, 0)))
print(f"\n===== 逐字段行为分类 (静止 baseline vs 动杆 action) =====")
for t in order[:6]:
    print(f"\n########## type=0x{t:02x}  (len={t}B) ##########")
    print(f"{'off':<5}{'闲时范围':<26}{'闲时中位':<10}{'动杆范围':<26}{'单增比':<7} 判定")
    for off in range(6, t - 1, 2):
        va = series(ra_recs, t, off)
        vb = series(rb_recs, t, off)
        if len(va) < 20 or len(vb) < 20:
            continue
        sa, sb = sorted(va), sorted(vb)
        span_a = sa[-1] - sa[0]
        span_b = sb[-1] - sb[0]
        amid = sa[len(sa)//2]
        mono = mono_ratio(va)
        if span_a <= 2 and span_b <= 2:
            kind = "常量"
        elif mono > 0.8 and span_a > 500:
            kind = "计数器↑"
        elif span_a > 500:
            kind = "闲时即变(遥测/IMU)"
        elif span_b > 400 and span_b > span_a + 300:
            kind = "==> 摇杆候选!"
        elif span_b > span_a + 50:
            kind = "动杆略增"
        else:
            kind = "稳定"
        print(f"{off:<5}{sa[0]:>6}..{sa[-1]:<7} {amid:>9}   {sb[0]:>6}..{sb[-1]:<7} {mono:<7.2f} {kind}")
