#!/bin/bash
set -e
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
PROJECT=/mnt/c/my_project/TUN_NAT_HUB
NCPU=20

echo "============================================"
echo "  OTA FINAL BUILD (SPL NOR write + panic=5)"
echo "============================================"

# ============================================
# 1. U-Boot bootcmd: add panic=5
# ============================================
echo ""
echo "=== [1/5] U-Boot bootcmd (panic=5) ==="
cd /home/xlong/v3s/u-boot
chown -R xlong:xlong . 2>/dev/null || true

python3 -c "
import re
c = open('.config').read()
# Add panic=5 before root=
c = c.replace('root=/dev/mtdblock3', 'panic=5 root=/dev/mtdblock3')
open('.config','w').write(c)
print('panic=5:', 'panic=5' in open('.config').read())
"

# ============================================
# 2. SPL: add spi0_write + retry logic
# ============================================
echo ""
echo "=== [2/5] SPL NOR write + retry ==="
python3 -c "
import re
path = '/home/xlong/v3s/u-boot/arch/arm/mach-sunxi/spl_spi_sunxi.c'
c = open(path).read()

# Add SPI write function before the existing A/B code
write_func = '''
/* TUN_NAT_HUB: SPI NOR write via sun6i registers */
static void sunxi_spi0_write_cmd(u32 len, const u8 *cmd)
{
	uintptr_t base = 0x01C68000; /* V3s SPI0 */
	writel(len, base + 0x30); /* MBC */
	writel(len, base + 0x34); /* MTC */
	writel(len, base + 0x38); /* BCC */
	for (u32 i = 0; i < len; i++)
		writeb(cmd[i], base + 0x18); /* TXD */
	setbits_le32(base + 0x10, 1 << 31); /* TCR XCH */
	while ((readl(base + 0x1C) & 0x7F) < len); /* FIFO_STA wait */
	udelay(1);
}

static u8 sunxi_spi0_read_status(void)
{
	u8 cmd = 0x05; /* RDSR */
	u8 status = 0;
	uintptr_t base = 0x01C68000;
	writel(1, base + 0x30); writel(1, base + 0x34); writel(1, base + 0x38);
	writeb(cmd, base + 0x18);
	setbits_le32(base + 0x10, 1 << 31);
	while ((readl(base + 0x1C) & 0x7F) < 2);
	readl(base + 0x1C); /* discard cmd echo */
	status = readb(base + 0x1C);
	udelay(1);
	return status;
}

static void spi0_write_byte(u32 addr, u8 data)
{
	uintptr_t base = 0x01C68000;
	u8 cmd[6];
	/* Write Enable */
	cmd[0] = 0x06;
	sunxi_spi0_write_cmd(1, cmd);
	/* Page Program */
	cmd[0] = 0x02;
	cmd[1] = (u8)(addr >> 16);
	cmd[2] = (u8)(addr >> 8);
	cmd[3] = (u8)(addr);
	cmd[4] = data;
	sunxi_spi0_write_cmd(5, cmd);
	/* Wait WIP clear */
	while (sunxi_spi0_read_status() & 0x01);
}
'''

# Insert before spi0_deinit but after A/B code
insert_before = 'spi0_deinit();'
c = c.replace(insert_before, write_func + '\n\t' + insert_before)

# Update A/B retry logic: check retry and auto-fallback
old_ab = '''/* TUN_NAT_HUB A/B OTA: read slot flag, patch U-Boot binary if B */
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
\t}'''

new_ab = '''/* TUN_NAT_HUB A/B OTA v9: read slot/confirmed/retry, auto-fallback on failure */
\t{
\t\tunsigned char flag, confirmed, retry;
\t\tspi0_read_data(&flag, 0xFC000, 1);
\t\tspi0_read_data(&confirmed, 0xFC004, 1);
\t\tspi0_read_data(&retry, 0xFC005, 1);

\t\t/* Auto-fallback: if trial mode and retries left, decrement */
\t\tif (confirmed == 0x00 && retry > 0) {
\t\t\tretry--;
\t\t\tspi0_write_byte(0xFC005, retry);
\t\t\tif (retry == 0) {
\t\t\t\t/* All retries exhausted, fallback to other slot */
\t\t\t\tflag = (flag == 0xFF) ? 0x00 : 0xFF;
\t\t\t\tspi0_write_byte(0xFC000, flag);
\t\t\t\tspi0_write_byte(0xFC004, 0xFF); /* mark confirmed */
\t\t\t}
\t\t}

\t\t/* Slot B: patch U-Boot root= string */
\t\tif (flag == 0x00) {
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
\t}'''

c = c.replace(old_ab, new_ab)
open(path, 'w').write(c)
print('SPL write+retry: OK')
print('has spi0_write_byte:', 'spi0_write_byte' in open(path).read())
print('has auto-fallback:', 'retry == 0' in open(path).read())
"

# ============================================
# 3. Build U-Boot
# ============================================
echo ""
echo "=== [3/5] U-Boot clean + build ==="
cd /home/xlong/v3s/u-boot
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- clean 2>&1 | tail -3
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j$NCPU 2>&1 | tail -5
cp spl/sunxi-spl.bin u-boot.bin $PROJECT/backup/
echo "U-Boot done: SPL=$(stat -c%s spl/sunxi-spl.bin) UBoot=$(stat -c%s u-boot.bin)"
strings u-boot.bin | grep -o "panic=5\|root=/dev/mtdblock3" | head -3

# ============================================
# 4. Build Kernel
# ============================================
echo ""
echo "=== [4/5] Kernel clean + build ==="
cd /home/xlong/v3s/linux
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- clean 2>&1 | tail -3
sed -i 's/CONFIG_USB_G_SERIAL=m/CONFIG_USB_G_SERIAL=y/' .config
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j$NCPU zImage dtbs 2>&1 | tail -5
cp arch/arm/boot/zImage $PROJECT/backup/zImage_new
cp arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb $PROJECT/backup/sun8i-v3s-licheepi-zero-dock.dtb_new
echo "Kernel done: $(stat -c%s $PROJECT/backup/zImage_new) bytes"

# ============================================
# 5. Build rootfs (skip Buildroot make, direct compile)
# ============================================
echo ""
echo "=== [5/5] Build rootfs ==="

echo "--- Compile web_server with upgrade logging ---"
# Add logging to web_server before compiling
python3 -c "
import re
ws = open('$PROJECT/ubuntu/src/web_server.cpp').read()
# Add logging in upgrade function - find dd command and add cout before/after
old_dd = 'std::cout << \"[fw] current slot: \" << (runningOnB ? \"B\" : \"A\")'
new_dd = 'std::cout << \"[fw] START upgrade, target: \" << inactiveDev << std::endl; std::cout << \"[fw] current slot: \" << (runningOnB ? \"B\" : \"A\")'
ws = ws.replace(old_dd, new_dd)

# Add log after dd success
old_success = 'sync();' + '\n\t' + '}'  # end of slot write block
new_log = 'std::cout << \"[fw] slot flag written to /dev/mtdblock0\" << std::endl;' + '\n\t\t' + 'sync();'
ws = ws.replace('sync();', new_log)

open('$PROJECT/ubuntu/src/web_server.cpp','w').write(ws)
print('web_server logging added')
"

cd /home/xlong/v3s/buildroot-2024.02
TGT=output/target
arm-linux-gnueabihf-g++ -std=c++17 -Os -o $TGT/usr/local/bin/web_server $PROJECT/ubuntu/src/web_server.cpp -lpthread 2>&1 | tail -2
chmod +x $TGT/usr/local/bin/web_server
echo "web_server: $(stat -c%s $TGT/usr/local/bin/web_server) bytes"

# Copy init scripts
cp $PROJECT/ubuntu/scripts/S99tun_nat_hub $TGT/etc/init.d/
cp $PROJECT/ubuntu/scripts/setup_v3s_fixed.sh $TGT/usr/local/bin/setup_v3s.sh
chmod +x $TGT/etc/init.d/S99tun_nat_hub $TGT/usr/local/bin/setup_v3s.sh

# Build squashfs
rm -f output/images/rootfs.squashfs
mksquashfs output/target output/images/rootfs.squashfs -comp xz -b 1048576 -Xdict-size 1048576 -noappend 2>&1 | tail -3

# Add 12-byte verification tail to rootfs
echo -n "TUN_NAT_HUB" > /tmp/tail.bin
python3 -c "
import struct, zlib
data = open('/home/xlong/v3s/buildroot-2024.02/output/images/rootfs.squashfs','rb').read()
crc = zlib.crc32(data) & 0xFFFFFFFF
tail = b'TUN_NAT_HUB' + struct.pack('<I', crc)
with open('/home/xlong/v3s/buildroot-2024.02/output/images/rootfs.squashfs','ab') as f:
    f.write(tail)
print('Tail appended: TUN_NAT_HUB + CRC32=0x%08X' % crc)
"

cp output/images/rootfs.squashfs $PROJECT/backup/rootfs.squashfs
echo "rootfs: $(stat -c%s $PROJECT/backup/rootfs.squashfs) bytes (with 12B tail)"

# ============================================
# 6. Build SPI image + FEL flash
# ============================================
echo ""
echo "=== Build SPI image ==="
cd $PROJECT
python3 -B scripts/build_spi_final.py 2>&1 | tail -8

echo ""
echo "=== FEL flash ==="
sunxi-fel list 2>&1 || { echo "FEL not found - needs manual trigger"; exit 1; }
sunxi-fel spiflash-write 0 backup/spi_image.bin 2>&1
echo "FEL exit=$?"
sunxi-fel spiflash-read 0 32 /tmp/vFinal.bin 2>&1
hexdump -C /tmp/vFinal.bin
sunxi-fel spiflash-read 0xFC000 8 /tmp/vFinalCtl.bin 2>&1
hexdump -C /tmp/vFinalCtl.bin

echo ""
echo "============================================"
echo "  BUILD COMPLETE"
echo "============================================"
echo "SPL:     $(stat -c%s $PROJECT/backup/sunxi-spl.bin) bytes"
echo "U-Boot:  $(stat -c%s $PROJECT/backup/u-boot.bin) bytes"
echo "zImage:  $(stat -c%s $PROJECT/backup/zImage_new) bytes"
echo "rootfs:  $(stat -c%s $PROJECT/backup/rootfs.squashfs) bytes"
echo "SPI img: $(stat -c%s $PROJECT/backup/spi_image.bin) bytes"
