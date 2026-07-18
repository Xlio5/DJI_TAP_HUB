#!/usr/bin/env python3
"""
SPI 镜像 — 含 U-Boot env 分区，重启后自动启动
mtdparts=firmware:1M(uboot),64k(dtb),6M(kernel),-(rootfs) g_serial.idVendor=0x0BDA g_serial.idProduct=0x8812 g_serial.use_acm=0
"""
import subprocess, os, struct, binascii

IN_WSL = os.path.exists("/home/xlong")

def wsl_cat(path):
    if IN_WSL:
        with open(path, "rb") as f:
            return f.read()
    return subprocess.check_output(["wsl", "bash", "-c", f"cat {path}"])

print("Reading artifacts...")
spl  = wsl_cat("/home/xlong/v3s/u-boot/spl/sunxi-spl.bin")
uboot = wsl_cat("/home/xlong/v3s/u-boot/u-boot.bin")
dtb  = wsl_cat("/home/xlong/v3s/linux/arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb")
zimage = wsl_cat("/home/xlong/v3s/linux/arch/arm/boot/zImage")

sq_paths = [
    "/mnt/c/my_project/TUN_NAT_HUB/backup/rootfs.squashfs",
    r"c:\my_project\TUN_NAT_HUB\backup\rootfs.squashfs",
]
squashfs = None
for p in sq_paths:
    try:
        with open(p, "rb") as f:
            squashfs = f.read()
        break
    except:
        continue
if not squashfs:
    print("ERROR: squashfs not found")
    exit(1)

print(f"SPL:      {len(spl):>8,} B  ({len(spl)/1024:.0f}KB)")
print(f"U-Boot:   {len(uboot):>8,} B  ({len(uboot)/1024:.0f}KB)")
print(f"DTB:      {len(dtb):>8,} B")
print(f"zImage:   {len(zimage):>8,} B  ({len(zimage)/1024/1024:.1f}MB)")
print(f"squashfs: {len(squashfs):>8,} B  ({len(squashfs)/1024/1024:.1f}MB)")

# Build env binary
bootargs = ("console=ttyS0,115200 root=/dev/mtdblock3 rootfstype=squashfs rootwait "
            "mtdparts=firmware:1M(uboot),64k(dtb),6M(kernel),-(rootfs) g_serial.idVendor=0x0BDA g_serial.idProduct=0x8812 g_serial.use_acm=0")
bootcmd = "bootz 0x41000000 - 0x42000000"
env_str = "bootargs=" + bootargs + "\0" + "bootcmd=" + bootcmd + "\0"
env_bytes = env_str.encode().ljust(0x1FFC, b'\0')
crc = binascii.crc32(env_bytes) & 0xFFFFFFFF
env_bytes += struct.pack('<I', crc)
env_bytes = env_bytes.ljust(0x2000, b'\xFF')
print(f"ENV:      {len(env_bytes):>8,} B  (CRC=0x{crc:08X})")

# Build SPI image
img = bytearray([0xFF] * (16*1024*1024))

# SPL at 0 (eGON header)
img[0:len(spl)] = spl

# U-Boot proper at 0x8000
img[0x8000:0x8000+len(uboot)] = uboot

# ENV at 0x7E000 (before DTB at 1MB, safe gap after U-Boot)
env_off = 0x7E000
img[env_off:env_off+len(env_bytes)] = env_bytes

# DTB at 1MB
dtb_off = 1024 * 1024
img[dtb_off:dtb_off+len(dtb)] = dtb

# zImage at 1088KB (mtd2=kernel)
kernel_off = 1088 * 1024
img[kernel_off:kernel_off+len(zimage)] = zimage

# squashfs at 7232KB (mtd3=rootfs)
rootfs_off = 7232 * 1024
img[rootfs_off:rootfs_off+len(squashfs)] = squashfs

used = rootfs_off + len(squashfs)
total = len(img)

print(f"""
SPI NOR 16MB Layout:
  SPL      @ 0x{0:06X} ({len(spl)//1024}KB) — eGON header
  U-Boot   @ 0x{0x8000:06X} ({len(uboot)//1024}KB)
  ENV      @ 0x{env_off:06X} (8KB, CRC=0x{crc:08X}) — bootcmd + bootargs baked in
  DTB      @ 0x{dtb_off:06X} (64KB partition)
  zImage   @ 0x{kernel_off:06X} ({len(zimage)//1024}KB)
  squashfs @ 0x{rootfs_off:06X} ({len(squashfs)//1024}KB)
  FREE       {(total-used)//1024}KB for OTA

mtdparts=firmware:1M(uboot),64k(dtb),6M(kernel),-(rootfs) g_serial.idVendor=0x0BDA g_serial.idProduct=0x8812 g_serial.use_acm=0
root=/dev/mtdblock3 rootfstype=squashfs
bootcmd=bootz 0x41000000 - 0x42000000

SPL preload: kernel@0x41000000 (SPI 0x110000), DTB@0x42000000 (SPI 0x100000)
""")

out_paths = [
    "/mnt/c/my_project/TUN_NAT_HUB/backup/spi_image.bin",
    r"c:\my_project\TUN_NAT_HUB\backup\spi_image.bin",
]
out = out_paths[0] if IN_WSL else out_paths[1]
with open(out, "wb") as f:
    f.write(bytes(img))
print(f"Saved: {out} ({len(img)} bytes)")
