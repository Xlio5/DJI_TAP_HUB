# TUN_NAT_HUB 全志 V3s 移植 — 产品需求文档

> 来源项目: TUN_NAT_HUB (RK3588)  
> 目标平台: 全志 Allwinner V3s (ARM Cortex-A7, Cortex-M7 可选)  
> 编制日期: 2026-06-24

---

## 一、项目背景与目标

### 1.1 现状

TUN_NAT_HUB v1.1.0 已在 **RK3588 (Rock 5C)** 上稳定运行，实现了 DJI RC PLUS 2 遥控器通过 USB 线缆访问局域网 IP 摄像头的功能。核心架构：

```
DJI RC (Android) ←─USB Bulk (g_serial)──→ RK3588 (Ubuntu)
    ↑                                        ↑
  TUN 10.0.0.2                           TUN 10.0.0.1
VpnService                                SNAT → LAN
```

### 1.2 移植动机

| 维度 | RK3588 (Rock 5C) | 全志 V3s | 分析 |
|------|-----------------|----------|------|
| 芯片定位 | 高性能 AIoT 旗舰 | 低成本 IPC 主控 | V3s 成本约为 RK3588 的 1/10~1/20 |
| 功耗 | 10~15W | 1~3W | V3s 可用无人机电池长时间供电 |
| 体积 | 85×56mm (开发板) | 芯片级集成 DDR2 | V3s 可直接嵌入 DJI RC 外壳内 |
| 价格 | ~500-800 RMB | ~30-50 RMB | 大规模部署可行 |
| USB | DWC3 USB3.0 OTG | USB2.0 OTG (MUSB/EHCI) | 协议兼容，带宽满足 |
| 量产性 | 开发板 | QFP128 封装，SMT 批量 | V3s 成熟量产数年 |

### 1.3 目标

将 TUN_NAT_HUB 的 **服务端**（USB Gadget + TUN + NAT）完整移植到 Allwinner V3s，Android 端保持不变。达成：

- ✅ USB g_serial Bulk 通信（VID 0x0BDA PID 0x8812 伪装不变）
- ✅ TUN 虚拟网卡（10.0.0.1/24）+ NAT 转发
- ✅ Web 配置面板（Python，端口 8080）
- ✅ systemd/sysvinit 开机自启
- ✅ 硬件看门狗（V3s 内置 WDOG）

---

## 二、目标平台分析

### 2.1 全志 V3s 硬件规格

| 参数 | 值 | 对项目影响 |
|------|-----|-----------|
| CPU | ARM Cortex-A7, 1.2GHz (单核) | 编译需 `arm-linux-gnueabihf` toolchain |
| 内存 | 64MB DDR2 (片内集成) | 需控制内存占用，daemon 当前 ~2-4MB 可接受 |
| USB | 1× USB2.0 OTG (HS 480Mbps) | 需配置 dr_mode=peripheral |
| 以太网 | 1× 10/100M MAC (需外部 PHY) | LAN 口可达，或使用 SPI/RMII 以太网 |
| 存储 | SPI NOR/NAND + SDIO | 系统镜像通常 8-32MB |
| GPIO | 51 个 | USB ID 检测可用 |
| WDOG | 内置硬件看门狗 | 设备稳定性保障 |
| 编码器 | H.264 1080p@30fps | **可复用做视频流处理** |
| 音频 | ADC + Line Out | 本项目不用 |

### 2.2 软件环境约束

| 项目 | RK3588 当前 | V3s 目标 | 差异 |
|------|-----------|---------|------|
| OS | Ubuntu 22.04 (arm64) | Buildroot / Yocto | **无 apt，需手动构建 rootfs** |
| 内核 | 6.1 (mainline) | 5.2~6.1 (LicheePi Zero) | g_serial 和 TUN 均支持 |
| C 库 | glibc | musl 或 uClibc-ng | **musl 兼容性需要验证**，CMake 需适配 |
| Init | systemd | BusyBox init / sysvinit | **服务管理方式不同** |
| Python | Python 3.12 | Python 3.x (Buildroot 勾选) | web_panel.py 依赖纯标准库，兼容 |
| SSH | OpenSSH 服务端 | Dropbear | paramiko 兼容，SSH 方式不变 |
| 包管理 | apt | 无 | 所有依赖编译进 rootfs |
| 工具链 | g++ 13 (native) | arm-linux-gnueabihf-g++ 交叉编译 | CMake toolchain file |

### 2.3 关键风险

| 风险 | 等级 | 说明 | 缓解 |
|------|------|------|------|
| g_serial 驱动差异 | **中** | V3s 内核的 musb 驱动与 DWC3 行为不同 | 先用 `modprobe g_serial` 验证，失败则用 configfs |
| 64MB 内存不足 | **高** | daemon(4MB) + Python(8MB) + 内核(20MB) + 网络栈 | **必须裁剪** Buildroot 最小化 |
| USB OTG ID 引脚 | **中** | V3s 硬件设计需拉低 USB0-ID 到 GND | 与硬件工程师确认原理图 |
| musl vs glibc | **低** | CMake + C++17 完全标准 | pthread/网络均为 POSIX，musl 兼容 |
| 以太网 PHY 缺失 | **高** | 部分 V3s 板无以太网 PHY | 必须选用带 RMII PHY 的板（如 LicheePi Zero + ETH 底板） |
| Python 解释器 | **低** | Buildroot 内置 python3 支持 | web_panel.py 纯标准库，零 pip 依赖 |

---

## 三、功能需求（What）

### 3.1 核心功能（Phase 1）

**F1: USB Gadget (g_serial Bulk)**

```
模组加载: modprobe g_serial use_acm=0 use_obex=0 idVendor=0x0BDA idProduct=0x8812
结果: /dev/ttyGS0 出现，crw-rw-rw-
验证: DJI RC 端 UsbManager.deviceList 可见 VID:PID=0x0BDA:0x8812
```

**F2: TUN 虚拟网卡**

```
接口: tun_hub, IP 10.0.0.1/24, MTU 1400
内核: CONFIG_TUN=y (必须编译进内核)
创建: ip tuntap add dev tun_hub mode tun (或守护进程内部 ioctl)
```

**F3: IP 包转发 (Daemon)**

```
输入: 编译产物 usb_tund (ARMv7, 静态链接 musl)
行为: TUN↔TTY 双线程，帧协议 Magic=0x544E，心跳 1000ms
兼容: 与 Android 端 UsbBridge.kt + FrameCodec.kt 完全一致
```

**F4: NAT + 路由**

```
SNAT: iptables MASQUERADE 10.0.0.0/24 → LAN 网口 (eth0)
FORWARD: tun_hub ↔ eth0 双向
TCP MSS: 自动 clamp
ip_forward: /proc/sys/net/ipv4/ip_forward = 1
```

**F5: Web 配置面板**

```
语言: Python 3.x, 纯标准库
端口: 0.0.0.0:8080
功能: 概览/配置/网络/帮助 4 Tab, 笔记本页面本兼容
API: /api/heartbeat, /api/config, /api/forward/add, /api/forward/del
```

**F6: 端口转发 (DNAT)**

```
方向: 外网 → DJI RC
机制: iptables PREROUTING DNAT (end1 → 10.0.0.2)
管理: App 侧边栏 4 字段表单（协议/外网端口/DJI IP/目标端口）
```

**F7: TCP 延迟测试端口**

```
服务: tcpPingServer 线程
端口: 10.0.0.1:9999
行为: accept → close (仅测 TCP 握手 RTT)
```

### 3.2 非功能需求

| 需求 | 目标值 | 验证方法 |
|------|--------|----------|
| USB Bulk 延迟 | ≤ 10ms (p50 TCP RTT) | App "测延迟" 或 RK3588→Android nc |
| 吞吐量 | ≥ 20Mbps (USB 单向) | iperf3 10.0.0.1 ↔ 10.0.0.2 |
| 内存占用 | daemon ≤ 8MB, 系统总 ≤ 32MB | `free -m` |
| 启动时间 | ≤ 30s (上电→daemon 就绪) | `systemctl status` 或 `ps | grep usb_tund` |
| 崩溃恢复 | 自动重启 (≤ 5s) | 手动 `kill -9` daemon，检查重连 |
| 24h 稳定性 | 无内存泄漏，无 USB 断连 | `valgrind` 或 `/proc/pid/status` VmRSS 监控 |
| 看门狗 | 60s 不喂狗 → 硬件复位 | `echo 1 > /dev/watchdog` 测试 |

### 3.3 兼容性需求

- **Android APK 不改** — 使用现有 v1.1.0 APK 即可
- **帧协议不变** — `protocol/frame.h` 与 `FrameCodec.kt` 保持同步
- **VID/PID 不变** — 0x0BDA:0x8812 (RTL8812AU 伪装)
- **IP 规划不变** — 10.0.0.0/24 TUN 网段 + 192.168.88.0/24 LAN 网段

---

## 四、技术架构

### 4.1 整体数据流（不变）

```
DJI RC (Android, 不变)                 V3s (移植目标)
┌──────────────────────┐  USB Bulk     ┌─────────────────────┐
│ VpnService            │◄════════════►│ /dev/ttyGS0         │
│ TUN: 10.0.0.2/24     │  VID=0x0BDA  │ usb_tund (ARMv7)    │
│ Route: 192.168.88.0  │  PID=0x8812  │ TUN↔TTY 线程       │
│ UsbBridge.kt          │  帧: TN+Len  │ tcpPingServer :9999 │
└──────────────────────┘              │ web_panel.py :8080  │
                                       └─────────┬───────────┘
                                                  │ MASQUERADE
                                       ┌─────────▼───────────┐
                                       │ LAN 192.168.88.x    │
                                       └─────────────────────┘
```

### 4.2 V3s 软件栈

```
应用层:
├── /usr/local/bin/usb_tund       ← C++ 守护进程 (ARMv7 musl 静态链接)
├── /usr/local/bin/web_panel.py   ← Python 3.x Web 面板
├── /usr/local/bin/setup_gadget.sh ← g_serial 加载脚本
├── /usr/local/bin/setup_nat.sh   ← TUN + NAT 配置脚本
└── /etc/init.d/S99tun_nat_hub    ← sysvinit 启动脚本

内核层:
├── CONFIG_USB_GADGET=y
├── CONFIG_USB_G_SERIAL=m
├── CONFIG_TUN=y
├── CONFIG_NETFILTER=y (iptables)
└── musb (Mentor USB OTG) driver

硬件层:
├── USB0 OTG (PB6-PB7, ID pin PB8)
├── RMII Ethernet (PE0-PE9) — 需要 PHY 芯片 (如 IP101GR)
├── SPI NOR Flash (SPI0) — 系统镜像
└── WDOG — 硬件看门狗
```

### 4.3 CMake 交叉编译

```cmake
# toolchain-armv7-musl.cmake
SET(CMAKE_SYSTEM_NAME Linux)
SET(CMAKE_SYSTEM_PROCESSOR arm)
SET(CMAKE_C_COMPILER   arm-linux-gnueabihf-gcc)
SET(CMAKE_CXX_COMPILER arm-linux-gnueabihf-g++)
SET(CMAKE_FIND_ROOT_PATH /path/to/buildroot/output/host/arm-buildroot-linux-musleabihf/sysroot)
```

### 4.4 系统服务管理

V3s 使用 **BusyBox init**（非 systemd），服务脚本位于 `/etc/init.d/`：

```sh
#!/bin/sh
# /etc/init.d/S99tun_nat_hub — V3s 服务启动脚本
case "$1" in
  start)
    echo "Starting TUN_NAT_HUB..."
    /usr/local/bin/setup_gadget.sh
    /usr/local/bin/setup_nat.sh
    /usr/local/bin/usb_tund &
    /usr/local/bin/web_panel.py &
    ;;
  stop)
    killall usb_tund web_panel.py
    ;;
  restart)
    $0 stop; sleep 1; $0 start
    ;;
esac
```

---

## 五、开发计划

### Phase 0: 环境搭建（2-3 天）

| 任务 | 产出 | 工时 |
|------|------|------|
| 选型 V3s 开发板 (LicheePi Zero/自定义底板) | 硬件就绪 | 0.5d |
| 搭建 Buildroot 构建环境 (含交叉编译 toolchain) | 可编译 rootfs | 1d |
| 内核配置: 勾选 USB Gadget/Serial/TUN/Netfilter | `.config` 确认 | 0.5d |
| 制作最小系统镜像 (SPI NOR / SD 卡) | 系统能启动 | 0.5d |
| 验证 USB OTG Device 模式 (dmesg 确认 musb) | `ls /sys/class/udc/` | 0.5d |

### Phase 1: 核心移植（3-4 天）

| 任务 | 产出 | 工时 |
|------|------|------|
| **Task 1.1**: 编写 CMake toolchain file (armv7-musl) | 交叉编译可用 | 0.5d |
| **Task 1.2**: 交叉编译 + 修复 musl 兼容性问题 | `usb_tund` ARMv7 二进制 | 1d |
| **Task 1.3**: 修改 `setup_gadget.sh` 适配 V3s (无 modprobe -r 等问题) | g_serial 加载 | 0.5d |
| **Task 1.4**: 修改 `setup_nat.sh` 适配 V3s (网口名称可能是 eth0 非 end1) | TUN+NAT 配置 | 0.5d |
| **Task 1.5**: 编写 BusyBox init 启动脚本 (替代 systemd service) | 开机自启 | 0.5d |
| **Task 1.6**: 集成 web_panel.py (Buildroot 勾选 python3) | Web 面板运行 | 0.5d |

### Phase 2: 集成验证（2-3 天）

| 任务 | 产出 | 工时 |
|------|------|------|
| **Task 2.1**: USB 连通性验证 (DJI RC ↔ V3s) | UsbBridge 找到设备 | 1d |
| **Task 2.2**: TUN 数据通 ping 测试 (Android ↔ V3s) | RTT < 10ms | 0.5d |
| **Task 2.3**: NAT 验证 (Android ping 局域网设备) | ICMP 可达 | 0.5d |
| **Task 2.4**: RTSP 视频播放测试 | 画面正常，延迟 < 350ms | 0.5d |
| **Task 2.5**: Web 面板 + API 验证 (心跳/配置/转发) | 所有 API 返回 200 | 0.5d |

### Phase 3: 稳定性（2-3 天）

| 任务 | 产出 | 工时 |
|------|------|------|
| **Task 3.1**: 硬件看门狗集成 (+ 喂狗线程) | 崩溃自动复位 | 0.5d |
| **Task 3.2**: 24h 长时间压力测试 | VmRSS 不增长，USB 不断连 | 1d |
| **Task 3.3**: 重启/冷启动循环测试 (10 轮) | 每轮均成功 | 1d |
| **Task 3.4**: 性能基准测试 (带宽/延迟对比 RK3588) | 性能对比数据 | 0.5d |

### Phase 4: 文档与交付（1-2 天）

| 任务 | 产出 | 工时 |
|------|------|------|
| **Task 4.1**: 编写 V3s 部署手册 (docs/v3s-deploy.md) | 新人可操作 | 0.5d |
| **Task 4.2**: 编写 Buildroot defconfig | 可复现构建 | 0.5d |
| **Task 4.3**: 编写工具链安装/使用指南 | 开发者可编译 | 0.5d |
| **Task 4.4**: 知识回流 (Obsidian Vault) | 移植经验记录 | 0.5d |

---

## 六、文件修改清单

### 需要修改的文件

| 文件 | 修改内容 | 幅度 |
|------|----------|------|
| `ubuntu/CMakeLists.txt` | 新增 ARMv7 交叉编译选项 + linux-gnueabihf 检测 | 中 |
| `ubuntu/src/main.cpp` | 添加 WDOG 喂狗线程、可能的 musl 兼容 ifdef | 小 |
| `ubuntu/src/tun_iface.cpp` | 无修改（标准 POSIX） | 无 |
| `ubuntu/scripts/setup_gadget.sh` | 移除 `modprobe -r`（V3s 可能不支持卸载），添加内核版本检测 | 小 |
| `ubuntu/scripts/setup_nat.sh` | 网口检测优先级调整为 eth0 > end1（V3s 习惯），移除 systemd 依赖 | 小 |
| `ubuntu/web_panel.py` | 添加 iptables 路径检测 (V3s 可能 `iptables-legacy`) | 小 |
| `protocol/frame.h` | 无修改（C99+extern C，兼容 musl） | 无 |

### 新增的文件

| 文件 | 用途 |
|------|------|
| `ubuntu/cmake/toolchain-armv7-musl.cmake` | 交叉编译工具链定义 |
| `ubuntu/config/S99tun_nat_hub` | BusyBox init 启动脚本 |
| `configs/v3s_buildroot_defconfig` | Buildroot 配置（含必需包列表） |
| `docs/v3s-deploy.md` | V3s 部署文档 |
| `scripts/cross_build_v3s.sh` | 一键交叉编译脚本 |

### 不变的文件

整个 `android/` 目录、`protocol/frame.h`、`scripts/` 诊断脚本均无需修改。

---

## 七、验收标准

### 7.1 功能验收

| 测试项 | 预期 | 方法 |
|--------|------|------|
| ① USB 枚举 | DJI RC 上 UsbManager.deviceList 可见 VID=0x0BDA PID=0x8812 | App 日志 `找到设备` |
| ② USB 连接 | UsbBridge 双协程启动，日志显示 `USB 已连接` | logcat 关键字 |
| ③ VPN 建立 | TUN 接口 tun0: 10.0.0.2/24 Route 192.168.88.0/24 | `adb shell ip addr show tun0` |
| ④ 心跳 | App 显示 3 灯全绿 + 带宽显示 | 日志 `心跳 OK #N` |
| ⑤ 局域网 ping | Android ping 192.168.88.x 响应 ≤ 5ms | `adb shell ping -c 5 192.168.88.100` |
| ⑥ RTSP 视频 | 播放器正常拉流、无花屏、延迟 ≤ 300ms | 肉眼观察 + VLC 对比 |
| ⑦ 端口转发添加 | App 添加规则后 `iptables -t nat -L PREROUTING` 可见 | SSH 检查 |
| ⑧ 延迟测试 | 测 10 次 RTT，丢包 ≤ 1 | App "测延迟" 按钮 |
| ⑨ Web 面板 | 浏览器访问 :8080，4 Tab 正常 | curl + Chrome |
| ⑩ 冷启动 | 上电 30s 内 daemon 就绪，USB 可连接 | 断电重启验证 |

### 7.2 性能验收

| 指标 | RK3588 基准 | V3s 目标 |
|------|-----------|---------|
| TCP RTT (p50) | 3~6ms | ≤ 10ms |
| USB 吞吐 | 31Mbps | ≥ 15Mbps (USB2.0 HS) |
| daemon 内存 | 2~4MB | ≤ 8MB |
| 系统总内存 | ~500MB | ≤ 32MB |
| CPU 空载 | <1% | <5% |

### 7.3 稳定性验收

- 24h 运行 VmRSS 波动 ≤ 1MB
- 10 次冷启动 USB 100% 识别
- 硬件看门狗正常触发

---

## 八、待决策事项

| # | 问题 | 选项 | 建议 |
|---|------|------|------|
| D1 | V3s 开发板选型？ | ① LicheePi Zero + ETH 底板 ② 自定义 PCB | 开发阶段用 LicheePi Zero，量产转自定义 |
| D2 | 系统构建用 Buildroot 还是 Yocto？ | ① Buildroot (简单、快) ② Yocto (灵活、大) | **Buildroot** — V3s 社区成熟，镜像小 |
| D3 | 以太网 PHY 方案？ | ① RMII + IP101GR ② SPI 以太网 (ENC28J60) | **RMII + IP101GR** — 性能好，V3s 原生支持 |
| D4 | C 库用 musl 还是 uClibc-ng？ | ① musl ② uClibc-ng | **musl** — C++17 兼容性更好 |
| D5 | daemon 是否静态链接？ | ① 静态 (无依赖，大 ~2MB) ② 动态 (小，需 libc) | **静态链接** — rootfs 无需部署 C++ 标准库 |
| D6 | Python 还是 Lua 做 Web 面板？ | ① Python 3 (8MB 内存) ② Lua + lhttpd (2MB) | **先维持 Python** — 代码零修改；优化阶段可切 |

---

## 九、附录

### A. 全志 V3s 关键引脚

| 引脚 | 功能 | 说明 |
|------|------|------|
| PB6/PB7 | USB0-DM/DP | USB OTG 数据线 |
| PB8 | USB0-ID | 拉低 = Device 模式 |
| PE0-PE9 | RMII (ETH) | 需外接 25MHz 晶振 + PHY |
| PG0-PG13 | SDC0 (SD Card) | 系统启动介质 |
| PC0-PC3 | SPI0 (NOR Flash) | 替代启动介质 |
| PA0-PA1 | UART0 (Debug) | 调试串口 115200 8N1 |

### B. Buildroot 最小必需包

```
BR2_arm=y
BR2_cortex_a7=y
BR2_ARM_EABIHF=y
BR2_TOOLCHAIN_BUILDROOT_MUSL=y
BR2_PACKAGE_HOST_GDB=y
BR2_PACKAGE_PYTHON3=y
BR2_PACKAGE_IPTABLES=y
BR2_PACKAGE_DROPBEAR=y
BR2_ROOTFS_DEVICE_CREATION_DYNAMIC_EUDEV=y
CONFIG_USB_G_SERIAL=m
CONFIG_TUN=y
CONFIG_NETFILTER_XTABLES=y
CONFIG_NF_NAT=y
CONFIG_NF_CONNTRACK=y
CONFIG_IP_NF_IPTABLES=y
CONFIG_IP_NF_NAT=y
CONFIG_WATCHDOG=y
```

### C. RK3588 vs V3s 对比速查

| 项目 | RK3588 | V3s | 影响 |
|------|--------|-----|------|
| 架构 | ARMv8.2-A (A76+A55) | ARMv7-A (A7) | toolchain 从 aarch64 → armv7 |
| 内核 | 6.1 mainline | 5.2~6.1 | USB gadget 配置方式可能不同 |
| USB 控制器 | DWC3 | MUSB | g_serial 参数可能不同 |
| 内存 | 4GB+ | 64MB | Python 内存需监控 |
| 网络接口名 | end1 | eth0 | setup_nat.sh 网口检测已覆盖 |
| 系统 | Ubuntu | Buildroot | 服务管理方式变化 |
| 编译 | 本地编译 | 交叉编译 | 需 CMake toolchain file |
