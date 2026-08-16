# TUN_NAT_HUB 项目交接文档

> 更新日期: 2026-08-16
> 用途: 复制到新会话继续工作
> 基于完整会话整理, 冲突处以最后一次确认为准

---

## 〇、当前进行中任务（2026-08-16 优先看）

### 🔥 做法 B: 砍 10.0.0.x + 手机 IP 改 144.11 — ✅ 已实现真机验证 (2026-08-16)
- **决策（老大拍板）**：砍掉 10.0.0.x 隧道内部网段，手机 tun0 用局域网真 IP **192.168.144.11**，V3s = 144.66
- **✅ 真机验证通过**：
  - 手机 tun0 = **192.168.144.11**（唯一地址，10.0.0.2 已移除），App 1.6.35
  - 电脑 **ping 144.11** 通（2-5ms）
  - App 收 rcmsg（V3s → **144.11:65530**）：遥控页 "dji_rc online RC"，摇杆实时
  - V3s 路由 `144.11/32 dev tun_hub` + eth0 proxy_arp=1 ✅
  - tun_hub 无 10.0.0.1 IP（不配内部地址）✅
  - 电脑 UDP → **144.11:14550** 到手机 UDP 层（NoPorts+3 = 到手机但 QGC 未匹配，QGC v4-mapped 坑，非隧道问题）
- **为什么可行**（实测已确认）：
  - V3s INPUT 链 policy ACCEPT，`144.66:8080` 从 V3s 本机访问返回 `{"version":"1.6.26"}` ✅ —— **App 代码注释里"eth0 INPUT 投递坏"的 bug 已不存在**
  - web_server 监听 `0.0.0.0:8080`（通配），144.66 和 144.11 都能到
- **完整方案**：[docs/LAN_IDENTITY_ARCH.md](docs/LAN_IDENTITY_ARCH.md)（含实测记录 + 改造清单 + 同网段坑）
- **改动**：App（TunNatVpnService/MainActivity/CrsfBridge/视频文件，版本 **1.6.35**/code 74）+ 固件（dji_rc/S99/setup_v3s.sh/main/tun_iface，版本 **1.6.29**）
- **⚠️ 电脑端有感**：uart2udp --target、QGC 目标 IP、App 端口转发 dest 都要从 `144.200` 改成 `144.11`
- **⚠️ 待固化**：V3s 当前仍是 F1.6.26（dji_rc/web_server/usb_tund 运行时重启用了新参数，但固件未固化，重启后回旧版）— 需重建 rootfs OTA

### LAN 身份 v1（x.x.x.200 双地址方案）— 已实现真机验证通过
- **需求**：老大要"用起来像真实局域网"——局域网设备（电脑/摄像头）能直接访问手机，不用逐端口配转发
- **根因**：手机 TUN 只有 `10.0.0.2`（外人看不见的隧道网段），LAN→手机要靠逐端口 DNAT 白名单
- **方案**：手机 TUN **多挂一个 LAN 身份地址 `x.x.x.200`**（从 lanSubnet 推导，默认 192.168.144.200），V3s eth0 开 proxy_arp 代答 + `/32` 路由进隧道
  - 局域网设备 ping/访问 `192.168.144.200` = 同网段直接 ARP → V3s 代答 → 隧道 → 手机，**零配置**
  - 控制面（10.0.0.1 web / 10.0.0.2 rcmsg / crsf-bridge）**完全不动**
- **改动**：
  - App `TunNatVpnService.kt`：`addAddress(lanAddr, 24)` 加 LAN 身份；`openProtectedPort` 改绑 `0.0.0.0`（同时收 10.0.0.2 和 144.200）
  - `setup_nat.sh`：LAN_PHONE_IP 推导 + `ip route add x.x.x.200/32 dev tun_hub` + `eth0 proxy_arp=1` + 入向 FORWARD `-d x.x.x.200 -j ACCEPT`
  - 固件 1.6.27→**1.6.28**，App 1.6.33→**1.6.34**（versionCode 73）
- **⚠️ 实际部署修正（重要）**：
  - V3s 实际用的是 **`setup_v3s.sh`**（S99 调用），不是 setup_nat.sh！LAN 身份逻辑加到 setup_v3s.sh，setup_nat.sh 改动无效（旧 RK3588 脚本）
  - **`openProtectedPort` 不能用 `InetSocketAddress("0.0.0.0")`** —— 系统 IPv6 开启时会变 v4-mapped 双栈 socket（内核 `::ffff:10.0.0.2`），收不到经 tun0 进入的 IPv4 包（实测 InDatagrams 涨但 rx_queue=0）。**必须用 `DatagramChannel.open(StandardProtocolFamily.INET)`** 强制纯 IPv4 socket（实测 OK）
  - LAN 身份从 lanSubnet 推导（x.x.x.200），网段变更自动跟随
- **✅ 真机验证通过 (2026-08-16)**：
  - 电脑 `ping 192.168.144.200` 通（1-2ms，V3s tcpdump 抓到双向 ICMP echo）
  - 电脑发 UDP → `192.168.144.200:9000` 到达手机 UDP 层（手机 NoPorts +5 精确匹配）
  - App 收 rcmsg（10.0.0.2:65530）正常：遥控页显示 "dji_rc online RC"，CH1-16 摇杆实时
  - USB 隧道双向流量 Tx 7.0M / Rx 690K 在涨
  - QGC MAVLink + 视频走 `192.168.144.200:14550`：电脑 uart2udp 12.62 KB/s 持续发送无报错，数据到 QGC socket（V3s FORWARD 到 144.200 计数 1510K 包 / 1900MB）
  - **V3s INPUT bug 已不存在**：INPUT policy ACCEPT，`144.66:8080` 本机访问正常
- **产物 md5**：web_server `434d26e5`；APK 30.3MB；**注意固件 F 版本仍是 1.6.26**（web_server 推 /tmp 未固化，固化需重建 rootfs OTA）

### 摇杆 CRSF 输出 + Lua 桥同时工作（未完成）
- **目标**：crsf 模式既能输出摇杆 CRSF（飞控），又能配置 ELRS Lua（接收机页）
- **固件 v1.6.25（ringbuf 版）已在 V3s 运行**，但 Lua 配置未打通
- **关键发现：V3s BOTHER 设 400000 实际输出 460800**（不是 400k）！
  - 460800 采样能正确解析标准 CRSF（`C8 21 16` 摇杆帧），400000 采样乱码
  - 影响：400k 电脑桥乱码 = 波特率不匹配，非固件 bug
- **发送架构**：v1.6.25 用 ringbuf（`g_tx_ring` 4096B），摇杆帧+Lua 帧统一入队，主循环 15ms 定时 `tx_flush` 批量写 UART0（单一写者无竞态）
- **现状**：摇杆帧正常（COM30 460800 抓到 999 帧 0x16）；V3s bridge 收到 451 次 Lua 命令；但 **COM30 抓不到 Lua 帧 → ELRS 未响应**
- **待解决**：① 确认 Lua 帧是否被 tx_flush 发出（可能 ringbuf 被摇杆占满挤掉，或 ELRS 未响应）；② ELRS 波特率需匹配 460800
- **详细**：[docs/crsf_lua_bridge_plan.md §6.5](docs/crsf_lua_bridge_plan.md)

### 调试环境
- 电脑转发桥 COM10↔COM30（`tmp/_serial_bridge.py`），COM30 连 V3s UART0，COM10 连 ELRS
- **波特率用 460800**（V3s 实际输出），解析脚本 `tmp/_parse_crsf_frames.py`
- V3s 当前 dji_rc 输出 460800 8N1（/tmp ringbuf 版）

---

## 一、最终目标

DJI RC 遥控器 → V3s 中转 → SBUS/CRSF 输出，配套 Android App 配置 + 双向回传。

1. **V3s 输出标准 SBUS/CRSF 协议**（UART0，可变波特率）
2. **App 可配置**：SBUS/CRSF 切换、通道映射（EdgeTX 风格）、波特率
3. **PB6 检测切换 UART0 角色**：上拉=协议输出，接地=debug 串口（含运行中自动切换）
4. **CRSF 双向回传**（遥控数据 + 遥测数据）
5. **ELRS Lua 参数配置**（通过 CRSF 双向协议 + App 跑 Lua 脚本生成界面）

## 二、关键背景

- V3s 只有 3 个 UART：UART0(ttyS0)/UART1(ttyS1)/UART2(ttyS2)
- UART0 原本是内核 console + debug 串口，现释放为协议输出
- 硬件已定：**PB6 默认上拉**，接地触发 debug 模式
- V3s 内存仅 50MB，rootfs 是只读 squashfs（4.468MB 分区）
- 系统：BusyBox（无 pkill/无 bash/无 python3，用 killall），3.4 内核 7.1.0
- 交叉编译：WSL Ubuntu-20.04 + arm-linux-gnueabihf-g++（GCC 9.4）
- Android App：Kotlin + Jetpack Compose（DJI RC 上运行）
- 网络：V3s eth0 = 192.168.144.66 + 172.20.10.3 备用，DJI RC WiFi = 10.248.133.x

## 三、已确认的事实（证据）

### PB6 物理电平
```
devmem 0x01C20834 (PB DATA):
  上拉 → 0x00000040 (bit6=1)
  接地 → 0x00000000 (bit6=0)
```

### 寄存器布局（sun8i-v3s pinctrl @0x01C20800）
```
BANK_MEM_SIZE = 0x24, PULL_REGS_OFFSET = 0x1c
PB = bank 1 → bank offset 0x24
  CFG1 (PB4-7) @0x28, PB6 = CFG1 bit24-25 (0=input)
  DATA @0x34, PB6 = bit6
  PU0  @0x40, PB6 = bit12-13 (01=pull-up)
```
**关键坑**：0x01C20800 & ~0xFFF = 0x01C20000 是 clock 区！mmap 必须加页内偏移 **0x800** 才到 pinctrl。

### U-Boot APB2 时钟（串口乱码根因）
- sun6i APB2 原配置 PLL6/40 = **15MHz**，但驱动 CFG_SYS_NS16550_CLK = **24MHz**
- 不匹配 → 波特率错（实际 72115）→ 串口乱码
- **修复**：APB2 改 OSC24M（24MHz），与驱动匹配 → 串口 115200 正常

### dropbear host key
- 原 S50dropbear 加 `-R` → 每次重启重新生成 host key
- **修复**：去 `-R`，固化 `/etc/dropbear_ed25519_host_key`
- dropbear 启动参数: `-r /etc/dropbear_ed25519_host_key`

### 网络 IP
- eth0: `192.168.144.66/24`（DHCP 或 static fallback）+ `172.20.10.3/24`（备用，iPhone 热点网段）
- tun_hub: `10.0.0.1/24`
- App TUN: `10.0.0.2/24`（VpnService）
- rcmsg UDP: dji_rc → `10.0.0.2:65530`

### usb_tund tun_hub（隧道根因）
- usb_tund 重启后 tun_hub 可能 DOWN（mtu 1500, noop, 无 IP）→ TUN write EIO → 隧道停
- **修复**：TunIface 自配置 tun_hub（SIOCSIFMTU 1400 + SIOCSIFFLAGS UP + SIOCSIFADDR 10.0.0.1/24）

### App USB 连接
- DJI RC 的 USB 权限广播可能不触发 → App 需**轮询 hasPermission**
- USB 伪装: g_serial idVendor=0x0BDA idProduct=0x8812（RTL8812AU, 绕过 DJI 白名单）

### 串口输入/解码
- ttyS1 (921600) / ttyS2 (115200) 有数据，dji_rc 解码正常
- UART1 = RC/0xAE（DJI-B 摇杆），UART2 = SPECIAL/0x02（DJI-A 按键）

## 四、长期偏好

1. **称呼用户为"老大"**（CLAUDE.md 硬性规则）
2. 所有注释用中文
3. 每完成一轮改动立即 git commit
4. 知识回流到 Obsidian Vault
5. 失败 2 次必须停手诊断，报告根因，等确认
6. 分析问题时**结合两端**（App + V3s）看，不只看单端

## 五、硬性规则（CLAUDE.md）

1. 回复必须含"老大"
2. 失败即停手，连续 2 次失败禁止第 3 次，先诊断
3. 硬件操作一次性完成（列出完整步骤）
4. 被指"不要逃避"时立刻复盘回根因
5. 写后必须读回验证（SD 卡/SPI flash）
6. 失败 2 次后提出完整分析报告
7. 所有操作 AI 直接执行，不让用户手动敲指令
8. 遇到问题先分析再动手，禁止看到报错就盲目改
9. 涉及硬件/接线问题时，先确认物理状态再改代码

## 六、输出格式

- 固件版本 v1.6.4，App 版本 v1.5.2（当前分支 feature/crsf-elrs）
- 代码引用用 markdown 链接 `[文件](路径:行号)`
- 汇报用表格清晰呈现验证结果

## 七、已经完成的工作

### PB6 运行中自动切换（完整修复验证）
- `pb6_grounded()` mmap 读寄存器，**每次检测重新 open+mmap+munmap**（页内偏移 0x800）
- 根因链三层：
  1. 代码落在已否定 pread（pread 读回全 0）→ 恢复 mmap（`475c94e`）
  2. inittab getty respawn + login shell 占 ttyS0 → 禁用 getty + getty_stop 用 fuser -k（`1c0a9a2`）
  3. UDP sendto 阻塞卡死主循环 → 非阻塞 socket（`4ba484b`）
- 真机验证：运行中接地/断开多次往返切换正常

### U-Boot（115200 + PB6 bootcmd + APB2 修复）
- CONFIG_BOOTCOMMAND = PB6 检测版（接地→console=ttyS0,115200，上拉→console=null）
- APB2 改 OSC24M（24MHz）修复串口乱码
- 串口 UART0 115200 正常（用户确认"串口显示 ok"）

### OTA A/B 槽切换（验证通过）
- 连续 20 次 OTA 测试 20/20 成功（上传→重启→切槽稳定）
- **但 web_server OTA 对部分固件报 "bad squashfs magic"**（需查 web_server OTA 接收 bug）

### CRSF/ELRS 增强（分支 feature/crsf-elrs）
- 地址/帧类型修正（DEVICE_PING=0x28 等）
- Heartbeat + 扩展头帧 + Device_Ping
- 参数协议（Device_Info + Settings_Entry + Parameter Read/Write）
- 回传状态机 + 参数表（crsf_handle_request）
- 审查修复（buffer 溢出 + vlen + Device_Info dest）

### CH5/CH6 对调
- UART1 (RC/0xAE) 的 CH5/CH6 对调，实机验证正常
- dji_rc md5 `86f48284`

### CRSF-Lua 桥接（分支 feature/crsf-lua-bridge，M1-M3 完成）
- M1: V3s `--crsf-bridge` 模式（UART0 CRSF 帧 ↔ 网口 UDP 65532 透明转发）`1e75ebd`
- M2: App LuaJ 引擎 + EdgeTX API 绑定（crossfireTelemetryPush/lcd）`a41aaff`
- M3: elrsV3.lua + LuaParamActivity 参数界面 `a41aaff`
- M4 待验证（需 ELRS 模块 + 真机）

### dropbear host key 固化
- S50dropbear 去 `-R`，固化 key 到 `/etc/dropbear_ed25519_host_key`
- SSH host key 重启不变

### setup_v3s 双 IP
- eth0 192.168.144.66（DHCP/static）+ 172.20.10.3（备用）
- 144 + 172 共存确认（ip addr 显示两个 IP）

### usb_tund tun_hub 自配置（核心修复）
- TunIface 构造后自配置 tun_hub（MTU+UP+IP），不依赖 setup_v3s.sh 时序
- 修复 TUN write EIO + 隧道停转
- usb_tund md5 `e06545ac`

### App USB 连接修复
- MainActivity 权限轮询（DJI RC 权限广播不触发，主动检测 hasPermission）`3b8f35d`
- BootReceiver 回退 ea10633 原始 + 权限独立 action
- UsbBridge 幂等 + disconnecting 标志（避免重连循环）

## 八、重要决策及其理由

| 决策 | 理由 |
|---|---|
| UART0 释放为协议输出 | 只有 3 个 UART，协议输出必须用 UART0 |
| PB6 检测角色切换 | 一个 GPIO 让 UART0 一鱼两吃 |
| mmap 每次重映射 | 运行中同映射读到旧值，重映射读实时值 |
| 页内偏移 0x800 | 0x01C20000 是 clock 区不是 pinctrl |
| APB2 改 OSC24M | 匹配驱动 CFG_SYS_NS16550_CLK=24MHz，修串口乱码 |
| dropbear host key 固化 rootfs | 方案1（最简单），SSH 重启不变 |
| usb_tund 自配置 tun_hub | 不依赖 setup_v3s.sh 时序，重启后隧道自动恢复 |
| App 权限轮询 | DJI RC 权限广播不触发，主动检测 hasPermission |
| CRSF 透明桥接 | V3s 变桥，App 跑 Lua 脚本决策，解耦 |
| g_serial 伪装 RTL8812AU | 绕过 DJI RC USB 白名单 |

## 九、被否定的方案

| 方案 | 否定理由 |
|---|---|
| SPI env 存 bootcmd | CONFIG_ENV_IS_IN_FLASH 未启用，U-Boot 不读 |
| pread/pwrite /dev/mem | 读回全 0，不可靠 |
| DTB bias-pull-up 为主 | 运行时未生效（读取方式问题）|
| BootReceiver 完全忽略 ATTACHED | 可能阻止必要重启，最终回退 + 权限独立 action |
| App 强制重启叠加多修复 | 过度修改导致连接不稳，回退到能连上的基线 |
| 权限广播依赖 | DJI RC 不触发标准广播，改轮询 |

## 九·五、本轮验证与修复（2026-08-15，feature/crsf-lua-m4）

### OTA 反复测试（固件 1.6.16 → 1.6.17，3/3 通过）
- 连续 3 次 A↔B 循环升级，每次上传返回 `{"ok":true}` HTTP 200，启动槽正确切换（mtdblock3↔4）
- **MEMERASE + full compare + OTA ctl 写入全部稳定**，A/B 槽前 4.2MB 内容与本地 rootfs 逐字节一致（md5 `e2320890...`）
- 顺带确认：**V3s 的 dropbear host key 每次重启都会变**（SSH 需先探测当前指纹）

### 修复：bridge 模式 src_cfg 热重配不生效（commit b865ca9）
- **现象**：App 改反向/范围/映射，固件 API 值变了但 SBUS/CRSF 输出没变
- **根因**：dji_rc 以 `--crsf-bridge` 运行时，热重配 `if (!g_crsf_bridge && ...)` 跳过整个 SPI config 重载 → src_cfg 只在启动时加载，运行中修改不生效
- **修复**：去掉 bridge 对 load_rc_output_cfg 的跳过（src_cfg/map/lock 即时更新），仅跳过 mode/baud 导致的 UART0 角色重开（`reconfigureIo = cfgOk && modeDiff && !g_crsf_bridge`）
- **验证**：运行中 POST st1_mid=1800 → ch1 即时 1500→1800；恢复 1500 即时生效
- **固件版本 1.6.16 → 1.6.17**，已 OTA 固化到 A 槽（rootfs_v1617.squashfs，dji_rc md5 `ebb2fcc7`，web_server md5 `d8a0bf5a`）

### 新增：按键长按触发配置（commit 042a3e4 + ee6cb8f）
- **需求**：普通按键源（REC/RTH/STOP/FOCUS/C1-C3/AIRCRAFT/BACK/BTN/方向键 14 个）加"长按触发"开关：按住 ≥500ms 才视为有效按下，短按不触发（防误触），阈值固定 500ms
- **实现**：
  - rc_map.h/c：RC_CFG_NUM 71→85，每按键源加 `_lp` 配置项（0/1），sanitize 对 `_lp` 归一 0/1（防被钳到 [800,2200]），新增 `rc_cfg_lp()` 公开 API
  - **长按确认状态下沉到 src_value**（v1.6.20，commit ee6cb8f）：`g_lp_confirmed[SRC_COUNT]` + `rc_map_lp_set/get`，src_value 对独立按键源检查确认状态（未确认返回 off），**复合源（C12/SHOT/DIR）读原始字段不受影响**；dji_rc `update_long_press` 只更新确认状态不改 st，src_lock_active 检查确认（短按不 toggle 自锁）
  - App：通道工作台每行加"长按"开关（v1.6.21）+ 开关组 `_lp` 行
- **版本**：固件 1.6.18→1.6.19→1.6.20，App 1.6.19→1.6.20→1.6.21→1.6.23
- **验证**：src_cfg_names 85 项（含 14 `_lp`），rec_lp 保存/读回 0↔1 正常；真机按键验证待老大操作
- **审查结论**（2026-08-15）：无 CRITICAL；修复 1 个 HIGH（长按污染复合源）+ 4 个 LOW（注释/死变量/时间戳）

### crsf 模式同时摇杆输出 + Lua 桥 + 审查修复（commit cf61938，固件 v1.6.23/App v1.6.32）
- **需求**：crsf 模式既要输出摇杆 CRSF 又能配 Lua
- **实现**：去掉 sbus_send_if_p20 的 `!g_crsf_bridge` 跳过（之前 bridge 不输出摇杆），bridge 下行线程写 UART0 加 g_out_write_mtx 与 out_send 互斥防帧交错
- **审查修复**：g_crsf_bridge 改 atomic；App 工作台 sbus_std 硬编码 true → 加载回传；CRSF 波特率三处统一 115200；手动默认按 sbus_std；配置页保存加 onResult
- **验证**：crsf 模式 `out ok mode=c`（摇杆帧）+ bridge 线程启动（Lua 桥 65532）

### 波特率热重配修复（commit ad666ec，固件 v1.6.22）
- **问题**：热重配切波特率时 `g_out_fd < 0` 才重开输出口，SBUS 无回传线程时 fd 不关闭 → 波特率不变（实测仍 400k）
- **修复**：热重配无条件关闭旧 fd 再重开 uart_open_out
- **验证**：115200 8N1↔100k 8E2 双向热重配都生效；老大实测 115200 正常
- **固化**：web OTA 双槽 v1.6.22（A/B 槽前 4.2MB md5 一致 `b4f6d4ce`）
- 附：App v1.6.28 配置页选标准/兼容联动 roBaud=auto（commit a2d3e4a）

### bridge(ELRS Lua) 按 SPI mode 自动启停（commit 0102938，固件 v1.6.21）
- **问题**：dji_rc 以 `--crsf-bridge` 启动强制 CRSF 输出，用户切 SBUS 后无输出（S99 固定传 --crsf-bridge）
- **修复**：启动读 SPI mode，sbus 则禁用 bridge（UART0 输出 SBUS），crsf 则启用 bridge；热重配时动态启停 bridge 线程
- **效果**：切 SBUS → SBUS 输出无 Lua 桥；切 CRSF → CRSF 输出 + ELRS Lua 桥（接收机页可用）
- **验证**：sbus 启动 SBUS 8E2 fd=5 无 bridge；切 crsf bridge 线程启动（65532 监听）；切回 sbus bridge 停

### App 配置界面清理（commit 7b2ef64）
- 删配置页"RC 遥控器"占位区块 + RC 输出区块通道映射编辑（遥控页通道工作台已有）
- 播放引擎 + 解码器合并为组合式下拉（UDP_SELF 下列出各 H264 解码器）
- App 1.6.21→1.6.22→1.6.23

### 修复：自锁不生效 + 低端点 900 显示不全（commit de235f2）
- **自锁没用**：bridge 模式 `out_send` 被跳过（UART0 专用于 CRSF-Lua 桥），自锁 latch 只在 `out_send → build_output_channels(advance_latch=true)` 推进，主循环 write_state_file/send_rcmsg 用 false（只应用不推进）→ latch 永不 toggle
  - 修复：send_rcmsg/write_state_file 改用 `g_crsf_bridge` 作为 advance_latch（bridge 主循环推进；非 bridge 保持 out_send 推进避免重复 toggle）
- **900 显示不全**：ChannelScale 值气泡在 `fillMaxWidth(pct)` 容器 TopEnd，pct=7% 时标签超出左边界被裁剪
  - 修复：气泡改独立 BoxWithConstraints + offset 定位，中心跟随 pct 但 clamp 在容器内永不裁剪
- **固件 v1.6.17 → 1.6.18**（rootfs_v1618，dji_rc md5 `9a9ab0cb`）；**App v1.6.18 → 1.6.19**（versionCode 58）
- ✅ 老大真机确认两项正常

### App 通道配置页验证
- ✅ 通道设置卡片加载固件配置（"● 已连接"，范围 900/2000 正确显示）
- ✅ 范围编辑输入框获得焦点（软键盘弹出）+ 低端点 900 保存生效
- ✅ 保存链路（App POST → 固件 SPI 保存 → 读回）
- ✅ 反向 checkbox 点击/状态显示正确
- ⚠️ 自锁输出效果需 **PB6 上拉（协议输出模式）** 才能观察（latch 在 out_send 推进）；当前 PB6 接地 debug 模式无法看

### 遗留/注意
- **PB6 接地 = debug 模式，UART0 不输出协议**（老大调试用；恢复上拉才输出）
- 板上 dji_rc 从 /usr/local/bin 运行（rootfs 固化版）；调试期可 base64 传 /tmp 跑新版本

## 十、当前进度

- ✅ PB6 运行中自动切换：完整修复验证
- ✅ U-Boot 串口 115200（APB2 修复，不乱码）
- ✅ OTA 20/20 验证（切槽稳定）
- ✅ CRSF 增强 + CH5/CH6 对调（dji_rc 86f48284）
- ✅ CRSF-Lua 桥接 M1-M3（分支 feature/crsf-lua-bridge）
- ✅ dropbear host key 固化
- ✅ 144 + 172 双 IP
- ✅ usb_tund tun_hub 自配置（隧道稳定）
- ✅ App 权限轮询 + USB 连接稳定
- ⚠️ App 视频/RC 最终验证（隧道已通，需 App 侧确认）
- ⚠️ OTA 对部分固件报 bad magic（web_server OTA bug）

## 十一、尚未完成的任务

1. **App 视频 + RC 数据最终验证**：隧道已稳定（usb_tund 双向转发），需确认 App 显示
2. **OTA bad magic 问题**：web_server OTA 对 rootfs_v5 报错，需查 web_server OTA 接收逻辑
3. **CRSF-Lua M4 真机验证**：需 ELRS 模块 + 部署 bridge 固件
4. **App "VpnService 残留强制重启"优化**：每次启动一次多余重启（不影响最终连接）
5. **固件固化**：usb_tund 修复版需固化到固件（rootfs_v5 已构建 + spi_image_v5 已打包）
6. 安装 App 到 DJI RC（新版本含权限轮询）

## 十二、不能随意修改的内容

1. **dji_rc.cpp 的 mmap 页内偏移 0x800**（必须保留）
2. **g_crsf_stop 独立原子量**（不能复用 g_stop 控 t3）
3. **退出顺序**：join 前 close fd（防死锁）
4. **getty 用 killall**（busybox 无 pkill）+ getty_stop 用 fuser -k
5. **PB6 硬件默认上拉**（硬件已定，不能改接地语义）
6. **dji_rc 动态编译**（静态超分区 4.468MB）
7. S99 不能再用 devmem 读 PB6（交给 dji_rc 统一处理）
8. **每轮改动后 git commit**
9. **usb_tund 自配置 tun_hub**（已修复隧道，勿移除）
10. **App 权限轮询**（DJI RC 广播不触发，勿改回广播依赖）
11. **APB2 OSC24M**（勿改回 PLL6/40，会串口乱码）
12. **dropbear -r 固化 key**（勿加回 -R）

## 十三、新会话接下来先做什么

1. **固化 usb_tund 修复版到固件**：FEL 烧录 spi_image_v5（`backup/spi_image_v5.bin`，md5 `17ba5b7a`，含 usb_tund `e06545ac`）
2. **验证 App 视频 + RC 数据**：隧道已通，确认 App 端显示
3. **查 OTA bad magic**：web_server OTA 对部分固件报错，定位接收逻辑 bug
4. **CRSF-Lua M4**：部署 bridge 固件 + ELRS 模块验证参数读写
5. 全程保持"写后读回验证" + 每轮 git commit

## 十四、关键文件

- `ubuntu/src/dji_rc.cpp`：主守护进程（PB6 检测 + SBUS/CRSF 输出 + rcmsg）
- `ubuntu/src/crsf.h/c`：CRSF 协议
- `ubuntu/src/rc_map.h/c`：通道映射
- `ubuntu/src/main.cpp`：usb_tund（tun_hub ↔ ttyGS0 桥）
- `ubuntu/src/tun_iface.cpp`：TUN 接口（自配置 tun_hub）
- `ubuntu/src/heartbeat.cpp`：心跳
- `ubuntu/scripts/S99tun_nat_hub`：启动脚本
- `ubuntu/scripts/setup_v3s.sh`：TUN + NAT + 双 IP
- `android/.../MainActivity.kt`：App 主界面（权限轮询）
- `android/.../UsbBridge.kt`：USB 桥
- `android/.../TunNatVpnService.kt`：VPN 服务
- `android/.../crsf/`：CRSF-Lua 桥接（LuaEngine/CrsfBridge/LuaParam*）
- `scripts/build_spi_image.py`：SPI 镜像构建
- `docs/crsf_lua_bridge_plan.md`：CRSF-Lua 计划
- `docs/ota_ab_slot_issue.md`：OTA 问题记录

## 十五、固件产物 md5

### v1.6.29（做法 B: 砍 10.0.0.x, 手机 = 144.11, App 1.6.35）— 已真机验证, 待固化

| 文件 | md5 |
|---|---|
| dji_rc（rcmsg/crsfbr-host → 192.168.144.11）| `e46cdaa2` |
| web_server（版本号 1.6.29, RTP 目标 144.11）| `22a4d301` |
| usb_tund（tun_hub 不配内部 IP, main 绑 0.0.0.0:9999）| `97562926`（/tmp/usb_tund_new）|
| app-debug.apk（App 1.6.35 / versionCode 74）| 30.3MB（md5 待补）|

### v1.6.28（LAN 身份: 手机 144.200 局域网直连, App 1.6.34）— 已真机验证（被 v1.6.29 取代）

| 文件 | md5 |
|---|---|
| dji_rc（与 v1.6.27 同代码, 未改动）| `af2be23e` |
| web_server（版本号 1.6.28）| `434d26e5` |
| app-debug.apk（App 1.6.34 / versionCode 73）| 30.3MB（md5 待设备在线时补）|

### v1.6.27（CRSF Lua 时分复用, 仅 /tmp 临时运行, 未固化）— 上一版

| 文件 | md5 |
|---|---|
| dji_rc（Lua 时分复用 tx_lua + UART0 自动恢复）| `af2be23e` |
| web_server（/tmp 版, md5 未记录）| — |

### 早期（留存）

| 文件 | md5 |
|---|---|
| dji_rc（CH5/CH6 对调 + CRSF 增强）| `86f48284` |
| usb_tund（tun_hub 自配置修复）| `e06545ac` |
| web_server | `69f47711` |
| rootfs_v5.squashfs（含 usb_tund 修复）| `c91ada62` |
| spi_image_v5.bin（待烧录）| `17ba5b7a` |

### v1.6.4（RTSP UDP DNAT 自动重试修复）

| 文件 | md5 |
|---|---|
| web_server v1.6.4（DNAT 启动自动重试）| `35d997ec732cc34528d598b4dba3d3e3` |
| rootfs_v164.squashfs（基于 v1.6.2 + 新 web_server）| `a112ca29c239eed916b2897ccdd20318` |

## 十六、Git 分支状态

| 分支 | 状态 |
|---|---|
| `flash` | v150 稳定版（HEAD `1173708`，已 push Gitee）|
| `feature/crsf-elrs` | **当前分支**（HEAD `bd5d37b`，CRSF 增强 + CH5/CH6 + usb_tund 修复）|
| `feature/crsf-lua-bridge` | CRSF-Lua 桥接（M1-M3 已提交，含固件产物）|
