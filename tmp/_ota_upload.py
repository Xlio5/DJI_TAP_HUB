"""OTA 上传 v149 rootfs 到设备 inactive 槽 + 确认响应"""
import http.client, os, sys

HOST = "192.168.144.66"
PORT = 8080
PATH = "/api/firmware/upload"
FW = r"c:\my_project\TUN_NAT_HUB\backup\rootfs_v149.squashfs"

data = open(FW, "rb").read()
print(f"上传 {FW}: {len(data)} bytes")

conn = http.client.HTTPConnection(HOST, PORT, timeout=300)
conn.request("POST", PATH, body=data, headers={
    "Content-Type": "application/octet-stream",
    "Content-Length": str(len(data)),
})
resp = conn.getresponse()
body = resp.read().decode(errors="replace")
print("HTTP", resp.status)
print("响应:", body)
conn.close()
