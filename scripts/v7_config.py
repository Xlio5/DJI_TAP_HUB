#!/usr/bin/env python3
"""v7: CONFIG_CMDLINE_OVERWRITE + U-Boot no setenv + SPL patches zImage"""
import re, os

# 1. Kernel: OVERWRITE
kc = open("/home/xlong/v3s/linux/.config").read()
kc = re.sub(r"# CONFIG_CMDLINE_OVERWRITE is not set", "CONFIG_CMDLINE_OVERWRITE=y", kc)
kc = re.sub(r"CONFIG_CMDLINE_EXTEND=y", "# CONFIG_CMDLINE_EXTEND is not set", kc)
full = (
    'CONFIG_CMDLINE="console=ttyS0,115200 root=/dev/mtdblock3 rootfstype=squashfs rootwait '
    'mtdparts=firmware:1M(uboot),64k(dtb),6M(kernel),4800k(rootfs_a),-(rootfs_b) '
    'g_serial.idVendor=0x0BDA g_serial.idProduct=0x8812 g_serial.use_acm=0"'
)
kc = re.sub(r'CONFIG_CMDLINE=".*"', full, kc)
open("/home/xlong/v3s/linux/.config", "w").write(kc)
print("Kernel OVERWRITE:", "root=/dev" in open("/home/xlong/v3s/linux/.config").read())

# 2. U-Boot: remove setenv
os.system("chown xlong:xlong /home/xlong/v3s/u-boot/.config")
uc = open("/home/xlong/v3s/u-boot/.config").read()
uc = re.sub(r"CONFIG_BOOTCOMMAND=.*", 'CONFIG_BOOTCOMMAND="fdt addr 0x42000000; bootz 0x41000000 - 0x42000000"', uc)
open("/home/xlong/v3s/u-boot/.config", "w").write(uc)
print("UBoot no setenv:", "setenv" not in open("/home/xlong/v3s/u-boot/.config").read())

# 3. SPL check
spl = open("/home/xlong/v3s/u-boot/arch/arm/mach-sunxi/spl_spi_sunxi.c").read()
print("SPL patches kernel:", "kern[i+8]" in spl)
print("V7 configured")
