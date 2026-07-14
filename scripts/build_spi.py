#!/usr/bin/env python3
"""SPI镜像: SPL@0, U-Boot@32KB, DTB@1MB, zImage@1.1MB, squashfs"""
import subprocess

def wsl_read(path):
    return subprocess.check_output(["wsl", "bash", "-c", f"cat {path}"])

print("Reading artifacts...")
spl      = wsl_read("/home/xlong/v3s/u-boot/spl/sunxi-spl.bin")
uboot    = wsl_read("/home/xlong/v3s/u-boot/u-boot.bin")
dtb      = wsl_read("/home/xlong/v3s/linux/arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb")
zimage   = wsl_read("/home/xlong/v3s/linux/arch/arm/boot/zImage")

with open(r"c:\my_project\TUN_NAT_HUB\backup\rootfs.squashfs", "rb") as f:
    squashfs = f.read()

print(f"SPL:      {len(spl)} B")
print(f"U-Boot:   {len(uboot)} B")
print(f"zImage:   {len(zimage)} B ({len(zimage)/1024/1024:.1f}MB)")
print(f"squashfs: {len(squashfs)} B ({len(squashfs)/1024/1024:.1f}MB)")

img = bytearray([0xFF] * (16 * 1024 * 1024))

# SPL at offset 0 (Boot ROM scans from 0 for SPI NOR)
img[0 : len(spl)] = spl

# U-Boot proper at 0x8000 (32KB) = CONFIG_SYS_SPI_U_BOOT_OFFS
img[0x8000 : 0x8000 + len(uboot)] = uboot

# DTB at 1MB
img[1024*1024 : 1024*1024 + len(dtb)] = dtb

# zImage at 1.1MB
zi_off = 1126 * 1024
img[zi_off : zi_off + len(zimage)] = zimage

# squashfs
sq_off = ((zi_off + len(zimage) + 131071) // 131072) * 131072
img[sq_off : sq_off + len(squashfs)] = squashfs

used = sq_off + len(squashfs)

print(f"\nSPI NOR 16MB Layout (Boot ROM scans from offset 0):")
print(f"  0KB - {len(spl)//1024}KB:    SPL ({len(spl)//1024}KB)")
print(f"  32KB - {(0x8000+len(uboot))//1024}KB: U-Boot proper ({len(uboot)//1024}KB)")
print(f"  1024KB - 1036KB: DTB")
print(f"  {zi_off//1024}KB - {(zi_off+len(zimage))//1024}KB: zImage ({len(zimage)//1024}KB)")
print(f"  {sq_off//1024}KB - {used//1024}KB: squashfs ({len(squashfs)//1024}KB)")
print(f"  {used//1024}KB - 16384KB: OTA ({(16*1024*1024-used)//1024}KB)")

out = r"c:\my_project\TUN_NAT_HUB\backup\spi_image.bin"
with open(out, "wb") as f:
    f.write(bytes(img))
print(f"\nSaved: {out}")
