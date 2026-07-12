import subprocess, shutil, os

def wsl_read(path):
    return subprocess.check_output(["wsl", "bash", "-c", f"cat {path}"])

sd = "E:"
print(f"SD card: {sd}")

# New DTB with SPI NOR node
dtb = wsl_read("/home/xlong/v3s/linux/arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb")
print(f"DTB: {len(dtb)} bytes")

with open(sd + "/sun8i-v3s-licheepi-zero-dock.dtb", "wb") as f:
    f.write(dtb)
print("DTB updated on SD")

# Read other artifacts
uboot = wsl_read("/home/xlong/v3s/u-boot/u-boot-sunxi-with-spl.bin")
zimage = wsl_read("/home/xlong/v3s/linux/arch/arm/boot/zImage")
squashfs = wsl_read("/home/xlong/v3s/buildroot-2024.02/output/images/rootfs.squashfs")

# Build SPI image
SPI_SIZE = 16 * 1024 * 1024
img = bytearray([0xFF] * SPI_SIZE)
zimage_offset = 1126 * 1024
rootfs_offset = ((zimage_offset + len(zimage) + 131071) // 131072) * 131072

img[8*1024 : 8*1024 + len(uboot)] = uboot
img[1024*1024 : 1024*1024 + len(dtb)] = dtb
img[zimage_offset : zimage_offset + len(zimage)] = zimage
img[rootfs_offset : rootfs_offset + len(squashfs)] = squashfs

with open(sd + "/spi_image.bin", "wb") as f:
    f.write(bytes(img))
print(f"SPI image: {len(img)} bytes")

print("\nFiles on SD:")
for f in sorted(os.listdir(sd)):
    if f != "System Volume Information":
        size = os.path.getsize(os.path.join(sd, f))
        print(f"  {f:50s} {size:>10,} bytes")
