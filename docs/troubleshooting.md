# Troubleshooting

## USB device is not detected

Confirm the Linux gadget driver created `/dev/ttyGS0`, the configured VID/PID matches Android's `device_filter.xml`, and Android granted USB permission. Reconnecting USB does not grant VPN consent automatically.

## VPN starts but LAN traffic does not pass

Check the selected LAN subnet, `tun_hub` state, Linux IP forwarding, route table, and NAT counters. Verify both endpoints use the same reference subnet and that the destination is not already routed through Android Wi-Fi.

## RC sticks update slowly

Inspect `/tmp/rc_state.json` on Linux. `adb_ge_hz` measures parsed getevent input, while `rcmsg_tx_hz` and `rcmsg_tx_dt_ms` measure output. A healthy input with a slow output points to publication or transport; a slow `adb_ge_hz` points to ADB/getevent acquisition.

## Buttons react late or twice

Use strict `v3s_adb` mode when Linux owns ADB acquisition. REC/SHOT overlap between `getevent` and `40007`; strict mode assigns those controls to `getevent` and strips the duplicate `40007` bits. Other `40007` controls depend on receiving both press and release change frames.

## Network ADB cannot connect

Verify ADB over TCP is enabled and authorized on the Android target, the Linux device can route to the selected address/port, and only one key pair is expected. Never copy a maintainer's ADB private key into the repository.

## Android native build cannot find GStreamer

Set `GSTREAMER_ROOT_ANDROID` to a local directory containing `arm64/include` and `arm64/lib`. The repository deliberately excludes prebuilt GStreamer archives; see [Getting Started](getting-started.md).
