#!/usr/bin/env python3
"""v8 FINAL: SPL patches U-Boot binary + U-Boot bootcmd hardcodes root="""
import re, os

# ====== 1. SPL: restore U-Boot binary search+patch ======
SPL = "/home/xlong/v3s/u-boot/arch/arm/mach-sunxi/spl_spi_sunxi.c"
spl = open(SPL).read()

# Remove old memory-based slot flag read
old_mem = '/* TUN_NAT_HUB A/B OTA: read slot flag to DTB tail (U-Boot preserves) */\n\tspi0_read_data((void *)0x42004000, 0xFC000, 4);\n\n\t'
spl = spl.replace(old_mem, '')

# Insert U-Boot binary patching approach
new_code = '''/* TUN_NAT_HUB A/B OTA: read slot flag, patch U-Boot binary if B */
\t{
\t\tunsigned char flag;
\t\tspi0_read_data(&flag, 0xFC000, 1);
\t\tif (flag == 0x00) {
\t\t\t/* Slot B: change root=/dev/mtdblock3 -> mtdblock4 in U-Boot binary */
\t\t\tchar *uboot = (char *)0x42e00000;
\t\t\tfor (int i = 0; i < 0x80000; i++) {
\t\t\t\tif (uboot[i] == 'm' && uboot[i+1] == 't' && uboot[i+2] == 'd' &&
\t\t\t\t    uboot[i+3] == 'b' && uboot[i+4] == 'l' && uboot[i+5] == 'o' &&
\t\t\t\t    uboot[i+6] == 'c' && uboot[i+7] == 'k' && uboot[i+8] == '3') {
\t\t\t\t\tuboot[i+8] = '4';
\t\t\t\t\tbreak;
\t\t\t\t}
\t\t\t}
\t\t}
\t}

\t'''

spl = spl.replace('\tspi0_deinit();', new_code + '\tspi0_deinit();')
open(SPL, "w").write(spl)
print("SPL: patches U-Boot binary ✓")
print("mtdblock3 search:", "mtdblock3" in open(SPL).read() and "k[i+8]" not in open(SPL).read())


# ====== 2. U-Boot: hardcode root=/dev/mtdblock3 ======
os.system("chown xlong:xlong /home/xlong/v3s/u-boot/.config")
cfg = open("/home/xlong/v3s/u-boot/.config").read()

bootcmd = (
    'setenv bootargs console=ttyS0,115200 '
    'root=/dev/mtdblock3 rootfstype=squashfs rootwait '
    'mtdparts=firmware:1M(uboot),64k(dtb),6M(kernel),4800k(rootfs_a),-(rootfs_b) '
    'g_serial.idVendor=0x0BDA g_serial.idProduct=0x8812 g_serial.use_acm=0; '
    'fdt addr 0x42000000; bootz 0x41000000 - 0x42000000'
)
cfg = re.sub(r'CONFIG_BOOTCOMMAND=.*', 'CONFIG_BOOTCOMMAND="' + bootcmd + '"', cfg)
open("/home/xlong/v3s/u-boot/.config", "w").write(cfg)
print("UBoot: root=/dev/mtdblock3 hardcoded ✓")
print("Has root=/dev:", "root=/dev/mtdblock3" in open("/home/xlong/v3s/u-boot/.config").read())
print("No ${ } vars:", "${" not in open("/home/xlong/v3s/u-boot/.config").read())

os.system("cd /home/xlong/v3s/u-boot && rm -f spl/sunxi-spl.bin u-boot.bin")
print("Ready to build")
