# TUN_NAT_HUB 架构设计文档

> 三方案并行设计 + 综合评审 · 2026-06-13  
> **最终方案：以 MVP 为主体骨架，分阶段吸收稳健/性能设计**

---

## 一、项目目标

Android 设备通过 **USB 线**（自定义 Bulk 传输）访问 RK3588 Ubuntu 所在局域网的设备（如 IP 摄像头），实现透明 IP 包转发。

### 核心约束

| 约束 | 说明 |
|------|------|
| USB 通信 | 自定义 Bulk 传输（非 RNDIS/ECM，避免 Android 网卡驱动限制） |
| Android TUN | VpnService.Builder API（无 root，接受状态栏 VPN 图标） |
| 目标 | 透明 NAT 网关优先（Android 可 ping/访问局域网），应用层代理备用 |
| 性能 | 最大 4Mbps 码流，额外延迟目标 <10ms |
| USB 拓扑 | RK3588 作为 USB Gadget (Device)，Android 作为 USB Host |
| 不依赖项 | 不需要 Android INTERNET 权限（USB 通道走 USB Host API，TUN 走 VpnService） |

---

## 二、整体架构

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          Android 手机 (USB Host)                           │
│                                                                            │
│  ┌──────────────┐    ┌──────────────────┐    ┌─────────────────────────┐  │
│  │  摄像头App     │───>│ Android 网络栈    │───>│   TUN 接口 (VpnService) │  │
│  │  (VLC/自研)   │    │ (路由表导向 TUN)  │    │   tun0: 10.0.0.2/24     │  │
│  └──────────────┘    └──────────────────┘    └────────────┬────────────┘  │
│                                                           │                │
│                                          tunFd.read()     │ tunFd.write()  │
│                                                           │                │
│  ┌────────────────────────────────────────────────────────┴────────────┐  │
│  │                    UsbTunBridge (Kotlin 协程)                         │  │
│  │                                                                       │  │
│  │  Coroutine-1 (IO): TUN.read() ──> framePack() ──> USB.bulkTransfer() │  │
│  │  Coroutine-2 (IO): USB.bulkTransfer() ──> frameUnpack() ──> TUN.write()│  │
│  └───────────────────────────────┬──────────────────────────────────────┘  │
│                                  │                                         │
│                    USB Host API  │  UsbDeviceConnection                    │
│                    bulkTransfer  │  (Bulk OUT endpoint / Bulk IN endpoint) │
└──────────────────────────────────┼─────────────────────────────────────────┘
                                   │
                    ═══════════════╪═══════════════
                     USB 2.0 线缆  │  (标准 A-to-C)
                    ═══════════════╪═══════════════
                                   │
┌──────────────────────────────────┼─────────────────────────────────────────┐
│                       RK3588 Ubuntu (USB Gadget/Device)                     │
│                                  │                                          │
│  ┌───────────────────────────────┴──────────────────────────────────────┐  │
│  │                  usb_tund Daemon (C++守护进程)                         │  │
│  │                                                                        │  │
│  │  主线程: 信号处理 + 心跳保活 + 统计采集                                  │  │
│  │  IO-Thread-1: TUN.read() ──> framePack() ──> USB-EP-IN.write()       │  │
│  │  IO-Thread-2: USB-EP-OUT.read() ──> frameUnpack() ──> TUN.write()    │  │
│  └───────────┬──────────────────────────────────────┬───────────────────┘  │
│              │                                      │                       │
│    ┌─────────▼───────────┐              ┌───────────▼───────────┐          │
│    │ /dev/usb-ffs/tun_nat/│              │   /dev/net/tun        │          │
│    │  ep1 (Bulk OUT)     │              │   tun_hub (10.0.0.1)  │          │
│    │  ep2 (Bulk IN)      │              └───────────┬───────────┘          │
│    └─────────────────────┘                          │                       │
│                                                    │                       │
│                                ┌───────────────────▼───────────────────┐   │
│                                │        Linux 内核路由 + NAT            │   │
│                                │   ip_forward = 1                       │   │
│                                │   iptables MASQUERADE (SNAT)           │   │
│                                │   TCP MSS Clamping (mtu 1400)         │   │
│                                └───────────────────┬───────────────────┘   │
│                                                    │                       │
│                                         eth0: 局域网 IP                    │
└────────────────────────────────────────────┬──────────────────────────────┘
                                             │
                              ═══════════════╪═══════════════
                              以太网 / WiFi  │
                              ═══════════════╪═══════════════
                                             │
                    ┌────────────────────────▼─────────────────────────┐
                    │              局域网设备                            │
                    │  IP Camera: 192.168.88.100:554 (RTSP)            │
                    │  NAS / PC / 其他设备                              │
                    └──────────────────────────────────────────────────┘
```

### 地址规划

```
Android TUN (tun0):      10.0.0.2/24
RK3588 TUN (tun_hub):    10.0.0.1/24
USB链路内部网段:          10.0.0.0/24 (点到点)
目标局域网:               192.168.88.0/24 (可配置)
```

### 数据流路径（以 Android ping 192.168.88.100 为例）

```
1. Android App 发出 ICMP Echo Request (dst=192.168.88.100)
2. Android 内核路由: 192.168.88.0/24 via tun0 → TUN 接口
3. VpnService 从 tunFd 读取原始 IP 包
4. 帧打包: [Magic(0x544E)][Length][IP_Packet]
5. USB Bulk OUT 传输 → RK3588
6. RK3588 usb_tund 接收、解帧、写入 tun_hub
7. 内核路由 + MASQUERADE SNAT (src 10.0.0.2 → eth0 IP)
8. 从 eth0 发出到局域网
9. 回包沿反向路径经 conntrack DNAT 回到 Android
```

---

## 三、USB 通信协议

### 帧格式（最终确定）

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|             Magic (0x544E)     |         Length (N)            |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                                                               |
|                    Payload (N bytes)                           |
|              (原始 IPv4/IPv6 包, 含 IP 头)                      |
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

| 字段 | 偏移 | 大小 | 说明 |
|------|------|------|------|
| Magic | 0 | 2B | 固定 `0x544E` ("TN")，用于帧同步 |
| Length | 2 | 2B | Payload 长度，大端序，范围 [0, 2048] |
| Payload | 4 | N | 完整的 IP 包（含 IP 头） |

**特殊帧：**
- `Length = 0`：心跳帧 PING/PONG（无 Payload）
- `Length = 2`：Credit 帧（Payload 为 2B Credit 值，Phase 3 使用）

**设计决策：**
- ❌ 无 CRC — USB Bulk 已有 CRC16 保护，应用层 CRC 仅检测软件 bug
- ❌ 无序列号 — USB 是有序可靠传输（不丢包不重排）
- ❌ 无 Flags/StreamID — 点对点单流，无需多路复用
- ✅ Magic `0x544E` 提供帧边界检测，Length 提供二次校验

### 心跳机制

```
发送端 ──[PING: Mag=0x544E, Len=0]──► 接收端
发送端 ◄──[PONG: Mag=0x544E, Len=0]── 接收端

Ubuntu 每 1000ms 发 PING
Android 收到 PING 立即回 PONG
Ubuntu 3000ms 无 PONG → 判定断开
Android 5000ms 无任何帧 → 判定断开
```

---

## 四、技术栈

### Android 端

```
语言:       Kotlin
UI:         Jetpack Compose (极简界面)
协程:       kotlinx-coroutines-android
USB:        android.hardware.usb (UsbManager / UsbDeviceConnection)
VPN:        android.net.VpnService.Builder
构建:       Gradle KTS + AGP
最低SDK:    API 26 (Android 8.0)
目标SDK:    API 34
```

**关键参数：**
```kotlin
VpnService.Builder()
    .setSession("TUN_NAT_HUB")
    .setMtu(1400)                       // MTU 1400，减少分片
    .addAddress("10.0.0.2", 24)         // Android TUN IP
    .addRoute("192.168.88.0", 24)       // 只路由局域网流量
    .addDnsServer("192.168.88.1")       // 局域网 DNS（可配置）
    .setBlocking(true)                  // 阻塞模式，配合 Dispatchers.IO
    .establish()
```

### Ubuntu 端 (RK3588)

```
语言:       C++17
构建:       CMake
IO:         epoll (非 io_uring，4Mbps 下 epoll 充分)
线程:       pthread (2 IO 线程 + 1 主线程)
USB:        ConfigFS + FunctionFS (内核标准框架)
TUN:        /dev/net/tun + IFF_TUN + IFF_NO_PI
NAT:        iptables MASQUERADE + TCPMSS
守护:       systemd
外部依赖:   零（仅 libc + libpthread）
```

**TUN 创建：**
```cpp
int fd = open("/dev/net/tun", O_RDWR);
struct ifreq ifr = {};
ifr.ifr_flags = IFF_TUN | IFF_NO_PI;  // IFF_NO_PI 去掉 4 字节包头
strncpy(ifr.ifr_name, "tun_hub", IFNAMSIZ);
ioctl(fd, TUNSETIFF, &ifr);
```

---

## 五、USB Gadget 配置 (RK3588)

### ConfigFS + FunctionFS 配置脚本

```bash
#!/bin/bash
# setup_gadget.sh — 一次性配置 USB Gadget

modprobe libcomposite
modprobe usb_f_fs

GADGET=/sys/kernel/config/usb_gadget/tun_nat
mkdir -p $GADGET

# USB 描述符
echo "0x2207" > $GADGET/idVendor       # 自定义 VID
echo "0x0010" > $GADGET/idProduct      # 自定义 PID
echo "0x0200" > $GADGET/bcdUSB         # USB 2.0
echo "0x0100" > $GADGET/bcdDevice

# 设备字符串
mkdir -p $GADGET/strings/0x409
echo "RK3588"         > $GADGET/strings/0x409/manufacturer
echo "TUN NAT Hub"    > $GADGET/strings/0x409/product
echo "TUNNATHUB2024"  > $GADGET/strings/0x409/serialnumber

# 配置描述符
mkdir -p $GADGET/configs/c.1/strings/0x409
echo "Bulk Transfer"  > $GADGET/configs/c.1/strings/0x409/configuration
echo "500"            > $GADGET/configs/c.1/MaxPower

# FunctionFS 实例
mkdir -p $GADGET/functions/ffs.tun_nat
mkdir -p /dev/usb-ffs/tun_nat
mount -t functionfs tun_nat /dev/usb-ffs/tun_nat

# 绑定到配置
ln -s $GADGET/functions/ffs.tun_nat $GADGET/configs/c.1/

# 激活 UDC（守护进程写完 descriptor 后执行）
UDC=$(ls /sys/class/udc/ | head -1)
echo "$UDC" > $GADGET/UDC
```

### Android 端 USB Host

```kotlin
// 通过 VID/PID 枚举设备
val device: UsbDevice = usbManager.deviceList.values
    .first { it.vendorId == 0x2207 && it.productId == 0x0010 }

// 请求权限 + 打开连接
val conn = usbManager.openDevice(device)!!
conn.claimInterface(device.getInterface(0), true)

// 获取 Bulk 端点
val epOut = device.getInterface(0).getEndpoint(0)  // Bulk OUT
val epIn  = device.getInterface(0).getEndpoint(1)  // Bulk IN

// 收发
conn.bulkTransfer(epOut, data, data.size, 1000)
val n = conn.bulkTransfer(epIn, buffer, buffer.size, 1000)
```

**AndroidManifest.xml 声明：**
```xml
<uses-feature android:name="android.hardware.usb.host" android:required="true" />
```

---

## 六、NAT + 路由配置 (RK3588)

```bash
#!/bin/bash
# setup_nat.sh

# 创建 TUN 接口
ip tuntap add dev tun_hub mode tun
ip addr add 10.0.0.1/24 dev tun_hub
ip link set tun_hub up

# 开启 IP 转发
sysctl -w net.ipv4.ip_forward=1

# SNAT: USB 侧流量经 eth0 做源地址转换
iptables -t nat -A POSTROUTING -s 10.0.0.0/24 -o eth0 -j MASQUERADE

# FORWARD: 允许双向转发
iptables -A FORWARD -i tun_hub -o eth0 -j ACCEPT
iptables -A FORWARD -i eth0 -o tun_hub \
    -m state --state ESTABLISHED,RELATED -j ACCEPT

# TCP MSS Clamping: 防止 TCP 协商过大 MSS
iptables -t mangle -A FORWARD \
    -p tcp --tcp-flags SYN,RST SYN \
    -j TCPMSS --clamp-mss-to-pmtu
```

---

## 七、线程/协程模型

### Ubuntu — 三线程

```
main thread
├── signal handler (SIGTERM/SIGINT → graceful shutdown)
├── heartbeat thread (每 1000ms PING，超时检测)
├── stats collector (每 5s 吞吐/延迟/丢包统计)
│
├── IO Thread 1: TUN → USB (出向)
│   epoll tunFd → read(IP包) → framePACK → write(epIN)
│
└── IO Thread 2: USB → TUN (入向)
    epoll epOUT → read(frame) → frameUNPACK → write(tunFd)
```

### Android — 双协程

```
VpnService (主线程)
├── startForeground(notification)
├── establish() TUN
│
├── Coroutine 1: TUN → USB (出向)
│   Dispatchers.IO: tunInputStream.read() → framePack → bulkTransfer(OUT)
│
└── Coroutine 2: USB → TUN (入向)
    Dispatchers.IO: bulkTransfer(IN) → frameUnpack → tunOutputStream.write()
```

---

## 八、开发路线图

### Phase 1: MVP 骨架 (8-10 天)

```
目标: Android 可以 ping 通局域网设备

Day 1-2: USB 连通性
├── RK3588: ConfigFS + FunctionFS 配置 + 验证程序
└── Android: USB Host API 枚举 + 权限 + 收发测试

Day 3-4: TUN + 帧协议
├── 两端帧编解码 (protocol/frame.h)
├── Ubuntu: TUN 创建 + 双线程收发
└── Android: VpnService + 双协程收发

Day 5-6: NAT + 连通性
├── Ubuntu: iptables MASQUERADE + TCPMSS
├── Android → ping 局域网设备验证
└── Android → HTTP 访问摄像头验证

Day 7-8: 稳定性
├── USB 热插拔测试
├── Android Doze 模式测试
└── 长时间运行泄漏检测

Day 9-10: 打包
├── systemd 服务单元
├── 构建系统确认
└── architecture.md 更新
```

### Phase 2: 可靠性加固 (4-6 天)

```
目标: 生产可用，自动恢复

├── 心跳保活 + 自动重连
├── systemd Restart=always + watchdog
├── Android 前台 Service + WakeLock
├── 结构化日志 + 统计
└── 24h 压力测试 + 修复
```

### Phase 3: 性能优化 (3-5 天)

```
目标: 降低延迟、提高利用率

├── 固定内存池 (减少分配)
├── 批量聚合 (减少 USB 事务)
├── Credit 流控 (防止溢出)
├── 线程优先级调优
└── 基准测试: 延迟 <1ms 目标
```

---

## 九、技术风险

### 高风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| RK3588 DWC3 USB Gadget 不稳定 | 无法建立 USB 通信 | 使用 BSP 推荐内核；准备 RNDIS 回退方案 |
| Android OEM ROM USB 权限限制 (MIUI/ColorOS) | 部分设备无法连接 | 完整权限申请流程；ROM 兼容性文档 |
| Android Doze 断流 | 通信间歇中断 | startForeground() + WakeLock + 省电白名单 |
| USB Bulk 实际带宽不足 | 达不到 4Mbps | 4Mbps 仅占 HS 带宽 0.8%，极低风险 |

### 中风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| MTU 不匹配导致分片 | 延迟增加 | 固定 MTU 1400 + TCP MSS Clamping |
| 帧 Magic 误匹配 | 丢帧 | Length 二次校验 |
| conntrack 表溢出 | 新连接失败 | 监控 + 按需增大限制 |
| 交叉编译 ARM64 问题 | 无法部署 | CMake toolchain 预先配置 |

---

## 十、明确弃用的设计（含原因）

| 弃用设计 | 原因 |
|----------|------|
| io_uring | 对 FunctionFS 字符设备收益极低，epoll 在 4Mbps 下充分够用 |
| USB 3.0 Bulk Streams | Android USB Host API 不暴露此能力，需 root + 自定义内核驱动 |
| 零拷贝 (TUN ↔ USB splice) | TUN 和 FunctionFS 之间不支持 splice，需修改内核驱动 |
| 应用层 CRC | USB Bulk 已有 CRC16，额外 CRC 只检测软件 bug |
| 分片重组协议 | USB 一次 Bulk Transfer 可承载 1500 字节 IP 包，无需分片 |
| StreamID 多路复用 | 点对点单流场景，后续多设备时再引入 |

---

## 十一、项目文件规划

```
TUN_NAT_HUB/
├── CLAUDE.md
├── docs/
│   └── architecture.md              ← 本文件
├── protocol/
│   └── frame.h                      ← 共享帧格式定义
├── android/
│   └── app/src/main/java/com/tunnathub/
│       ├── TunNatVpnService.kt      ← VpnService 核心
│       ├── UsbBridge.kt             ← USB 收发 + 帧编解码
│       ├── HeartbeatManager.kt      ← 心跳保活
│       └── MainActivity.kt          ← 控制界面
├── ubuntu/
│   ├── CMakeLists.txt
│   ├── src/
│   │   ├── main.cpp                 ← 入口 + 信号处理
│   │   ├── usb_gadget.cpp/.h        ← FunctionFS 管理
│   │   ├── tun_iface.cpp/.h         ← TUN 设备管理
│   │   ├── frame.cpp/.h             ← 帧编解码
│   │   └── heartbeat.cpp/.h         ← 心跳 + 统计
│   ├── scripts/
│   │   ├── setup_gadget.sh          ← USB Gadget 初始化
│   │   └── setup_nat.sh             ← NAT + MSS 配置
│   └── config/
│       └── tun_nat_hub.service      ← systemd unit
└── scripts/
    ├── build_all.sh
    └── deploy_ubuntu.sh
```

---

## 十二、关键设计决策表

| 决策 | 选择 | 理由 |
|------|------|------|
| 隧道层 | TUN (L3 IP) | 比 TAP (L2) 简单，无需处理 ARP/DHCP |
| USB 框架 | ConfigFS + FunctionFS | Linux 内核标准，无需内核模块 |
| 帧协议 | 4-byte 头 (Magic + Length) | 极简，零解析开销 |
| Android VPN | VpnService.Builder | 无 root，Play Store 合法 |
| 语言 Android | Kotlin + 协程 | 官方语言，协程天然匹配收发模型 |
| 语言 Ubuntu | C++17 + pthread | 系统级性能，零外部依赖 |
| IO 模型 Ubuntu | epoll | 4Mbps 下充分，io_uring 收益极低 |
| NAT 策略 | MASQUERADE SNAT | 内核级，零用户态开销 |
| MTU | 1400 | 减少分片，TCP MSS Clamping 配合 |
| 守护 Ubuntu | systemd | 自动启动 + 崩溃重启 |
