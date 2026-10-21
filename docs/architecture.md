# Architecture

## System Overview

```mermaid
flowchart LR
    RC[Android DJI controller] --> APP[TUN NAT Hub app]
    APP -->|USB serial gadget\nTN framed IP| HUB[Linux / V3s hub]
    HUB -->|Ethernet| LAN[Camera and LAN devices]
    HUB -->|Network ADB| RC
    HUB -->|CRSF or SBUS| RADIO[RC radio link]
    APP -->|VpnService TUN| APP
    HUB -->|TUN + NAT| LAN
```

Android owns the user-facing VPN and USB host side. Linux owns USB gadget mode, packet forwarding, network ADB acquisition, RC output, and the management API. The components can run headlessly after startup.

## IP Packet Flow

```mermaid
sequenceDiagram
    participant A as Android application
    participant T as VpnService TUN
    participant U as USB bridge
    participant H as Linux tun_hub
    participant N as NAT and routing
    participant L as LAN device
    A->>T: IP packet for configured LAN subnet
    T->>U: Read packet
    U->>H: TN magic + length + IP payload
    H->>N: Write payload to tun_hub
    N->>L: Forward or DNAT through Ethernet
    L-->>N: Response packet
    N-->>H: tun_hub packet
    H-->>U: TN framed payload
    U-->>T: Write packet
    T-->>A: Deliver to protected socket or app
```

Only the configured LAN subnet is routed into the VPN. Heartbeats use a zero-length `TN` frame, so link liveness does not require an IP packet.

## RC Input Flow

```mermaid
flowchart LR
    GE[getevent event4 axes\nand event3 keys] -->|ADB shell streams| ADB[Linux ADB multiplexer]
    P4[localhost:40007\nDUML changes] -->|ADB shell stream| ADB
    ADB --> FUSE[Freshness and ownership fusion]
    FUSE -->|periodic 50 Hz + immediate edges| RCM[RCMSG]
    RCM --> APP[Android RC UI]
    FUSE --> MAP[Channel mapping]
    MAP --> CRSF[CRSF output]
    MAP --> SBUS[SBUS output]
```

In strict `v3s_adb` mode, duplicated REC/SHOT signals are owned by `getevent`; `40007` supplies the remaining button and mode transitions. Button edges may trigger an immediate RCMSG while the periodic stream keeps axes and state refreshed.

## Startup Sequence

```mermaid
sequenceDiagram
    participant OS as Android OS
    participant BR as BootReceiver
    participant VPN as Foreground VPN service
    participant USB as USB bridge
    participant INIT as Linux init/systemd
    participant D as Linux daemons
    OS->>BR: BOOT_COMPLETED or USB_DEVICE_ATTACHED
    BR->>BR: Match configured VID/PID and permission
    BR->>VPN: Start foreground service
    VPN->>USB: Enumerate and open USB device
    INIT->>D: Load gadget and start usb_tund/web_server/dji_rc
    USB->>D: Establish framed link
    D->>D: Start TUN/NAT and optional ADB RC streams
    VPN-->>OS: Persistent notification and running data path
```

Android still requires the user to grant VPN consent and any required USB/accessibility/Shizuku permissions at least once. The receiver cannot silently bypass Android security prompts.

## Module Relationship

```mermaid
flowchart TB
    subgraph Android
        UI[Compose UI]
        SVC[TunNatVpnService]
        UB[UsbBridge]
        AR[Android RC readers]
        VP[RTSP players]
        UI --> SVC
        UI --> VP
        SVC --> UB
        SVC --> AR
    end
    subgraph Shared
        TN[protocol/frame.h\nTN framing contract]
        RC[RCM1 / CRSF conventions]
    end
    subgraph Linux
        UT[usb_tund]
        WS[web_server]
        DR[dji_rc]
        AC[ADB client and multiplexer]
        RF[RC fusion and mapping]
        UT --> TN
        DR --> AC
        DR --> RF
        WS --> DR
    end
    UB --> TN
    AR --> RC
    RF --> RC
    RC --> UI
```

The shared C header is the canonical IP framing contract. RCMSG currently has mirrored Kotlin and C++ definitions; changes must update both sides and their tests in the same commit.

## Trust Boundaries

- USB connects two privileged endpoints; do not expose gadget nodes to untrusted local users.
- Network ADB grants shell-equivalent access to the target Android device and should be isolated to a trusted link.
- The Linux web API can alter networking and firmware state; bind or firewall it to a management network.
- NAT and forwarding rules affect the whole device. Test changes on recoverable hardware before production use.
