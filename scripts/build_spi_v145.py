#!/usr/bin/env python3
"""构建 v1.4.5 完整 SPI 固件镜像 — 用新 rootfs (rootfs_new.squashfs, 含修复版 web_server)
生成 backup/spi_image_v145.bin, 并校验其中 rootfs 的 web_server md5 == 0a117b63"""
import subprocess, os, struct, hashlib

def wsl_cat(path):
    return subprocess.check_output(["wsl", "bash", "-c", f"cat {path}"])

print("=== 构建 v1.4.5 SPI 镜像 ===\n")
spl  = wsl_cat("/home/xlong/v3s/u-boot/spl/sunxi-spl.bin")
uboot = wsl_cat("/home/xlong/v3s/u-boot/u-boot.bin")
dtb  = wsl_cat("/home/xlong/v3s/linux/arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb")
zimage = wsl_cat("/home/xlong/v3s/linux/arch/arm/boot/zImage")

sq_path = r"c:\my_project\TUN_NAT_HUB\backup\rootfs_new.squashfs"
with open(sq_path, "rb") as f:
    squashfs = f.read()

print(f"SPL:      {len(spl):>8,} B")
print(f"U-Boot:   {len(uboot):>8,} B")
print(f"DTB:      {len(dtb):>8,} B")
print(f"zImage:   {len(zimage):>8,} B")
print(f"squashfs: {len(squashfs):>8,} B")
print(f"rootfs md5: {hashlib.md5(squashfs).hexdigest()}")

# Boot env (与 build_spi_final.py 一致)
def binascii_crc32(data):
    import binascii
    return binascii.crc32(data) & 0xFFFFFFFF

# PB6 检测: 接地→console=ttyS0@115200 (debug); 上拉→console=null (协议输出)
base_args = ("panic=5 sunxi_wdt.nowayout=1 "
             "rootfstype=squashfs rootwait "
             "mtdparts=firmware:1M(uboot),64k(dtb),6M(kernel),4576k(rootfs_a),-(rootfs_b) g_serial.idVendor=0x0BDA g_serial.idProduct=0x8812 g_serial.use_acm=0")
bootcmd = ("if gpio input 1 6; then "
           "setenv bootargs console=ttyS0,115200 " + base_args + "; "
           "else "
           "setenv bootargs console=null " + base_args + "; "
           "fi; bootz 0x41000000 - 0x42000000")
bootargs = "console=ttyS0,115200 " + base_args
env_str = "bootargs=" + bootargs + "\0" + "bootcmd=" + bootcmd + "\0"
env_bytes = env_str.encode().ljust(0x1FFC, b'\0')
crc = binascii_crc32(env_bytes)
env_bytes += struct.pack('<I', crc)
env_bytes = env_bytes.ljust(0x2000, b'\xFF')

img = bytearray([0xFF] * (16 * 1024 * 1024))
img[0:len(spl)] = spl
img[0x8000:0x8000+len(uboot)] = uboot
env_off = 0x7E000
img[env_off:env_off+len(env_bytes)] = env_bytes
dtb_off = 1024 * 1024
img[dtb_off:dtb_off+len(dtb)] = dtb
kernel_off = 1088 * 1024
img[kernel_off:kernel_off+len(zimage)] = zimage
rootfs_off = 7232 * 1024
img[rootfs_off:rootfs_off+len(squashfs)] = squashfs
# A/B OTA ctl @ 0xFC000: initial=A, confirmed=FF, retry=0
img[0xFC000] = 0xFF
img[0xFC004] = 0xFF
img[0xFC005] = 0

out = r"c:\my_project\TUN_NAT_HUB\backup\spi_image_v145.bin"
with open(out, "wb") as f:
    f.write(bytes(img))
print(f"\n保存: {out} ({len(img)} bytes)")

# 校验: rootfs magic + web_server md5
assert img[rootfs_off:rootfs_off+4] == b"hsqs", "rootfs magic 错误!"
print(f"rootfs magic @ 0x{rootfs_off:X}: hsqs OK")

# 校验: 提取 squashfs 到 WSL /tmp, unsquashfs 后校验二进制 md5
extracted_wsl = "/tmp/_v145_rootfs.tmp.sq"
with open(r"c:\my_project\TUN_NAT_HUB\backup\_v145_rootfs.tmp.sq", "wb") as f:
    f.write(squashfs)
r = subprocess.run(["wsl", "bash", "-lc",
    f"cp /mnt/c/my_project/TUN_NAT_HUB/backup/_v145_rootfs.tmp.sq {extracted_wsl} && rm -rf /tmp/v145_check && unsquashfs -q -d /tmp/v145_check {extracted_wsl} && md5sum /tmp/v145_check/usr/local/bin/web_server /tmp/v145_check/usr/local/bin/usb_tund /tmp/v145_check/usr/local/bin/dji_rc"],
    capture_output=True, text=True)
print("\n=== rootfs 内容校验 (web_server 应为 0a117b63 修复版) ===")
print(r.stdout)
print(r.stderr[:500])
os.remove(r"c:\my_project\TUN_NAT_HUB\backup\_v145_rootfs.tmp.sq")
print("[done]")
