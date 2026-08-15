# TUN_NAT_HUB — 核心产品需求文档

> 更新日期: 2026-08-14 | 基于当前分支 feature/crsf-lua-m4 实测状态
> 反向梳理 + 持续同步。实现细节见 `docs/architecture.md` 和 `docs/USAGE.md`。

## Problem

DJI RC PLUS 2 无人机遥控器在野外作业时需要通过 USB 线缆访问配套计算机所在局域网内的 IP 摄像头和其他网络设备，但 DJI RC PLUS 2 的 Android 系统不开放 USB 网络共享（RNDIS/ECM），WiFi 在户外不可用，且 `UsbManager.openDevice()` 受 DJI 白名单限制。**不用本项目，用户无法在遥控器屏幕上实时查看无人机载荷相机的视频流。**

在视频隧道之外，用户还需要**用遥控器直接配置射频链路参数**（ELRS 高频头的 Packet Rate 等）——这是 FPV 用户日常必做的操作，当前只能通过电脑串口连接 ELRS 模块完成，野外不可行。

## Evidence

- **视频隧道已验证**：USB 隧道实测吞吐 ~87Mbps（RK3588）/ 目标 ≥15Mbps（V3s），TCP RTT 3-6ms (p50)，满足 4Mbps 视频流 + <10ms 延迟目标
- **V3s 平台已量产级可用**：固件 v1.6.8 已烧录部署，ELRS 高频头 + DJI RC 真机联调通过（2026-08-14）
- **OTA A/B 槽升级 20/20 验证通过**（2026-08-10）：上传→重启→自动切槽稳定，含坏固件回退
- **CRSF 双向链路已物理打通**（2026-08-14）：V3s ping → ELRS → Device_Info 响应回传 → V3s UDP 全链路验证成功
- **CRSF-Lua 界面模拟器验证通过**：elrsV3.lua 参数列表渲染 + 上下选择 + 改值（mock 数据）
- **待验证**：App 真机（DJI RC）加载 ELRS 真实参数界面（M4，非 mock）—— `Assumption — needs validation via 真机部署验证`

## Users

- **Primary**: 无人机系统集成工程师 — 使用 DJI RC PLUS 2 遥控器，需要在户外通过 USB 线缆访问配套计算机（RK3588/V3s）局域网内的 IP 摄像头和网络设备，并配置射频链路
- **Secondary**: 无人机飞手/操作员 — 需要在遥控器屏幕上实时查看载荷相机画面（RTSP），管理端口转发，调整 ELRS 参数
- **Not for**: 普通手机用户（依赖 DJI RC PLUS 2 的 USB Host 白名单绕过机制）、不需要 USB 直连的场景（WiFi 已有成熟方案）、需要多路 4K 视频编码的场景（V3s 单核 A7 性能不足）

## Hypothesis

We believe **USB 线缆上的 TUN 虚拟网卡隧道（g_serial + 自定义帧协议 + NAT 转发）+ CRSF 双向桥接（V3s 透明转发 + App Lua 引擎）** will **为 DJI RC PLUS 2 提供透明、低延迟的局域网访问 + 遥控器直接配置射频参数** for **无人机系统集成工程师**.

We'll know we're right when **4Mbps RTSP 视频流持续稳定播放 >30 分钟，TCP 延迟 <10ms (p99)，USB 热插拔后 30 秒内自动恢复，且 App 在 DJI RC 真机上加载 ELRS 真实参数界面并成功修改参数**。

## Success Metrics

| Metric | Target | How measured |
|---|---|---|
| 视频流稳定性 | 4Mbps RTSP 连续播放 >30min 无断流 | 实际飞行测试 + App 内带宽监控 |
| 隧道延迟 | TCP RTT <10ms (p99)，<5ms (p50) | App 内置延迟测试（TCP connect to 10.0.0.1:9999） |
| 连接恢复 | USB 热插拔后 <30s 自动恢复 | 冷启动测试脚本 + 手动插拔测试 |
| 端口转发正确性 | 外网→内网 DNAT 规则 100% 转发正确 | `iptables -t nat -L` 验证 + 实际 TCP 连接测试 |
| 开机自启 | BOOT_COMPLETED 后 <60s VPN 就绪 | 冷启动诊断脚本 |
| V3s USB 吞吐 | ≥15Mbps | iperf 10.0.0.1 ↔ 10.0.0.2 |
| V3s daemon 内存 | ≤8MB | `/proc/pid/status` 每小时采样 |
| OTA 升级成功率 | 100% | Web 上传 → reboot → 版本号变化 |
| OTA 失败回退 | 3 次内切回旧槽 | 故意上传坏固件 → 自动回退 |
| **ELRS Lua 真机配置** | **DJI RC 上加载真实参数并改值成功** | **App 接收机页 → 参数界面 → 改值 → ELRS 生效** |

## Scope

**MVP** — 以下能力构成可验证假设的最小产品：
1. Android VPN Service 创建 TUN 接口并路由目标子网
2. USB Bulk 端点上的自定义帧协议（Magic + Length + Payload）
3. Linux 端 g_serial TTY 守护进程（TUN↔TTY 双向桥接）
4. Linux NAT MASQUERADE 实现 Android→LAN 透明访问
5. Web 配置面板（状态监控 + 端口转发管理）

**已实现的增值功能（截至 v1.6.8 / App v1.6.0）：**
- RTSP 视频播放器（EasyPlayer 原生 SDK，1ms 低延迟缓冲）
- 端口转发管理（TCP/UDP，4 字段表单，外网端口≠目标端口）
- 心跳链路检测（1s 轮询，3s 超时，App 侧三指示灯）
- 实时带宽显示（内核 tun_hub 统计，Tx/Rx Mbps）
- 多路摄像头管理（命名 + RTSP URL 配置）
- TCP 延迟测量工具（10.0.0.1:9999）
- USB 热插拔自动重连（30s 重试循环 + CAS 保护的 fd 切换）
- **V3s 平台移植**（全志 V3s，Buildroot，物料 ~30 RMB）
- **PB6 UART0 角色切换**（协议输出 / debug 串口，运行中自动切换）
- **OTA A/B 槽在线升级**（20/20 验证，含自动回退）
- **CRSF 双向增强**（Device_Info / Settings_Entry / Parameter Read/Write 状态机 + CH5/CH6 对调）
- **CRSF-Lua 桥接 M1-M3**（V3s 透明桥 + App LuaJ 引擎 + elrsV3.lua 参数界面）

**Out of scope**
- 视频编码/解码加速（使用第三方 SDK：EasyPlayer） — 非本项目核心能力
- 多客户端同时连接 — 当前为点对点架构（单 Android + 单 Linux），Hub 模式留待后续
- 无线传输（WiFi/4G/蓝牙） — 项目聚焦 USB 有线方案
- 生产级安全（TLS/认证） — USB 物理连接已是安全边界；web panel 无认证
- ELRS 之外的射频协议配置 — CRSF-Lua 桥接先聚焦 ELRS，其他模块依赖脚本兼容性

## Delivery Milestones

<!-- Business outcomes, not engineering tasks. /plan turns each into a plan. -->
<!-- Status: pending | in-progress | complete -->

| # | Milestone | Outcome | Status | Plan |
|---|---|---|---|---|
| 1 | MVP: 基础 TUN-over-USB 隧道 | Android 能 ping 通 Linux LAN 内设备 | **complete** | — |
| 2 | 可靠性: 热插拔恢复 + 心跳 + 错误处理 | 野外作业不掉线 | **complete** | — |
| 3 | 增值功能: RTSP 播放 + 端口转发 + 延迟测试 | 完整无人机操控体验 | **complete** | — |
| 4 | V3s 平台移植 + PB6 角色切换 | 物料成本降 10-20x，固件 v1.6.8 量产可用 | **complete** | — |
| 5 | OTA A/B 在线升级 | 浏览器一键升级 + 失败自动回退 | **complete** | — |
| 6 | CRSF-Lua 桥接: 真机 ELRS 参数配置 | DJI RC 上直接配置 ELRS 高频头参数（链路 + 渲染 + 改值全部打通） | **complete**（2026-08-14 真机验证：T-14 900 TX + 改值 1:8→1:16 生效） | — |
| 7 | 固件固化 + 清理 | 验证过的 bridge 逻辑固化进固件，删除测试残留 | pending | — |

## 当前进度追踪（CRSF-Lua 里程碑 6）

> 更新时间: 2026-08-14 | 详细交接见 [docs/SESSION_HANDOFF_CRSF_LUA.md](docs/SESSION_HANDOFF_CRSF_LUA.md)

### ✅ 已完成（完整打通 2026-08-14）
- **链路全通**：App(elrsV3.lua) → VPN(tun0) → USB → V3s bridge → UART0(115200) → 桥 → ELRS → Device_Info/Settings_Entry 回传 → App → Lua 渲染参数
- **真机完整验证**：DJI RC 显示 "T-14 900 TX" + 6 行参数，**改值 Telem Ratio 1:8→1:16 ELRS 生效**
- **7 个根因修复**：
  1. 固件 crsf_rx_byte CRC 校验起点 addr→type（ELRS 帧格式）
  2. 固件 bridge fwd 写入重试（摇杆占 TX）
  3. App CrsfBridge 收发分离 + bind 65532 + openProtectedPort
  4. App bindProcessToVpnNetwork（发包走 tun0）
  5. App buildCrsfFrame CRC 范围 len→len+1
  6. **固件 crsf_rx_thread 启动条件：bridge 模式也启动上行转发**（原仅 out_mode==c，SBUS 下 ELRS 响应不转发 → Device_Info 丢）
  7. **固件 bridge 模式跳过摇杆 CRSF 输出**（摇杆帧干扰 ELRS Lua backchannel，UART0 专用于 Lua 桥）
- **App 收包加固**（1.6.12）：stop() 释放 protectedPort + rxThread 连续消费多帧
- **UI 改进**：右侧操作按钮列 + 选中箭头 + 编辑 BLINK 闪烁
- **版本**：固件 1.6.10（待固化）、App 1.6.12

### ⚠️ 卡点（已解决 2026-08-14）
1. ~~Device_Info(36B) 偶发不到 App~~ → ✅ 根因: crsf_rx_thread 未启动 + 摇杆帧干扰, 已修复
2. ~~参数渲染偶发 0 行~~ → ✅ 依赖 #1, 已随修复解决

### 🆕 RC 通道配置入口（2026-08-15）
- **固件 src_cfg 移植**（v1.6.14）：RC 通道源配置系统（每输入源 min/max/mid/rev + 开关触发值）
  - rc_map.h/c: rc_src_cfg_t (71 参数) + rc_cfg_names + defaults/sanitize/set_cfg
  - web_server: 读/存/API 响应 src_cfg + src_cfg_names
  - dji_rc: load_rc_output_cfg 应用 src_cfg
  - **验证**: st1_min 1000→1100 保存读回成功 ✅
- **App 遥控页通道配置卡片**（v1.6.16）：客户友好界面
  - 输出协议 (SBUS/CRSF) + 预设 + 通道映射 (CH1-16) + 输入源微调 (分组折叠)
  - apiPost 加回调反馈 (保存成功/失败)
- **OTA 空间修复**（v1.6.14）：web_server tmpPath /var/log→/tmp（dji_rc.log 撑满 /var/log 导致 OTA write 失败）
- ⚠️ **已知问题**: App USB 授权弹窗反复弹（DJI RC 不保存 USB 授权, hasPermission 反复 false）→ 待修
3. 固件未固化（V3s 跑 /tmp 调试版 dji_rc）→ 待固化（M7）

### 🔧 调试方法
完整调试方式（桥监测/帧对比/V3s 状态/常用命令）见 [docs/SESSION_HANDOFF_CRSF_LUA.md §8](docs/SESSION_HANDOFF_CRSF_LUA.md)

### 📚 文档索引（CRSF-Lua / 项目）
| 文档 | 内容 |
|---|---|
| [docs/SESSION_HANDOFF_CRSF_LUA.md](docs/SESSION_HANDOFF_CRSF_LUA.md) | **CRSF-Lua 交接 + 进度 + 调试方法**（新会话从这里开始） |
| [docs/CRSF_LUA_PROGRESS_20260814.md](docs/CRSF_LUA_PROGRESS_20260814.md) | 调试进度记录 |
| [docs/crsf_lua_bridge_plan.md](docs/crsf_lua_bridge_plan.md) | 桥接架构 + App Lua 引擎计划 |
| [docs/crsf_ondevice_debug_notes.md](docs/crsf_ondevice_debug_notes.md) | 真机调试规范（VPN/USB 权限步骤） |
| [docs/BUILD.md](docs/BUILD.md) | V3s 固件构建（base rootfs 提取） |
| [docs/ANDROID_BUILD_REQUIREMENTS.md](docs/ANDROID_BUILD_REQUIREMENTS.md) | Android 编译环境（GStreamer min 集已入库） |
| [docs/CODEMAPS/android.md](docs/CODEMAPS/android.md) · [ubuntu.md](docs/CODEMAPS/ubuntu.md) | 代码地图 |
| [docs/PLATFORM.md](docs/PLATFORM.md) · [RELEASE.md](docs/RELEASE.md) · [USAGE.md](docs/USAGE.md) | 平台/发布/使用 |
| [docs/architecture.md](docs/architecture.md) | 整体架构 |

## Open Questions

- [x] **ELRS Lua 真机验证（M4）**：✅ 已解决（2026-08-14 真机打通，App bindProcessToVpnNetwork + openProtectedPort + dji_rc t3 启动）
- [x] ELRS 响应回传稳定性：✅ 已解决（crsf_rx_thread 启动 + 跳过摇杆输出后稳定回传）
- [x] CRSF-Lua 桥接固化位置：✅ 固化进 dji_rc（bridge 模式），非独立 uart_bridge
- [ ] Hub 模式（多 Android 客户端连接同一 Linux 板）何时需要？当前点对点架构能否满足所有已知场景？
- [ ] Web Panel 是否需要认证？（当前无需认证，USB 物理连接为安全边界；若未来支持网络访问需要）

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| DJI 固件更新封堵 RTL8812AU VID/PID 白名单 | Medium | High — 所有 DJI RC PLUS 2 用户无法使用 | 探索其他白名单设备 VID/PID；FunctionFS 自定义描述符备用方案 |
| V3s eth0 UDP 本地投递坏 | 已确认 | High — CRSF-Lua 链路依赖 UDP | App 走 tun_hub (10.0.0.1)，不用 eth0；已在文档固化 |
| ELRS 波特率轮换（~7s）导致会话中断 | Medium | Medium — Lua 参数读取失败 | 持续 ping + 等待；参考 elrs_lua_python 的 find_baud |
| App 发包走 wlan0（-uid 路由覆盖 tun0） | 已确认 | High — 隧道内 CRSF 不可达 | App 侧路由修复；DNAT 源限定规避 |
| OTA 对部分固件报 bad squashfs magic | Low（历史） | Medium | web_server OTA 接收逻辑复查（已记录，优先级低） |
| g_serial 内核模块在某些 Linux 板不可用 | Low (RK3588) / Medium (V3s) | High — 核心传输链路断裂 | 已用 MUSB 验证 g_serial 兼容；FunctionFS 作为 fallback |
| Android 系统杀死 VPN Service | Medium | Medium — 隧道中断直到 App 重启 | 前台 Service 通知 + BOOT_COMPLETED 自动启动 + 30s 重试循环 |

---
*Status: DRAFT — 持续同步当前进度。CRSF-Lua M4 真机验证的实施方案 pending via /plan。*
