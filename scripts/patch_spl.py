#!/usr/bin/env python3
"""Patch SPL to preload kernel + DTB from SPI to fixed RAM addresses"""
import subprocess, os

# Detect if running in WSL (access Linux paths directly)
if os.path.exists("/home/xlong/v3s/u-boot/arch/arm/mach-sunxi/spl_spi_sunxi.c"):
    # Running inside WSL
    UBOOT_ROOT = "/home/xlong/v3s/u-boot"
    def read_file(path):
        with open(path) as f:
            return f.read()
    def write_file(path, content):
        with open(path, "w") as f:
            f.write(content)
else:
    # Running on Windows, use wsl
    UBOOT_ROOT = "/home/xlong/v3s/u-boot"
    def read_file(path):
        return subprocess.check_output(["wsl", "bash", "-c", f"cat {path}"]).decode()
    def write_file(path, content):
        subprocess.run(["wsl", "bash", "-c", f"cat > {path}"], input=content.encode())

# Read the file
original = read_file(f"{UBOOT_ROOT}/arch/arm/mach-sunxi/spl_spi_sunxi.c")

# Find the insertion point: after U-Boot loading, before spi0_deinit
old = '\t}\n\n\tspi0_deinit();'
new = '''	}

	/* TUN_NAT_HUB: preload kernel+DTB so U-Boot can bootz without sf cmd
	 * Kernel: SPI 0x110000 -> RAM 0x41000000 (size 0x5a7888)
	 * DTB:    SPI 0x100000 -> RAM 0x42000000 (size 0x4000)
	 */
	spi0_read_data((void *)0x41000000, 0x110000, 0x5a7888);
	spi0_read_data((void *)0x42000000, 0x100000, 0x4000);

	spi0_deinit();'''

patched = original.replace(old, new)

if patched == original:
    print("ERROR: Pattern not found! Checking for variations...")
    if 'spi0_deinit()' in original:
        print("  spi0_deinit found but pattern mismatch")
        # Show context around spi0_deinit
        idx = original.index('spi0_deinit()')
        print(repr(original[idx-30:idx+30]))
    else:
        print("  spi0_deinit NOT found!")
    exit(1)

# Write back
write_file(f"{UBOOT_ROOT}/arch/arm/mach-sunxi/spl_spi_sunxi.c", patched)

print("Patch applied!")

# Verify
patched_check = read_file(f"{UBOOT_ROOT}/arch/arm/mach-sunxi/spl_spi_sunxi.c")
if "preload kernel" in patched_check:
    # Show the key lines
    for line in patched_check.split("\n"):
        if "preload" in line.lower() or "spi0_read_data" in line:
            print(line.strip())
else:
    print("WARNING: Patch may not have applied correctly")
