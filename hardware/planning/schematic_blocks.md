# TUN_NAT_HUB V3s EVT Schematic Blocks

## 1. V3s Minimum System

Baseline: Lichee Pi Zero core board.

Include:

- Allwinner V3s eLQFP128.
- 24MHz main crystal and load capacitors.
- 32.768kHz RTC crystal and load capacitors.
- RESET circuit.
- SZQ precision resistor.
- All power pins and local decoupling capacitors.

Review points:

- Keep decoupling placement close to V3s pins.
- Do not change VCPU/VSYS/VDRAM/AVCC topology unless there is a measured reason.
- Keep UART0 available from first power-on.

## 2. Power

Baseline: Lichee Pi Zero power design.

Include:

- 5V input path.
- 3V3 rail.
- VCPU rail.
- AVCC/EPHY filtering.
- Power LED.
- Test points for 5V, 3V3, VCPU, AVCC, and GND.

EVT rule:

- Leave enough current margin.
- Add input protection and enough bulk capacitance for USB plug-in transients.

## 3. USB OTG Device Gateway

Baseline: Lichee Pi Zero USB OTG design.

Include:

- USB D+ and D-.
- VBUS detect.
- USB_ID handling.
- USB ESD protection near connector.
- USB D+/D-/VBUS/GND test points.

Product behavior:

- V3s is the USB device/gadget.
- DJI RC is the USB host.
- Firmware enumerates as `0x0BDA:0x8812`.

Layout rules:

- 90 ohm USB differential pair.
- Short route, matched length, minimal stubs and vias.

## 4. SPI NOR

Baseline: Lichee Pi Zero SPI Flash option.

Include:

- 16MB minimum SPI NOR, 32MB preferred.
- CS, SCK, MOSI, MISO.
- WP/HOLD pull-ups.
- Optional series resistors on signal lines.
- MISO recovery pad/button path for forcing FEL/bypassing bad SPI boot data.

## 5. TF Card

Baseline: Lichee Pi Zero TF card circuit.

Include:

- SDC0 CMD/CLK/D0-D3.
- Card detect if used by the reference design.
- ESD protection if connector placement requires it.

Purpose:

- Development boot.
- Recovery from broken SPI firmware.

## 6. Ethernet

Baseline: Lichee Pi Zero Dock EPHY + RJ45.

Include:

- V3s internal 100M EPHY signals.
- RJ45 with integrated magnetics or equivalent discrete magnetics.
- EPHY power filtering.
- EPHY precision resistor network.
- LINK/ACT indication.

Rule:

- Do not replace this with USB Ethernet or SPI Ethernet in EVT.

## 7. UART and SC16IS752IPW Auxiliary Port

Use Lichee Pi Zero IO markings:

- UART0 debug: PB8/PB9.
- UART1 external: PE21/PE22.
- UART2 external: PB0/PB1 remains available.
- PB6/PB7 are TWI0/I2C0 for SC16IS752IPW. UART0 is fixed as debug; the old
  PB6 debug-switch function is removed.
- PB2/PB3/PB4/PB5 drive the TMUX1511 mode enables:
  `NORMAL_RX_EN`, `TX_BUS_EN`, `CRSF_RX_EN`, and `SBUS_TX_EN`.

SC16IS752IPW rules:

- I2C address is `0x48` for the current schematic strap.
- IRQ# is not connected in the current revision; Linux sc16is7xx uses polling.
- 14.7456MHz crystal is the UART baud-rate reference.
- Firmware must keep `TX_BUS_EN` and `SBUS_TX_EN` mutually exclusive, and keep
  `NORMAL_RX_EN` and `CRSF_RX_EN` mutually exclusive.

## 8. RGB Status LED

Add one SK6812/WS2812-compatible RGB LED.

Preferred:

- SK6812 Mini-E or another 3.3V-input-compatible LED.

Circuit:

- GPIO to DIN through 330R.
- 0R link for GPIO isolation/reroute.
- 0.1uF close to LED VDD/GND.
- 1uF to 10uF nearby bulk capacitance.

GPIO:

- Select one unused LCD/CSI/audio-related GPIO after final pin mux review.
- Do not consume USB, SPI0, SDC0, EPHY, UART0, UART1, or UART2 pins.

## 9. Buttons and Recovery

Include:

- RESET button.
- RECOVERY/FEL button or pads.
- SPI MISO pull-low recovery option.

Purpose:

- Force FEL/recovery when SPI firmware is broken.
- Allow field and factory recovery without rework.

## 10. EVT Test Points

Minimum:

- 5V, 3V3, VCPU, AVCC, GND.
- USB VBUS, D+, D-.
- SPI CS, SCK, MOSI, MISO.
- UART0 TX/RX.
- UART1 TX/RX.
- UART2 TX/RX.
- RESET.
- RECOVERY/FEL.
- RGB data GPIO.
