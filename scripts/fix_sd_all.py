"""SD卡完整修复 — 写 squashfs + 修 MBR。需管理员权限"""
import struct, os

DISK = r"\\.\PhysicalDrive2"
SQ_FILE = r"c:\my_project\TUN_NAT_HUB\backup\rootfs.squashfs"

# 1. Write squashfs to raw disk at p2 offset
p2_start_sector = 67584
p2_offset = p2_start_sector * 512

with open(SQ_FILE, "rb") as f:
    sq_data = f.read()

print("Writing squashfs (" + str(len(sq_data)) + " bytes) to offset " + str(p2_offset))
disk = open(DISK, "rb+")
disk.seek(p2_offset)
disk.write(sq_data)
disk.flush()

# Verify
disk.seek(p2_offset)
verify = disk.read(4)
print("Verify magic: " + verify.hex() + " - " + ("OK" if verify == b"hsqs" else "FAIL"))

# 2. Read MBR, fix p2 entry
disk.seek(0)
mbr = bytearray(disk.read(512))

p2_sector_count = 16384
p2_entry = struct.pack(
    "<BBB3sB3sII",
    0x00, b"\x00\x00\x00", b"\x00\x00\x00",
    0x83, b"\xFE\xFF\xFF",
    p2_start_sector, p2_sector_count
)
mbr[0x1CE:0x1CE+16] = p2_entry
mbr[510] = 0x55
mbr[511] = 0xAA

disk.seek(0)
disk.write(mbr)
disk.flush()
disk.close()

print("MBR updated: p2 type=83, LBA=" + str(p2_start_sector) + ", sectors=" + str(p2_sector_count))
print("Done! Insert SD card into V3s and boot.")
