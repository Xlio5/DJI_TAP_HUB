#!/usr/bin/env python3
from pathlib import Path


LINUX = Path("/home/xlong/v3s/linux")
UBOOT = Path("/home/xlong/v3s/u-boot")
BINDING = LINUX / "include/dt-bindings/clock/sun8i-v3s-ccu.h"
DTS = LINUX / "arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dts"
BASE_DTS = LINUX / "arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero.dts"
CCU = LINUX / "drivers/clk/sunxi-ng/ccu-sun8i-v3s.c"
UBOOT_CLOCK = UBOOT / "arch/arm/mach-sunxi/clock_sun6i.c"


def ensure_binding_exports() -> None:
    text = BINDING.read_text()
    if "CLK_PLL_PERIPH0" not in text:
        text = text.replace(
            "#define CLK_CPU\t\t\t14\n",
            "#define CLK_PLL_PERIPH0\t\t9\n"
            "#define CLK_CPU\t\t\t14\n",
        )
    if "CLK_APB2" not in text:
        text = text.replace(
            "#define CLK_CPU\t\t\t14\n",
            "#define CLK_CPU\t\t\t14\n"
            "#define CLK_APB2\t\t18\n",
        )
    BINDING.write_text(text)


def ensure_dts_assigned_clock() -> None:
    text = DTS.read_text()
    marker = "assigned-clock-rates = <22222222>;"
    if marker in text:
        return

    compatible = (
        '\tcompatible = "licheepi,licheepi-zero-dock", "licheepi,licheepi-zero",\n'
        '\t\t     "allwinner,sun8i-v3s";\n'
    )
    assigned = (
        compatible
        +
        "\n"
        "\t/* APB2: 22.222MHz lets DW UART 2-bit DLF generate 921600 within 0.5%. */\n"
        "\tassigned-clocks = <&ccu CLK_APB2>;\n"
        "\tassigned-clock-parents = <&ccu CLK_PLL_PERIPH0>;\n"
        "\tassigned-clock-rates = <22222222>;\n"
    )
    if compatible not in text:
        raise SystemExit("compatible block not found in dock DTS")
    DTS.write_text(text.replace(compatible, assigned, 1))


def ensure_stdout_path_baud() -> None:
    text = BASE_DTS.read_text()
    text = text.replace("serial0:115200n8", "serial0:921600n8")
    BASE_DTS.write_text(text)


def ensure_ccu_apb2_default() -> None:
    text = CCU.read_text()
    marker = "SUN8I_V3S_APB2_UART_921600_REG"
    if marker not in text:
        text = text.replace(
            '#define SUN8I_V3S_PLL_AUDIO_REG\t0x008\n',
            '#define SUN8I_V3S_PLL_AUDIO_REG\t0x008\n'
            '#define SUN8I_V3S_APB2_REG\t\t0x058\n'
            '/* pll-periph0 / 27 ~= 22.222MHz for accurate 921600 with 2-bit UART DLF. */\n'
            '#define SUN8I_V3S_APB2_UART_921600_REG\t0x0200001a\n',
            1,
        )

    needle = "\tval = readl(reg + SUN8I_V3S_PLL_AUDIO_REG);\n"
    insert = (
        "\t/* Keep APB2/UART clock tree consistent before serial ports probe. */\n"
        "\twritel(SUN8I_V3S_APB2_UART_921600_REG, reg + SUN8I_V3S_APB2_REG);\n\n"
        "\tval = readl(reg + SUN8I_V3S_PLL_AUDIO_REG);\n"
    )
    if "Keep APB2/UART clock tree consistent" not in text:
        if needle not in text:
            raise SystemExit("CCU probe insertion point not found")
        text = text.replace(needle, insert, 1)

    CCU.write_text(text)


def ensure_uboot_apb2_default() -> None:
    text = UBOOT_CLOCK.read_text()
    old = (
        "\t\twritel(APB2_CLK_SRC_OSC24M|\n"
        "\t\t       APB2_CLK_RATE_N_1|\n"
        "\t\t       APB2_CLK_RATE_M(1),\n"
        "\t\t       &ccm->apb2_div);\n"
    )
    new = (
        "\t\t/* Use PLL6/27 (~22.222MHz) so 921600 console is accurate. */\n"
        "\t\twritel(APB2_CLK_SRC_PLL6|\n"
        "\t\t       APB2_CLK_RATE_N_1|\n"
        "\t\t       APB2_CLK_RATE_M(27),\n"
        "\t\t       &ccm->apb2_div);\n"
    )
    if new in text:
        return
    if old not in text:
        raise SystemExit("U-Boot APB2 clock init block not found")
    UBOOT_CLOCK.write_text(text.replace(old, new, 1))


ensure_binding_exports()
ensure_dts_assigned_clock()
ensure_stdout_path_baud()
ensure_ccu_apb2_default()
ensure_uboot_apb2_default()
print("patched V3S UART 921600 APB2 clock settings")
