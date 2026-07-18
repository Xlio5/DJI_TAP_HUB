#!/bin/bash
set -e
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
cd /home/xlong/v3s/u-boot

# Bootcmd: SPL already preloaded kernel+DTB to RAM, just boot
# Uses \x0a for newline, \x3b for semicolon in the config string
BOOTCMD='fdt addr 0x42000000;\x0asetenv bootargs console=ttyS0,115200 root=/dev/mtdblock3 rootfstype=squashfs rootwait mtdparts=firmware:1M(uboot),64k(dtb),6M(kernel),-(rootfs) g_serial.idVendor=0x0BDA g_serial.idProduct=0x8812 g_serial.use_acm=0;\x0abootz 0x41000000 - 0x42000000'

echo "=== Current bootcmd ==="
grep CONFIG_BOOTCOMMAND .config

# Use python to do the replacement (sed escaping is too painful)
python3 -c "
import re
with open('.config', 'r') as f:
    c = f.read()
new_cmd = 'fdt addr 0x42000000;\\\\x0asetenv bootargs console=ttyS0,115200 root=/dev/mtdblock3 rootfstype=squashfs rootwait mtdparts=firmware:1M(uboot),64k(dtb),6M(kernel),-(rootfs) g_serial.idVendor=0x0BDA g_serial.idProduct=0x8812 g_serial.use_acm=0;\\\\x0abootz 0x41000000 - 0x42000000'
c = re.sub(r'CONFIG_BOOTCOMMAND=.*', 'CONFIG_BOOTCOMMAND=' + chr(34) + new_cmd + chr(34), c)
with open('.config', 'w') as f:
    f.write(c)
print('Done')
"

echo "=== After ==="
grep CONFIG_BOOTCOMMAND .config

echo ""
echo "=== olddefconfig ==="
make olddefconfig 2>&1 | tail -3

echo "=== After olddefconfig ==="
grep CONFIG_BOOTCOMMAND .config

echo ""
echo "=== If still wrong, force via include/config ==="
# As a backup: also set via CONFIG_EXTRA_ENV_SETTINGS which won't get overwritten
if ! grep -q "bootz 0x41000000" .config; then
  echo "Adding to EXTRA_ENV_SETTINGS..."
  sed -i 's|CONFIG_EXTRA_ENV_SETTINGS=.*|CONFIG_EXTRA_ENV_SETTINGS="bootcmd=fdt addr 0x42000000; setenv bootargs console=ttyS0,115200 root=/dev/mtdblock3 rootfstype=squashfs rootwait mtdparts=firmware:1M(uboot),64k(dtb),6M(kernel),-(rootfs) g_serial.idVendor=0x0BDA g_serial.idProduct=0x8812 g_serial.use_acm=0; bootz 0x41000000 - 0x42000000"|' .config
  make olddefconfig 2>&1 | tail -3
  grep -E 'CONFIG_BOOTCOMMAND|CONFIG_EXTRA_ENV' .config
fi

echo ""
echo "=== Rebuilding ==="
rm -f u-boot.bin spl/sunxi-spl.bin
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j$(nproc) 2>&1 | tail -5
echo "Done"

echo ""
echo "=== Verify in binary ==="
strings u-boot.bin | grep "bootz 0x41000000" | head -3

ls -lh spl/sunxi-spl.bin u-boot.bin

# Copy
cat spl/sunxi-spl.bin > /tmp/uboot_combined.bin
cat u-boot.bin >> /tmp/uboot_combined.bin
cp spl/sunxi-spl.bin u-boot.bin /tmp/uboot_combined.bin /mnt/c/my_project/TUN_NAT_HUB/backup/
echo "Copied to backup"
