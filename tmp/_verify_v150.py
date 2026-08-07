"""读回验证 spi_image_v150: U-Boot bootcmd + rootfs dji_rc + inittab"""
import hashlib, subprocess

p = r"c:\my_project\TUN_NAT_HUB\backup\spi_image_v150.bin"
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
print("rootfs md5 (应 de22318a):", hashlib.md5(rootfs).hexdigest())

tmp = r"c:\my_project\TUN_NAT_HUB\tmp\_v150_root.sq"
with open(tmp, "wb") as f:
    f.write(rootfs)

cmd = (
    "rm -rf /tmp/v150_x && "
    "unsquashfs -q -d /tmp/v150_x /mnt/c/my_project/TUN_NAT_HUB/tmp/_v150_root.sq 2>&1 | tail -1 && "
    "echo -n 'dji_rc md5 (应 fad8b8f2): ' && md5sum /tmp/v150_x/usr/local/bin/dji_rc | awk '{print $1}' && "
    "echo -n 'inittab ttyS0 启用行: ' && (grep -c '^ttyS0::respawn' /tmp/v150_x/etc/inittab || echo 0)"
)
subprocess.run(["wsl", "-d", "Ubuntu-20.04", "--", "bash", "-c", cmd], check=True)
print("DONE")
