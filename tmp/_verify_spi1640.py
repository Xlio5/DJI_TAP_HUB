"""验证 spi_image.bin 内嵌 rootfs 为 v1.6.40 + 归档"""
import hashlib, shutil

SRC = r"c:\my_project\TUN_NAT_HUB\backup\spi_image.bin"
RFS_SRC = r"c:\my_project\TUN_NAT_HUB\backup\rootfs_v1640.squashfs"
OFF = 0x710000
rfs_size = len(open(RFS_SRC, "rb").read())
with open(SRC, "rb") as f:
    f.seek(OFF)
    rfs = f.read(rfs_size)
m1 = hashlib.md5(rfs).hexdigest()
m2 = hashlib.md5(open(RFS_SRC, "rb").read()).hexdigest()
print(f"spi内嵌 rootfs: {m1}")
print(f"rootfs_v1640  : {m2}")
print("一致 ✓" if m1 == m2 else "不一致!")
ARCHIVE = r"c:\my_project\TUN_NAT_HUB\backup\spi_image_v1640_20260824_aux_tmux_fix.bin"
shutil.copyfile(SRC, ARCHIVE)
print("归档:", ARCHIVE)
