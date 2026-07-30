#!/usr/bin/env python3
from pathlib import Path


PROJECT = Path("/mnt/c/my_project/TUN_NAT_HUB")
IMAGE = PROJECT / "backup/spi_image.bin"

CHECKS = [
    ("SPL", 0x000000, 0x006000, Path("/tmp/v3s_verify/spl.bin")),
    ("ENV", 0x07E000, 0x002000, Path("/tmp/v3s_verify/env.bin")),
    ("DTB", 0x100000, 0x010000, Path("/tmp/v3s_verify/dtb_part.bin")),
    ("KERNEL", 0x110000, 0x5A7A18, Path("/tmp/v3s_verify/zImage.bin")),
    ("ROOTFS", 0x710000, 0x3F4000, Path("/tmp/v3s_verify/rootfs.bin")),
]


image = IMAGE.read_bytes()
for name, offset, size, readback in CHECKS:
    expected = image[offset : offset + size]
    actual = readback.read_bytes()
    match = expected == actual
    print(f"{name}: expected={len(expected)} read={len(actual)} match={match}")
    if not match:
        for index, (want, got) in enumerate(zip(expected, actual)):
            if want != got:
                start = max(0, index - 16)
                end = min(len(expected), index + 16)
                print(f"{name}: first_diff=0x{index:x}")
                print(f"{name}: expected={expected[start:end].hex()}")
                print(f"{name}: actual  ={actual[start:end].hex()}")
                break
        raise SystemExit(f"{name} readback mismatch")

print("VERIFY_OK")
