# TUN_NAT_HUB 项目交接文档

> 更新日期: 2026-08-08
> 用途: 复制到新会话继续工作
> 基于完整会话整理, 冲突处以最后一次确认为准

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
