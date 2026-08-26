"""从 SPI 镜像提取内嵌 squashfs (rootfs_a @ 0x710000) 到临时文件"""
import sys, os

SRC = r"c:\my_project\TUN_NAT_HUB\backup\spi_image_v1638_20260823_txhz_debug.bin"
OFF = 0x710000
SIZE = 4576 * 1024
OUT = r"c:\my_project\TUN_NAT_HUB\tmp\_rfs_from_spi.squashfs"

with open(SRC, "rb") as f:
    f.seek(OFF)
    data = f.read(SIZE)
with open(OUT, "wb") as f:
    f.write(data)
print(f"extracted {len(data)} bytes -> {OUT}")

# 计算 md5 对比
import hashlib
print("spi内嵌 rootfs md5:", hashlib.md5(data).hexdigest())
with open(r"c:\my_project\TUN_NAT_HUB\backup\rootfs_v1638_20260823_txhz_debug.squashfs", "rb") as f:
    print("单独 rootfs   md5:", hashlib.md5(f.read()).hexdigest())
