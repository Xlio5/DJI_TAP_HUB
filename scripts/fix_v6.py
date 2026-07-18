#!/usr/bin/env python3
"""Fix SPL + U-Boot for A/B OTA v6 (DTB memory slot flag)"""
import os, re

UBOOT_DIR = "/home/xlong/v3s/u-boot"

# === 1. Fix SPL ===
spl_path = f"{UBOOT_DIR}/arch/arm/mach-sunxi/spl_spi_sunxi.c"
spl = open(spl_path).read()

# Remove everything between 'TUN_NAT_HUB' (preload) and 'spi0_deinit()'
# and replace with just the slot flag read
preload_marker = "/* TUN_NAT_HUB: preload kernel+DTB"
deinit_marker = "spi0_deinit();"
preload_idx = spl.find(preload_marker)
deinit_idx = spl.find(deinit_marker, preload_idx)

# Get the preload kernel+DTB lines (keep those)
preload_block = spl[preload_idx:deinit_idx]
# Extract only the two spi0_read_data lines for kernel+DTB
kernel_read = "spi0_read_data((void *)0x41000000, 0x110000, 0x5A78B8);"
dtb_read = "spi0_read_data((void *)0x42000000, 0x100000, 0x4000);"

new_middle = f"""{preload_marker} so U-Boot can bootz without sf cmd
\t * Kernel: SPI 0x110000 -> RAM 0x41000000 (size 0x5A78B8)
\t * DTB:    SPI 0x100000 -> RAM 0x42000000 (size 0x4000)
\t */
\t{kernel_read}
\t{dtb_read}

\t/* TUN_NAT_HUB A/B OTA: read slot flag to DTB tail (U-Boot preserves) */
\tspi0_read_data((void *)0x42004000, 0xFC000, 4);

\t"""

spl = spl[:preload_idx] + new_middle + spl[deinit_idx:]
open(spl_path, "w").write(spl)
print(f"SPL: slot@0x42004000 {'OK' if '0x42004000' in open(spl_path).read() else 'FAIL'}")

# === 2. Fix U-Boot bootcmd ===
cfg_path = f"{UBOOT_DIR}/.config"
os.system(f"chown xlong:xlong {cfg_path}")
cfg = open(cfg_path).read()

bootcmd = (
    'setexpr slot *0x42004000; '
    'if test ${slot} -eq 0; then setenv rootpart /dev/mtdblock4; '
    'else setenv rootpart /dev/mtdblock3; fi; '
    'setenv bootargs console=ttyS0,115200 root=${rootpart} rootfstype=squashfs rootwait '
    'mtdparts=firmware:1M(uboot),64k(dtb),6M(kernel),4800k(rootfs_a),-(rootfs_b) '
    'g_serial.idVendor=0x0BDA g_serial.idProduct=0x8812 g_serial.use_acm=0; '
    'fdt addr 0x42000000; bootz 0x41000000 - 0x42000000'
)

cfg = re.sub(r'CONFIG_BOOTCOMMAND=.*', 'CONFIG_BOOTCOMMAND="' + bootcmd + '"', cfg)
open(cfg_path, "w").write(cfg)
print(f"UBoot: setexpr *0x42004000 {'OK' if '*0x42004000' in open(cfg_path).read() else 'FAIL'}")
print(f"UBoot: rootpart {'OK' if 'rootpart' in open(cfg_path).read() else 'FAIL'}")

print("DONE v6")
