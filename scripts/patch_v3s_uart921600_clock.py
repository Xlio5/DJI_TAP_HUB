#!/usr/bin/env python3
from pathlib import Path


LINUX = Path("/home/xlong/v3s/linux")
BINDING = LINUX / "include/dt-bindings/clock/sun8i-v3s-ccu.h"
DTS = LINUX / "arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dts"
BASE_DTS = LINUX / "arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero.dts"


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


ensure_binding_exports()
ensure_dts_assigned_clock()
ensure_stdout_path_baud()
print("patched V3S UART 921600 APB2 clock settings")
