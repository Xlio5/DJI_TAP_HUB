#!/usr/bin/env python3
import os, re
UBOOT = "/home/xlong/v3s/u-boot/.config"
os.system("chown xlong:xlong " + UBOOT)
c = open(UBOOT).read()

cmd = (
    'if itest *0x42004000 == 0; then '
    'setenv rootpart /dev/mtdblock4; else '
    'setenv rootpart /dev/mtdblock3; fi; '
    'setenv bootargs console=ttyS0,115200 root=${rootpart} rootfstype=squashfs rootwait '
    'mtdparts=firmware:1M(uboot),64k(dtb),6M(kernel),4800k(rootfs_a),-(rootfs_b) '
    'g_serial.idVendor=0x0BDA g_serial.idProduct=0x8812 g_serial.use_acm=0; '
    'fdt addr 0x42000000; bootz 0x41000000 - 0x42000000'
)
c = re.sub(r'CONFIG_BOOTCOMMAND=.*', 'CONFIG_BOOTCOMMAND="' + cmd + '"', c)
open(UBOOT, "w").write(c)
print("itest *0x42004000: " + ("OK" if "*0x42004000" in open(UBOOT).read() else "FAIL"))
print("rootpart: " + ("OK" if "rootpart" in open(UBOOT).read() else "FAIL"))
