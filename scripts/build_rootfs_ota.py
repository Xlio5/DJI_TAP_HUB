#!/usr/bin/env python3
"""Build rootfs with web_server logging + 12B verification tail"""
import os, shutil, zlib, struct

PROJECT = "/mnt/c/my_project/TUN_NAT_HUB"
TGT = "/home/xlong/v3s/buildroot-2024.02/output/target"
CPP = f"{PROJECT}/ubuntu/src/web_server.cpp"

# 1. Add logging to web_server source BEFORE compilation
ws_src = open(CPP).read()

# Add log after inactiveDev assignment
old = 'std::cout << "[fw] current slot: " << (runningOnB ? "B" : "A")'
new = ('std::cout << "[fw] UPGRADE START: target=" << inactiveDev << ", size=" << contentLen << std::endl;'
       '\n\t' + old)
if old in ws_src:
    ws_src = ws_src.replace(old, new)
    print("Added upgrade start log")

# Add log after dd success
old2 = 'std::string flashCmd = "dd if=" + tmpPath + " of=" + inactiveDev + " bs=4096 2>&1";'
new2 = ('std::cout << "[fw] dd " << tmpPath << " -> " << inactiveDev << std::endl;'
        '\n\t' + old2)
if old2 in ws_src:
    ws_src = ws_src.replace(old2, new2)
    print("Added dd log")

# Add log after slot write
old3 = '::close(slotFd);\n\t\tsync();'
new3 = ('::close(slotFd);'
        '\n\t\tstd::cout << "[fw] slot flag + confirmed/retry written" << std::endl;'
        '\n\t\tsync();')
if old3 in ws_src:
    ws_src = ws_src.replace(old3, new3)
    print("Added slot write log")

open(CPP, "w").write(ws_src)

# 2. Compile web_server
print("Compiling web_server...")
os.system(f"arm-linux-gnueabihf-g++ -std=c++17 -Os -o {TGT}/usr/local/bin/web_server {CPP} -lpthread 2>&1 | tail -2")
os.chmod(f"{TGT}/usr/local/bin/web_server", 0o755)
print(f"web_server: {os.path.getsize(f'{TGT}/usr/local/bin/web_server')} bytes")

# 3. Copy init scripts
for src, dst in [
    (f"{PROJECT}/ubuntu/scripts/S99tun_nat_hub", f"{TGT}/etc/init.d/"),
    (f"{PROJECT}/ubuntu/scripts/setup_v3s_fixed.sh", f"{TGT}/usr/local/bin/setup_v3s.sh"),
]:
    shutil.copy(src, dst)
    os.chmod(dst, 0o755)

# 4. Build squashfs
print("Building squashfs...")
os.chdir("/home/xlong/v3s/buildroot-2024.02")
os.system("mksquashfs output/target /tmp/rootfs_tmp.sq -comp xz -b 1048576 -Xdict-size 1048576 -noappend 2>&1 | tail -3")

# 5. Append 12B verification tail (TUN_NAT_HUB + CRC32)
with open("/tmp/rootfs_tmp.sq", "rb") as f:
    data = f.read()
crc = zlib.crc32(data) & 0xFFFFFFFF
tail = b"TUN_NAT_HUB" + struct.pack("<I", crc)
with open(f"{PROJECT}/backup/rootfs.squashfs", "wb") as f:
    f.write(data + tail)
print(f"rootfs: {os.path.getsize(f'{PROJECT}/backup/rootfs.squashfs')} bytes (tail=12B, CRC=0x{crc:08X})")

# 6. Also build SPI image
print("Building SPI image...")
os.chdir(PROJECT)
os.system("python3 -B scripts/build_spi_final.py 2>&1 | tail -6")
print(f"spi_image: {os.path.getsize(f'{PROJECT}/backup/spi_image.bin')} bytes")

print("DONE - rootfs + SPI image ready")
