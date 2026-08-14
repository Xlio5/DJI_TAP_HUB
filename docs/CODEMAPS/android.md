# Android 代码地图

> 最后更新: 2026-06-28 | 版本: v1.1.0 | 语言: Kotlin + Jetpack Compose

## 文件索引

```
android/app/src/main/java/com/tunnathub/app/
├── MainActivity.kt              ← 主界面 (Compose UI + 状态管理 + API 客户端)
├── BootReceiver.kt              ← 开机自启 + USB 热插拔广播
├── PlayerScreen.kt              ← RTSP 播放器 Composable (独立页面)
├── RtspPlayer.kt                ← 外部播放器启动器 (Intent)
├── service/
│   └── TunNatVpnService.kt      ← VPN Service (TUN 接口 + 路由 + 前台通知)
├── usb/
│   └── UsbBridge.kt             ← USB 通信桥 (双协程 + 帧收发 + 心跳)
└── proto/
    └── FrameCodec.kt            ← 帧编解码器 (Magic=0x544E, 与 frame.h 同步)
```

## 架构分层

```
┌─────────────────────────────────────────┐
│  UI Layer (Compose)                     │
│  MainActivity.kt                        │
│  ├── 侧边栏 (VPN状态/心跳/带宽/摄像头)     │
│  ├── RTSP 播放器 (EasyPlayer SDK)        │
│  ├── 端口转发管理 (4字段表单)              │
│  └── 延迟测试 (TCP connect to :9999)     │
├─────────────────────────────────────────┤
│  Service Layer                          │
│  TunNatVpnService.kt                    │
│  ├── VpnService.Builder → TUN 接口       │
│  ├── protect() → 绕过 VPN 的 socket      │
│  └── 前台通知 + 生命周期管理              │
├─────────────────────────────────────────┤
│  Transport Layer                        │
│  UsbBridge.kt                           │
│  ├── USB Host API (UsbManager)           │
│  ├── TUN→USB 协程 (IN endpoint)          │
│  ├── USB→TUN 协程 (OUT endpoint)         │
│  ├── 帧编解码 (FrameCodec)               │
│  └── 心跳 PONG 自动回复                  │
├─────────────────────────────────────────┤
│  Protocol Layer                         │
│  FrameCodec.kt                          │
│  ├── 编码: IP包 → Magic+Len+Payload      │
│  ├── 解码: 字节流 → UnpackResult         │
│  └── 缓冲池: 16×2052B 复用               │
├─────────────────────────────────────────┤
│  Platform                               │
│  ├── Android 8+ (API 26)                 │
│  ├── Kotlin 1.9.24 + Compose BOM 2024.05│
│  └── EasyPlayer NDK (arm64-v8a)          │
└─────────────────────────────────────────┘
```

## 关键文件详解

### 1. [MainActivity.kt](../android/app/src/main/java/com/tunnathub/app/MainActivity.kt) — 主界面

**职责**: 所有 UI + 状态管理 + HTTP API 客户端

**状态变量** (Compose `mutableStateOf`):
```
isVpnActive       — VPN 是否运行
isUsbConnected    — USB 是否已连接
lastHeartbeat     — 最近心跳时间戳
heartbeatHistory  — 最近 3 次心跳结果 (Boolean 列表)
bandwidthTx/Rx    — 实时带宽 (bps)
latencyMs         — 最近延迟测试结果
cameras           — 摄像头列表 (名称 + RTSP URL)
forwardRules      — 端口转发规则列表
```

**UI 结构**:
- `Scaffold` + `NavigationDrawer` 侧边栏布局
- 侧边栏: VPN 状态卡片 → USB 连接状态 + 心跳指示灯(3 点) → 实时带宽(Tx/Rx Mbps) → 摄像头列表 → 端口转发 → 延迟测试按钮 → 版本号
- 主内容区: RTSP 播放器 (SurfaceView)
- 暗色主题: `Color(0xFF0F172A)` 背景

**HTTP API 客户端** (调用 Linux Web Panel):
```
GET  /api/heartbeat       → 心跳轮询 (1s 间隔)
GET  /api/stats           → 带宽数据
POST /api/forward/add     → 添加端口转发
POST /api/forward/del     → 删除端口转发
POST /api/camera/add      → 添加摄像头
POST /api/camera/del      → 删除摄像头
GET  /api/config          → 获取配置
```

### 2. [TunNatVpnService.kt](../android/app/src/main/java/com/tunnathub/app/service/TunNatVpnService.kt) — VPN 服务

**职责**: 创建 TUN 虚拟网卡 + 管理 VPN 生命周期

**关键参数**:
```
TUN IP:    10.0.0.2/24
路由:      192.168.144.0/24 (LAN 设备)
           10.0.0.0/24     (隧道内网)
MTU:       1400
DNS:       8.8.8.8 (占位，不用于隧道)
```

**生命周期**:
1. `onCreate()` → `VpnService.Builder` 配置地址/路由/MTU
2. `establish()` → 获取 TUN fd (`ParcelFileDescriptor`)
3. `protect()` → 保护 USB socket 不被 VPN 路由（避免循环）
4. 启动 `UsbBridge` — 传入 TUN fd
5. `onDestroy()` → 关闭 UsbBridge → 关闭 TUN fd

**USB 连接重试**: 三重指数退避 (1s → 2s → 4s)，最多重试 3 次

### 3. [UsbBridge.kt](../android/app/src/main/java/com/tunnathub/app/usb/UsbBridge.kt) — USB 通信桥

**职责**: USB Bulk 双工传输 + 心跳响应

**协程模型**:
```
Coroutine 1 (tunToUsb):     TUN.read() → FrameCodec.encode() → USB OUT endpoint (bulkTransfer)
Coroutine 2 (usbToTun):     USB IN endpoint (bulkTransfer) → FrameCodec.decode() → TUN.write()
```

**关键设计**:
- CDC ACM Bulk 端点: 自动查找 IN/OUT 端点（方向判断）
- DTR/RTS 激活: `connection.controlTransfer(0x22, 0x01)` 唤醒 g_serial TTY
- 心跳 PONG: 检测到 `UnpackResult.Heartbeat` 时直接回复 PONG，不经过 TUN
- 断开检测: `bulkTransfer` 返回负数 → 标记 `isConnected = false` → VPN Service 重连
- 超时: 10ms (非阻塞轮询)
- 缓冲池: 16 × 2052B 复用，减少 GC 压力

**USB 设备筛选**:
```
VID: 0x0BDA (Realtek)
PID: 0x8812 (RTL8812AU)
→ DJI RC PLUS 2 白名单已许可此 VID/PID
```

### 4. [FrameCodec.kt](../android/app/src/main/java/com/tunnathub/app/proto/FrameCodec.kt) — 帧编解码

**帧格式** (与 `protocol/frame.h` 完全一致):
```
Byte 0:    0x54 ('T')
Byte 1:    0x4E ('N')       → Magic = 0x544E
Byte 2-3:  Payload Length   (big-endian, 0-2048)
Byte 4+:   Payload          (raw IP packet 或 heartbeat)
```

**特殊帧**:
- `length = 0` → Heartbeat (PING/PONG)
- `length = 2` → Credit frame (Phase 3 预留)

**UnpackResult 密封类**:
```kotlin
sealed class UnpackResult {
    data class Data(val payload: ByteArray) : UnpackResult()
    object Heartbeat : UnpackResult()
    object Credit : UnpackResult()
    object MagicMismatch : UnpackResult()
    data class Error(val message: String) : UnpackResult()
}
```

**缓冲池**:
```kotlin
class BufferPool(size: Int, bufferSize: Int)
// 复用 16 个 ByteArray(2052)，避免频繁分配
```

### 5. [BootReceiver.kt](../android/app/src/main/java/com/tunnathub/app/BootReceiver.kt) — 开机自启

**监听的广播**:
- `BOOT_COMPLETED` → 启动 VPN Service
- `UsbManager.ACTION_USB_DEVICE_ATTACHED` → USB 插入时重启 VPN
- `UsbManager.ACTION_USB_DEVICE_DETACHED` → USB 拔出时停止 VPN

**开机自启策略**: 30s 内每 1s 轮询 USB 设备列表 → 发现目标设备 → 启动 VPN

### 6. [PlayerScreen.kt](../android/app/src/main/java/com/tunnathub/app/PlayerScreen.kt) — RTSP 播放器

**职责**: EasyPlayer NDK 的原生 SurfaceView 封装

**参数**:
- 缓冲时间: 1ms (低延迟模式)
- 传输协议: TCP (RTSP over TCP 穿透 TUN 隧道)
- 硬解码: 开启

### 7. [RtspPlayer.kt](../android/app/src/main/java/com/tunnathub/app/RtspPlayer.kt) — 外部播放器

**职责**: 通过 Android Intent 调用外部播放器 (EasyPlayer / VLC)

**场景**: 绕过 VPN EPERM 问题（部分播放器无法 bind TUN 接口）

## 数据流

```
RTSP 摄像头 (192.168.144.100:554)
    ↓ RTSP/TCP
Linux 板 eth0
    ↓ NAT MASQUERADE
Linux TUN (10.0.0.1)
    ↓ g_serial /dev/ttyGS0
USB Bulk 端点
    ↓ UsbBridge.usbToTun 协程
    ↓ FrameCodec.decode()
Android TUN fd (10.0.0.2)
    ↓ VpnService.protect()
App Socket (EasyPlayer)
    ↓ SurfaceView
DJI RC PLUS 2 屏幕
```

## 构建

```bash
cd android
./gradlew assembleDebug      # Debug APK
./gradlew assembleRelease    # Release APK (需签名)
```

**构建配置**:
- AGP 8.5.0, Gradle 8.5
- compileSdk 34, minSdk 26, targetSdk 34
- ABI: arm64-v8a only
- EasyPlayer NDK .so: `app/src/main/jniLibs/arm64-v8a/`
