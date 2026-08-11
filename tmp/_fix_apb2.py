#!/usr/bin/env python3
"""修改 sun6i APB2 时钟: PLL6/40(15MHz) -> OSC24M(24MHz), 匹配 CFG_SYS_NS16550_CLK=24M"""
import re

p = "/home/xlong/v3s/u-boot/arch/arm/mach-sunxi/clock_sun6i.c"
s = open(p).read()

old = """\t\t/* uart clock source is apb2 */
\t\t/* Use PLL6/40 (15MHz) so 921600 uses integer DLL=1. */
\t\twritel(APB2_CLK_SRC_PLL6|
\t\t       APB2_CLK_RATE_N_1|
\t\t       APB2_CLK_RATE_M(40),
\t\t       &ccm->apb2_div);"""

new = """\t\t/* uart clock source is apb2 */
\t\t/* Use OSC24M (24MHz) 与 CFG_SYS_NS16550_CLK=24MHz 匹配,
\t\t * 避免 PLL6/40(15MHz) 与驱动 24MHz 不匹配导致串口乱码。 */
\t\twritel(APB2_CLK_SRC_OSC24M|
\t\t       APB2_CLK_RATE_N_1|
\t\t       APB2_CLK_RATE_M(1),
\t\t       &ccm->apb2_div);"""

if old in s:
    s = s.replace(old, new)
    open(p, "w").write(s)
    print("OK: APB2 改为 OSC24M 24MHz")
else:
    print("FAIL: 未找到原配置")
    # 打印当前内容供排查
    for i, line in enumerate(s.splitlines(), 1):
        if "apb2_div" in line or "APB2_CLK" in line:
            print(f"{i}: {line}")
