#!/usr/bin/env python3
"""校验 SC16IS752 DTB 节点地址与时钟配置。"""

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DTB = ROOT / "backup" / "sun8i-v3s-licheepi-zero-dock-sc16.dtb"


def decompile_dtb(dtb: Path) -> str:
    if not dtb.exists():
        raise SystemExit(f"DTB not found: {dtb}")

    cmd = ["dtc", "-I", "dtb", "-O", "dts", str(dtb)]
    if sys.platform.startswith("win"):
        cmd = [
            "wsl.exe",
            "-d",
            "Ubuntu-20.04",
            "--",
            "dtc",
            "-I",
            "dtb",
            "-O",
            "dts",
            _to_wsl_path(dtb),
        ]
    return subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT)


def _to_wsl_path(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    rest = resolved.as_posix().split(":", 1)[1]
    return f"/mnt/{drive}{rest}"


def main() -> int:
    dtb = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DTB
    dts = decompile_dtb(dtb)
    block_match = None
    for match in re.finditer(r"serial@([0-9a-f]+)\s*\{(?P<body>.*?)\n\s*\};", dts, re.S):
        if 'compatible = "nxp,sc16is752";' in match.group("body"):
            block_match = match
            break
    if block_match is None:
        print("FAIL: SC16 serial node not found")
        return 1

    node_addr = block_match.group(1)
    body = block_match.group("body")
    checks = {
        "node serial@4d": node_addr == "4d",
        "compatible nxp,sc16is752": 'compatible = "nxp,sc16is752";' in body,
        "reg 0x4d": re.search(r"reg = <0x4d>;", body) is not None,
        "clock 14745600": re.search(r"clock-frequency = <0xe10000>;", body) is not None,
        "old serial@48 absent": "serial@48" not in dts,
        "old reg 0x48 absent": re.search(r"reg = <0x48>;", body) is None,
    }

    failed = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"{'OK' if ok else 'FAIL'}: {name}")
    if failed:
        print("SC16 DTB verification failed")
        return 1
    print("SC16 DTB verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
