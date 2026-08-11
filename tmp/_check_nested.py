# -*- coding: utf-8 -*-
# 验证大记录内部嵌套 f6 64 / f5 64 子记录
import collections

ACT = r"c:\my_project\TUN_NAT_HUB\tmp\_8902_action.raw"
raw = open(ACT, "rb").read()

# 用 len=type 切主记录
def split_main(raw):
    recs = []  # (type, start, bytes)
    i = 0
    n = len(raw)
    while i < n - 3:
        if (raw[i] == 0xf6 or raw[i] == 0xf5) and raw[i+1] == 0x64:
            L = raw[i+2]
            if 8 <= L <= 120 and i + L <= n:
                recs.append((raw[i], raw[i+2], i, bytes(raw[i:i+L])))
                i += L
                continue
        i += 1
    return recs

recs = split_main(raw)
print(f"主记录总数: {len(recs)}")

# 统计每个主记录内嵌套的 f6 64 / f5 64 出现次数（跳过头部 4 字节）
nested_inside = collections.Counter()   # (main_type, sub_type) -> count
main_nested_cnt = collections.Counter()
for frame, typ, pos, r in recs:
    cnt = 0
    j = 4  # 跳过 f6 64 <len> 00 头部
    while j < len(r) - 3:
        if (r[j] == 0xf6 or r[j] == 0xf5) and r[j+1] == 0x64:
            sub = r[j+2]
            nested_inside[(typ, sub)] += 1
            cnt += 1
            j += 2
        else:
            j += 1
    if cnt:
        main_nested_cnt[typ] += 1

print("\n== 主记录内嵌子记录: 出现次数 (主type -> 子type) ==")
for (mtyp, styp), c in nested_inside.most_common(25):
    print(f"  主 0x{mtyp:02x} 内嵌子 0x{styp:02x}: {c} 次")

print("\n== 各主type中 含嵌套 的记录比例 ==")
total = collections.Counter(t for _, t, _, _ in recs)
for t in sorted(main_nested_cnt):
    print(f"  0x{t:02x}: {main_nested_cnt[t]}/{total[t]} 条含嵌套")

# 抽样: 0x60 记录内部嵌套内容
print("\n== 0x60 记录内部嵌套抽样 ==")
shown = 0
for frame, typ, pos, r in recs:
    if typ != 0x60:
        continue
    j = 4
    inner = []
    while j < len(r) - 3:
        if (r[j] == 0xf6 or r[j] == 0xf5) and r[j+1] == 0x64:
            inner.append((j, r[j], r[j+2]))
            j += 2
        else:
            j += 1
    if inner and shown < 5:
        print(f"  0x60 记录 @0x{pos:08x}: 嵌套 {inner}")
        shown += 1
    if shown >= 5:
        break
