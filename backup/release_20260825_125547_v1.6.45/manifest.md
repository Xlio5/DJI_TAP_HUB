# TUN_NAT_HUB Firmware Release v1.6.45

- version: v1.6.45
- timestamp: 20260825_125547
- branch: codex/sc16-remote-test
- source_commit: b31e44badeda3e0b41b601c7c463133101f07cd1
- rootfs: rootfs_v1.6.45_20260825_125547.squashfs
- rootfs_size: 4214784
- rootfs_sha256: 9e31b4c40fad9280d7b973f24b71b4ea0d3f71feae1ba05a613c70e8de0fc02b
- spi_image: spi_image_v1.6.45_20260825_125547.bin
- spi_image_size: 16777216
- spi_image_sha256: c7b7d0849621b1b59474e4e5dccd881b0f1a299df76c389eeec378b915ca6c4a

## Layout

- SPI total: 16 MiB
- SPL/U-Boot: image start and 0x8000
- env: 0x7e000
- dtb: 0x100000
- kernel: 0x110000
- rootfs_a: 0x710000
- rootfs type: squashfs

## Purpose

固化 RTSP 视频回流相关 V3s TUN/NAT 配置：tun_hub=10.0.0.1/24，Android 主隧道地址=10.0.0.2，LAN 身份 x.x.x.11 DNAT 到 10.0.0.2，并对 x.x.x.11 主动访问 LAN 摄像头做 eth0 MASQUERADE。

## Readback Verification

- rootfs copy-back cmp: OK
- spi alias copy-back cmp: OK
- rootfs magic in SPI @0x710000: hsqs OK
- SPI rootfs slice cmp: OK
- setup_v3s.sh contains INTERNAL_FWD_ADDR=10.0.0.2: OK
- setup_v3s.sh contains MASQUERADE: OK
- web_server strings contains 1.6.45: OK
- SPI bootargs contains console=ttyS0,115200: OK
