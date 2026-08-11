# -*- coding: utf-8 -*-
# 8902 协议解析: 帧结构 + 全部 cmd 码表 + 逐字段分类(闲时变化 vs 摇杆候选)
import collections, statistics

BASE = r"c:\my_project\TUN_NAT_HUB\tmp\_8902_baseline.raw"
ACT  = r"c:\my_project\TUN_NAT_HUB\tmp\_8902_action.raw"

def find_anchors(raw):
    """所有 f6 64 / f5 64 锚点 -> [(pos, is_f5, type_or_len)]"""
    anchors = []
    i = 0
    n = len(raw)
    while i < n - 3:
        if raw[i] == 0xf6 and raw[i+1] == 0x64:
            anchors.append((i, False, raw[i+2]))
            i += 2
        elif raw[i] == 0xf5 and raw[i+1] == 0x64:
            anchors.append((i, True, raw[i+2]))
            i += 2
        else:
            i += 1
    return anchors

def int16(v):
    return v - 65536 if v >= 32768 else v

raw_a = open(BASE, "rb").read()
raw_b = open(ACT, "rb").read()
anch_a = find_anchors(raw_a)
anch_b = find_anchors(raw_b)
print(f"baseline 锚点: f6={sum(1 for _,f,_ in anch_a if not f)} f5={sum(1 for _,f,_ in anch_a if f)}")
print(f"action   锚点: f6={sum(1 for _,f,_ in anch_b if not f)} f5={sum(1 for _,f,_ in anch_b if f)}")

# ---- 1) 每 type 的规范长度: 锚点到下一锚点距离的众数 ----
def canonical_lengths(anchors, raw):
    """f6 type -> 众数长度; f5 len -> 是否 4+len"""
    gaps = collections.defaultdict(list)
    for k in range(len(anchors)):
        pos, is_f5, tl = anchors[k]
        nxt = anchors[k+1][0] if k+1 < len(anchors) else len(raw)
        gap = nxt - pos
        if gap <= 0 or gap > 300:
            continue
        gaps[(is_f5, tl)].append(gap)
    canon = {}
    for (is_f5, tl), gs in gaps.items():
        if is_f5:
            canon[("f5", tl)] = (4 + tl, len(gs))
        else:
            c = collections.Counter(gs)
            mode_len, mode_cnt = c.most_common(1)[0]
            total = len(gs)
            canon[("f6", tl)] = (mode_len, mode_cnt, total)
    return canon

canon_a = canonical_lengths(anch_a, raw_a)
canon_b = canonical_lengths(anch_b, raw_b)

print("\n===== 协议码表 (cmd: 规范长度, 静止/动杆出现次数) =====")
# 合并两个文件的 type 集合
all_types = set()
for key in canon_a:
    all_types.add(key)
for key in canon_b:
    all_types.add(key)

# f6 码表
f6_types = sorted([t for (frame, t) in all_types if frame == "f6"])
print(f"\n-- f6 64 定长遥测帧, 共 {len(f6_types)} 个 cmd 码 --")
print(f"{'cmd':<6}{'长度':<6}{'静止次数':<10}{'动杆次数':<10}  说明")
for t in f6_types:
    la = canon_a.get(("f6", t))
    lb = canon_b.get(("f6", t))
    L = (la[0] if la else lb[0])
    na = la[2] if la else 0
    nb = lb[2] if lb else 0
    print(f"0x{t:02x}  {L:<6}{na:<10}{nb:<10}")

# f5 码表
f5_lens = sorted([L for (frame, L) in all_types if frame == "f5"])
print(f"\n-- f5 64 变长事件帧, 共 {len(f5_lens)} 种长度 --")
print(f"{'len':<6}{'静止次数':<10}{'动杆次数':<10}")
for L in f5_lens:
    na = canon_a.get(("f5", L), (0, 0))[1]
    nb = canon_b.get(("f5", L), (0, 0))[1]
    print(f"{L:<6}{na:<10}{nb:<10}")
