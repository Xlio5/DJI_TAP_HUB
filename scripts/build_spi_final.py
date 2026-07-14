#!/usr/bin/env python3
"""
SPI 镜像最终版 — mtdparts 对齐
Layout:  1M(uboot), 64K(dtb), -(rootfs=squashfs)
zImage 不放进 Flash — SPL 预载到 RAM
"""
import subprocess, os, sys, pathlib

# Detect if in WSL
IN_WSL = os.path.exists("/home/xlong")

def wsl_cat(path):
    if os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    # Windows fallback
    return subprocess.check_output(["wsl", "bash", "-c", f"cat {path}"])

print("Reading artifacts...")
spl  = wsl_cat("/home/xlong/v3s/u-boot/spl/sunxi-spl.bin")
uboot = wsl_cat("/home/xlong/v3s/u-boot/u-boot.bin")
dtb  = wsl_cat("/home/xlong/v3s/linux/arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb")
zimage = wsl_cat("/home/xlong/v3s/linux/arch/arm/boot/zImage")

# Use custom squashfs (check both WSL and Windows paths)
sq_paths = [
    "/mnt/c/my_project/TUN_NAT_HUB/backup/rootfs.squashfs",
    r"c:\my_project\TUN_NAT_HUB\backup\rootfs.squashfs",
    "/home/xlong/v3s/buildroot-2024.02/output/images/rootfs.squashfs",
]
sq_found = False
for p in sq_paths:
    try:
        with open(p, "rb") as f:
            squashfs = f.read()
        sq_found = True
        break
    except:
        continue

if not sq_found:
    print("ERROR: squashfs not found! Tried:", sq_paths)
    exit(1)

print(f"SPL:     {len(spl):>8,} B  ({len(spl)/1024:.0f}KB)")
print(f"U-Boot:  {len(uboot):>8,} B  ({len(uboot)/1024:.0f}KB)")
print(f"DTB:     {len(dtb):>8,} B")
print(f"zImage:  {len(zimage):>8,} B  ({len(zimage)/1024/1024:.1f}MB)")
print(f"squashfs:{len(squashfs):>8,} B  ({len(squashfs)/1024/1024:.1f}MB)")

# Build SPI image with mtdparts-aligned layout
# mtdparts = firmware:1M(uboot),64k(dtb),6M(kernel),-(rootfs)
img = bytearray([0xFF] * (16*1024*1024))

# SPL at 0 (eGON header)
img[0:len(spl)] = spl

# U-Boot proper at 0x8000 (CONFIG_SYS_SPI_U_BOOT_OFFS)
img[0x8000:0x8000+len(uboot)] = uboot

# DTB at 1MB (mtd1 = dtb partition)
dtb_off = 1024 * 1024
img[dtb_off:dtb_off+len(dtb)] = dtb
mtd1_end = dtb_off + 64*1024  # 64KB partition

# kernel at 1088KB (mtd2 = kernel partition, 6MB)
kernel_off = 1088 * 1024
img[kernel_off:kernel_off+len(zimage)] = zimage
mtd2_end = kernel_off + 6*1024*1024  # 6MB partition

# rootfs at 7232KB (mtd3 = rootfs partition, remaining space)
rootfs_off = 7232 * 1024
img[rootfs_off:rootfs_off+len(squashfs)] = squashfs

used = rootfs_off + len(squashfs)
total = len(img)

print(f"""
SPI NOR 16MB Layout:
  mtd0 (uboot)  : 0x000000-0x100000   (1MB)
    SPL @0, U-Boot @0x8000
  mtd1 (dtb)    : 0x100000-0x110000   (64KB)
    DTB @0x100000
  mtd2 (kernel) : 0x110000-0x710000   (6MB)
    zImage @0x110000 ({len(zimage)//1024}KB)
  mtd3 (rootfs) : 0x710000-{used:x}  ({len(squashfs)//1024}KB used of {(16*1024*1024-rootfs_off)//1024}KB)
    squashfs @0x710000

mtdparts=firmware:1M(uboot),64k(dtb),6M(kernel),-(rootfs)
root=/dev/mtdblock3

SPL preloads: kernel@0x41000000 from SPI 0x110000, DTB@0x42000000 from SPI 0x100000
""")

out_paths = [
    "/mnt/c/my_project/TUN_NAT_HUB/backup/spi_image.bin",
    r"c:\my_project\TUN_NAT_HUB\backup\spi_image.bin",
]
out = out_paths[0] if os.path.exists(os.path.dirname(out_paths[0])) else out_paths[1]
with open(out, "wb") as f:
    f.write(bytes(img))
print(f"Saved: {out} ({len(img)} bytes)")
