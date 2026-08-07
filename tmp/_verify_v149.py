"""读回验证 spi_image_v149: U-Boot bootcmd + rootfs 固化 dji_rc + inittab 禁用"""
import hashlib, subprocess

p = r"c:\my_project\TUN_NAT_HUB\backup\spi_image_v149.bin"
d = open(p, "rb").read()

UBOOT_OFF, UBOOT_LEN = 0x8000, 404384
ROOTFS_OFF = 0x710000
SQ_LEN = 4599808

seg = d[UBOOT_OFF:UBOOT_OFF + UBOOT_LEN]
rootfs = d[ROOTFS_OFF:ROOTFS_OFF + SQ_LEN]

print("镜像总长:", len(d))
print("\n=== U-Boot 段 bootcmd ===")
print("gpio input PB6:", b"gpio input PB6" in seg)
print("console=ttyS0,115200:", b"console=ttyS0,115200" in seg)
print("console=null:", b"console=null" in seg)

print("\n=== rootfs 段 ===")
print("magic hsqs:", rootfs[:4] == b"hsqs")
print("rootfs md5 (应 69a317ce):", hashlib.md5(rootfs).hexdigest())

# 提取 rootfs 段, 供 WSL unsquashfs 校验 dji_rc + inittab
tmp = r"c:\my_project\TUN_NAT_HUB\tmp\_v149_root.sq"
with open(tmp, "wb") as f:
    f.write(rootfs)

cmd = (
    "rm -rf /tmp/v149_x && "
    "unsquashfs -q -d /tmp/v149_x /mnt/c/my_project/TUN_NAT_HUB/tmp/_v149_root.sq 2>&1 | tail -1 && "
    "echo -n 'dji_rc md5 (应 68a6b7b5): ' && md5sum /tmp/v149_x/usr/local/bin/dji_rc | awk '{print $1}' && "
    "echo -n 'inittab ttyS0 启用行: ' && (grep -c '^ttyS0::respawn' /tmp/v149_x/etc/inittab || echo 0)"
)
subprocess.run(["wsl", "-d", "Ubuntu-20.04", "--", "bash", "-c", cmd], check=True)
print("DONE")
