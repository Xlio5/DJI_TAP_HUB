# Getting Started

## Android Prerequisites

- JDK 17.
- Android SDK 34.
- Android NDK and CMake 3.22.1 as requested by the Gradle project.
- An arm64 GStreamer Android SDK subset containing the headers and static libraries referenced by `android/app/src/main/cpp/CMakeLists.txt`.

Set the SDK path for the current shell before building:

```powershell
$env:GSTREAMER_ROOT_ANDROID = 'D:\sdk\gstreamer-android-min'
./scripts/build-android.ps1
```

The pointed directory must contain `arm64/include`, `arm64/lib`, and `arm64/lib/gstreamer-1.0`. GStreamer is intentionally not vendored because it is a separately licensed third-party distribution.

The first device run may require explicit VPN consent, USB host permission, notification permission, and either Shizuku or another supported privileged path for local `getevent`. Android does not allow these grants to be silently created by a normal APK.

## Linux Host Build

Install CMake, a C++17 compiler, Make or Ninja, and pthread development support. Then run:

```sh
./scripts/build-linux.sh
```

The resulting host binaries are under `build/linux`. Unit tests do not require the V3s board. Hardware services require Linux TUN, USB gadget support, routing/firewall tools, and device-specific serial interfaces.

For ARMv7 cross compilation, use the supplied toolchain as a starting point and set your compiler prefix explicitly:

```sh
cmake -S ubuntu -B build/linux-armv7 \
  -DCMAKE_TOOLCHAIN_FILE=ubuntu/cmake/toolchain-armv7-linux.cmake
cmake --build build/linux-armv7 --parallel
```

## Reference Network

The checked-in device scripts use this reference layout:

| Node | Address | Role |
| --- | --- | --- |
| Android VPN identity | `192.168.144.11` | App endpoint on the bridged LAN |
| Linux/V3s Ethernet | `192.168.144.66` | Hub and management API |
| Example camera | `192.168.144.31` | RTSP source |

Change these values consistently on both endpoints when your LAN differs. Use an isolated lab network while validating NAT and DNAT rules.

## Device Installation Model

The repository provides reference service and shell files under `ubuntu/config` and `ubuntu/scripts`. They assume root access and paths such as `/usr/local/bin`; inspect and adapt them to the target image rather than running them against an unrelated Linux host.

The normal order is:

1. Load the USB serial gadget and confirm `/dev/ttyGS0` exists.
2. Configure `tun_hub`, IP forwarding, NAT, and Ethernet.
3. Start `usb_tund` and `web_server`.
4. Start `dji_rc` when RC acquisition/output is required.
5. Attach Android, grant the one-time permissions, and verify heartbeats before enabling forwarding.

## Publication Check

Before committing a public change, run:

```sh
python3 scripts/check-public-tree.py .
```

The check rejects common private keys, local developer paths, credentials, release binaries, captures, and internal agent metadata.
