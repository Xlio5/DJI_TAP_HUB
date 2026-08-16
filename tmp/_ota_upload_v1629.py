# -*- coding: utf-8 -*-
"""OTA 上传 rootfs_v1629 (v1.6.29, 做法B 手机 144.11)"""
import urllib.request, os, sys, hashlib, time

HOST = "http://192.168.144.66:8080"
FW = r"c:\my_project\TUN_NAT_HUB\backup\rootfs_v1629.squashfs"  # md5 be803124 (修复版: S99 144.11 + setup_v3s head-1)

def main():
    data = open(FW, "rb").read()
    print(f"固件大小: {len(data)/1024/1024:.1f} MB")
    print(f"md5: {hashlib.md5(data).hexdigest()}")
    print("上传中... V3s 将自动刷写+重启")
    req = urllib.request.Request(f"{HOST}/api/firmware/upload", data=data, method="POST",
                                 headers={"Content-Type": "application/octet-stream"})
    try:
        resp = urllib.request.urlopen(req, timeout=180)
        print("响应:", resp.status, resp.read().decode()[:300])
        print("上传成功! 等待 V3s 刷写+重启 (~20s)")
        return 0
    except Exception as e:
        print(f"上传失败: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
