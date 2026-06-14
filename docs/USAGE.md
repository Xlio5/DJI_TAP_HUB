# TUN_NAT_HUB 部署与使用手册

> 适用版本：v5 (g_serial Pure Bulk + RTL8812AU VID/PID 伪装)  
> 更新日期：2026-06-14

---

## 目录

1. [硬件连接](#1-硬件连接)
2. [RK3588 端部署](#2-rk3588-端部署)
3. [DJI RC 端安装](#3-dji-rc-端安装)
4. [日常使用](#4-日常使用)
5. [Web 配置面板](#5-web-配置面板)
6. [延迟测试与诊断](#6-延迟测试与诊断)
7. [故障排查](#7-故障排查)
8. [开发环境](#8-开发环境)

---

## 1. 硬件连接

```
DJI RC PLUS 2 (USB-C)  ──[USB 2.0 A-to-C 线]──►  RK3588 (USB-C OTG)
                                                       │
                                                   [千兆网线]
                                                       │
                                                   交换机/路由器
                                                       │
                                               IP Camera / PC / ...
```

**关键点：**
- RK3588 的 USB 口必须支持 **OTG/Device 模式**（Rock 5C 的两个 USB-C 口均可）
- 必须先给 RK3588 上电，等服务启动完毕后再插 USB 线到 DJI RC
- 线材建议用数据线（不是仅充电线），质量好的 USB 2.0 即可

---

## 2. RK3588 端部署

### 方式一：一键安装（推荐）

从 U 盘或 SCP 将 `tun_nat_hub_rk3588.tar.gz` 拷贝到 RK3588：

```bash
# 解压
tar xzf tun_nat_hub_rk3588.tar.gz
cd tun_nat_hub_pkg

# 安装（需要 sudo）
sudo bash install.sh
```

安装脚本自动完成：
1. 停止旧服务
2. 安装 `usb_tund` 守护进程 → `/usr/local/bin/`
3. 安装 `setup_gadget.sh` / `setup_nat.sh` → `/usr/local/bin/`
4. 安装 systemd 服务 → `/etc/systemd/system/`
5. 安装 Web 面板 + TCP Echo Server → `/home/xlong/`
6. 修复 Windows 换行符（CRLF → LF）
7. 启用开机启动并立即运行

### 方式二：从源码编译部署

```bash
# 在 RK3588 上
cd /home/xlong
mkdir -p tun_build/protocol tun_build/src

# 上传源文件（从开发机）
#   protocol/frame.h → tun_build/protocol/
#   ubuntu/src/*     → tun_build/src/
#   ubuntu/CMakeLists.txt → tun_build/

# 编译
cd tun_build
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build

# 安装
sudo cp build/usb_tund /usr/local/bin/
sudo cp ubuntu/scripts/setup_gadget.sh /usr/local/bin/
sudo cp ubuntu/scripts/setup_nat.sh /usr/local/bin/
sudo systemctl enable --now tun_nat_hub
```

### 验证部署

```bash
# 检查服务状态
systemctl status tun_nat_hub
systemctl status tun_web

# 查看实时日志
journalctl -u tun_nat_hub -f

# 检查 USB Gadget 是否就绪
ls -la /dev/ttyGS0

# 检查 TUN 接口
ip addr show tun_hub

# 检查 iptables NAT 规则
sudo iptables -t nat -L POSTROUTING -n
```

### 服务说明

| 服务 | 用途 | 端口 |
|------|------|------|
| `tun_nat_hub` | USB ↔ TUN 守护进程 | 无（/dev/ttyGS0 ↔ tun_hub） |
| `tun_web` | Web 配置面板 | TCP 8080 |

### IP 地址规划

| 设备 | 接口 | IP | 说明 |
|------|------|-----|------|
| RK3588 | tun_hub | 10.0.0.1/24 | TUN 隧道内部 |
| DJI RC | VPN TUN | 10.0.0.2/24 | VpnService 分配 |
| RK3588 | end1 | DHCP (如 192.168.88.66) | 局域网口 |
| 摄像头 | — | 192.168.88.100 | 示例 |
| 局域网 | — | 192.168.88.0/24 | 目标网段 |

---

## 3. DJI RC 端安装

### 编译 APK

```bash
# 在开发机 Windows 上
cd android
./gradlew assembleDebug
# APK 在 app/build/outputs/apk/debug/app-debug.apk
```

### 安装到 DJI RC

```bash
# 通过 ADB 安装（需要先 ADB 连接到 DJI RC）
adb connect 172.24.91.112:33625    # DJI RC WiFi 调试地址（端口可能变化）
adb install app/build/outputs/apk/debug/app-debug.apk
```

### 首次使用

1. 确认 RK3588 已开机且 `tun_nat_hub` 服务运行中
2. 将 USB 线连接 DJI RC 和 RK3588
3. 打开 TUN NAT HUB App
4. 左侧状态栏应显示 **"USB 已检测"**（绿色圆点）
5. 点击 **"连接"** 按钮
6. 系统弹出 VPN 授权对话框 → 点击 **"确定"**
7. 状态栏变为 **"VPN 已连接"**
8. 输入 RTSP 地址（如 `rtsp://192.168.88.100:554/stream1`）
9. 点击 **"开始播放"**

> **注意：** 如果冷启动后 USB 未检测到，拔插一次 USB 线即可。App 已自动处理权限申请。

### 界面说明

```
┌──────────────┬──────────────────────────────────────────┐
│  侧边栏 340dp │              全屏视频 16:9                │
│              │                                          │
│  TUN NAT HUB │          ╔══════════════════╗            │
│  USB · VPN   │          ║  RTSP 视频画面    ║            │
│  状态指示灯   │          ║  (EasyPlayer)    ║            │
│              │          ║  不拉伸无变形     ║            │
│  RTSP 地址栏 │          ╚══════════════════╝            │
│  ▶ 开始播放  │                                          │
│  ■ 停止播放  │                                          │
│  播放状态     │                                          │
│  ⏱ 测延迟    │          无视频时显示提示文字              │
│              │                                          │
│  底栏信息     │  ◀ / ✕ 折叠/展开侧边栏                   │
└──────────────┴──────────────────────────────────────────┘
```

- **◀ 按钮**：折叠侧边栏，视频全屏
- **☰ 按钮**：展开侧边栏
- **延迟测试**：点击测试 USB 隧道 RTT（TCP 握手延迟），结果格式 `avg/p50/p95 ms`
- RTSP 地址自动保存，下次打开 App 自动填入

---

## 4. 日常使用

### 开机流程

1. **RK3588 通电** → 自动启动 `tun_nat_hub` + `tun_web`（systemd enable 已设置）
2. **USB 线连接** DJI RC ↔ RK3588
3. **打开 App** → 点击 **"连接"** → 确认 VPN 授权
4. **点击 ▶ 播放** → 查看视频

### 端口转发（局域网 → DJI RC）

DJI RC 通过 NAT 上网，局域网设备无法直接访问 DJI RC。如需从 Windows 发数据给 DJI RC App：

**方式一：Web 面板添加（推荐）**

打开浏览器访问 `http://192.168.88.66:8080` → **配置** Tab → 添加端口转发。
示例：UDP 5000 → 10.0.0.2，则 Windows 向 `192.168.88.66:5000` 发送的 UDP 数据会被转发到 DJI RC。

**方式二：命令行添加**

```bash
# 转发 UDP 5000 到 DJI RC
sudo iptables -t nat -A PREROUTING -i end1 -p udp --dport 5000 -j DNAT --to-destination 10.0.0.2:5000
sudo iptables -A FORWARD -i end1 -o tun_hub -p udp --dport 5000 -j ACCEPT
```

> **关键：** DJI RC App 中创建 DatagramSocket 后必须调用 `VpnService.protect(socket)` 防止被 VPN 路由吞掉。

---

## 5. Web 配置面板

浏览器访问：**`http://<RK3588_LAN_IP>:8080`** （通常是 `http://192.168.88.66:8080`）

### 四个 Tab

| Tab | 内容 |
|-----|------|
| **📖 概览与链路** | 实时带宽、累计流量、完整数据链路图、帧协议格式、关键参数 |
| **⚙️ 配置** | RTSP 摄像头地址设置、端口转发添加/删除 |
| **🌐 网络与防火墙** | 网口信息、iptables 规则、系统运行时间、流量统计、内存/磁盘 |
| **❓ 使用说明** | 项目介绍、IP 规划、常见问题解答 |

### 面板特性

- 纯 Python 标准库实现，零依赖
- 页面每 2 秒自动刷新数据
- 配置持久化到 `/home/xlong/tun_nat_hub_config.json`

---

## 6. 延迟测试与诊断

### 内置延迟测试（App）

在 App 侧边栏点击 **"⏱ 测延迟"** 按钮，对 `10.0.0.1:9999`（RK3588 TCP Echo Server）发起 10 次 TCP connect 测试。

**结果解读：**
```
5.7/4.0/17.9 ms (avg/p50/p95, 丢包=0)
```
- **avg** = 平均往返延迟
- **p50** = 中位数（50% 的请求延迟低于此值）
- **p95** = 95 分位（95% 的请求延迟低于此值）
- **丢包** = 10 次中失败的次数

**典型值：**
- USB 隧道 TCP RTT：3~6ms（p50）
- 视频端到端延迟：250~350ms（大头在摄像头编码 + 播放器缓冲）

### 手动测试

```bash
# 从 RK3588 ping DJI RC
ping 10.0.0.2

# 从 Windows 测试到 RK3588 echo server（经过 DNAT）
echo hello | nc -w 2 192.168.88.66 9999

# 查看实时 daemon 统计（每 5 秒输出）
journalctl -u tun_nat_hub -f | grep 统计
# 输出格式: [统计] TX=1234/567890B RX=1234/567890B err=0
```

---

## 7. 故障排查

### USB 问题

| 现象 | 可能原因 | 解决 |
|------|---------|------|
| App 显示 "USB 未连接" | USB 线松动或线材不好 | 重新插拔 USB 线；换高质量数据线 |
| App 显示 "USB 已检测" 但连接无反应 | USB 权限未授予 | DJI RC 冷启动后需重新授权；拔插 USB 线重试 |
| `dmesg` 出现 "g_serial not found" | gadget 模块未加载 | `sudo modprobe g_serial use_acm=0 use_obex=0` |
| /dev/ttyGS0 不存在 | g_serial 加载失败 | `sudo bash /usr/local/bin/setup_gadget.sh` |

### 网络问题

| 现象 | 可能原因 | 解决 |
|------|---------|------|
| VPN 已连接但 ping 不通 10.0.0.1 | TUN 接口未创建 | `sudo bash /usr/local/bin/setup_nat.sh` |
| 能 ping 10.0.0.1 但不通局域网 | NAT 规则丢失 | 检查 `iptables -t nat -L POSTROUTING` |
| RTSP 连接超时 | 摄像头 IP 不对或防火墙 | 先 ping 摄像头确认可达；检查 RTSP URL |
| 视频延迟高（>500ms） | 摄像头编码参数 | 检查摄像头 GOP、码率设置 |

### 服务问题

| 现象 | 可能原因 | 解决 |
|------|---------|------|
| `systemctl status tun_nat_hub` 显示 failed | 脚本换行符错误 | `sed -i 's/\r$//' /usr/local/bin/setup_gadget.sh setup_nat.sh` |
| 服务频繁重启 | 设备文件不存在 | `journalctl -u tun_nat_hub -n 20` 查看日志 |
| Web 面板打不开 | tun_web 未启动 | `sudo systemctl start tun_web` |

### 诊断命令

```bash
# 一键诊断
echo "=== USB Gadget ===" && ls -la /dev/ttyGS0 2>&1
echo "=== TUN ===" && ip addr show tun_hub 2>&1
echo "=== NAT ===" && sudo iptables -t nat -L POSTROUTING -n 2>&1
echo "=== FORWARD ===" && sudo iptables -L FORWARD -n 2>&1
echo "=== Daemon ===" && systemctl is-active tun_nat_hub 2>&1
echo "=== Stats ===" && journalctl -u tun_nat_hub --no-pager -n 3 2>&1
```

---

## 8. 开发环境

### 目录结构

```
TUN_NAT_HUB/
├── android/          ← Android APK (Kotlin + Jetpack Compose)
├── ubuntu/           ← RK3588 服务端 (C++17 + CMake)
├── protocol/         ← 共享帧协议定义 (frame.h)
├── docs/             ← 文档 (architecture.md + USAGE.md)
├── scripts/          ← 部署/打包/诊断脚本
└── tun_nat_hub_pkg/  ← 打包目录 (gitignored)
```

### 构建

| 平台 | 命令 | 产出 |
|------|------|------|
| Android | `cd android && ./gradlew assembleDebug` | `app-debug.apk` |
| Ubuntu ARM64 | 在 RK3588 上 `cmake -B build && cmake --build build` | `usb_tund` |
| 部署打包 | `python scripts/build_and_package.py` | `tun_nat_hub_rk3588.tar.gz` |

### 关键参数

| 参数 | 值 | 位置 |
|------|-----|------|
| USB VID/PID | 0x0BDA:0x8812 | `setup_gadget.sh`, `UsbBridge.kt` |
| 帧协议 Magic | 0x544E ("TN") | `protocol/frame.h` |
| TUN MTU | 1400 | `TunNatVpnService.kt`, `setup_nat.sh` |
| USB 超时 | 10ms | `UsbBridge.kt` |
| TTY VTIME | 0 (即时返回) | `main.cpp` |
| 心跳间隔 | 1000ms | `main.cpp`, `frame.h` |
| TCP Echo 端口 | 9999 | `echo_srv.py` |

### RK3588 访问信息

| 项 | 值 |
|-----|-----|
| SSH | `ssh xlong@192.168.88.66` (密码: 1234) |
| Web 面板 | `http://192.168.88.66:8080` |
| 开发密码 | `1234` |

---

## 附录 A：链路数据流

```
App(RTSP Client)         Android VpnService          USB 线              RK3588 usb_tund          Linux 内核            IP Camera
      │                        │                       │                       │                    │                    │
      │── connect() ──────────►│                       │                       │                    │                    │
      │                        │── TUN read() ────────►│                       │                    │                    │
      │                        │── 帧打包 [TN][len][IP]─►│                      │                    │                    │
      │                        │── bulkTransfer() ─────►│                       │                    │                    │
      │                        │                       │── /dev/ttyGS0 ────────►│                    │                    │
      │                        │                       │── [TN][len][IP] ──────►│                    │                    │
      │                        │                       │                       │── 解帧 ───────────►│                    │
      │                        │                       │                       │── TUN write() ────►│                    │
      │                        │                       │                       │                    │── SNAT ──────────►│
      │                        │                       │                       │                    │── end1 发出 ──────►│
      │                        │                       │                       │                    │                    │── RTSP 请求
      │                        │                       │                       │                    │◄── RTSP 响应 ─────│
      │                        │                       │                       │◄── conntrack DNAT─│                    │
      │                        │                       │◄── /dev/ttyGS0 ────────│                    │                    │
      │◄── bulkTransfer() ─────│                       │                       │                    │                    │
      │◄── 解帧 ───────────────│                       │                       │                    │                    │
      │◄── TUN write() ────────│                       │                       │                    │                    │
      │◄── connect() OK ───────│                       │                       │                    │                    │
```

## 附录 B：端口转发原理

```
Windows (192.168.88.x)
    │
    │ UDP dst=192.168.88.66:5000
    ▼
交换机 ──► RK3588 end1 (192.168.88.66)
                │
                │ iptables PREROUTING DNAT: 192.168.88.66:5000 → 10.0.0.2:5000
                ▼
            tun_hub (10.0.0.1)
                │
                │ iptables FORWARD ACCEPT
                ▼
            USB 隧道
                │
                ▼
            DJI RC TUN (10.0.0.2)
                │
                │ App DatagramSocket.receive()
                ▼
            App 处理
```

> Windows 发 `192.168.88.66:5000`，DJI RC App 在 `10.0.0.2:5000` 收到。  
> **不要填 10.0.0.2 作为目标地址** — 局域网设备看不到隧道内部地址！
