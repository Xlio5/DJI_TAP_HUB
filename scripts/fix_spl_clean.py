#!/usr/bin/env python3
"""Complete rewrite of SPL A/B+write section — clean structure"""
import sys

path = "/home/xlong/v3s/u-boot/arch/arm/mach-sunxi/spl_spi_sunxi.c"
spl = open(path).read()

# 1. REMOVE all TUN_NAT_HUB code between kernel preload and SPL_LOAD_IMAGE_METHOD
preload = "/* TUN_NAT_HUB: preload kernel+DTB"
end_marker = "SPL_LOAD_IMAGE_METHOD"
preload_idx = spl.find(preload)
end_idx = spl.find(end_marker)
if preload_idx < 0 or end_idx < 0:
    print("ERROR: markers not found")
    sys.exit(1)

# 2. Build clean replacement section
replace = """/* TUN_NAT_HUB: preload kernel+DTB so U-Boot can bootz without sf cmd
\t * Kernel: SPI 0x110000 -> RAM 0x41000000 (size 0x5A78B8)
\t * DTB:    SPI 0x100000 -> RAM 0x42000000 (size 0x4000)
\t */
\tspi0_read_data((void *)0x41000000, 0x110000, 0x5A78B8);
\tspi0_read_data((void *)0x42000000, 0x100000, 0x4000);

\t/* TUN_NAT_HUB A/B OTA: slot + auto-fallback */
\t{
\t\tunsigned char flag, confirmed, retry;
\t\tspi0_read_data(&flag, 0xFC000, 1);
\t\tspi0_read_data(&confirmed, 0xFC004, 1);
\t\tspi0_read_data(&retry, 0xFC005, 1);

\t\t/* Auto-fallback: if trial mode, decrement retry count */
\t\tif (confirmed == 0x00 && retry > 0) {
\t\t\tretry--;
\t\t\tspi0_write_byte(0xFC005, retry);
\t\t\tif (retry == 0) {
\t\t\t\t/* All retries exhausted, switch back to other slot */
\t\t\t\tflag = (flag == 0xFF) ? 0x00 : 0xFF;
\t\t\t\tspi0_write_byte(0xFC000, flag);
\t\t\t\tspi0_write_byte(0xFC004, 0xFF); /* mark confirmed */
\t\t\t}
\t\t}

\t\t/* Slot B: change root=/dev/mtdblock3 -> mtdblock4 in U-Boot binary */
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
\t}

\tspi0_deinit();

\treturn ret;
}

/* TUN_NAT_HUB: SPI NOR write functions for retry counter persistence */

static void spi0_write_enable(void)
{
\tu8 cmd = 0x06;
\tuintptr_t base = 0x01C68000;
\twritel(1, base + 0x30); writel(1, base + 0x34); writel(1, base + 0x38);
\twriteb(cmd, base + 0x18);
\tsetbits_le32(base + 0x10, 1 << 31);
\twhile ((readl(base + 0x1C) & 0x7F) < 1);
\tudelay(1);
}

static u8 spi0_read_sr(void)
{
\tuintptr_t base = 0x01C68000;
\tu8 cmd = 0x05;
\twritel(1, base + 0x30); writel(1, base + 0x34); writel(1, base + 0x38);
\twriteb(cmd, base + 0x18);
\tsetbits_le32(base + 0x10, 1 << 31);
\twhile ((readl(base + 0x1C) & 0x7F) < 2);
\treadl(base + 0x1C);
\treturn readb(base + 0x1C);
}

static void spi0_write_byte(u32 addr, u8 data)
{
\tu8 pp_cmd[5] = {0x02, 0, 0, 0, 0};
\tuintptr_t base = 0x01C68000;

\t/* Write Enable */
\tspi0_write_enable();

\t/* Page Program */
\tpp_cmd[1] = (u8)(addr >> 16);
\tpp_cmd[2] = (u8)(addr >> 8);
\tpp_cmd[3] = (u8)(addr);
\tpp_cmd[4] = data;
\twritel(5, base + 0x30); writel(5, base + 0x34); writel(5, base + 0x38);
\tfor (int i = 0; i < 5; i++)
\t\twriteb(pp_cmd[i], base + 0x18);
\tsetbits_le32(base + 0x10, 1 << 31);
\twhile ((readl(base + 0x1C) & 0x7F) < 5);
\tudelay(1);

\t/* Wait for write complete */
\twhile (spi0_read_sr() & 0x01);
}

"""

spl = spl[:preload_idx] + replace + spl[end_idx:]
open(path, "w").write(spl)

# Verify
c = open(path).read()
checks = [
    ("preload kernel", "preload kernel" in c),
    ("spi0_write_byte", "spi0_write_byte" in c),
    ("spi0_write_enable", "spi0_write_enable" in c),
    ("spi0_read_sr", "spi0_read_sr" in c),
    ("auto-fallback", "retry == 0" in c),
    ("SPL_LOAD_IMAGE_METHOD", "SPL_LOAD_IMAGE_METHOD" in c),
    ("spi0_deinit only once", c.count("spi0_deinit();") == 2),  # def+call
]
for name, ok in checks:
    print(f"  {name}: {'OK' if ok else 'FAIL'}")
print("DONE")
