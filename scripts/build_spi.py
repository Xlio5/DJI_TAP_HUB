#!/usr/bin/env python3
"""构建 16MB SPI Flash 镜像 — U-Boot SPL 在 offset 0 (NOR Flash 规范)"""
import subprocess, os

def wsl_read(path):
    return subprocess.check_output(["wsl", "bash", "-c", f"cat {path}"])

print("Reading artifacts...")
uboot    = wsl_read("/home/xlong/v3s/u-boot/u-boot-sunxi-with-spl.bin")
dtb      = wsl_read("/home/xlong/v3s/linux/arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb")
zimage   = wsl_read("/home/xlong/v3s/linux/arch/arm/boot/zImage")
squashfs = subprocess.check_output(["wsl", "bash", "-c", "cat /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs.squashfs"])
print(f"U-Boot:   {len(uboot):>10,} B")
print(f"DTB:      {len(dtb):>10,} B")
print(f"zImage:   {len(zimage):>10,} B ({len(zimage)/1024/1024:.1f} MB)")
print(f"squashfs: {len(squashfs):>10,} B ({len(squashfs)/1024/1024:.1f} MB)")

img = bytearray([0xFF] * (16 * 1024 * 1024))

# SPI NOR: U-Boot SPL at OFFSET 0 (not 8KB like SD!)
img[0 : len(uboot)] = uboot

# DTB at 1MB (SPL+U-Boot about 500KB, safe margin)
dtb_off = 1024 * 1024
img[dtb_off : dtb_off + len(dtb)] = dtb

# zImage at 1.1MB
zi_off = 1126 * 1024
img[zi_off : zi_off + len(zimage)] = zimage

# squashfs at next 128K boundary
sq_off = ((zi_off + len(zimage) + 131071) // 131072) * 131072
img[sq_off : sq_off + len(squashfs)] = squashfs

used = sq_off + len(squashfs)
total = len(img)

print(f"\nSPI NOR Layout:")
print(f"  0KB - {len(uboot)//1024}KB:    U-Boot SPL+proper   ({len(uboot)//1024} KB)")
print(f"  {dtb_off//1024}KB - {(dtb_off+len(dtb))//1024}KB:  DTB                 ({len(dtb)//1024} KB)")
print(f"  {zi_off//1024}KB - {(zi_off+len(zimage))//1024}KB:  zImage              ({len(zimage)//1024} KB)")
print(f"  {sq_off//1024}KB - {used//1024}KB:  rootfs.squashfs     ({len(squashfs)//1024} KB)")
print(f"  {used//1024}KB - 16384KB:  OTA free            ({(total-used)//1024} KB)")

out = r"c:\my_project\TUN_NAT_HUB\backup\spi_image.bin"
with open(out, "wb") as f:
    f.write(bytes(img))
print(f"\nSaved: {out} ({len(img)} bytes)")
