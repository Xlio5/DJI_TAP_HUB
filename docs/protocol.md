# Protocol Reference

## TN Framing

USB carries a byte stream. Every IP packet is wrapped in a four-byte header defined by `protocol/frame.h`:

| Offset | Size | Meaning |
| --- | --- | --- |
| 0 | 2 | ASCII `TN` (`0x54 0x4e`) |
| 2 | 2 | Big-endian payload length |
| 4 | 0-2048 | Raw IPv4 payload |

A payload length of zero is a heartbeat. A two-byte payload is reserved for flow-control credit. Parsers must reject invalid magic, payloads larger than 2048 bytes, and incomplete frames while preserving enough buffered data to resume after the next read.

## RCMSG

Linux publishes an `RCM1` datagram to Android UDP port `65530`. The current wire record is 72 bytes and little-endian. It carries sequence/timestamp metadata, 16 normalized channels, discrete controls, source status, and flags indicating whether `getevent` and `40007` were fresh when the frame was composed.

The canonical implementations are:

- Linux encoder/decoder: `ubuntu/src/dji_rc.cpp`
- Android decoder: `android/app/src/main/java/com/tunnathub/app/RcMsg.kt`
- Android publisher for local fusion: `android/app/src/main/java/com/tunnathub/app/rc/RcMsgCodec.kt`

Do not change field order or structure size on one endpoint alone. Increment the protocol version, update both implementations, and add compatibility tests whenever the layout changes.

## RC Source Rules

- `getevent` provides high-rate stick axes and the buttons assigned to input events.
- TCP port `40007` provides DUML state/change frames for controls unavailable through `getevent`.
- In strict `v3s_adb` mode, overlapping REC/SHOT controls are stripped from `40007` to prevent one physical press from being emitted twice.
- A periodic RCMSG stream refreshes complete state; an actual button transition can request immediate publication to reduce edge latency.

## Related Ports

| Port | Transport | Purpose |
| --- | --- | --- |
| `40007` | TCP inside Android target | DJI DUML RC event source |
| `8080` | HTTP | Linux management/status API |
| `65530` | UDP | Linux-to-Android RCMSG |
| `65531` | UDP | Android RC publication / telemetry path |
| `65532` | UDP | CRSF bridge |

These ports are implementation defaults, not an authentication boundary. Restrict them with interface binding and firewall policy.
