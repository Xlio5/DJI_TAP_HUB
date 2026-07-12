# V3s 全新部署指南

> TUN_NAT_HUB — 将 Allwinner V3s (ARMv7) 作为 USB NAT 网关，DJI RC 通过 USB Bulk 透传访问 LAN 设备。

## 前置条件

| 条件 | 说明 |
|------|------|
| **V3s 系统** | Buildroot 制作的 rootfs，kernel 需含 `g_serial` 模块 |
| **网络** | V3s eth0 通过 DHCP 获取 LAN IP（如 192.168.144.x），能出外网 |
| **开发机** | 需 `arm-linux-gnueabihf-g++` 交叉编译工具链 |
| **访问方式** | SSH: `root@<v3s_ip>` 密码 `root` |

---

## 一、系统架构

```
┌─ V3s (ARMv7) ────────────────────────────────────────┐
│                                                        │
│  g_serial (USB Gadget)     usb_tund (C++ daemon)       │
│  VID=0x0BDA PID=0x8812     /dev/ttyGS0 ←→ tun_hub     │
│  (伪装 RTL8812AU)           帧协议封装/解封            │
│                             10.0.0.1/24                │
│                                                        │
│  iptables MASQUERADE + FORWARD                         │
│  TCP MSS Clamping                                      │
│                                                        │
│  eth0: 192.168.x.x (DHCP)                              │
│                                                        │
│  web_panel.py :8080 — Web 配置 API                     │
└────────────────────────────────────────────────────────┘
```

**数据流：**
```
DJI RC (Android) ──USB Bulk──► V3s ──NAT──► LAN 设备 (摄像头/图传/...)
      10.0.0.2                  10.0.0.1         192.168.x.x
```

---

## 二、需要部署的文件

| 文件 | 源路径 | 目标路径 | 作用 |
|------|--------|----------|------|
| `usb_tund` | `ubuntu/build_v3s/usb_tund` | `/usr/local/bin/` | C++ 守护进程 |
| `web_panel.py` | `ubuntu/web_panel.py` | `/usr/local/bin/` | Web 配置面板 |
| `setup_gadget.sh` | `ubuntu/scripts/setup_gadget.sh` | `/usr/local/bin/` | 加载 g_serial |
| `setup_nat.sh` | `ubuntu/scripts/setup_nat.sh` | `/usr/local/bin/` | TUN + NAT |
| `S99tun_nat_hub` | `ubuntu/scripts/S99tun_nat_hub` | `/etc/init.d/` | 开机自启 |

---

## 三、Step by Step

### Step 1：交叉编译 daemon

在开发机上执行（需要 arm-linux-gnueabihf 工具链）：

```bash
# 安装交叉编译器 (Ubuntu/Debian)
sudo apt install g++-arm-linux-gnueabihf

# 编译
cd TUN_NAT_HUB
bash scripts/cross_build_v3s.sh
```

产物：`ubuntu/build_v3s/usb_tund`，验证：

```bash
file ubuntu/build_v3s/usb_tund
# 输出: usb_tund: ELF 32-bit LSB executable, ARM, EABI5 version 1 (SYSV) ...
```

### Step 2：上传文件到 V3s

```bash
# 设置 V3s IP（根据实际修改）
V3S_IP="192.168.144.66"

# 上传 daemon
scp ubuntu/build_v3s/usb_tund root@${V3S_IP}:/usr/local/bin/

# 上传 web_panel
scp ubuntu/web_panel.py root@${V3S_IP}:/usr/local/bin/

# 上传脚本
scp ubuntu/scripts/setup_gadget.sh root@${V3S_IP}:/usr/local/bin/
scp ubuntu/scripts/setup_nat.sh root@${V3S_IP}:/usr/local/bin/
scp ubuntu/scripts/S99tun_nat_hub root@${V3S_IP}:/etc/init.d/

# 设置权限
ssh root@${V3S_IP} "chmod +x /usr/local/bin/usb_tund /usr/local/bin/web_panel.py \
    /usr/local/bin/setup_gadget.sh /usr/local/bin/setup_nat.sh \
    /etc/init.d/S99tun_nat_hub"
```

### Step 3：配置开机自启

```bash
ssh root@${V3S_IP}

# 确认 init.d 脚本存在
ls -la /etc/init.d/S99tun_nat_hub

# 测试手动启动
/etc/init.d/S99tun_nat_hub start
```

**重启后会自动执行**（BusyBox init 按 S 前缀字母序执行 `S99*`）。

> 如果 V3s 使用 systemd 而非 BusyBox init，用 `ubuntu/config/tun_nat_hub.service` 替代。

### Step 4：验证

```bash
# 1. 检查进程
ssh root@${V3S_IP} "ps aux | grep -E 'usb_tund|web_panel'"

# 2. 检查 TUN 接口
ssh root@${V3S_IP} "ip addr show tun_hub"
# 应显示: inet 10.0.0.1/24

# 3. 检查 USB Gadget
ssh root@${V3S_IP} "ls -la /dev/ttyGS0"
# 应显示: crw-rw-rw- ... /dev/ttyGS0

# 4. 检查 Web API
ssh root@${V3S_IP} "wget -q -O - http://127.0.0.1:8080/api/heartbeat"
# 应返回: {"status":"ok","version":"1.1.0"}

# 5. 检查 iptables
ssh root@${V3S_IP} "iptables -t nat -L POSTROUTING -n | grep 10.0.0"
# 应有 10.0.0.0/24 → MASQUERADE 规则

# 6. 检查 USB 模式
ssh root@${V3S_IP} "cat /sys/devices/platform/soc/1c19000.usb/musb-hdrc.2.auto/mode"
# 应显示: peripheral
```

### Step 5：插入 DJI RC 验证

插入 USB 线后，在 Android 端检查：

```bash
# DJI RC 端 dmesg 应显示
adb shell dmesg | grep "idVendor=0bda"
# usb 1-1: new high-speed USB device number X using musb-hdrc
# idVendor=0bda, idProduct=8812
```

TUN_NAT_HUB App 上：
- USB● 绿点 + VPN● 绿点
- TopBar 显示 "已连接 (USB Bulk)"

---

## 四、Web API 参考

web_panel 监听 `8080` 端口，提供以下接口：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/heartbeat` | 服务状态 |
| GET | `/api/config` | 获取当前配置 |
| POST | `/api/config` | 更新配置 (JSON body) |
| POST | `/api/forward/add` | 添加端口转发 |
| POST | `/api/forward/remove` | 移除端口转发 |
| GET | `/api/status` | 网络状态 + 统计 |

---

## 五、故障排查

### g_serial 没加载

```bash
# 检查模块
lsmod | grep g_serial

# 手动加载
modprobe -r g_serial
modprobe g_serial use_acm=0 use_obex=0 idVendor=0x0BDA idProduct=0x8812
ls /dev/ttyGS0
```

### tun_hub 不存在

```bash
# 手动创建
ip tuntap add dev tun_hub mode tun
ip addr add 10.0.0.1/24 dev tun_hub
ip link set tun_hub up
```

### DJI RC 看不到设备

```bash
# 检查 USB 模式
cat /sys/devices/platform/soc/1c19000.usb/musb-hdrc.2.auto/mode

# 如果不是 peripheral，手动切换
echo peripheral > /sys/devices/platform/soc/1c19000.usb/musb-hdrc.2.auto/mode

# 触发重枚举（有助于 DJI RC 重新检测）
echo host > /sys/devices/platform/soc/1c19000.usb/musb-hdrc.2.auto/mode
sleep 5
echo peripheral > /sys/devices/platform/soc/1c19000.usb/musb-hdrc.2.auto/mode
```

### 日志查看

```bash
# daemon 日志
cat /var/log/usb_tund.log

# web_panel 日志
cat /var/log/web_panel.log

# 内核 USB 日志
dmesg | grep -i "g_serial\|musb\|gadget"
```

### 手动重启服务

```bash
/etc/init.d/S99tun_nat_hub restart
# 或
killall usb_tund
sleep 1
/usr/local/bin/usb_tund > /var/log/usb_tund.log 2>&1 &
```

---

## 六、LAN 网段变更

如果 V3s 接入不同网段的局域网（如 `192.168.88.x` → `192.168.144.x`）：

1. **V3s 自动检测**：`web_panel.py` 启动时从 `eth0` 实际 IP 自动推断 LAN 网段
2. **App 端同步**：在 App 高级设置中修改 LAN 网段，或修改 RTSP URL 后 App 会自动同步网段
3. **VPN 重启**：修改网段后需要断开 VPN 重连，`addRoute` 才会生效

---

## 七、常见场景

### 场景 A：首次部署全新 V3s

按 Step 1→5 完整走一遍。

### 场景 B：只更新 daemon

```bash
scp ubuntu/build_v3s/usb_tund root@${V3S_IP}:/usr/local/bin/
ssh root@${V3S_IP} "killall usb_tund; sleep 1; /usr/local/bin/usb_tund > /var/log/usb_tund.log 2>&1 &"
```

### 场景 C：只更新 web_panel

```bash
scp ubuntu/web_panel.py root@${V3S_IP}:/usr/local/bin/
ssh root@${V3S_IP} "killall python3; sleep 1; python3 /usr/local/bin/web_panel.py > /var/log/web_panel.log 2>&1 &"
```

---

## 八、Buildroot 内核配置参考

确保 kernel 开启以下选项：

```
Device Drivers →
  [*] USB support →
    <*> USB Gadget Support →
      <*> USB Gadget Drivers →
          <*> Serial Gadget (g_serial)
  [*] Network device support →
      <*> Universal TUN/TAP device driver support

Networking support →
  [*] Networking options →
      [*] Network packet filtering (Netfilter) →
          <*> IP tables support
          <*>   MASQUERADE target support
          <*>   TCPMSS target support
```

---

## 九、版本对应关系

| usb_tund 版本 | 特性 |
|---------------|------|
| v5 | 单 fd + 自动重连 + TCP Ping Server |
| v4 | 双 fd (TTY 可关闭) + 自动重连 |
| v3 | 初始 TUN↔TTY 桥接 |

| App 版本 | 特性 |
|----------|------|
| 1.2.2 | UDP 端口保护 + LAN 网段自动同步 |
| 1.2.0 | Tab 导航 UI 重构 |
| 1.1.0 | 初始版本 |
