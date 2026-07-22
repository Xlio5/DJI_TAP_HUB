# TUN_NAT_HUB V3s EVT Bring-Up Checklist

## Before PCB Order

- [ ] V3s minimum system matches Lichee Pi Zero reference.
- [ ] Power tree reviewed against Lichee Pi Zero reference.
- [ ] USB D+/D- impedance and routing constraints defined.
- [ ] USB ESD protection placed near connector.
- [ ] VBUS detect and USB_ID handling reviewed for device mode.
- [ ] SPI NOR wiring reviewed, including WP/HOLD pull-ups.
- [ ] SPI MISO recovery pull-low path exists.
- [ ] TF card SDC0 wiring reviewed.
- [ ] EPHY + RJ45 follows Lichee Pi Zero Dock reference.
- [ ] UART0 debug header is accessible.
- [ ] UART1 and UART2 headers match Lichee Pi Zero IO allocation.
- [ ] RGB LED GPIO does not conflict with fixed interfaces.
- [ ] RESET and RECOVERY/FEL buttons are accessible.
- [ ] Test points exist for all required power and boot signals.

## First Power-On

- [ ] Current-limited supply is used.
- [ ] 5V rail voltage verified.
- [ ] 3V3 rail voltage verified.
- [ ] VCPU rail voltage verified.
- [ ] AVCC/EPHY rail voltage verified.
- [ ] RESET behavior verified.
- [ ] 24MHz clock present.
- [ ] UART0 boot log visible.

## Boot Media

- [ ] TF card boot works.
- [ ] SPI NOR can be read.
- [ ] SPI NOR can be written.
- [ ] SPI boot works.
- [ ] Bad SPI image can be bypassed through recovery/FEL path.

## USB Gateway

- [ ] V3s enters USB peripheral/device mode.
- [ ] DJI RC sees USB device.
- [ ] Device enumerates as VID/PID `0x0BDA:0x8812`.
- [ ] `/dev/ttyGS0` exists on V3s.
- [ ] Android app detects USB.
- [ ] VPN starts.
- [ ] TUN heartbeat works.

## Ethernet

- [ ] RJ45 link LED works.
- [ ] V3s obtains or uses expected LAN IP.
- [ ] `eth0` link is stable.
- [ ] NAT rules apply.
- [ ] Android can ping LAN target through USB tunnel.
- [ ] RTSP camera stream works through the tunnel.

## Reliability

- [ ] 10 cold boots pass.
- [ ] 10 USB re-plugs pass.
- [ ] 24h tunnel runtime test passes.
- [ ] OTA trial boot and fallback path verified.
- [ ] RGB status mapping verified.
