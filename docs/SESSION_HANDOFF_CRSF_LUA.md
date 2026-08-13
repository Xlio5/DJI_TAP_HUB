# CRSF-Lua 真机调试交接文档（可复制到新会话）

> 生成时间：2026-08-14
> 会话主题：DJI RC / V3s / ELRS 的 CRSF-Lua 桥接（安卓 App 跑 elrsV3.lua 配置 ELRS 参数）
> 用途：新会话直接复制本文件全部内容作为上下文，无需重跑前期调试

---

## 一、最终目标

**DJI RC 遥控器 → V3s 中转 → SBUS/CRSF 输出，配套 Android App 配置 + 双向回传。**

当前正在做的具体目标：
**让安卓 App 跑 elrsV3.lua 脚本，经 V3s bridge 连 ELRS 高频头，实现 ELRS 参数配置界面（上下选择 + 改值）。**

完整链路：
```
安卓App(跑 elrs.lua) → UDP 65532 → V3s bridge → UART0 → ELRS 高频头
        ↑                              ↑          ↑
        └────────── CRSF 参数帧回传 ←──┘          └── 电脑桥 COM10↔COM30 (调试用)
```

---

## 二、关键背景（硬件/网络/环境）

### 设备
| 设备 | 说明 | 连接 |
|---|---|---|
| **DJI RC PLUS 2** (rc701) | 遥控器，adb 连接 | 隧道 IP 10.0.0.2，WiFi 10.169.25.210 |
| **V3s** | Allwinner V3s, Buildroot 2024.02 | LAN 192.168.144.66 + 172.20.10.3（双 IP） |
| **ELRS 高频头** | T-14 900 TX，Silicon Labs CP210x | 电脑 **COM10**，波特率 **115200** |
| **V3s UART0** (ttyS0) | USB-SERIAL CH340 | 电脑 **COM30**，波特率 115200（ELRS Lua） |

### 参考实现（关键！）
**`c:/my_project/elrs_lua_python/`** —— Python 完整 ELRS Lua 实现，已在电脑上直接连 ELRS 验证成功：
- `crsf.py`：CRSF 协议（帧格式、CRC8 poly 0xD5、地址常量）
- `lua_session.py`：Lua backchannel 状态机（elrsV3.lua 的 Python 移植）
- `elrs_serial.py`：串口层 + 波特率探测（find_baud）
- `main.py`：CLI 入口
- `elrsV3.lua`：Lua 脚本

**已验证**：`python main.py --port COM10` 能连上 ELRS，显示 "T-14 900 TX"，加载参数（如 "Packet Rate 100Hz"）。

### 分支
- 当前分支：`feature/crsf-lua-bridge`
- 合并过：`feature/crsf-elrs`（Android 播放引擎迭代）
- 远程：Gitee `origin`

---

## 三、已确认的事实（经过验证）

### RC 端口/协议（8902 分析结论）
1. RC 开放 TCP：**8901/8902/40007/40008/40009** + adb 5555
2. **40009** = 0xAE 摇杆帧，~20Hz 突发：`55 1e 04 8a a2 82 <seq 2B> 00 06 ae ...` 6通道16bit 中位1024
   - rc701 用 **2 字节 seq + `00 06`**；老 RC 用 1 字节 seq + `08 00`（**不能硬套**）
3. **8902** = `f6/f5 64 <len> 00` 定长/变长混合流，**type 值 = 记录长度**（0x56=86B、0x60=96B…），内含嵌套子记录
4. 诊断脚本已提交：`6059c7a`（tmp/_probe_ports.py 等）

### CRSF 协议（来自 elrs_lua_python/crsf.py，权威）
- 帧格式：`[addr][frame_size][type][dest][orig][payload...][crc]`
- **CRC8 poly 0xD5**
- 地址：`0xC8`=FC, `0xEA`=遥控器, `0xEE`=ELRS TX 模块, `0x00`=广播
- 帧类型：0x28 Device_Ping, 0x29 Device_Info, 0x2B Settings_Entry, 0x2C Parameter_Read, 0x2D Parameter_Write, 0x2E ELRS Status
- **Device_Ping 必须用广播 dest=0x00**（ELRS 才响应）：`c8 04 28 00 ea 55`
- ELRS 响应 Device_Info(0x29)，payload 含设备名 "T-14 900 TX\0ELRS"

### ELRS 高频头
- **波特率 115200**（不是 420000！）
- 设备名 "T-14 900 TX"，900MHz ELRS TX 模块
- 响应广播 Device_Ping → Device_Info
- 平时静默（只接收摇杆发送），需主动发 CRSF 命令才响应参数

### V3s 关键事实
- **eth0 (192.168.144.66) UDP 本地投递(INPUT) 坏**——包到网卡但不到本地 socket
- **tun_hub (10.0.0.1) UDP 投递正常**——App 应走 tun_hub
- **端口转发不影响 65532**（DNAT 规则源限定摄像头 192.168.144.31，非 .31 源不匹配）
- **UDP↔UART 双向透传已验证**（独立 uart_bridge 程序）：
  - UDP→UART：V3s 发 UDP 65532 → bridge → UART0 → COM30 收到（无丢包，压力测试 50 帧×66B 精确匹配）
  - UART→UDP：COM30 发 → bridge → UDP（电脑/本地收，内容匹配）
- **非阻塞 UART busy-loop 是收不到包的原因**（占 CPU 干扰 recvfrom）——**必须用阻塞 read/recvfrom**
- UART0 波特率：ELRS Lua 用 **115200**；dji_rc CRSF 输出用 420000

---

## 四、长期偏好

1. **称呼用户为"老大"**（每次回复必须出现）
2. **自动化**：所有操作（构建/部署/测试/git）AI 直接执行，不让用户手动敲指令；用户只提供信息（IP/密码/设备名）
3. **中文交流**，技术术语保留英文
4. **知识回流**：解决非显而易见的 bug/决策 → 写入 `c:\Users\xlong\Documents\Obsidian Vault\00_收件箱\YYYY-MM-DD-{主题}.md`
5. 写文档/记录到项目 docs/ 下，方便跨会话

---

## 五、硬性规则（CLAUDE.md，最高优先级）

1. **称呼老大**：所有回复必须含"老大"
2. **失败 2 次停手**：连续失败 2 次禁止试第 3 次，停下来验证根因 + 报告 + 等确认
3. **硬件操作一次性列全**：SD 卡/USB 插拔一次性给完整文件清单和步骤
4. **被指出"不要逃避"时**：立刻停手复盘回到根因
5. **写后必须读回验证**：写 SD/SPI 等必须读回校验，禁止假设成功
6. **失败 2 次后完整分析报告**：现象/尝试过/最可能根因/推荐方案（只给一个）
7. **每次编译变更必须同步递增版本号**：
   - V3s 固件：`ubuntu/src/web_server.cpp:44` `#define VERSION`
   - Android App：`android/app/build.gradle.kts:15-16` versionCode/versionName
   - 版本号写进 commit message + 文档同步

---

## 六、输出格式

- Git commit：`<type>(<scope>): 描述`（feat/fix/chore/docs/refactor/perf）
- 中文注释
- 代码遵循 Google C++ Style / Android Kotlin Style
- 回复用清晰分节（## 或表格）

---

## 七、已完成的工作（按时间）

1. **8902/端口分析**：诊断脚本提交 `6059c7a`（端口探测、摇杆帧解析、协议码表）
2. **分支合并**：`feature/crsf-lua-bridge` ← `feature/crsf-elrs`，解决 dji_rc.cpp 冲突
3. **Lua 界面（模拟器验证）**：
   - `elrs.lua`（r18）→ `android/app/src/main/assets/elrs.lua`
   - `mockup/elrsmock.lua` 假数据（getVersion 返回 `-simu` 触发 setMock）
   - LuaEngine 重构（EdgeTX API 绑定 + 返回-table 约定）
   - MainActivity 侧边栏加"接收机"tab + LuaParamEmbed
   - 模拟器验证：参数列表渲染 + 上下选择 + 确认改值 全部通过
4. **固件构建（多次迭代）**：
   - 1.6.5 → 1.6.6 → 1.6.7 → 1.6.8（版本号递增，见 git log）
   - 修复 S99tun_nat_hub CRLF → LF（busybox not found 根因）
   - 修复 dji_rc PB6 切协议补启动 bridge 线程
   - 修复 dji_rc bridge 用独立 g_bridge_stop（不再被 t3 的 g_crsf_stop 干扰）
5. **UDP↔UART 双向透传验证**（独立 uart_bridge 程序）：
   - 阻塞 UART read + 阻塞 recvfrom
   - UDP→UART 无丢包（50 帧×66B 精确）
   - UART→UDP 内容匹配
6. **ELRS Lua 验证（电脑直连）**：参考 elrs_lua_python 程序连 COM10 成功，加载 "T-14 900 TX" + Packet Rate 参数

---

## 八、重要决策及其理由

| 决策 | 理由 |
|---|---|
| **固件构建用 base rootfs 提取（rootfs_v7）**，不是 buildroot target 直接 mksquashfs | buildroot target 里 setup_v3s.sh 是旧的，丢失 172.20.10.3 备用 IP；base 提取保留全部固化配置，只替换二进制 |
| **V3s bridge 用独立 uart_bridge（阻塞版）**，不是 dji_rc bridge | dji_rc bridge（固件版）收不到 UDP；独立程序阻塞 read/recvfrom 能收能转发；非阻塞 busy-loop 是收包失败根因 |
| **真机 host 用 10.0.0.1（tun_hub）** | 192.168.144.66（eth0）UDP 投递坏，tun_hub 正常 |
| **ELRS 波特率 115200** | ELRS Lua backchannel 实际用 115200（不是 420000） |
| **电脑桥 COM10↔COM30 透明转发** | 调试架构：ELRS 接电脑 COM10，V3s UART0 接电脑 COM30，电脑透明桥，可监测数据；与 V3s bridge（UDP↔UART）不冲突 |
| **Device_Ping 用广播 dest=0x00** | ELRS 只响应广播 ping（`c8 04 28 00 ea 55`），单播 dest=0xEE 不响应 |

---

## 九、被否定的方案

1. **dji_rc bridge（固件版）**：收不到 UDP（rx 0），调试版能收——最终用独立 uart_bridge
2. **App 发 10.0.0.1 走 tun0**：RC 路由 `ip route get 10.0.0.1 uid App` 走 wlan0（每-uid 规则覆盖 tun0），包到不了 V3s——**未解决**（见未完成任务）
3. **buildroot target 直接 mksquashfs**：丢失 172 IP，被否定
4. **移除 VPN allowBypass**：试过，没解决 App 发包走 wlan0 问题
5. **CrsfBridge bind tun0 IP (10.0.0.2)**：bind 源地址不影响出站接口选择，无效

---

## 十、当前进度（2026-08-14）

### ✅ 已通
- **ELRS 高频头本身**：参考 Python 程序直连 COM10 成功，加载 "T-14 900 TX" 参数
- **V3s bridge UDP↔UART**：独立 uart_bridge 验证双向无丢包
- **V3s → UART0 → 电脑桥 → ELRS**：V3s 发广播 Device_Ping，电脑桥监测到转发到 ELRS
  - 电脑桥输出：`[V3s→ELRS] 6B: c8042800ea55`
- **V3s → ELRS 方向**：广播 ping 成功到达 ELRS

### ❌ 未通/未确认
- **ELRS 响应回传**：ELRS 响应（Device_Info 0x29）→ 电脑桥 → V3s → UDP → App **未确认**
  - 参考程序直连 COM10 能收到 ELRS 响应，但经电脑桥链路时未看到 `[ELRS→V3s]`
- **安卓 App 连 V3s bridge 加载 ELRS 参数**：未完成
- **App 发包走 tun0 的路由问题**：App 发 10.0.0.1:65532 走 wlan0 不到 V3s（见"被否定的方案"）

### 当前 V3s 状态
- V3s 跑的是 **/tmp 的 uart_bridge**（115200，UDP 65532 ↔ UART0），**不是固件里的 dji_rc**
- uart_bridge 目标：UART→UDP 发 10.0.0.2（安卓 App）
- 电脑桥：tmp/_com_bridge.py（COM10↔COM30，115200）

---

## 十一、尚未完成的任务（按优先级）

1. **打通 ELRS 响应回传**：ELRS(COM10) → 电脑桥 → V3s → UDP → App
   - 检查电脑桥是否透明转发 ELRS 响应到 COM30
   - 检查 V3s uart_bridge 的 UART→UDP 是否收到 ELRS 响应并转发
   - 参考 elrs_lua_python/lua_session.py 理解 ELRS Lua 完整交互（需持续 ping + 等待响应）
2. **安卓 App 连 V3s bridge 加载 ELRS Lua 参数**：App 跑 elrs.lua，经链路连 ELRS
3. **解决 App 发包走 tun0 路由问题**：App CrsfBridge 发包走 wlan0 不到 V3s（需 App 侧修复）
4. **固件固化**：把验证过的 bridge 逻辑固化到 dji_rc/固件（当前跑 /tmp 的 uart_bridge）
5. **版本号同步**：固件每次编译递增；文档同步
6. **清测试残留**：V3s /tmp 的测试工具（uart_bridge/udp_send 等）

---

## 十二、不能随意修改的内容

1. **CLAUDE.md 强制规则**（称呼老大、失败停手、读回验证、版本号递增等）
2. **`ubuntu/src/web_server.cpp:44` 版本号定义**（每次编译内容变化必须递增）
3. **`.gitattributes`**：`*.sh text eol=lf`、`*.lua text eol=lf`（防脚本 CRLF 化）
4. **`ubuntu/scripts/S99tun_nat_hub`**：必须 LF 换行，含 crsf-bridge 启动参数
5. **`ubuntu/scripts/setup_v3s.sh`**：含 172.20.10.3 备用 IP（144+172 双 IP），不能丢
6. **固件构建方式**：必须用 base rootfs 提取（rootfs_v7），不能改回 buildroot target 直接 mksquashfs
7. **`c:/my_project/elrs_lua_python/` 参考实现**：是 ELRS Lua 的权威参考，改链路前先对照它

---

## 十三、新会话接下来先做什么

**第一步（最高优先级）**：打通 ELRS 响应回传链路
1. 启动电脑桥：`python -u c:/my_project/TUN_NAT_HUB/tmp/_com_bridge.py`（COM10↔COM30，115200）
2. 确认 V3s uart_bridge 在跑（115200，UDP 65532↔UART0）：
   - SSH 192.168.144.66，`ps -ef | grep uart_bridge`；若没跑：`/tmp/uart_bridge 115200 10.0.0.2`
3. V3s 发广播 Device_Ping：`/tmp/udp_send 10.0.0.1 65532`（帧 `c8 04 28 00 ea 55`）
4. 看电脑桥监测是否出现 `[ELRS→V3s]`（ELRS 响应回传）
5. 若回传通：V3s uart_bridge 应收到 ELRS 响应（UART→UDP），App 应能加载参数

**第二步**：让安卓 App 连 V3s bridge 验证 ELRS Lua 加载
- 参考 elrs_lua_python/lua_session.py 的交互流程（Device_Ping → 持续等待 → Settings_Read）
- App 进接收机页，CrsfBridge 发包到 10.0.0.1:65532

**第三步**：若 App 发包走 wlan0 不到 V3s，修 App 侧路由（见"被否定的方案"）

---

## 十四、关键文件清单

| 文件 | 说明 |
|---|---|
| `tmp/_com_bridge.py` | 电脑桥 COM10↔COM30（115200，带监测） |
| `tmp/_uart_bridge.c` + `tmp/uart_bridge` | 独立 UDP↔UART bridge（阻塞版，V3s 跑） |
| `tmp/_udp_send.c` + `tmp/udp_send` | UDP 发送测试工具（广播 Device_Ping） |
| `tmp/_udp_send_big.c` + `tmp/udp_send_big` | 大帧发送器（66B 压力测试） |
| `tmp/_udp_recv.c` + `tmp/udp_recv` | UDP 接收测试 |
| `tmp/_build_v168.sh` | 固件构建（base rootfs 提取方式） |
| `tmp/_add_rootfs_tail.py` | 固件验证尾（TUN_NAT_HUB + CRC32） |
| `ubuntu/src/dji_rc.cpp` | dji_rc 守护进程（crsf-bridge 代码） |
| `ubuntu/src/web_server.cpp` | web_server（版本号定义） |
| `ubuntu/scripts/S99tun_nat_hub` | 启动脚本（LF，crsf-bridge 参数） |
| `ubuntu/scripts/setup_v3s.sh` | 网络配置（144+172 双 IP） |
| `android/app/src/main/java/com/tunnathub/app/crsf/` | App 侧 Lua 引擎（LuaEngine/CrsfBridge/LuaParam*） |
| `android/app/src/main/assets/elrs.lua` | ELRS Lua 脚本（r18） |
| `android/app/src/main/assets/mockup/elrsmock.lua` | 假数据（模拟器调试） |
| `c:/my_project/elrs_lua_python/` | **ELRS Lua 权威参考实现**（Python） |
| `docs/crsf_ondevice_debug_notes.md` | 真机调试规范（VPN 授权 + 触发连接） |
| `docs/BUILD.md` | 构建规则（base rootfs + LF） |
