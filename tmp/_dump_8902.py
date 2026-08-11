# -*- coding: utf-8 -*-
# 8902 原始数据 dump + diff —— 供老大人工对比摇杆字段
#
# 用法:
#   python _dump_8902.py baseline [秒数]    # 抓 N 秒存 baseline.raw + 输出 hex dump
#   python _dump_8902.py action   [秒数]    # 抓 N 秒(动杆时跑) 存 action.raw
#   python _dump_8902.py diff                # 对比 baseline.raw vs action.raw, 输出变化字段
#
# 人工对比方法:
#   分别打开 baseline.txt / action.txt, 同 type 同偏移的字节列差异 → 摇杆字段
import socket, time, sys, collections

HOST = "10.169.25.112"
PORT = 8902
BASE = r"c:\my_project\TUN_NAT_HUB\tmp\_8902_baseline"
ACT  = r"c:\my_project\TUN_NAT_HUB\tmp\_8902_action"
MAIN_LEN = {0x56:86, 0x60:96, 0x32:50, 0x50:80, 0x22:34, 0x38:56,
            0x00:76, 0x48:72, 0x54:84, 0x34:52}

def grab(secs):
    s = socket.create_connection((HOST, PORT), timeout=5)
    s.settimeout(0.5)
    raw = bytearray()
    t0 = time.time()
    while time.time() - t0 < secs:
        try:
            c = s.recv(65536)
        except socket.timeout:
            c = b""
        if c:
            raw += c
    s.close()
    return bytes(raw)

def split_records(raw):
    """按 f6 64 锚点 + 固定主长度切分, 锚点校验防漂移"""
    recs = []
    i = 0
    while i < len(raw):
        if raw[i] == 0xf6 and raw[i+1] == 0x64 and i + 2 < len(raw):
            t = raw[i+2]
            L = MAIN_LEN.get(t)
            # 下一个锚点必须正好在 i+L, 否则回退逐字节找
            if L and i + L <= len(raw) and raw[i+L] == 0xf6 and raw[i+L+1] == 0x64:
                recs.append((t, bytes(raw[i:i+L])))
                i += L
                continue
        i += 1
    return recs

def dump_txt(recs, path):
    lines = []
    for t in MAIN_LEN:
        tr = [r for (tt, r) in recs if tt == t]
        if not tr:
            continue
        lines.append(f"=== type=0x{t:02x} ({MAIN_LEN[t]}B)  记录数={len(tr)} ===")
        show = tr[:16] + tr[-2:]
        for k, r in enumerate(show):
            tag = f"[#{k:3d}]" if k < 16 else "[..]"
            rows = []
            for off in range(0, len(r), 8):
                seg = r[off:off+8]
                hh = " ".join(f"{b:02x}" for b in seg)
                rows.append(f"{off:04x} {hh}")
            lines.append(f"  {tag} {' | '.join(rows)}")
        lines.append("")
    open(path, "w", encoding="utf-8").write("\n".join(lines))
    print(f"  hex dump -> {path}")

def run_phase(name, secs):
    print(f"[{name}] 抓 {HOST}:{PORT} {secs}s ...", flush=True)
    raw = grab(secs)
    recs = split_records(raw)
    print(f"[{name}] {len(raw)} bytes, 切出 {len(recs)} 条主长度记录", flush=True)
    dump_txt(recs, name + ".txt")
    open(name + ".raw", "wb").write(raw)
    print(f"[{name}] raw -> {name}.raw", flush=True)

def run_diff():
    a_raw = open(BASE + ".raw", "rb").read()
    b_raw = open(ACT + ".raw", "rb").read()
    a = split_records(a_raw)
    b = split_records(b_raw)
    print(f"baseline {len(a)} 条, action {len(b)} 条", flush=True)

    # 按 (type, off) 统计 u16 值集合
    def fields(recs, start_ratio, end_ratio):
        """取时间窗中间的记录, (type,off)-> 值集合"""
        lo = int(len(recs) * start_ratio)
        hi = int(len(recs) * end_ratio)
        res = collections.defaultdict(set)
        for t, r in recs[lo:hi]:
            for off in range(6, len(r) - 1, 2):
                res[(t, off)].add(r[off] | (r[off+1] << 8))
        return res

    # baseline 用前 1/3, action 用后 1/3, 尽量避开动作过渡
    fa = fields(a, 0.0, 0.33)
    fb = fields(b, 0.5, 1.0)

    print("\n==== baseline 稳定 / action 变化 的字段 (摇杆候选) ====", flush=True)
    found = False
    for key in fa:
        sa, sb = fa[key], fb.get(key, set())
        if len(sa) <= 4 and sb and (max(sb) - min(sb) > 300):
            bmid = sorted(sa)[len(sa)//2]
            print(f"  type=0x{key[0]:02x} off={key[1]:2d}  基线中心={bmid:6d}  动作值[{min(sb):6d}..{max(sb):6d}] ({len(sb)}种)", flush=True)
            found = True
    if not found:
        print("  (未发现满足条件的字段)", flush=True)

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0
    if mode == "diff":
        run_diff()
    elif mode == "baseline":
        run_phase(BASE, secs)
    elif mode == "action":
        run_phase(ACT, secs)
    else:
        print("用法: baseline|action|diff [秒数]")
