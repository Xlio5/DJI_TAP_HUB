"""读回验证 spi_image_v148: rootfs 段 (正确长度) 固化 dji_rc"""
import hashlib, subprocess

p = r"c:\my_project\TUN_NAT_HUB\backup\spi_image_v148.bin"
d = open(p, "rb").read()

ROOTFS_OFF = 0x710000
SQ_LEN = 4599808  # rootfs_v147.squashfs 长度

rootfs = d[ROOTFS_OFF:ROOTFS_OFF + SQ_LEN]
print("rootfs 段 md5 (应 8ede7290):", hashlib.md5(rootfs).hexdigest())
print("magic hsqs:", rootfs[:4] == b"hsqs")

# 写正确长度的 rootfs 段到 WSL 可读路径, unsquashfs 提取 dji_rc
tmp = r"c:\my_project\TUN_NAT_HUB\tmp\_v148_root.sq"
with open(tmp, "wb") as f:
    f.write(rootfs)

cmd = (
    "rm -rf /tmp/v148_x && mkdir -p /tmp/v148_x && "
    "unsquashfs -q -d /tmp/v148_x /mnt/c/my_project/TUN_NAT_HUB/tmp/_v148_root.sq 2>&1 | tail -1 && "
    "echo -n 'dji_rc md5 (应 54e2a723): ' && md5sum /tmp/v148_x/usr/local/bin/dji_rc | awk '{print $1}'"
)
subprocess.run(["wsl", "-d", "Ubuntu-20.04", "--", "bash", "-c", cmd], check=True)
print("DONE")
