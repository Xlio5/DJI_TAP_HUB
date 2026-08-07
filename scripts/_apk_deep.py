# -*- coding: utf-8 -*-
"""AXML (AndroidManifest) 字符串提取 + DEX 字符串提取"""
import zipfile
import struct
import sys
import collections
import re

APK = sys.argv[1] if len(sys.argv) > 1 else r"C:\my_project\TUN_NAT_HUB\master-app-debug.apk"
z = zipfile.ZipFile(APK)


def read_uleb128(buf, pos):
    result = 0
    shift = 0
    while True:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result, pos


def parse_axml_strings(data):
    """解析 AXML 的字符串池，返回字符串列表"""
    if len(data) < 8:
        return []
    magic = struct.unpack_from("<H", data, 0)[0]
    if magic != 0x0003:  # AXML magic (0x00080003 low 16 bits = 0x0003)
        return []
    header_size = struct.unpack_from("<H", data, 4)[0]
    pool_type = struct.unpack_from("<H", data, header_size)[0]
    if pool_type != 0x0001:  # ResStringPool
        return []
    # ResStringPool header starts at header_size
    pos = header_size
    stringCount = struct.unpack_from("<I", data, pos)[0]
    flags = struct.unpack_from("<I", data, pos + 8)[0]
    stringsStart = struct.unpack_from("<I", data, pos + 12)[0]
    pos += 16
    offsets = struct.unpack_from("<%dI" % stringCount, data, pos)
    is_utf8 = bool(flags & 0x100)
    strings = []
    for off in offsets:
        spos = header_size + stringsStart + off
        if is_utf8:
            _, p = read_uleb128(data, spos)  # utf16 len
            _, p = read_uleb128(data, p)     # utf8 len
            end = data.find(b"\x00", p)
            if end == -1:
                s = data[p:]
            else:
                s = data[p:end]
            strings.append(s.decode("utf-8", "replace"))
        else:
            # utf-16le, 0x00 0x00 terminated
            end = spos
            while end + 1 < len(data) and not (data[end] == 0 and data[end + 1] == 0):
                end += 2
            try:
                strings.append(data[spos:end].decode("utf-16le", "replace"))
            except Exception:
                strings.append("")
    return strings


def extract_manifest_strings():
    print("=" * 60)
    print("[1] AndroidManifest.xml 字符串池")
    print("=" * 60)
    data = z.read("AndroidManifest.xml")
    strs = parse_axml_strings(data)
    print(f"字符串总数: {len(strs)}")
    interesting = []
    for s in strs:
        if not s:
            continue
        if re.match(r'^[a-zA-Z0-9_.$]{3,}$', s):  # 类名/包名/权限
            interesting.append(s)
    for s in interesting:
        print(f"  {s}")


def extract_dex_strings():
    print("\n" + "=" * 60)
    print("[2] DEX 字符串 (提取感兴趣的)")
    print("=" * 60)
    dex_files = [n for n in z.namelist() if n.endswith(".dex")]
    all_hits = collections.Counter()
    url_hits = []
    pkg_hits = []
    for dex in sorted(dex_files, key=lambda n: int(re.search(r'\d+', n).group()) if re.search(r'\d+', n) else 0):
        data = z.read(dex)
        if len(data) < 112 or data[:8] != b"dex\n035\0":
            print(f"  {dex}: 非标准 DEX，跳过")
            continue
        string_ids_size = struct.unpack_from("<I", data, 56)[0]
        string_ids_off = struct.unpack_from("<I", data, 60)[0]
        strings = []
        for i in range(min(string_ids_size, 300000)):
            off = struct.unpack_from("<I", data, string_ids_off + i * 4)[0]
            utf16_len, p = read_uleb128(data, off)
            end = data.find(b"\x00", p)
            if end == -1:
                continue
            s = data[p:end].decode("utf-8", "replace")
            strings.append(s)
        # 分类收集
        for s in strings:
            if re.match(r'^https?://', s):
                url_hits.append((dex, s))
            elif re.match(r'^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$', s):
                all_hits[s] += 1
        print(f"  {dex}: {string_ids_size} strings")
    print("\n--- 网络 URL (前 40) ---")
    for dex, s in url_hits[:40]:
        print(f"  [{dex}] {s}")
    print(f"\n  ... 共 {len(url_hits)} 个 URL")
    print("\n--- 出现频次最高的包名/类名 (前 60) ---")
    for name, cnt in all_hits.most_common(60):
        print(f"  {cnt:4d}  {name}")


extract_manifest_strings()
extract_dex_strings()
