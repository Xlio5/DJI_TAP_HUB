# TUN_NAT_HUB V3s EVT Pin Map

This pin map follows the Lichee Pi Zero IO allocation where applicable.

## Fixed Interfaces

| Function | V3s Pin / Group | Direction | Notes |
|---|---|---|---|
| UART0_TX | PB8 | Output | Debug console TX. |
| UART0_RX | PB9 | Input | Debug console RX. |
| UART1_TX | PE21 | Output | External serial port 1 TX. |
| UART1_RX | PE22 | Input | External serial port 1 RX. |
| UART2_TX | PB0 | Output | External serial port 2 TX. |
| UART2_RX | PB1 | Input | External serial port 2 RX. |
| UART2_RTS | PB2 | Output | Optional flow control. |
| UART2_CTS | PB3 | Input | Optional flow control. |
| USB_DM | USB0-DM | Bidirectional | Follow Lichee Pi Zero USB OTG. |
| USB_DP | USB0-DP | Bidirectional | Follow Lichee Pi Zero USB OTG. |
| SPI0_CS | SPI0 | Output | SPI NOR chip select. |
| SPI0_SCK | SPI0 | Output | SPI NOR clock. |
| SPI0_MOSI | SPI0 | Output | SPI NOR data out. |
| SPI0_MISO | SPI0 | Input | SPI NOR data in; add recovery pull-low option. |
| SDC0_CMD | SDC0 | Bidirectional | TF card. |
| SDC0_CLK | SDC0 | Output | TF card. |
| SDC0_D0-D3 | SDC0 | Bidirectional | TF card. |
| EPHY_TX/RX | EPHY | Analog | 100M Ethernet PHY pairs. |
| RESET | RESET | Input | Reset button and test point. |

## RGB GPIO

The RGB LED GPIO is intentionally not fixed yet.

Selection rule:

- Pick one unused LCD/CSI/audio-related GPIO after the Lichee Pi Zero schematic
  and V3s pin mux table are reviewed in Lceda Pro.
- Do not use USB, SPI0, SDC0, EPHY, UART0, UART1, or UART2 pins.

Schematic placeholder:

```text
V3S_GPIO_RGB
```

## Connector Pinout

```text
J_UART0_DEBUG
  1: 3V3
  2: UART0_TX / PB8
  3: UART0_RX / PB9
  4: GND

J_UART1
  1: 3V3
  2: UART1_TX / PE21
  3: UART1_RX / PE22
  4: GND

J_UART2
  1: 3V3
  2: UART2_TX / PB0
  3: UART2_RX / PB1
  4: UART2_RTS / PB2
  5: UART2_CTS / PB3
  6: GND
```

## Open Decisions

| ID | Decision | Default |
|---|---|---|
| HW-D1 | RGB GPIO final pin | Choose unused LCD/CSI/audio GPIO. |
| HW-D2 | SPI NOR size | Prefer 32MB, allow 16MB minimum. |
| HW-D3 | USB connector | USB-C physical connector, USB2.0 device wiring. |
| HW-D4 | RGB LED voltage | Prefer 3.3V-compatible SK6812 variant. |
