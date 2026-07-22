# TUN_NAT_HUB Hardware Workspace

This directory contains the hardware design workspace for the V3s EVT board.

## Tool

Primary EDA tool:

- Lceda Pro / JLC EDA Pro
- Installed executable on this workstation:
  `C:\Program Files\lceda-pro\lceda-pro.exe`

## Board Target

- Board name: `TUN_NAT_HUB_V3S_EVT`
- Baseline: Lichee Pi Zero core board + Lichee Pi Zero Dock Ethernet
- Main functions:
  - Allwinner V3s minimum system
  - USB OTG device gateway
  - 100M Ethernet through V3s EPHY
  - SPI NOR product boot
  - TF card development/recovery boot
  - UART0 debug console
  - UART1 and UART2 external serial headers
  - SK6812/WS2812-compatible RGB status LED
  - RESET and RECOVERY/FEL buttons

## Directory Layout

```text
hardware/
  README.md
  lceda/
    README.md
    TUN_NAT_HUB_V3S_EVT/
      .gitkeep
  refs/
    README.md
  planning/
    schematic_blocks.md
    pinmap.md
    bom_draft.csv
    bringup_checklist.md
```

## Workflow

1. Create or import the Lceda Pro project in `hardware/lceda/TUN_NAT_HUB_V3S_EVT/`.
2. Rebuild the schematic by blocks listed in `planning/schematic_blocks.md`.
3. Use `planning/pinmap.md` as the pin allocation source of truth.
4. Use `planning/bom_draft.csv` as the first BOM seed.
5. Before ordering EVT PCBs, run through `planning/bringup_checklist.md`.

## Notes

Keep the first EVT revision debug-friendly. Do not aggressively reduce board
area or remove recovery paths until USB enumeration, Ethernet, SPI boot, and
OTA fallback have been verified on self-designed hardware.
