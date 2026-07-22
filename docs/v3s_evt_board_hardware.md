# TUN_NAT_HUB V3s EVT Board Hardware Definition

> Status: EVT hardware definition
> Baseline: Lichee Pi Zero core board + Lichee Pi Zero Dock Ethernet design
> Date: 2026-07-22

## 1. Goal

This board is the first self-designed EVT hardware for TUN_NAT_HUB.

The goal is to replace the current Lichee Pi Zero development setup with a
debuggable product-shape board while keeping the proven Lichee Pi Zero circuits
as much as possible.

Primary product function:

- USB 2.0 device/gadget gateway for DJI RC.
- 100M Ethernet LAN access for IP camera / LAN devices.
- V3s Linux system running TUN, NAT, USB tunnel daemon, and web service.
- SPI NOR boot for product firmware.
- TF card retained for development and recovery.

## 2. Design Baseline

Use existing Lichee Pi Zero designs wherever possible:

- V3s minimum system follows Lichee Pi Zero.
- Power tree follows Lichee Pi Zero.
- USB OTG follows Lichee Pi Zero, adjusted for product device mode usage.
- SPI NOR and TF card follow Lichee Pi Zero.
- Ethernet follows Lichee Pi Zero Dock EPHY + RJ45 design.
- UART0 debug follows Lichee Pi Zero IO definition.
- UART1 and UART2 use the Lichee Pi Zero marked IO positions.

New project-specific additions:

- One RGB status LED, preferably SK6812/WS2812 compatible.
- Recovery/FEL button and explicit recovery test points.
- Product-oriented interface layout for USB gateway + Ethernet.

## 3. Required Modules

| Module | Requirement | Notes |
|---|---|---|
| V3s minimum system | Required | Follow Lichee Pi Zero reference design. |
| Power | Required | 5V input, 3V3, VCPU, AVCC/EPHY supplies. Keep EVT margin. |
| USB OTG | Required | USB2.0 device mode for DJI RC host. |
| SPI NOR | Required | 16MB minimum, 32MB optional. Product boot and OTA storage. |
| TF card | Required for EVT | Keep for boot recovery and development. |
| EPHY + RJ45 | Required | V3s internal 100M PHY + RJ45 with magnetics. |
| UART0 | Required | Debug console. |
| UART1 | Required | External serial port 1. |
| UART2 | Required | External serial port 2, RTS/CTS optional. |
| RGB LED | Required | SK6812/WS2812 compatible single-wire LED. |
| Buttons | Required | RESET and RECOVERY/FEL. |
| Test points | Required | Power, USB, SPI, UART, reset, recovery, key clocks/signals. |

## 4. UART Allocation

Use the Lichee Pi Zero IO allocation directly.

| Function | V3s Pin Group | Purpose |
|---|---|---|
| UART0_TX | PB8 | Debug console TX. |
| UART0_RX | PB9 | Debug console RX. |
| UART1_TX | PE21 | External serial port 1 TX. |
| UART1_RX | PE22 | External serial port 1 RX. |
| UART2_TX | PB0 | External serial port 2 TX. |
| UART2_RX | PB1 | External serial port 2 RX. |
| UART2_RTS | PB2 | Optional UART2 flow control. |
| UART2_CTS | PB3 | Optional UART2 flow control. |

Recommended connectors:

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

Note: With the Lichee Pi Zero IO allocation, the board has UART0 for debug and
UART1/UART2 as two external serial ports. If more external UARTs are needed in
the future, add an external UART expander instead of consuming boot-critical IO.

## 5. RGB Status LED

Use one SK6812/WS2812-compatible RGB LED.

Recommended part choice:

- Prefer SK6812 Mini-E or another 3.3V-input-compatible RGB LED.
- If using a 5V WS2812B, add a level shifter because V3s GPIO is 3.3V.

Recommended circuit:

```text
V3S_GPIO_RGB -- 330R -- RGB_DIN
3V3 or 5V ------------ RGB_VDD
GND ------------------ RGB_GND
```

Placement and passive parts:

- Put 0.1uF close to the RGB LED VDD/GND pins.
- Add 1uF to 10uF nearby if the LED is powered from a longer rail segment.
- Place a 0R option on the data line so the GPIO can be isolated or rerouted.
- Place the LED near the enclosure light pipe or board edge.

Suggested status mapping:

| Color | Meaning |
|---|---|
| Yellow slow blink | System booting. |
| Blue solid | USB enumerated. |
| Green solid | TUN/NAT/link healthy. |
| Red fast blink | Service or boot failure. |
| Purple breathing | OTA upgrade in progress. |
| White blink | Recovery or factory-test mode. |

The RGB GPIO must not use USB, SPI0, SDC0, EPHY, UART0, UART1, or UART2 pins.
Select one unused LCD/CSI/audio-related GPIO after the schematic pin mux review.

## 6. USB OTG Product Rules

The product uses V3s as the USB device/gadget and DJI RC as the USB host.

Schematic requirements:

- Follow Lichee Pi Zero USB OTG reference design.
- Keep VBUS detect and USB_ID handling debuggable.
- Prefer fixed peripheral/device behavior for the product path.
- Add USB ESD protection near the connector.
- Route D+/D- as a 90 ohm differential pair.
- Keep D+/D- short, matched, and with minimal vias.
- Add test points for USB D+, D-, VBUS, and GND.

Firmware expectation:

- USB gadget enumerates with VID/PID `0x0BDA:0x8812`.
- Linux exposes `/dev/ttyGS0` for the USB tunnel daemon.

## 7. Boot, Recovery, and Storage

Product boot path:

- SPI NOR boots SPL/U-Boot/kernel/rootfs.
- Existing TUN_NAT_HUB SPI image layout and A/B OTA flow remain the software
  baseline.

EVT recovery path:

- Keep TF card socket for alternate boot and recovery.
- Keep UART0 debug console.
- Add RESET button.
- Add RECOVERY/FEL button or pads.
- Add SPI MISO pull-low recovery pad/button to force bypassing bad SPI boot data.

SPI NOR recommendations:

- 16MB minimum.
- 32MB preferred if BOM and availability allow.
- Keep WP/HOLD pulled up.
- Place SPI Flash close to V3s.
- Add optional series resistors on CS/SCK/MOSI/MISO if layout permits.

## 8. Ethernet

Use the Lichee Pi Zero Dock Ethernet design as the reference.

Requirements:

- V3s internal 100M EPHY.
- RJ45 with integrated magnetics, or equivalent discrete magnetics + RJ45.
- Keep EPHY analog supply filtering from the reference design.
- Keep EPHY precision resistor network from the reference design.
- Route Ethernet differential pairs with controlled impedance.
- Provide LINK/ACT indication through RJ45 LEDs or board LEDs.

This board should not use USB Ethernet or SPI Ethernet for the main LAN path.
The V3s internal EPHY is the intended product network interface.

## 9. Test Points

Minimum EVT test points:

- 5V input.
- 3V3.
- VCPU.
- AVCC/EPHY supply.
- GND.
- USB VBUS.
- USB D+.
- USB D-.
- SPI CS/SCK/MOSI/MISO.
- UART0 TX/RX.
- UART1 TX/RX.
- UART2 TX/RX.
- RESET.
- RECOVERY/FEL.
- RGB data GPIO.

## 10. Board-Level Block Diagram

```text
              +----------------------+
5V_IN --------| Power tree           |
USB_VBUS -----| 3V3 / VCPU / AVCC    |
              +----------+-----------+
                         |
                  +------v------+
                  | Allwinner V3s |
                  |              |
DJI RC <----------| USB OTG      |
LAN <------------>| EPHY + RJ45  |
SPI NOR <-------->| SPI0         |
TF Card <-------->| SDC0         |
Debug <---------->| UART0        |
Serial 1 <--------| UART1        |
Serial 2 <--------| UART2        |
RGB LED <---------| GPIO         |
RESET/FEL <------>| RESET/BOOT   |
                  +-------------+
```

## 11. EVT Design Priorities

First EVT board priorities:

1. Debuggability.
2. Recovery from bad SPI firmware.
3. Reliable USB enumeration on DJI RC.
4. Reliable 100M Ethernet link.
5. Stable power during plug-in and boot.
6. Enough test points for board bring-up.

Do not optimize board area or BOM aggressively in EVT. Cost reduction belongs
in the second or third hardware revision after USB, Ethernet, boot, and OTA are
verified on the self-designed PCB.
