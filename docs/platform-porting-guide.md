# TUN_NAT_HUB RK3588 核心操作手册

> 提取日期: 2026-06-13  
> 目标: 将已验证的核心组件移植到其他 Linux 平台（ARM64/x86）

---

## 一、核心组件清单

| 文件 | 部署路径 | 用途 |
|------|----------|------|
| `bin/usb_tund` | `/usr/local/bin/` | 守护进程（ELF ARM64） |
| `bin/setup_gadget.sh` | `/usr/local/bin/` | USB Gadget 初始化（开机调用） |
| `bin/setup_nat.sh` | `/usr/local/bin/` | TUN + NAT + Forward 配置（开机调用） |
| `systemd/tun_nat_hub.service` | `/etc/systemd/system/` | systemd 服务单元 |
| `boot/rock-5c-usb-otg.dtbo` | `/boot/dtb/rockchip/overlay/` | USB-C OTG Device 模式 overlay |
| `boot/armbianEnv.txt` | `/boot/` | 追加 `overlays=rock-5c-usb-otg` |
| `src/` | 任意目录 | 源码（C++17，CMake） |
| `protocol/frame.h` | 编译路径 | 共享帧协议头文件 |

备份包: `backup/tun_nat_hub_backup.tar.gz` (528KB)

---

## 二、架构原理

```
Android (USB Host)                    RK3588 (USB Gadget/Device)
 ┌──────────────┐                      ┌─────────────────────┐
 │  VpnService   │    USB Bulk IN      │  /dev/ttyGS0        │
 │  TUN:         │◄══════════════════►│  (g_serial          │
 │  10.0.0.2/24  │   (ep1 OUT)    (ep2│   use_acm=0)        │
 │               │    ep81 IN)         │                     │
 │  路由:        │                      │  usb_tund:          │
 │  192.168.88.0 │                      │   TUN↔TTY 双线程   │
 │  /24          │                      │   心跳 1000ms      │
 └──────────────┘                      └────────┬────────────┘
                                                │
                                       ┌────────▼────────────┐
                                       │  tun_hub:           │
                                       │  10.0.0.1/24       │
                                       │  MASQUERADE SNAT    │
                                       │  → end1/eth0        │
                                       └────────┬────────────┘
                                                │
                                       ┌────────▼────────────┐
                                       │  局域网 (192.168.88.x)│
                                       │  摄像头/NAS/PC       │
                                       └─────────────────────┘
```

### 数据流

```
Android App → tun0(10.0.0.2) → 路由捕获(192.168.88.0/24)
  → tunFd.read() → framePack(4B头+IP包) → USB bulkTransfer(OUT ep01)
  → RK3588 /dev/ttyGS0 → frameUnpack → tun_hub write()
  → 内核路由 → MASQUERADE SNAT → end1 → 局域网设备

回程: 局域网 → conntrack DNAT → tun_hub → framePack → USB bulkTransfer(IN ep81)
  → Android tunFd.write() → 内核交付给 App
```

---

## 三、移植步骤（新平台）

### 3.1 前置条件

- Linux 内核 ≥ 5.10，开启以下内核选项：
  ```
  CONFIG_USB_GADGET=y
  CONFIG_USB_CONFIGFS=y
  CONFIG_USB_F_FS=y (备用)
  CONFIG_USB_G_SERIAL=m (或 builtin)
  CONFIG_TUN=y
  ```
- USB Device Controller (UDC) 可用: `ls /sys/class/udc/`
- 至少一个物理网口（用于 NAT 出向）
- 编译工具: CMake 3.16+, g++ 9+, pthread

### 3.2 步骤

```bash
# 1. 解压备份包
tar xzf tun_nat_hub_backup.tar.gz -C /

# 2. 确认文件到位
ls -la /usr/local/bin/usb_tund
ls -la /usr/local/bin/setup_gadget.sh
ls -la /usr/local/bin/setup_nat.sh
ls -la /etc/systemd/system/tun_nat_hub.service

# 3. 修改 setup_gadget.sh 中的 vid/pid 如有冲突
# 4. 确认 setup_nat.sh 的 LAN 网口自动检测正确
#    默认会自动选 end1 > eth0 > en*

# 5. 如果是 ARM 平台但非 rock-5c：
#    - 删除 /boot/armbianEnv.txt 中的 overlays=rock-5c-usb-otg 行
#    - 删除 /boot/dtb/rockchip/overlay/rock-5c-usb-otg.dtbo
#    - 手动确保 USB UDC 配置为 device/peripheral 模式
#    - 方法: 查 DTS 中 dr_mode 是否为 "peripheral" 或 "otg"

# 6. 启用开机自启
systemctl daemon-reload
systemctl enable tun_nat_hub
systemctl start tun_nat_hub

# 7. 验证
systemctl status tun_nat_hub
ls /dev/ttyGS0
ip addr show tun_hub

# 8. 编译源码（如需修改）
cd /path/to/src && cmake -B build && cmake --build build -- -j$(nproc)
```

### 3.3 x86_64 平台注意事项

- 重新编译 daemon: `cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build`
- 确认目标机器的 UDC 名称：`ls /sys/class/udc/`
- g_serial 参数可通过 `modinfo g_serial` 查看
- 如无 `/dev/ttyGS0`，可用 configfs 创建自定义 Gadget

---

## 四、关键配置

### 4.1 USB Gadget (setup_gadget.sh)

```bash
modprobe g_serial use_acm=0 use_obex=0 idVendor=0x2207 idProduct=0x0010
```

- `use_acm=0` — 纯 Bulk 管道模式，非 CDC ACM（免握手机制）
- `use_obex=0` — 无 OBEX 协议
- `idVendor=0x2207 / idProduct=0x0010` — 自定义 VID/PID（与 Android 端 device_filter.xml 对应）

### 4.2 TUN + NAT (setup_nat.sh)

```bash
# TUN MTU 1400，低延迟队列 (qlen=10, pfifo)
# iptables MASQUERADE: 10.0.0.0/24 → LAN 网口
# FORWARD: tun_hub ↔ LAN 双向
# TCP MSS Clamping
```

### 4.3 systemd 服务

```
ExecStartPre=setup_gadget.sh   # 加载 g_serial
ExecStartPre=setup_nat.sh      # 配置 TUN+NAT
ExecStart=usb_tund             # 守护进程
Restart=always
```

### 4.4 守护进程架构 (v5)

```
主线程: 打开 /dev/ttyGS0 → gTtyFd(原子变量)
IO-1 (TUN→TTY): read TUN → framePack → write gTtyFd（含心跳）
IO-2 (TTY→TUN): read gTtyFd → frameUnpack → write TUN
主循环: 检测 gTtyFd 断开 → 自动重连 → 更新 gTtyFd
```

### 4.5 帧协议 (protocol/frame.h)

```
 0  1  2  3
[Magic 0x54 0x4E][Length 2B BE][Payload N bytes]
- Magic: "TN" = 0x544E
- Length=0: 心跳帧(PING/PONG)
- Length=2: Credit帧(Phase 3预留)
- Length≤2048: IP载荷
```

### 4.6 DTB Overlay（仅 rock-5c）

```dts
target-path = "/usbdrd3_0/usb@fc000000";
__overlay__ { dr_mode = "peripheral"; status = "okay"; };
```

将 USB-C 的 DWC3 控制从 host 模式切换到 peripheral/gadget 模式。

---

## 五、Android 端配置

Android 端核心文件位于 `android/app/src/main/java/com/tunnathub/app/`：

| 文件 | 用途 |
|------|------|
| `service/TunNatVpnService.kt` | VpnService：建立 TUN (MTU 1400, 路由 192.168.88.0/24) |
| `usb/UsbBridge.kt` | USB Host API 双协程收发 |
| `proto/FrameCodec.kt` | 帧编解码（与 frame.h 一致） |
| `MainActivity.kt` | 主界面：VPN 控制 + 播放器 |
| `BootReceiver.kt` | 开机自启 + USB 热插拔 |
| `PlayerScreen.kt` | EasyPlayer 嵌入式播放器 |

### AndroidManifest.xml 关键项

```xml
<uses-feature android:name="android.hardware.usb.host" android:required="true" />
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.BIND_VPN_SERVICE" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
```

---

## 六、故障排查

| 症状 | 可能原因 | 检查命令 |
|------|----------|----------|
| daemon 启动失败 | /dev/ttyGS0 不存在 | `ls /dev/ttyGS0`, `lsmod | grep g_serial` |
| RX=0 | Android 端 USB 未授权/未连接 | `dumpsys usb | grep -A5 8711` |
| ping 不通 | FORWARD 规则缺失 | `iptables -L FORWARD -n -v` |
| TUN 无数据 | TUN 接口状态 DOWN | `ip link show tun_hub` |
| UDC 不可用 | DTB dr_mode=host | `cat /sys/class/udc/*/state` |

### 快速诊断脚本

```bash
#!/bin/bash
echo "=== 守护进程 ==="; systemctl is-active tun_nat_hub
echo "=== TTY ==="; ls /dev/ttyGS0
echo "=== TUN ==="; ip addr show tun_hub | grep inet
echo "=== NAT ==="; iptables -t nat -L POSTROUTING -n | grep 10.0.0
echo "=== FORWARD ==="; iptables -L FORWARD -n | grep tun_hub
echo "=== UDC ==="; cat /sys/class/udc/*/state 2>/dev/null
```

---

## 七、已验证的硬件组合

| Server | Android | USB | 延迟 | 吞吐 |
|--------|---------|-----|------|------|
| RK3588 (rock-5c) | 小米 (MIUI, Android 14) | USB-C→USB-C | 2.7ms ping | 31Mbps TCP |

不支持: DJI RC PLUS 2 (Android 11, USB Host API 被系统限制)
