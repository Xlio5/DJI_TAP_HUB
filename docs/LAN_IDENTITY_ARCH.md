# LAN 身份架构 — 手机在局域网里"直接可见"

> 2026-08-16 实测定稿 · 分支 feature/crsf-lua-m4
> 目标: 手机在局域网(192.168.144.0/24)里有一个真 IP, 局域网设备零配置直达
> 演进: 10.0.0.x 隧道内部网段 → 全部收敛到 144 网段

---

## 一、为什么需要 LAN 身份

**原始架构**(10.0.0.x 隧道内部网段):
- 手机 TUN: `10.0.0.2`(隧道内部地址, 局域网设备看不见)
- V3s tun_hub: `10.0.0.1`
- 局域网设备想访问手机 → 必须 V3s 做逐端口 DNAT 白名单

**问题**: LAN→手机入向被 DNAT 端口白名单限制, 没配的端口全打空,
"用起来不像真实局域网"。

**方案**: 手机在局域网网段多挂一个真 IP(LAN 身份), V3s proxy_arp 代答,
局域网设备直接当普通设备访问, 零配置。

---

## 二、目标架构(做法 B: 砍 10.0.0.x, 手机 = 144.11)

```
         ┌──────────── 局域网 192.168.144.0/24 ────────────┐
         │                                                 │
  电脑/QGC/摄像头                                        V3s eth0
  144.x:任意端口 → 144.11                         192.168.144.66
         │              │                                │
         │              ▼                                │
         │     V3s eth0 proxy_arp 代答 144.11             │
         │              │  /32 路由 dev tun_hub           │
         │              ▼                                │
         │      USB 隧道 (ttyGS0 ↔ bulkTransfer)          │
         └──────────────────┬─────────────────────────────┘
                            ▼
                    手机 tun0: 144.11/24
                    (唯一地址, 局域网真 IP)
```

### 地址规划

| 角色 | IP | 说明 |
|------|-----|------|
| 手机 (DJI RC) | **192.168.144.11** | tun0 唯一地址, 局域网真 IP |
| V3s eth0 | 192.168.144.66 | 已有 |
| V3s tun_hub | 不配 IP 或 /32 辅助 | 只做路由, 不与 eth0 争 /24 |
| 局域网设备 | 144.x | 访问 144.11 = 手机, 144.66 = V3s |

### 三个内部用途的走法(砍掉 10.0.0.x 后)

| 用途 | 原来 (10.0.0.x) | 现在 (144 网段) |
|------|-----------------|-----------------|
| App 配置 V3s (web 8080) | `10.0.0.1:8080` | `144.66:8080` ✅ |
| rcmsg 摇杆 (V3s→App) | `10.0.0.2:65530` | `144.11:65530` ✅ |
| crsf-bridge (ELRS Lua) | `10.0.0.2:65532` | `144.11:65532` ✅ |

---

## 三、数据路径(实测验证)

### 局域网设备 → 手机(入向, 零配置)

```
电脑 ping/访问 192.168.144.11:任意端口
  → 同网段直接 ARP 问"谁是 144.11"
  → V3s eth0 proxy_arp=1 代答"是我"
  → 包发给 V3s eth0
  → 内核查路由: 144.11/32 dev tun_hub
  → USB 隧道 → 手机 tun0 → 内核投递给对应 socket
```

- 任意端口, 任意协议(TCP/UDP/ICMP)
- 局域网设备**零配置**, 不需要静态路由/DNAT

### 手机 → 局域网设备(出向)

```
手机 144.11 → 144.x
  → tun0 (144.0/24 路由) → USB → V3s tun_hub
  → 内核查路由: 144.x → eth0 → 局域网设备
```

### V3s 收包 socket 投递的关键

**Android VpnService 限制**: 隧道入站 IPv4 包只投递给**绑定具体 TUN 地址**的
纯 IPv4 socket。`0.0.0.0` 通配会被提升为 v4-mapped 双栈 socket, 收不到。

**实测证据**:
- `InetSocketAddress("0.0.0.0", port)` → 内核 `::ffff:10.0.0.2` (v4-mapped) → rx_queue=0 收不到
- `DatagramChannel.open(StandardProtocolFamily.INET)` 绑定具体 IP → 纯 IPv4 → 能收

---

## 四、实测记录 (2026-08-16)

### 4.1 电脑 ping 手机 LAN 身份 ✅

```
电脑 ping 192.168.144.200 (当时的 LAN 身份):
  192.168.144.200  2ms  0   ← 通
V3s tcpdump -i tun_hub icmp:
  192.168.144.88 > 192.168.144.200: ICMP echo request   ← 电脑
  192.168.144.200 > 192.168.144.88: ICMP echo reply     ← 手机回包
```
(电脑实际 IP = 192.168.144.88)

### 4.2 电脑 UDP 到手机(入向, 隧道转发) ✅

```
电脑发 5×UDP → 192.168.144.200:9000:
手机 /proc/net/snmp:
  InDatagrams +109, NoPorts +5 (正好 5 个包, 零丢失)
```
- 证明: 隧道转发任意端口 UDP 完整到达手机 UDP 层
- NoPorts +5 = 包到了但没 socket 监听该端口(9000), 触发 ICMP unreachable

### 4.3 V3s FORWARD 规则 ✅

```
iptables -L FORWARD -n -v | grep 192.168.144.200:
  1510K  1900M ACCEPT  eth0 → tun_hub  0.0.0.0/0 → 192.168.144.200
```
- 1510K 包 / 1900MB = QGC 视频 + MAVLink 走 LAN 身份直连的证据

### 4.4 QGC (DJI 上 org.mavlink.qgroundcontrol) ✅

- QGC 监听 `0.0.0.0:14550`(视频+MAVLink)
- 电脑 uart2udp → `192.168.144.200:14550`:
  ```
  S→U(192.168.144.200:14550): 12.62 KB/s ~740包  ← 持续发送, 无 10054 报错
  ```
- 数据到 QGC socket(缓冲有积压/消费), 隧道链路通

### 4.5 V3s INPUT 投递 bug 已不存在 ✅

**App 代码注释曾记录**: "必须用 10.0.0.1 (tun_hub INPUT 投递正常), 不能用
192.168.144.66 (eth0 INPUT 投递坏, V3s内核bug)"。

**实测 (2026-08-16)**:
```
V3s INPUT 链 policy ACCEPT (无 DROP)
V3s 本机测 http://192.168.144.66:8080/api/version → {"version":"1.6.26"} ✅
V3s 本机测 http://10.0.0.1:8080/api/version     → {"version":"1.6.26"} ✅
web_server 监听 0.0.0.0:8080 (通配所有接口)
```
- **eth0 INPUT 投递 bug 已不存在**, 可以放心砍 10.0.0.x

### 4.6 openProtectedPort 的 v4-mapped 坑(踩坑记录)

| 绑定方式 | 内核 socket | 收隧道 IPv4 包 |
|----------|-------------|----------------|
| `InetSocketAddress("0.0.0.0", port)` | `::ffff:...` v4-mapped | ❌ 收不到 |
| `InetSocketAddress("10.0.0.2", port)` | 纯 IPv4 | ✅ 能收 |
| `DatagramChannel.open(INET)` 绑具体 IP | 纯 IPv4 | ✅ 能收 |

**修复**: `openProtectedPortOn` 用 `DatagramChannel.open(StandardProtocolFamily.INET)`。

---

## 五、改造清单(做法 B: 砍 10.0.0.x, 手机 = 144.11)

### 5.1 Android App

| 文件 | 改动 |
|------|------|
| `TunNatVpnService.kt` | TUN_ADDRESS `10.0.0.2`→`144.11`; 删 LAN_ADDRESS/144.200 双地址(合并成一个); openProtectedPort 绑 144.11 |
| `MainActivity.kt` | 所有 `10.0.0.1:8080`→`144.66:8080`; `10.0.0.2`→`144.11`; v3sHost 改 144.66 |
| `CrsfBridge.kt` | send bind `10.0.0.2`→`144.11`; host→`144.66` |
| `build.gradle.kts` | 版本 1.6.34→**1.6.35** (versionCode 74) |

### 5.2 Ubuntu 固件

| 文件 | 改动 |
|------|------|
| `dji_rc.cpp` | RCMSG_HOST/crsfbr_host `10.0.0.2`→`144.11` |
| `S99tun_nat_hub` | `--rcmsg-host 144.11 --crsfbr-host 144.11` |
| `setup_v3s.sh` | tun_hub 配 `144.11/32`(替代 10.0.0.1/24); 加 `144.11/32 dev tun_hub` 路由 + eth0 proxy_arp; MASQUERADE 调整 |
| `web_server.cpp` | 版本 1.6.28→**1.6.29** |

### 5.3 关键路由细节

```
# V3s 上: 去手机 144.11 的包走隧道
ip route add 144.11/32 dev tun_hub
# V3s eth0: 代答 144.11 的 ARP (局域网设备找得到手机)
echo 1 > /proc/sys/net/ipv4/conf/eth0/proxy_arp
# V3s tun_hub: 不能再配 144.0/24 (会和 eth0 冲突), 只能 /32
```

**同网段坑**: 144.11 和 144.66 同在 /24, V3s tun_hub 若配 /24 会和 eth0 的
144.0/24 产生两条等长路由, 内核随机选 → 数据可能走错口。必须用 /32 主机路由。

---

## 六、影响评估

### 无感(局域网设备视角): 完全保持 ✅
- 局域网设备 ping/访问 144.11 = 手机, 144.66 = V3s, 跟普通局域网一致
- 不需要静态路由/DNAT, proxy_arp 代答

### 有感(电脑端配置): 144.200 → 144.11 需手动改 ⚠️
| 位置 | 原值 | 新值 |
|------|------|------|
| uart2udp --target | 192.168.144.200:14550 | 192.168.144.11:14550 |
| QGC 目标 IP | 144.200 (若有) | 144.11 |
| App 端口转发 dest | 144.200 | 144.11 |

### 版本号
- 固件 1.6.28 → 1.6.29
- App 1.6.34 → 1.6.35 (versionCode 74)
