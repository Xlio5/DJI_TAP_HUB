# -*- coding: utf-8 -*-
"""OTA 上传 rootfs_v1614 (v1.6.14, tmpPath 改 /tmp 修 OTA 空间)"""
import urllib.request, os, sys

HOST = "http://192.168.144.66:8080"
FW = r"c:\my_project\TUN_NAT_HUB\backup\rootfs_v1614.squashfs"

def main():
    data = open(FW, "rb").read()
    print(f"固件大小: {len(data)/1024/1024:.1f} MB")
    print(f"md5: {__import__('hashlib').md5(data).hexdigest()}")
    req = urllib.request.Request(f"{HOST}/api/firmware/upload", data=data, method="POST",
                                 headers={"Content-Type": "application/octet-stream"})
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        print("响应:", resp.status, resp.read().decode()[:200])
        print("上传成功! V3s 将自动重启 (~15s)")
        return 0
    except Exception as e:
        print(f"上传失败: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
