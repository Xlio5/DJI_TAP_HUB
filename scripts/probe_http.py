#!/usr/bin/env python3
"""探测 HTTP 服务，识别设备"""

import urllib.request
import sys

PATHS = [
    "/", "/api/", "/cgi-bin/", "/web/", "/index.html", "/admin/",
    "/status", "/snapshot.jpg", "/onvif/device_service",
    "/Streaming/Channels/101/preview", "/ISAPI/", "/devices/",
]

def probe(ip: str) -> None:
    print(f"\n=== {ip} ===")
    for path in PATHS:
        url = f"http://{ip}{path}"
        try:
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "Mozilla/5.0")
            with urllib.request.urlopen(req, timeout=3) as resp:
                content_type = resp.headers.get("Content-Type", "")
                server = resp.headers.get("Server", "")
                # Read a bit to check if it has title
                body = resp.read(2048).decode("utf-8", errors="ignore")
                title = ""
                if "<title>" in body:
                    title = body.split("<title>")[1].split("</title>")[0].strip()
                print(f"  {path} -> {resp.status} | Server: {server} | Type: {content_type} | Title: {title}")
                if resp.status == 200 and ("text/html" in content_type or title):
                    break  # Found a web page
        except Exception as e:
            pass  # skip dead paths silently

if __name__ == "__main__":
    targets = sys.argv[1:] if len(sys.argv) > 1 else ["192.168.144.88", "192.168.144.88"]
    for t in targets:
        probe(t)
