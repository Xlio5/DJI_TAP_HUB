# -*- coding: utf-8 -*-
"""APK 基本信息探测：结构、DEX、资源、证书"""
import zipfile
import collections
import sys
import hashlib

APK = sys.argv[1] if len(sys.argv) > 1 else r"C:\my_project\TUN_NAT_HUB\master-app-debug.apk"

z = zipfile.ZipFile(APK)
names = z.namelist()
print(f"APK: {APK}")
print(f"TOTAL ENTRIES: {len(names)}")

print("\n=== 顶层目录统计 ===")
tops = collections.Counter(n.split("/")[0] for n in names if "/" in n)
for k, v in sorted(tops.items(), key=lambda x: -x[1]):
    print(f"  {k}: {v}")

print("\n=== 关键文件 ===")
for n in names:
    low = n.lower()
    info = z.getinfo(n)
    if low.endswith(".dex") or "manifest" in low or low.startswith("lib/") or \
       low.endswith(".so") or "assets/" in low:
        print(f"  {n}  ({info.file_size} bytes, {info.compress_size} compressed)")

print("\n=== 原生库 lib/ 架构分布 ===")
libs = [n for n in names if n.startswith("lib/") and n.endswith(".so")]
arch = collections.Counter(n.split("/")[1] for n in libs)
for k, v in arch.items():
    print(f"  {k}: {v} libs")
for n in libs:
    print(f"    - {n.split('/')[-1]}")

print("\n=== APK SHA256 ===")
sha = hashlib.sha256(open(APK, "rb").read()).hexdigest()
print(f"  {sha}")
