#!/usr/bin/env python3
"""精确替换 WSL U-Boot .config 的 CONFIG_BOOTCOMMAND 为 PB6 检测版 (115200/console=null)"""
import re

path = "/home/xlong/v3s/u-boot/.config"

bootargs_then = ("setenv bootargs console=ttyS0,115200 panic=5 sunxi_wdt.nowayout=1 "
                 "root=/dev/mtdblock3 rootfstype=squashfs rootwait "
                 "mtdparts=firmware:1M(uboot),64k(dtb),6M(kernel),4576k(rootfs_a),-(rootfs_b) "
                 "g_serial.idVendor=0x0BDA g_serial.idProduct=0x8812 g_serial.use_acm=0")
bootargs_else = ("setenv bootargs console=null panic=5 sunxi_wdt.nowayout=1 "
                 "root=/dev/mtdblock3 rootfstype=squashfs rootwait "
                 "mtdparts=firmware:1M(uboot),64k(dtb),6M(kernel),4576k(rootfs_a),-(rootfs_b) "
                 "g_serial.idVendor=0x0BDA g_serial.idProduct=0x8812 g_serial.use_acm=0")

new_line = ('CONFIG_BOOTCOMMAND="if gpio input PB6; then ' + bootargs_then +
            '; else ' + bootargs_else +
            '; fi; fdt addr 0x42000000; bootz 0x41000000 - 0x42000000"')

s = open(path, encoding="utf-8").read()
s2, n = re.subn(r'^CONFIG_BOOTCOMMAND=.*$', new_line, s, count=1, flags=re.M)
assert n == 1, f"CONFIG_BOOTCOMMAND 替换失败 (n={n})"
open(path, "w", encoding="utf-8").write(s2)
print("已替换 CONFIG_BOOTCOMMAND 为 PB6 检测版")
