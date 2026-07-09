#!/usr/bin/env python3
"""获取 HTTP 页面内容"""

import urllib.request
import sys

ip = sys.argv[1] if len(sys.argv) > 1 else "192.168.144.31"
req = urllib.request.Request(f"http://{ip}")
req.add_header("User-Agent", "Mozilla/5.0")
with urllib.request.urlopen(req, timeout=5) as resp:
    body = resp.read(4096).decode("utf-8", errors="ignore")
    print(body[:3000])
