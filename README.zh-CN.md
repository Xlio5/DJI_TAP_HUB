# TUN NAT Hub

[English](README.md) | [架构](docs/architecture.md) | [开始使用](docs/getting-started.md) | [协议](docs/protocol.md)

TUN NAT Hub 用于把 Android 遥控终端与小型 Linux USB 设备连接起来，并通过 Android `VpnService` 访问真实局域网。USB 链路承载封装后的 IP 数据；Linux 端还可通过网络 ADB 获取 DJI 遥控输入，将 `getevent` 摇杆轴与 `40007` 端口按键数据融合，再输出 RCMSG、CRSF 或 SBUS。

本项目是独立的社区项目，与 DJI、Google、GStreamer 及相关硬件厂商不存在隶属或背书关系。

## 包含内容

- Android 应用：Kotlin、Jetpack Compose、`VpnService`、USB Host 与前台服务。
- Linux/V3s 服务：TUN 桥接、NAT 控制、网络 ADB 客户端、遥控融合与轻量 Web API。
- `TN` 共享封帧格式及 RC 数据报文档。
- 开机和 USB 接入自动启动，Activity 关闭后数据链路仍可持续运行。
- ADB 封包、RC 融合、来源选择、输入模式和 RTSP 辅助逻辑的主机单元测试。

## 仓库结构

| 路径 | 用途 |
| --- | --- |
| `android/` | Android 应用与测试 |
| `ubuntu/` | Linux/V3s C++ 服务、测试、服务配置和目标机脚本 |
| `protocol/` | 双端共享的线协议常量 |
| `docs/` | 架构、部署、协议和排障文档 |
| `scripts/` | 可重复构建与公开内容检查工具 |

本仓库有意不包含硬件设计、PCB 生产文件、固件/rootfs 镜像、APK、密钥、抓包和内部部署脚本。

## 快速构建

Android 侧需要 Android Studio 或 JDK 17、Android SDK/NDK/CMake；Linux 侧需要 CMake 3.16+ 和支持 C++17 的编译器。

```powershell
./scripts/build-android.ps1
```

Android 原生视频模块需要本地提供 GStreamer Android SDK 子集。将 `GSTREAMER_ROOT_ANDROID` 指向包含 `arm64/include` 和 `arm64/lib` 的目录，详见[开始使用](docs/getting-started.md)。

```sh
./scripts/build-linux.sh
```

Linux 主机构建会编译守护进程并运行现有单元测试。部署到设备时，还需要支持 USB gadget 的内核，以及配置 TUN、路由和防火墙所需的 root 权限。

## 参考网络

仓库默认使用 `192.168.144.0/24`：Android 为 `.11`，Linux/V3s Hub 为 `.66`，示例摄像头为 `.31`。这些是产品默认地址，不是凭据，可在应用和 Linux 配置中修改。

完整系统图和数据流见[架构文档](docs/architecture.md)，帧格式和端口见[协议文档](docs/protocol.md)。

## 安全与许可

本项目会使用 Android 和 Linux 的高权限能力。部署前应审查脚本、限制管理 API 的访问范围，并禁止提交 ADB 密钥或设备凭据。漏洞报告方式见 [SECURITY.md](SECURITY.md)。

本项目采用 GNU GPL v3.0 only。任何对外分发的修改版本都必须按同一许可证提供对应源码，详见 [LICENSE](LICENSE)。第三方组件继续适用其各自许可证，本仓库不分发 GStreamer Android SDK。
