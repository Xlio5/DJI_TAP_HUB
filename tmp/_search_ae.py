# -*- coding: utf-8 -*-
# 在 8902 流里搜索 40009 风格的 0xAE 摇杆帧 (55 1e 04 8a a2 82 ... 00 06 ae)
# 同时搜索 f6 64 ae 记录、以及各种 55 <len> 帧头
import collections

ACT  = r"c:\my_project\TUN_NAT_HUB\tmp\_8902_action.raw"
BASE = r"c:\my_project\TUN_NAT_HUB\tmp\_8902_baseline.raw"

raw = open(ACT, "rb").read()

# 1) 搜 0xAE 帧命令 (00 06 ae)
ae = []
i = 0
while True:
    i = raw.find(b"\x00\x06\xae", i)
    if i < 0:
        break
    # 回看 55 头
    st = raw.rfind(b"\x55", max(0, i - 40), i)
    ae.append((i, st))
    i += 3
print(f"[action] '00 06 ae' 出现 {len(ae)} 次")
if ae:
    for i, st in ae[:6]:
        print(f"  @0x{i:08x} (55头@0x{st:08x}): " + raw[max(0,st):i+20].hex(" "))

# 2) 搜 55 <len> 帧头统计 (len=0x1e=30)
cnt55 = collections.Counter()
i = 0
while i < len(raw) - 3:
    if raw[i] == 0x55:
        ln = raw[i+1]
        if ln < 0x50 and raw[i+2] == 0x04:
            cnt55[ln] += 1
        i += 2
    else:
        i += 1
print(f"\n[action] 55 <len> 04 帧头分布: {dict(cnt55.most_common(15))}")

# 3) f6 64 ae 00 (type=0xae 记录) 计数
t_ae = 0
i = 0
while i < len(raw) - 3:
    if raw[i] == 0xf6 and raw[i+1] == 0x64 and raw[i+2] == 0xae:
        t_ae += 1
        i += 2
    else:
        i += 1
print(f"[action] f6 64 ae 00 (type=0xae) 记录: {t_ae} 条")

# 4) type=0xae 记录内容抽样（不定长，按下一个 f6 64 或 55 头）
i = 0
shown = 0
while shown < 4:
    i = raw.find(b"\xf6\x64\xae\x00", i)
    if i < 0:
        break
    j = i + 4
    nxt = raw.find(b"\xf6\x64", i + 4)
    en = nxt if nxt > 0 else i + 64
    seg = raw[i:en]
    print(f"\ntype=0xae 记录 @0x{i:08x} ({len(seg)}B): " + seg[:48].hex(" "))
    i += 4
    shown += 1
