TUN_NAT_HUB V3s SPI Release
============================
Date: 2026-07-18 17:03
Git commit: 44310d3

Files:
  spi_image.bin          — 完整16MB SPI镜像 (FEL直刷)
  u-boot-sunxi-with-spl.bin — SD卡可启动合并镜像
  rootfs.squashfs        — 4.0MB rootfs (XZ)
  zImage                 — Linux 7.1.0 kernel
  sun8i-v3s-licheepi-zero-dock.dtb — DTB (dr_mode=peripheral)

Features:
  - DTB dr_mode=peripheral (无VBUS_ERROR)
  - DHCP 3秒超时→静态IP 192.168.144.66
  - S99 init脚本带时间戳
  - usb_tund + web_server 自动启动
  - tmpfs /var/log 日志
  - 启动时间 ~8秒

Flash via FEL:
  sunxi-fel spiflash-write 0 spi_image.bin

Make SD card bootable:
  dd if=u-boot-sunxi-with-spl.bin of=/dev/sdX bs=1024 seek=8
