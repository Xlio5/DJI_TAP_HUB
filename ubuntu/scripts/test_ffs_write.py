#!/usr/bin/env python3
"""Test FunctionFS ep0 descriptor write"""
import os, struct, errno

ffs = "/dev/usb-ffs/tun_nat/ep0"
fd = os.open(ffs, os.O_RDWR)
print(f"ep0 fd={fd}")

# USB descriptors
dev_desc = bytes([18,1,0,2, 0xFF,0,0,64, 0x07,0x22, 0x10,0x00, 0,1, 1,2,3,1])
cfg_desc = bytes([
    9,2, 32,0, 1,1, 0, 0x80, 0xFA,        # config
    9,4, 0,0, 2, 0xFF,0,0, 0,              # interface
    7,5, 0x01,0x02, 0,2, 0,                # ep1 OUT Bulk 512
    7,5, 0x82,0x02, 0,2, 0,                # ep2 IN Bulk 512
])

# Try V2 header first
all_desc = dev_desc + cfg_desc
total_len = 24 + len(all_desc)
# flags=1 means FUNCTIONFS_HAS_FS_DESC
hdr2 = struct.pack("<IIIIII", 3, total_len, 1, 2, 0, 0)
buf2 = hdr2 + all_desc
print(f"V2: total={total_len} hdr={len(hdr2)} desc={len(all_desc)}")
n = os.write(fd, buf2)
print(f"V2 write result: {n} (errno={errno.EINVAL if n < 0 else 'n/a'})")

if n < 0:
    # Retry with V1 format
    print("V2 failed, trying V1 format...")
    # V1: [4B LE length][descriptors][4B zero]
    buf1 = struct.pack("<I", len(all_desc)) + all_desc + struct.pack("<I", 0)
    n = os.write(fd, buf1)
    print(f"V1 write result: {n}")

if n < 0:
    print("Both formats failed, trying raw write...")
    n = os.write(fd, all_desc)
    print(f"Raw write result: {n}")
    n = os.write(fd, b"\0\0\0\0")
    print(f"Raw terminator write: {n}")

os.close(fd)
print("Done")
