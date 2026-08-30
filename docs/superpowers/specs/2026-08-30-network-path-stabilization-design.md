# A 方案：单播网络路径稳定化设计

> 日期：2026-08-30
> 范围：Android VpnService、USB TUN 隧道、V3s 路由/NAT、单播业务连接
> 不包含：mDNS/SSDP/广播代理、1:1 NAT、USB Ethernet、二层桥接

## 1. 背景与目标

当前链路采用 Android `tun0`、USB CDC Bulk 自定义 TN 帧、V3s `tun_hub` 和 `eth0` 组成的三层隧道。现场已经验证 App 1.6.67、固件 F1.6.53、USB 隧道和局域网转发在线，但网络路径仍分散在多个模块中：部分 Socket 显式绑定 VPN，部分依赖进程级绑定，ADB shell 和普通进程又可能走 Wi-Fi。

A 方案保持现有物理链路、USB 帧协议、地址和业务端口不变，目标是：

1. 固定 IP 的 TCP、UDP、ICMP、RTSP、RC 和 CRSF 单播业务稳定走预期路径。
2. App、USB、V3s 或摄像头任一环节异常时，可以准确定位故障层级。
3. USB 重枚举、VPN 重建、App 前后台切换和 V3s 重启后自动恢复。
4. V3s 网络规则可重复执行，不产生重复或相互冲突的 iptables 规则。
5. 不把 A 方案扩展为广播发现、真实二层接入或外部源 IP 保留方案。

## 2. 保持不变的兼容边界

| 项目 | 保持值 |
|---|---|
| Android 主隧道地址 | `10.0.0.2/24` |
| Android LAN 身份 | `192.168.144.11/24` |
| V3s 隧道地址 | `10.0.0.1/24` |
| V3s LAN 地址 | `192.168.144.66/24`，备用 `172.20.10.3/24` |
| TUN MTU | `1400` |
| USB 协议 | CDC ACM Bulk，TN 4 字节头 + IP payload |
| Web/API | TCP `8080` |
| 延迟测试 | TCP `9999` |
| RC App→V3s | UDP `65531` |
| RC V3s→App | UDP `65530` |
| CRSF bridge | UDP `65532` |
| LAN 身份入站 | `192.168.144.11` DNAT 到 `10.0.0.2` |

## 3. 目标架构

### 3.1 路径类型

所有 App 网络访问必须属于以下三类之一，不允许调用方自行组合 bind、protect 和进程绑定：

| 类型 | 用途 | 行为 |
|---|---|---|
| `TunnelClient` | App 主动访问 V3s、摄像头或局域网设备 | Socket 显式绑定 VPN Network，流量进入 `tun0` |
| `TunnelListener` | 接收从 V3s/局域网经 TUN 到达的数据 | 纯 IPv4 Socket 绑定 `10.0.0.2:port`，由工厂根据下表采用固定模式 |
| `PhysicalBypass` | 明确需要走遥控器物理 Wi-Fi 的连接 | Socket 调用 `VpnService.protect()`，不得用于 V3s/摄像头业务 |

新增 Android 内部网络路径组件，集中提供上述 Socket 工厂和 `Network.openConnection()` 封装。业务模块不再直接调用 `ConnectivityManager.Network.bindSocket()`、`VpnService.protect()` 或进程级网络绑定。

监听模式固定如下，不允许调用方临时选择：

| 流量 | 监听模式 |
|---|---|
| V3s RC 回传 `65530` | 纯 IPv4，绑定 `10.0.0.2`，调用 `protect()` |
| V3s CRSF 回传 `65532` | 纯 IPv4，绑定 `10.0.0.2`，调用 `protect()` |
| LAN 主动访问 Android 的普通端口 | 纯 IPv4，绑定 `10.0.0.2`，绑定 VPN Network，不调用 `protect()` |
| RTSP RTP 接收 | 由播放器创建纯 IPv4 Socket，并逐 Socket 绑定 VPN Network |

### 3.2 Android 路由

`VpnService.Builder` 显式配置：

- 地址 `10.0.0.2/24`。
- 地址 `<lan_subnet>.11/<prefix>`，默认 `192.168.144.11/24`。
- 路由 `10.0.0.0/24`。
- 路由当前 LAN 网段，默认 `192.168.144.0/24`。
- MTU `1400`。

不添加默认路由，不接管互联网流量。Wi-Fi 上网保持原路径，只有内部隧道网段和配置的 LAN 网段进入 USB。

### 3.3 V3s 路由与 NAT

`setup_v3s.sh` 继续维护：

- `tun_hub = 10.0.0.1/24`。
- `192.168.144.11/32 dev tun_hub` 主机路由。
- `ip_forward=1` 和 `eth0.proxy_arp=1`。
- `192.168.144.11 -> 10.0.0.2` 的入站 DNAT。
- Android 到 LAN 的 FORWARD 和回程 `ESTABLISHED,RELATED` 规则。
- 当前兼容用的 LAN 身份出向 MASQUERADE。

规则统一进入项目专用链，例如 `TUNHUB_PREROUTING`、`TUNHUB_FORWARD`、`TUNHUB_POSTROUTING`。内置链只保留一个跳转，项目链在启动时刷新后重新生成，避免不断追加重复规则，也不删除系统中其他服务的规则。`eth0` 与 `tun_hub` 之间的项目流量在允许规则之后显式拒绝，不能依靠全局 `FORWARD ACCEPT` 放行。

## 4. 模块改动

### 4.1 Android

| 模块 | 设计改动 |
|---|---|
| `TunNatVpnService.kt` | 显式添加内部网段路由；维护唯一 VPN Network 引用；提供链路代际编号；VPN 重建时关闭旧代际 Socket |
| 新增 `VpnSocketRouter.kt` | 提供三类 Socket 工厂和 VPN HTTP 连接入口；强制 IPv4；统一超时、绑定地址、日志和失败原因 |
| `CrsfBridge.kt` | 改用 `TunnelClient`/`TunnelListener`，取消分散的进程级网络绑定 |
| `RcMsgTransport.kt` | 使用 `TunnelClient`；检测 VPN 代际变化并重建 UDP Socket |
| RC 65530 接收 | 使用 `TunnelListener` 绑定 `10.0.0.2:65530`，Socket 失效后原子替换 |
| RTSP 播放模块 | RTSP TCP 和 RTP UDP 都使用 VPN Network；播放器停止时释放全部 Socket |
| Web/API 与9999测试 | 通过统一客户端工厂访问 `.66`，错误结果标记为路由、连接或超时 |
| `MainActivity.kt` | 只展示状态，不再承担网络绑定生命周期 |

禁止长期使用 `bindProcessToNetwork()`。进程级绑定会影响无关请求并容易在异常路径中残留，A 方案以逐 Socket 绑定为准。

### 4.2 V3s

| 模块 | 设计改动 |
|---|---|
| `setup_v3s.sh` | 拆分地址、路由、sysctl、iptables 四个幂等阶段；检查每一步结果 |
| `S99tun_nat_hub` | 先启动创建 `tun_hub` 的 `usb_tund`，再完成网络配置，最后启动 `web_server` 和 `dji_rc`；失败时记录阶段和退出码 |
| `usb_tund` | 保持 TN 协议不变；补充 USB/TUN 双向最后活动时间和重连次数 |
| `web_server.cpp` | 增加结构化网络状态接口，展示实际地址、路由、规则命中和进程状态 |
| RTSP NAT | 保持 `.31 -> 10.0.0.2` 回流逻辑；规则归入项目专用链并幂等生成 |

## 5. 链路状态与自愈

状态从低到高划分为：

1. `VPN_CREATED`：Android `tun0` 已建立且地址、路由正确。
2. `USB_ENUMERATED`：找到目标 VID/PID 且 Bulk IN/OUT 已声明。
3. `TUNNEL_ACTIVE`：双向至少收到一次有效 TN 帧或心跳。
4. `V3S_REACHABLE`：`.66:8080` 或 `10.0.0.1:9999` 成功。
5. `LAN_REACHABLE`：摄像头或配置的探测目标可达。

恢复规则：

- USB 连续写失败达到现有阈值后关闭当前连接并重新枚举。
- VPN 代际变化时，所有隧道 Socket 必须重建，禁止复用旧 Network 对象。
- RC 发布连续失败仍由现有健康检测重建融合运行时。
- V3s 网络脚本失败不得继续输出“ready”，Web 状态必须暴露失败阶段。
- 探测只用于状态判断，不因摄像头离线重启 USB 或 VPN。

## 6. 错误处理与可观测性

每个网络错误至少记录：路径类型、目标地址、VPN 代际、绑定结果、异常类别和时间。UI 不用单一“已连接”概括全部状态，而是分别展示 VPN、USB、隧道、V3s、LAN。

V3s 状态接口至少返回：

- `eth0`、`tun_hub` 地址和状态。
- `ip_forward`、`proxy_arp`。
- 项目专用 iptables 链是否存在及命中计数。
- `usb_tund` 的双向字节、错误、重连次数、最后活动时间。
- `web_server`、`usb_tund`、`dji_rc` 进程状态。

## 7. 安全边界

A 方案不继续依赖全局 `FORWARD ACCEPT` 作为功能保证。项目链只放行：

- LAN 到 `10.0.0.2` 的已配置入站路径。
- `tun_hub` 到当前 LAN 接口的出向流量。
- LAN 到 `tun_hub` 的 `ESTABLISHED,RELATED` 回程。
- 已配置的 RTSP RTP 回流。

上述允许规则后，对 `eth0 -> tun_hub` 和 `tun_hub -> eth0` 的其他流量显式拒绝；其他接口和其他服务的转发策略不由本项目修改。

本轮不引入用户认证、VPN加密或多客户端隔离，这些属于后续安全设计。

## 8. 测试与验收

### 8.1 自动测试

- Android Socket 工厂测试：三类路径选择、IPv4绑定、VPN代际失效。
- Android 路由配置测试：内部网段和LAN网段存在，不包含默认路由。
- V3s shell语法和幂等测试：连续执行两次规则数量不增加。
- iptables生成测试：不覆盖系统其他链，不产生重复跳转。
- TN帧协议回归：既有打包、拆包和心跳格式不变。

### 8.2 现场验收

1. App访问`192.168.144.66:8080`连续100次无路径漂移。
2. RC `65531`持续发布，V3s `65530`回传正常，运行30分钟无Socket静默死亡。
3. RTSP TCP建立和UDP RTP回流连续运行30分钟。
4. USB拔插一次后，App在15秒内恢复到`TUNNEL_ACTIVE`。
5. V3s重启后，App无需重启即可恢复业务连接。
6. App退到后台和重新进入后，不重复建立VPN或遗留旧Socket。
7. 连续执行两次V3s网络初始化，项目链规则数量和顺序一致。
8. ADB shell可以继续走Wi-Fi；App业务Socket必须走VPN，二者互不污染。

## 9. 交付边界

A 方案交付后，固定IP单播业务应具备统一路径、自动恢复和分层诊断能力。以下能力明确不作为A方案验收条件：自动发现设备、mDNS、SSDP、UDP广播、真实外部源IP、IPv6和二层透明桥接。
