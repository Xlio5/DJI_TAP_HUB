#!/usr/bin/env python3
"""构建 16MB SPI Flash 镜像 (U-Boot + DTB + zImage + squashfs)"""
import subprocess, os

def wsl_read(path):
    return subprocess.check_output(["wsl", "bash", "-c", f"cat {path}"])

print("Reading artifacts...")
uboot    = wsl_read("/home/xlong/v3s/u-boot/u-boot-sunxi-with-spl.bin")
dtb      = wsl_read("/home/xlong/v3s/linux/arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb")
zimage   = wsl_read("/home/xlong/v3s/linux/arch/arm/boot/zImage")
squashfs = wsl_read("/home/xlong/v3s/buildroot-2024.02/output/images/rootfs.squashfs")
# Use custom squashfs if exists
custom_sq = r"c:\my_project\TUN_NAT_HUB\backup\rootfs.squashfs"
if os.path.exists(custom_sq):
    with open(custom_sq, "rb") as f:
        squashfs = f.read()
    print(f"  Using custom squashfs: {len(squashfs)} bytes")

print(f"U-Boot:   {len(uboot):>10,} B")
print(f"DTB:      {len(dtb):>10,} B")
print(f"zImage:   {len(zimage):>10,} B ({len(zimage)/1024/1024:.1f} MB)")
print(f"squashfs: {len(squashfs):>10,} B ({len(squashfs)/1024/1024:.1f} MB)")

# 16MB blank (0xFF = erased NOR flash state)
img = bytearray([0xFF] * (16 * 1024 * 1024))

# U-Boot at 8KB (standard sunxi offset)
img[8*1024 : 8*1024 + len(uboot)] = uboot

# DTB at 1MB
img[1024*1024 : 1024*1024 + len(dtb)] = dtb

# zImage at 1.1MB
zimage_off = 1126 * 1024
img[zimage_off : zimage_off + len(zimage)] = zimage

# squashfs at next 128K boundary after zImage
sq_off = ((zimage_off + len(zimage) + 131071) // 131072) * 131072
img[sq_off : sq_off + len(squashfs)] = squashfs

used = sq_off + len(squashfs)
total = len(img)

print(f"\nSPI Flash 16MB Layout:")
print(f"  0KB - 1024KB:    U-Boot + env        (1.0 MB)")
print(f"  1024KB - {1024+len(dtb)//1024}KB:  DTB                 ({len(dtb)//1024} KB)")
print(f"  {zimage_off//1024}KB - {(zimage_off+len(zimage))//1024}KB: zImage              ({len(zimage)//1024} KB)")
print(f"  {sq_off//1024}KB - {used//1024}KB: rootfs.squashfs     ({len(squashfs)//1024} KB)")
print(f"  {used//1024}KB - 16384KB: OTA free            ({(total-used)//1024} KB)")

out = r"c:\my_project\TUN_NAT_HUB\backup\spi_image.bin"
with open(out, "wb") as f:
    f.write(bytes(img))
print(f"\nSaved: {out} ({len(img)} bytes)")
