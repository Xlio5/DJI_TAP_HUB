# FEL Fast Flash Method

This project has three firmware update paths. Pick the smallest path that matches the change.

| Change type | Preferred path | Why |
| --- | --- | --- |
| Android APK only | APK install or app release script | No V3s flash write is needed. |
| `S99tun_nat_hub`, `dji_rc`, `web_server`, user-space scripts | OTA if the board boots, otherwise rootfs-only FEL | These files live in squashfs rootfs. Rewriting SPL/U-Boot/kernel is unnecessary. |
| SPL, U-Boot, DTB, kernel, SPI layout, bootargs, rescue from broken boot | Full SPI FEL | Boot-chain changes need the whole 16MB image, or the board cannot reach OTA. |

## One Command

Default fast path, rootfs-only FEL:

```powershell
.\scripts\fel_quick_flash.ps1
```

Full 16MB SPI write:

```powershell
.\scripts\fel_quick_flash.ps1 -FullSpi
```

Use an explicit version when releasing:

```powershell
.\scripts\fel_quick_flash.ps1 -Version v1.6.55
```

Dry run without writing flash:

```powershell
.\scripts\fel_quick_flash.ps1 -DryRun
```

## What The Script Automates

1. Keeps WSL running with a hidden `wsl.exe ... sleep 900` process.
2. Finds the Allwinner FEL USB device `1f3a:efe8` through `usbipd list`.
3. Attaches the FEL device to WSL with `usbipd attach`.
4. Confirms `sunxi-fel list` can see `Allwinner V3s`.
5. Builds `backup/rootfs.squashfs` and `backup/spi_image.bin`.
6. Archives versioned artifacts under `backup/release_<timestamp>_<version>_fel/`.
7. Writes either the rootfs segment at `0x710000` or the full SPI image.
8. Reads back the written bytes and compares SHA256 before reporting success.

## Time Budget

For a user-space firmware change like `S99tun_nat_hub`, `dji_rc`, or `web_server`, use rootfs-only FEL. Expected time is usually 8-12 minutes including build, USB attach, write, readback, and hash compare.

Full SPI FEL is slower because it writes and reads back all 16MB. Use it only for boot-chain changes or rescue.

## Rules

- Do not search old `tmp/` scripts for routine flashing. Use `scripts/fel_quick_flash.ps1`.
- Do not skip readback verification after writing flash.
- Do not use full SPI mode for ordinary rootfs-only changes unless rescue requires it.
- Keep release artifacts versioned and timestamped.
