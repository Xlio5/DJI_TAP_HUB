import os, shutil

sd = "E:"

# Remove old files
for f in ["rootfs.cpio.gz", "rootfs_new.ext4.gz"]:
    p = os.path.join(sd, f)
    if os.path.exists(p):
        os.remove(p)
        print("Removed " + f)

# Copy new SPI image
src = r"c:\my_project\TUN_NAT_HUB\backup\spi_image.bin"
dst = os.path.join(sd, "spi_image.bin")
shutil.copy(src, dst)
print("spi_image.bin: " + str(os.path.getsize(dst)) + " bytes")

print()
for f in sorted(os.listdir(sd)):
    if "Volume" not in f:
        sz = os.path.getsize(os.path.join(sd, f))
        print("  {:45s} {:>6.0f} KB".format(f, sz/1024))
