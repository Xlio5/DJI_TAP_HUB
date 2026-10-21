# TUN NAT Hub

[简体中文](README.zh-CN.md) | [Architecture](docs/architecture.md) | [Getting Started](docs/getting-started.md) | [Protocol](docs/protocol.md)

TUN NAT Hub connects an Android-based controller to a small Linux USB device and exposes a real LAN through Android's `VpnService`. The same link carries framed IP packets, while the Linux side can acquire DJI remote-control input over network ADB, fuse `getevent` axes with port `40007` button data, and publish RCMSG, CRSF, or SBUS output.

This is an independent community project. It is not affiliated with or endorsed by DJI, Google, GStreamer, or the manufacturers of the supported boards.

## What Is Included

- Android app using Kotlin, Jetpack Compose, `VpnService`, USB host APIs, and a foreground service.
- Linux/V3s C++ services for the TUN bridge, NAT control plane, network ADB client, RC fusion, and a lightweight web API.
- Shared `TN` framing definition and documented RC datagrams.
- Boot and USB-attach startup support so the data path does not depend on keeping the activity open.
- Host-side unit tests for ADB framing, RC fusion, source selection, input modes, and RTSP helpers.

## Repository Layout

| Path | Purpose |
| --- | --- |
| `android/` | Android application and tests |
| `ubuntu/` | Linux/V3s C++ daemons, tests, service files, and target scripts |
| `protocol/` | Shared wire-format constants |
| `docs/` | Architecture, setup, protocol, and troubleshooting guides |
| `scripts/` | Reproducible build and publication checks |

Hardware design files, board manufacturing files, firmware/rootfs images, APKs, keys, captures, and private deployment scripts are intentionally not part of this repository.

## Quick Build

Requirements are Android Studio or JDK 17 plus Android SDK/NDK/CMake, and CMake 3.16+ with a C++17 compiler for Linux.

```powershell
./scripts/build-android.ps1
```

The Android native video module requires a locally supplied GStreamer Android SDK subset. Set `GSTREAMER_ROOT_ANDROID` to a directory containing `arm64/include` and `arm64/lib`; see [Getting Started](docs/getting-started.md).

```sh
./scripts/build-linux.sh
```

The Linux host build compiles the daemons and runs the available unit tests. Device deployment requires a compatible USB gadget kernel and root privileges for TUN, routing, and firewall configuration.

## Reference Topology

The checked-in defaults use `192.168.144.0/24`: Android is `.11`, the Linux/V3s hub is `.66`, and an example camera is `.31`. These are product defaults, not credentials, and can be changed in the app and Linux configuration.

See [Architecture](docs/architecture.md) for all system and data-flow diagrams, and [Protocol](docs/protocol.md) for framing and port assignments.

## Security

The project uses privileged Android and Linux facilities. Review scripts before deployment, isolate the management API from untrusted networks, and never commit ADB keys or device credentials. Report vulnerabilities according to [SECURITY.md](SECURITY.md).

## License

Copyright (C) 2026 TUN NAT Hub contributors.

This project is licensed under the GNU General Public License v3.0 only. Distributed modified versions must provide corresponding source under the same license. See [LICENSE](LICENSE).

Third-party components retain their own licenses. In particular, the repository does not redistribute the GStreamer Android SDK.
