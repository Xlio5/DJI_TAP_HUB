#!/usr/bin/env python3
"""SPI镜像 - initramfs方式: zImage内嵌rootfs, SPL直接加载内核"""
import subprocess

out = r"c:\my_project\TUN_NAT_HUB\backup\spi_image.bin"

# Read files (use WSL for the ones on Linux filesystem)
def wsl_cat(path):
    return subprocess.check_output(["wsl", "bash", "-c", f"cat {path}"])

uboot   = wsl_cat("/home/xlong/v3s/u-boot/spl/sunxi-spl.bin")
zimage  = wsl_cat("/home/xlong/v3s/linux/arch/arm/boot/zImage")
dtb     = wsl_cat("/home/xlong/v3s/linux/arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb")

print(f"U-Boot SPL: {len(uboot):>10,} B ({len(uboot)/1024:.0f}KB)")
print(f"zImage:     {len(zimage):>10,} B ({len(zimage)/1024/1024:.1f}MB)")
print(f"DTB:        {len(dtb):>10,} B")

img = bytearray([0xFF] * (16*1024*1024))

# SPL at 0 (sunxi-spl.bin has eGON header)
img[0:len(uboot)] = uboot

# zImage at 128KB (enough room after SPL 24KB)
zi_off = 128 * 1024
img[zi_off:zi_off+len(zimage)] = zimage

# DTB at... actually for initramfs we can put DTB anywhere
# Use append: kernel + DTB concatenated = zImage + DTB (U-Boot style)
# But with initramfs, kernel handles DTB too. Let's put DTB at known offset.
dtb_off = zi_off + len(zimage) + 4096  # aligned after zImage
img[dtb_off:dtb_off+len(dtb)] = dtb

used = dtb_off + len(dtb)

print(f"\nSPI NOR 16MB:")
print(f"  SPL@{0:>6x}:       {len(uboot)//1024}KB")
print(f"  zImage@{zi_off:>6x}:  {len(zimage)//1024}KB")
print(f"  DTB@{dtb_off:>6x}:      {len(dtb)//1024}KB")
print(f"  Total: {used//1024}KB / 16384KB = {used*100//(16*1024*1024)}%")

with open(out, "wb") as f:
    f.write(bytes(img))
print(f"\nSaved: {out} ({len(img)} bytes)")
