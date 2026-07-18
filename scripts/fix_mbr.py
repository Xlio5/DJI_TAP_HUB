"""写 SD 卡 MBR — 添加 p2 分区条目。需管理员权限"""
import struct, os

DISK = r"\\.\PhysicalDrive2"

# Read current MBR
f = open(DISK, "rb")
mbr = bytearray(f.read(512))
f.close()

# Keep p1 entry (offset 0x1BE, 16 bytes) as-is
# Add p2 entry at offset 0x1CE
p2_start_sector = 67584  # 0x10800
p2_sector_count = 16384  # 0x4000 (8MB)

p2_entry = struct.pack(
    "<BBB3sB3sII",
    0x00,                          # boot flag (not bootable)
    0x00, 0x00, 0x00,             # CHS start (unused for LBA)
    b"\x00\x00\x00",              # CHS start bytes
    0x83,                          # partition type (Linux native)
    b"\xFE\xFF\xFF",              # CHS end
    p2_start_sector,               # LBA start (little-endian)
    p2_sector_count                # Sector count (little-endian)
)

mbr[0x1CE:0x1CE + 16] = p2_entry

# Boot signature
mbr[510] = 0x55
mbr[511] = 0xAA

# Write back
f = open(DISK, "wb")
f.write(mbr)
f.flush()
f.close()

print("MBR updated!")
print("P1: type=0C, start=2048")
print("P2: type=83, start=" + str(p2_start_sector) + ", size=" + str(p2_sector_count) + " sectors")
print("SD card ready. Insert into V3s and boot.")
