# V3s Web And DJI Startup Design

## Goal

V3s firmware must boot the documented C++ web panel and the DJI RC daemon from the read-only rootfs, without relying on temporary files under `/var/log`.

## Decisions

- The active web implementation is `ubuntu/src/web_server.cpp`, built as `/usr/local/bin/web_server`.
- The legacy Python panel `ubuntu/web_panel.py` is not used by V3s startup or full firmware builds.
- `dji_rc` is built into `/usr/local/bin/dji_rc` and started by `S99tun_nat_hub`.
- UART0 debug is emitted on `/dev/ttyS0 @115200`.
- DJI debug output reports the latest channel state every 5 seconds.
- SBUS output is sent on `/dev/ttyS2 @115200`.

## Verification

- Compile `web_server` and `dji_rc` with the Buildroot toolchain.
- Inspect Buildroot target files before packaging.
- Package rootfs from the updated target.
- After SPI flashing, read back written flash regions and verify hashes.
