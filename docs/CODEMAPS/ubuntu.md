# Ubuntu 服务端代码地图

> 最后更新: 2026-06-28 | 版本: v1.1.0 (v5 架构) | 语言: C++17 + Python 3

## 文件索引

```
ubuntu/
├── CMakeLists.txt                ← CMake 构建 (目标: usb_tund)
├── src/
│   ├── main.cpp                  ← 守护进程入口 (v5: TUN↔TTY 桥接)
│   ├── tun_iface.cpp / .h        ← TUN 虚拟网卡封装 (RAII)
│   ├── usb_gadget.cpp / .h       ← USB FunctionFS Gadget (备用方案)
│   └── heartbeat.cpp / .h        ← 心跳管理器 + 统计
├── scripts/
│   ├── setup_gadget.sh           ← g_serial 内核模块加载
│   └── setup_nat.sh              ← TUN 接口 + iptables NAT 配置
├── config/
│   ├── tun_nat_hub.service       ← systemd daemon 单元
│   └── tun_web.service           ← systemd web panel 单元
└── web_panel.py                  ← Python Web 配置面板 (:8080)
```

## 架构分层

```
┌─────────────────────────────────────────┐
│  Management Layer                        │
│  web_panel.py                            │
│  ├── HTTP Server (:8080, 纯 stdlib)      │
│  ├── 4 Tab: Overview/Config/Network/Help │
│  ├── REST API: heartbeat/config/forward  │
│  └── iptables 直接调用 (子进程)           │
├─────────────────────────────────────────┤
│  Daemon Layer (v5)                       │
│  main.cpp                                │
│  ├── Thread 1: TUN→TTY (帧封装+发送)      │
│  ├── Thread 2: TTY→TUN (帧解包+写入)      │
│  ├── Thread 3: TCP Ping Server (:9999)   │
│  └── Main Thread: CAS 自动重连            │
├─────────────────────────────────────────┤
│  Abstraction Layer                       │
│  ├── TunIface (tun_iface.cpp)            │
│  │   └── RAII: open/readPacket/writePacket│
│  ├── UsbGadget (usb_gadget.cpp) [备用]    │
│  │   └── FunctionFS + ConfigFS stack     │
│  └── HeartbeatManager (heartbeat.cpp)     │
│      └── PING/PONG + 原子计数器 Stats     │
├─────────────────────────────────────────┤
│  Protocol                                │
│  protocol/frame.h                        │
│  ├── Magic=0x544E, Payload 0-2048B       │
│  ├── framePack() / frameUnpack()         │
│  └── 特殊帧: Heartbeat(Len=0), Credit(2) │
├─────────────────────────────────────────┤
│  Kernel                                  │
│  ├── g_serial (use_acm=0) → /dev/ttyGS0  │
│  ├── CONFIG_TUN → /dev/net/tun           │
│  ├── iptables (MASQUERADE + DNAT)        │
│  └── /proc/sys/net/ipv4/ip_forward       │
└─────────────────────────────────────────┘
```

## 关键文件详解

### 1. [main.cpp](../ubuntu/src/main.cpp) — 守护进程入口 (v5 架构)

**v5 架构核心**: 使用 g_serial TTY (`/dev/ttyGS0`) 而非 FunctionFS，单一文件描述符双工 IO。

**启动流程**:
```
1. 打开 /dev/ttyGS0 (30 次重试，每次 1s)
2. cfmakeraw() → VTIME=0, VMIN=0 (非阻塞零延迟)
3. TunIface::create("tun_hub", "10.0.0.1/24")
4. 启动 Thread 1: tunToTty (TUN read → framePack → TTY write)
5. 启动 Thread 2: ttyToTun (TTY read → frameUnpack → TUN write)
6. 启动 Thread 3: tcpPingServer (accept on 10.0.0.1:9999)
7. Main Thread: 监控 gTtyFd, CAS 自动重连
```

**线程模型**:
```
                  gTtyFd (std::atomic<int>)
                  CAS protected
                  ↓              ↓
    Thread 1: tunToTty    Thread 2: ttyToTun
    ┌──────────────┐      ┌──────────────┐
    │ TUN.read()   │      │ TTY.read()   │
    │ framePack()  │      │ ring buffer  │
    │ TTY.write()  │      │ frameUnpack()│
    │ heartbeat    │      │ TUN.write()  │
    │   PING 1s    │      │ PONG reply   │
    └──────────────┘      └──────────────┘
           ↓                      ↓
    Thread 3: tcpPingServer
    ┌──────────────┐
    │ accept()     │
    │ close()      │
    └──────────────┘
    (RTT measurement)
```

**关键参数**:
```
MTU:           1400
TTY 模式:      raw, non-blocking (VTIME=0, VMIN=0)
心跳间隔:      1000ms
心跳超时:      3000ms
Ring Buffer:   FRAME_MAX_LEN * 2 = 4104 bytes
TCP Ping Port: 10.0.0.1:9999
统计日志:      每 5s 打印一次
```

**CAS 自动重连** (防竞态):
```cpp
int expected = currentFd;
if (gTtyFd.compare_exchange_strong(expected, -1)) {
    // 成功将 fd 置为 -1，IO 线程看到 -1 会退出
    close(currentFd);  // 安全关闭
}
// -1 是 IO 线程的退出信号
```

**心跳内嵌**: 心跳 PING 在 Thread 1 (tunToTty) 中发送 —— 不创建独立心跳线程，减少线程数。Thread 2 收到 PING 时立即回复 PONG。

### 2. [tun_iface.cpp / .h](../ubuntu/src/tun_iface.cpp) — TUN 虚拟网卡

**TunIface 类 (RAII)**:
```cpp
class TunIface {
    int fd_;  // /dev/net/tun 文件描述符
public:
    bool create(const std::string& name, const std::string& ip);
    ssize_t readPacket(uint8_t* buf, size_t len);
    ssize_t writePacket(const uint8_t* buf, size_t len);
    void close();
};
```

**实现细节**:
- `open("/dev/net/tun", O_RDWR)` → `ioctl(TUNSETIFF)` 创建接口
- Flags: `IFF_TUN | IFF_NO_PI` (纯 IP 包，无额外包头)
- 非阻塞模式: `fcntl(fd, F_SETFL, O_NONBLOCK)`
- IP 配置: `ioctl(SIOCSIFADDR)` + `ioctl(SIOCSIFFLAGS)` 设置地址和启用接口

### 3. [usb_gadget.cpp / .h](../ubuntu/src/usb_gadget.cpp) — USB Gadget (备用方案)

**注意**: 此文件在当前 v5 架构中**未使用**（v5 直接用 g_serial），保留作为 FunctionFS 备用方案。

**UsbGadget 类 (RAII)**:
```cpp
class UsbGadget {
    int ep1_fd_, ep2_fd_;  // Bulk IN/OUT 端点
public:
    bool init();  // ConfigFS 目录树 + 描述符
    ssize_t readBulk(uint8_t* buf, size_t len);
    ssize_t writeBulk(const uint8_t* buf, size_t len);
    void close();
};
```

**ConfigFS 目录树**:
```
/sys/kernel/config/usb_gadget/tun_nat_hub/
├── idVendor  (0x0BDA)
├── idProduct (0x8812)
├── strings/0x409/
│   ├── manufacturer
│   └── product
├── configs/c.1/
│   └── strings/0x409/configuration
└── functions/ffs.usb0/
```

### 4. [heartbeat.cpp / .h](../ubuntu/src/heartbeat.cpp) — 心跳管理器

**HeartbeatManager 类**:
```cpp
class HeartbeatManager {
    std::atomic<bool> linkUp_{false};
    std::chrono::steady_clock::time_point lastPing_, lastPong_;
public:
    bool isLinkUp() const;
    void onPingSent();
    void onPongReceived();
    Stats getStats() const;
};
```

**Stats 结构** (全原子):
```cpp
struct Stats {
    std::atomic<uint64_t> pingsSent{0};
    std::atomic<uint64_t> pongsReceived{0};
    std::atomic<uint64_t> bytesTx{0};
    std::atomic<uint64_t> bytesRx{0};
    std::atomic<uint32_t> reconnectCount{0};
};
```

### 5. [setup_gadget.sh](../ubuntu/scripts/setup_gadget.sh) — USB Gadget 配置

**作用**: 加载 g_serial 内核模块并配置 VID/PID 伪装

```bash
modprobe g_serial use_acm=0 use_obex=0 \
    idVendor=0x0BDA idProduct=0x8812
# 结果: /dev/ttyGS0 出现
```

**g_serial 参数**:
- `use_acm=0` → 禁用 ACM (CDC Abstract Control Model)，使用纯 Bulk (类似 OBEX)
- `use_obex=0` → 单 TTY 设备 (GS0)
- `idVendor=0x0BDA` → 伪装为 Realtek
- `idProduct=0x8812` → 伪装为 RTL8812AU (DJI RC 白名单已许可)

### 6. [setup_nat.sh](../ubuntu/scripts/setup_nat.sh) — NAT 配置

**作用**: 创建 TUN 接口 + 配置 iptables NAT 规则

```bash
# TUN 接口
ip tuntap add dev tun_hub mode tun
ip addr add 10.0.0.1/24 dev tun_hub
ip link set tun_hub up mtu 1400

# IP 转发
echo 1 > /proc/sys/net/ipv4/ip_forward

# SNAT (Android → LAN)
iptables -t nat -A POSTROUTING -s 10.0.0.0/24 -o end1 -j MASQUERADE

# FORWARD
iptables -A FORWARD -i tun_hub -o end1 -j ACCEPT
iptables -A FORWARD -i end1 -o tun_hub -m state --state ESTABLISHED,RELATED -j ACCEPT

# TCP MSS Clamp
iptables -A FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu
```

### 7. [web_panel.py](../ubuntu/web_panel.py) — Web 配置面板

**技术栈**: Python 3 纯标准库 (`http.server` + `json` + `subprocess`)

**页面结构**:
```
http://10.0.0.1:8080/
├── Tab 1: 概览 / 链路图
│   ├── 系统信息 (hostname, uptime, kernel)
│   ├── 链路状态 (USB: connected/disconnected)
│   ├── 实时带宽 (从 /sys/class/net/tun_hub/statistics)
│   └── ASCII 拓扑图
├── Tab 2: 配置
│   ├── TUN IP / LAN 网段 / MTU
│   └── 保存/加载配置 (JSON 文件持久化)
├── Tab 3: 网络 / 防火墙
│   ├── iptables 规则展示
│   ├── 端口转发管理 (DNAT)
│   └── 摄像头列表管理
└── Tab 4: 帮助
    ├── 快速参考
    └── 排障指南
```

**REST API**:
```
GET  /api/heartbeat        → {"usb":"connected","uptime":1234,"version":"1.1.0"}
GET  /api/config           → {"tun_ip":"10.0.0.1","lan_network":"192.168.144.0/24",...}
GET  /api/stats            → {"tx_bytes":123456,"rx_bytes":654321,"tx_mbps":4.2,...}
GET  /api/system           → {"hostname":"...","uptime":...,"memory":...}
GET  /api/network          → {"interfaces":[...],"iptables_rules":[...]}
POST /api/forward/add      → body: {"proto":"tcp","ext_port":8080,"dest_ip":"10.0.0.2","dest_port":80}
POST /api/forward/del      → body: {"proto":"tcp","ext_port":8080}
POST /api/camera/add       → body: {"name":"前视相机","url":"rtsp://..."}
POST /api/camera/del       → body: {"name":"前视相机"}
```

**安全注意**: 当前无认证（USB 物理连接为安全边界）。输入校验: 端口范围 1-65535，IP 正则匹配，协议仅 tcp/udp。

**配置持久化**: `/home/xlong/tun_nat_hub_config.json`

**带宽计算**:
```python
def _read_bandwidth(self):
    # 读取 /sys/class/net/tun_hub/statistics/{tx,rx}_bytes
    # 计算与上次的差值 / 时间间隔 = Mbps
```

## 数据流

```
DJI RC (Android)
    ↓ USB Bulk (g_serial)
/dev/ttyGS0
    ↓ read() [Thread 2: ttyToTun]
Ring Buffer (4104 bytes)
    ↓ 扫描 Magic=0x544E
frameUnpack()
    ↓ 提取 Payload
TUN fd write()
    ↓ /dev/net/tun
Linux 内核 IP 栈
    ↓ 路由 + MASQUERADE
eth0 → LAN 设备 (192.168.144.x)
```

**反向路径**:
```
LAN 设备 → eth0 → 内核 IP 栈 → /dev/net/tun → TUN read() [Thread 1] → framePack() → /dev/ttyGS0 write() → USB Bulk → DJI RC
```

## 构建

```bash
cd ubuntu
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)
# 产物: build/usb_tund
```

**交叉编译 (ARMv7/V3s)**:
```bash
cd ubuntu
mkdir build_v3s && cd build_v3s
cmake .. \
    -DCMAKE_TOOLCHAIN_FILE=../cmake/toolchain-armv7-musl.cmake \
    -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)
```

**CMake 配置**:
- C++17 (`CMAKE_CXX_STANDARD 17`)
- 源文件: `main.cpp` + `tun_iface.cpp` (不含 usb_gadget.cpp)
- 头文件: `../protocol` (frame.h)
- 链接: `Threads::Threads`
- ARM64 检测: `CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64|arm"`

## systemd 服务

**tun_nat_hub.service** — 守护进程:
```ini
[Unit]
Description=TUN NAT Hub Daemon
After=network.target

[Service]
Type=simple
ExecStartPre=/usr/local/bin/setup_gadget.sh
ExecStartPre=/usr/local/bin/setup_nat.sh
ExecStart=/usr/local/bin/usb_tund
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**tun_web.service** — Web 面板:
```ini
[Unit]
Description=TUN NAT Hub Web Panel
After=tun_nat_hub.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/local/bin/web_panel.py
Restart=always

[Install]
WantedBy=multi-user.target
```
