#!/usr/bin/env python3
"""Fix SPL: add NOR write + retry logic PROPERLY"""
import sys

SPL_PATH = "/home/xlong/v3s/u-boot/arch/arm/mach-sunxi/spl_spi_sunxi.c"
spl = open(SPL_PATH).read()

# === 1. Add forward declaration before the A/B code ===
fwd_decl = "static void spi0_write_byte(u32 addr, u8 data);\n\n"
insert_at = spl.find("/* TUN_NAT_HUB A/B OTA v9")
if insert_at < 0:
    print("ERROR: cannot find A/B OTA marker")
    sys.exit(1)
spl = spl[:insert_at] + fwd_decl + spl[insert_at:]

# === 2. Remove BROKEN embedded write functions from A/B block ===
# The broken code was embedded inside the braces. Remove it.
# Find the end of the A/B block (closing brace before spi0_deinit)
ab_start = spl.find("/* TUN_NAT_HUB A/B OTA v9")
deinit_marker = "spi0_deinit();"
deinit_pos = spl.find(deinit_marker, ab_start)

# Everything between ab_start and deinit_pos is the A/B logic
# Check if broken functions leaked in
broken = "static void sunxi_spi0_write_cmd"
if broken in spl:
    # Find where broken code starts and ends
    broken_start = spl.find(broken)
    broken_end = spl.find(deinit_marker, broken_start)
    if broken_end > 0:
        # Remove broken code
        spl = spl[:broken_start] + spl[broken_end:]
        print("Removed broken embedded functions")

# === 3. Add CORRECT write functions BEFORE spi0_deinit() ===
deinit_pos = spl.find(deinit_marker)
if deinit_pos < 0:
    print("ERROR: cannot find spi0_deinit()")
    sys.exit(1)

write_functions = """/* TUN_NAT_HUB: SPI NOR write support for retry counter */
static void sunxi_spi0_write_cmd(u32 len, const u8 *cmd)
{
\tuintptr_t base = 0x01C68000;
\twritel(len, base + 0x30);
\twritel(len, base + 0x34);
\twritel(len, base + 0x38);
\tfor (u32 i = 0; i < len; i++)
\t\twriteb(cmd[i], base + 0x18);
\tsetbits_le32(base + 0x10, 1 << 31);
\twhile ((readl(base + 0x1C) & 0x7F) < len);
\tudelay(1);
}

static u8 sunxi_spi0_read_status(void)
{
\tu8 cmd = 0x05, status = 0;
\tuintptr_t base = 0x01C68000;
\twritel(1, base + 0x30);
\twritel(1, base + 0x34);
\twritel(1, base + 0x38);
\twriteb(cmd, base + 0x18);
\tsetbits_le32(base + 0x10, 1 << 31);
\twhile ((readl(base + 0x1C) & 0x7F) < 2);
\treadl(base + 0x1C);
\tstatus = readb(base + 0x1C);
\tudelay(1);
\treturn status;
}

static void spi0_write_byte(u32 addr, u8 data)
{
\tu8 cmd[6] = {0x06, 0x02, 0, 0, 0, 0};
\tcmd[2] = (u8)(addr >> 16);
\tcmd[3] = (u8)(addr >> 8);
\tcmd[4] = (u8)(addr);
\tcmd[5] = data;
\tsunxi_spi0_write_cmd(1, cmd);  /* Write Enable */
\tsunxi_spi0_write_cmd(5, cmd+1); /* Page Program */
\twhile (sunxi_spi0_read_status() & 0x01); /* Wait WIP */
}

"""

spl = spl[:deinit_pos] + write_functions + spl[deinit_pos:]

open(SPL_PATH, "w").write(spl)

# Verify
c = open(SPL_PATH).read()
print("Forward decl:", "static void spi0_write_byte(u32 addr, u8 data);" in c)
print("write_cmd:", "sunxi_spi0_write_cmd" in c)
print("read_status:", "sunxi_spi0_read_status" in c)
print("spi0_write_byte:", "spi0_write_byte(u32" in c)
print("auto-fallback:", "retry == 0" in c)
print("spi0_deinit after write:", c.find("spi0_write_byte") < c.find("spi0_deinit();", c.find("spi0_write_byte")))
print("DONE")
