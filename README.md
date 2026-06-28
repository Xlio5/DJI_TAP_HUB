# TUN_NAT_HUB

> USB 线缆上的透明 IP 隧道 — DJI RC PLUS 2 遥控器访问配套计算机局域网的零配置方案。

## 这是什么

TUN_NAT_HUB 让 **DJI RC PLUS 2 无人机遥控器**通过 **USB 线缆**透明访问配套计算机（RK3588/Linux 板）所在局域网内的 IP 摄像头和网络设备——无需 WiFi、无需网络配置、即插即用。

```
DJI RC PLUS 2 (Android)          Linux 板 (RK3588 / V3s)
┌──────────────────────┐  USB   ┌─────────────────────┐
│ VpnService            │◄──────►│ usb_tund 守护进程     │
│ TUN: 10.0.0.2        │ 线缆   │ TUN: 10.0.0.1        │
│ → 192.168.88.0/24    │        │ → NAT → LAN 设备     │
└──────────────────────┘        └─────────────────────┘
```

## 核心特性

- **透明 IP 隧道** — Android TUN 虚拟网卡 + Linux TUN 虚拟网卡，双向 IP 包转发
- **零配置** — USB 即插即用，30 秒内自动连接
- **RTSP 视频播放** — 遥控器屏幕实时查看 IP 摄像头画面（<10ms 延迟）
- **端口转发** — 局域网设备可主动访问 Android 端服务（DNAT）
- **Web 配置面板** — 浏览器管理端口转发、摄像头列表、网络状态
- **心跳监控** — 实时链路检测 + 带宽显示
- **开机自启** — Android BOOT_COMPLETED + Linux systemd 双重保障
- **低延迟** — TCP RTT 3-6ms (p50)，满足 4Mbps 视频流

## 硬件需求

| 角色 | 设备 | 说明 |
|------|------|------|
| 遥控器 | DJI RC PLUS 2 | Android 系统，USB Host 模式 |
| 配套计算机 | RK3588 (Rock 5C) 或其他 Linux 板 | USB Device 模式 (g_serial) |
| 连接线 | USB-C to USB-A 数据线 | 连接 DJI RC (USB-A) ↔ Linux 板 (USB-C OTG) |

> **V3s 移植进行中** — 全志 V3s (Cortex-A7, 64MB DDR2) 支持可将物料成本降至 ~30 RMB。详见 [`docs/PRD-v3s-porting.md`](docs/PRD-v3s-porting.md)。

## 快速开始

### 1. Linux 板部署

```bash
# 克隆仓库
git clone <repo-url> && cd TUN_NAT_HUB

# 一键部署到 RK3588 (192.168.88.66)
python3 scripts/deploy_master_to_rk3588.py

# 或手动部署
cd ubuntu && mkdir build && cd build
cmake .. && make -j$(nproc)
sudo ../scripts/setup_gadget.sh
sudo ../scripts/setup_nat.sh
sudo systemctl start tun_nat_hub tun_web
```

### 2. Android APK 安装

```bash
# 构建
cd android && ./gradlew assembleDebug

# 安装 (USB 调试)
adb install app/build/outputs/apk/debug/app-debug.apk

# 或使用预构建 APK
adb install master-app-debug.apk
```

### 3. 使用

1. 用 USB 线连接 DJI RC PLUS 2 和 Linux 板
2. 打开 TUN_NAT_HUB App
3. VPN 自动启动，状态面板显示连接状态
4. 在 RTSP 播放器中输入摄像头地址（如 `rtsp://192.168.88.100:554/stream`）
5. 使用 Web 面板（`http://10.0.0.1:8080`）或 App 侧边栏管理端口转发

## 项目结构

```
TUN_NAT_HUB/
├── android/                 # Android APK (Kotlin + Jetpack Compose)
│   └── app/src/main/java/com/tunnathub/app/
│       ├── service/         # VpnService + TUN 接口
│       ├── usb/             # USB Host 通信
│       ├── proto/           # 帧协议编解码
│       └── MainActivity.kt  # Compose UI
├── ubuntu/                  # Linux 服务端 (C++17 + CMake)
│   ├── src/                 # 守护进程源码
│   ├── scripts/             # g_serial + NAT 配置脚本
│   ├── config/              # systemd 服务单元
│   └── web_panel.py         # Web 配置面板
├── protocol/                # 通信协议定义 (C99 头文件)
├── docs/                    # 项目文档
│   ├── architecture.md      # 架构设计文档
│   ├── USAGE.md             # 部署和使用手册
│   ├── platform-porting-guide.md  # 平台移植指南
│   └── CODEMAPS/            # 代码地图
├── scripts/                 # 部署和诊断脚本 (~70 个)
├── .claude/                 # Claude Code 配置 + 自定义 Skills
│   └── prds/                # 产品需求文档
└── ref/                     # 参考项目
```

## 技术栈

| 层 | Android | Linux |
|----|---------|-------|
| 语言 | Kotlin | C++17, Python 3 |
| 框架 | Jetpack Compose | CMake, Boost.Asio (规划) |
| TUN | VpnService.Builder | /dev/net/tun (ioctl) |
| USB | UsbManager + UsbDeviceConnection | g_serial (CDC ACM) |
| 协议 | 自定义帧: Magic(0x544E) + Length + Payload (≤2048B) |
| NAT | — | iptables MASQUERADE + DNAT |
| 构建 | Gradle 8.5 + AGP | CMake 3.16 + g++ |

## 文档索引

| 文档 | 内容 |
|------|------|
| [CLAUDE.md](CLAUDE.md) | AI 开发助手指令 |
| [docs/architecture.md](docs/architecture.md) | 完整架构设计（方案对比、数据流、决策记录） |
| [docs/USAGE.md](docs/USAGE.md) | 部署和日常使用手册 |
| [docs/platform-porting-guide.md](docs/platform-porting-guide.md) | 新 Linux 平台移植步骤 |
| [docs/CODEMAPS/android.md](docs/CODEMAPS/android.md) | Android 代码地图 |
| [docs/CODEMAPS/ubuntu.md](docs/CODEMAPS/ubuntu.md) | Ubuntu 服务端代码地图 |
| [.claude/prds/tun-nat-hub-core.prd.md](.claude/prds/tun-nat-hub-core.prd.md) | 核心产品需求文档 |
| [.claude/prds/v3s-porting.prd.md](.claude/prds/v3s-porting.prd.md) | V3s 移植需求文档 |

## License

TBD

---
*Built with vibe coding. AI-driven development using Claude Code.*
