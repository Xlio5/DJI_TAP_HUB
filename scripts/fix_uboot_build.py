#!/usr/bin/env python3
"""Fix U-Boot dtc/pylibfdt and build"""
import os, shutil

UBOOT = "/home/xlong/v3s/u-boot"
PYLIB = f"{UBOOT}/scripts/dtc/pylibfdt"
os.chdir(UBOOT)

# 1. Fix pylibfdt directory
os.makedirs(PYLIB, exist_ok=True)
for name in ["libfdt.i_shipped", "requirements.txt", ".gitignore"]:
    open(f"{PYLIB}/{name}", "w").close()

with open(f"{PYLIB}/Makefile", "w") as f:
    f.write("always:\n\t@:\n")

with open(f"{PYLIB}/setup.py", "w") as f:
    f.write('from setuptools import setup\nsetup(name="libfdt")\n')

os.system(f"chown -R xlong:xlong {PYLIB}")
print("pylibfdt fixed")

# 2. Build U-Boot
print("Building U-Boot...")
os.system("chown -R xlong:xlong . 2>/dev/null")
rc = os.system("make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j20 2>&1")
print(f"Build exit: {rc}")

if os.path.exists("spl/sunxi-spl.bin"):
    print(f"SPL: {os.path.getsize('spl/sunxi-spl.bin')} bytes")
    print(f"UBoot: {os.path.getsize('u-boot.bin')} bytes")
    # Copy to project
    shutil.copy("spl/sunxi-spl.bin", "/mnt/c/my_project/TUN_NAT_HUB/backup/")
    shutil.copy("u-boot.bin", "/mnt/c/my_project/TUN_NAT_HUB/backup/")
    print("Copied to backup")
else:
    print("BUILD FAILED!")
    exit(1)
