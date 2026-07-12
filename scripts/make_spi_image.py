#!/usr/bin/env python3
"""创建 SPI Flash 镜像 (gzip kernel) + 复制到 SD 卡"""
import subprocess, os, shutil

def wsl_read(path):
    return subprocess.check_output(["wsl", "bash", "-c", f"cat {path}"])

print("Reading artifacts...")
uboot    = wsl_read("/home/xlong/v3s/u-boot/u-boot-sunxi-with-spl.bin")
dtb      = wsl_read("/home/xlong/v3s/linux/arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb")
zimage   = wsl_read("/home/xlong/v3s/linux/arch/arm/boot/zImage")
squashfs = wsl_read("/home/xlong/v3s/buildroot-2024.02/output/images/rootfs.squashfs")

print(f"U-Boot:   {len(uboot):>10,} bytes")
print(f"DTB:      {len(dtb):>10,} bytes ({len(dtb)/1024:.0f} KB)")
print(f"zImage:   {len(zimage):>10,} bytes ({len(zimage)/1024/1024:.1f} MB)")
print(f"squashfs: {len(squashfs):>10,} bytes ({len(squashfs)/1024/1024:.1f} MB)")

# 16MB blank (0xFF = erased state)
SPI_SIZE = 16 * 1024 * 1024
img = bytearray([0xFF] * SPI_SIZE)

# Layout
# 0KB:      U-Boot (8KB offset)
# 1024KB:   DTB
# 1126KB:   zImage (gzip)
# Align rootfs to 128K after zImage
zimage_offset = 1126 * 1024
rootfs_offset = ((zimage_offset + len(zimage) + 131071) // 131072) * 131072

img[8*1024 : 8*1024 + len(uboot)] = uboot
img[1024*1024 : 1024*1024 + len(dtb)] = dtb
img[zimage_offset : zimage_offset + len(zimage)] = zimage
img[rootfs_offset : rootfs_offset + len(squashfs)] = squashfs

used_end = rootfs_offset + len(squashfs)
free_kb = (SPI_SIZE - used_end) // 1024

print(f"""
SPI Flash 16MB layout:
  0KB - 1024KB:     U-Boot + env              (1 MB)
  1024KB - 1036KB:  DTB                       (12 KB)
  {zimage_offset//1024}KB - {(zimage_offset+len(zimage))//1024}KB:  zImage (gzip)             ({len(zimage)//1024} KB)
  {rootfs_offset//1024}KB - {used_end//1024}KB:  rootfs.squashfs (xz)      ({len(squashfs)//1024} KB)
  {used_end//1024}KB - 16384KB:  OTA 空闲                  ({free_kb} KB)

mtdparts: 1M(uboot),64k(dtb),{len(zimage)//1024}k(kernel),-(rootfs)

U-Boot bootcmd:
  sf probe 0
  sf read 0x42000000 0x100000 0x{len(dtb):x}
  sf read 0x41000000 0x{zimage_offset:x} 0x{len(zimage):x}
  bootz 0x41000000 - 0x42000000
""")

# Save image
out_img = r"c:\my_project\TUN_NAT_HUB\backup\spi_image.bin"
with open(out_img, "wb") as f:
    f.write(bytes(img))
print(f"SPI image saved: {out_img} ({len(img)} bytes)")

# Copy to SD card
sd = "E:"
shutil.copy2(out_img, os.path.join(sd, "spi_image.bin"))
print(f"Copied to {sd}spi_image.bin")

with open(os.path.join(sd, "zImage"), "wb") as f:
    f.write(zimage)
print(f"Updated {sd}zImage ({len(zimage)} bytes)")

with open(os.path.join(sd, "rootfs.squashfs"), "wb") as f:
    f.write(squashfs)
print(f"Copied {sd}rootfs.squashfs ({len(squashfs)} bytes)")
