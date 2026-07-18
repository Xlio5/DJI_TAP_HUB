#!/usr/bin/env python3
import os
UBOOT = "/home/xlong/v3s/u-boot/.config"
os.system("chown xlong:xlong " + UBOOT)
c = open(UBOOT).read()
c = c.replace("setexpr slot", "setenv rootpart /dev/mtdblock3; setexpr slot")
open(UBOOT, "w").write(c)
print("Fixed - default rootpart=mtdblock3")
