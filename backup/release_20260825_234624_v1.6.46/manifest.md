# TUN_NAT_HUB Firmware Release v1.6.46

- version: v1.6.46
- timestamp: 20260825_234624
- branch: codex/sc16-remote-test
- source_commit: b855de71d95972b906b6852c2d4002e4b0f65ed7
- rootfs: rootfs_v1.6.46_20260825_234624.squashfs
- rootfs_size: 4214784
- rootfs_sha256: 6ff997cf15077d4534bddbd06c60ba42e9afce2cbb8ecbef284a04dfcd597460
- spi_image: spi_image_v1.6.46_20260825_234624.bin
- spi_image_size: 16777216
- spi_image_sha256: 1502c8727441fe5ebd111ff19fdbcfc14034929da5afe23fb01685ecd738add3

## Layout

- SPI total: 16 MiB
- SPL/U-Boot: image start and 0x8000
- env: 0x7e000
- dtb: 0x100000
- kernel: 0x110000
- rootfs_a: 0x710000
- rootfs type: squashfs

## Purpose

固化 V3s TUN/NAT 与 RC 输出策略：tun_hub=10.0.0.1/24，Android 主隧道地址=10.0.0.2，LAN 身份 x.x.x.11 DNAT 到 10.0.0.2，并对 x.x.x.11 主动访问 LAN 摄像头做 eth0 MASQUERADE。dji_rc 使用 921600 输入 50ms 优先窗口，921600 有有效 RC 包时按该路包频率输出 SBUS/CRSF，超时后由 115200 路接管。

## Readback Verification

- rootfs copy-back cmp: OK
- spi alias copy-back cmp: OK
- rootfs magic in SPI @0x710000: hsqs OK
- SPI rootfs slice cmp: OK
- setup_v3s.sh contains INTERNAL_FWD_ADDR=10.0.0.2: OK
- setup_v3s.sh contains MASQUERADE: OK
- web_server strings contains 1.6.46: OK
- dji_rc strings contains active_src: OK
- dji_rc strings contains 921600: OK
- SPI bootargs contains console=ttyS0,115200: OK
