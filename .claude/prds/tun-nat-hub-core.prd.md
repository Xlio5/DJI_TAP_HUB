# TUN_NAT_HUB — 核心产品需求文档（反向 PRD）

> 本文档基于已有代码库（v1.1.0）反向梳理。记录产品解决了什么问题、给谁用、成功标准是什么。
> 实现细节见 `docs/architecture.md` 和 `docs/USAGE.md`。

## Problem

DJI RC PLUS 2 无人机遥控器在野外作业时需要通过 USB 线缆访问配套计算机（RK3588）所在局域网内的 IP 摄像头和其他网络设备，但 DJI RC PLUS 2 的 Android 系统不开放 USB 网络共享（RNDIS/ECM），WiFi 在户外不可用，且 `UsbManager.openDevice()` 受 DJI 白名单限制。**不用本项目，用户无法在遥控器屏幕上实时查看无人机载荷相机的视频流。**

## Evidence

- 项目已迭代至 v1.1.0，累计 20+ 次功能提交（git log 显示从 MVP 到 port forwarding、heartbeat、multi-camera、latency test 的完整演进）
- 已有完整的部署脚本体系（70+ 脚本）、systemd 服务单元、Web 配置面板
- 已在 RK3588 (Rock 5C) + DJI RC PLUS 2 组合上验证通过
- USB 隧道实测吞吐量 ~87Mbps，TCP RTT 3-6ms (p50)，满足 4Mbps 视频流 + <10ms 延迟目标
- 参考项目 PixelPilot 和 FPVue_android 的存在证明了同类需求的真实性

## Users

- **Primary**: 无人机系统集成工程师 — 使用 DJI RC PLUS 2 遥控器，需要在户外通过 USB 线缆访问配套计算机（RK3588/其他 Linux 板）局域网内的 IP 摄像头和网络设备
- **Secondary**: 无人机飞手/操作员 — 需要在遥控器屏幕上实时查看载荷相机画面（RTSP），管理端口转发规则
- **Not for**: 普通手机用户（依赖 DJI RC PLUS 2 的 USB Host 白名单绕过机制）、不需要 USB 直连的场景（WiFi 已有成熟方案）

## Hypothesis

We believe **USB 线缆上的 TUN 虚拟网卡隧道（g_serial + 自定义帧协议 + NAT 转发）** will **为 DJI RC PLUS 2 提供透明、低延迟的配套计算机局域网访问能力** for **无人机系统集成工程师**.
We'll know we're right when **4Mbps RTSP 视频流持续稳定播放 >30 分钟，TCP 延迟 <10ms (p99)，USB 热插拔后 30 秒内自动恢复连接**。

## Success Metrics

| Metric | Target | How measured |
|---|---|---|
| 视频流稳定性 | 4Mbps RTSP 连续播放 >30min 无断流 | 实际飞行测试 + App 内带宽监控 |
| 隧道延迟 | TCP RTT <10ms (p99)，<5ms (p50) | App 内置延迟测试（10 次 TCP connect to 10.0.0.1:9999） |
| 连接恢复 | USB 热插拔后 <30s 自动恢复 | 冷启动测试脚本 + 手动插拔测试 |
| 端口转发正确性 | 外网→内网 DNAT 规则 100% 转发正确 | `iptables -t nat -L` 验证 + 实际 TCP 连接测试 |
| 开机自启 | BOOT_COMPLETED 后 <60s VPN 就绪 | 冷启动诊断脚本 |

## Scope

**MVP** — 以下能力构成可验证假设的最小产品：
1. Android VPN Service 创建 TUN 接口并路由目标子网
2. USB Bulk 端点上的自定义帧协议（Magic + Length + Payload）
3. Linux 端 g_serial TTY 守护进程（TUN↔TTY 双向桥接）
4. Linux NAT MASQUERADE 实现 Android→LAN 透明访问
5. Web 配置面板（状态监控 + 端口转发管理）

**已实现的增值功能（v1.1.0）：**
- RTSP 视频播放器（EasyPlayer 原生 SDK，1ms 低延迟缓冲）
- 端口转发管理（TCP/UDP，4 字段表单，外网端口≠目标端口）
- 心跳链路检测（1s 轮询，3s 超时，App 侧三指示灯）
- 实时带宽显示（内核 tun_hub 统计，Tx/Rx Mbps）
- 多路摄像头管理（命名 + RTSP URL 配置）
- TCP 延迟测量工具（10.0.0.1:9999）
- USB 热插拔自动重连（30s 重试循环 + CAS 保护的 fd 切换）
- 冷启动诊断脚本
- 暗色主题 Compose UI + 侧边栏布局

**Out of scope**
- 视频编码/解码加速（使用第三方 SDK：EasyPlayer） — 非本项目核心能力
- 多客户端同时连接 — 当前为点对点架构（单 Android + 单 Linux），Hub 模式留待后续
- 无线传输（WiFi/4G/蓝牙） — 项目聚焦 USB 有线方案
- 生产级安全（TLS/认证） — USB 物理连接已是安全边界；web panel 无认证

## Delivery Milestones

| # | Milestone | Outcome | Status | Plan |
|---|---|---|---|---|
| 1 | MVP: 基础 TUN-over-USB 隧道 | Android 能 ping 通 Linux LAN 内设备 | **complete** | — |
| 2 | 可靠性: 热插拔恢复 + 心跳 + 错误处理 | 野外作业不掉线 | **complete** | — |
| 3 | 增值功能: RTSP 播放 + 端口转发 + 延迟测试 | 完整无人机操控体验 | **complete** | — |
| 4 | V3s 平台移植 | 物料成本降低 10-20x，功耗降低 3-5x | **pending** | → `/plan .claude/prds/v3s-porting.prd.md` |

## Open Questions

- [ ] Hub 模式（多 Android 客户端连接同一 Linux 板）何时需要？当前点对点架构能否满足所有已知场景？
- [ ] 是否需要支持 x86_64 Linux 板？（当前代码有部分 x86_64 适配，但未完整验证）
- [ ] Web Panel 是否需要认证？（当前无需认证，USB 物理连接为安全边界；若未来支持网络访问需要）
- [ ] 最大 MTU 是否可进一步优化？（当前 1400，USB 2.0 HS 支持 512B Bulk，分片开销待测量）

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| DJI 固件更新封堵 RTL8812AU VID/PID 白名单 | Medium | High — 所有 DJI RC PLUS 2 用户无法使用 | 探索其他白名单设备 VID/PID；FunctionFS 自定义描述符备用方案 |
| g_serial 内核模块在某些 Linux 板不可用 | Low (RK3588) / Medium (V3s) | High — 核心传输链路断裂 | V3s 移植前验证 MUSB 控制器的 g_serial 兼容性；FunctionFS 作为 fallback |
| USB Bulk 端点数据损坏（无 CRC 校验） | Very Low | Medium — 静默数据错误 | 协议层添加可选 CRC 校验帧（Phase 3 预留 Credit 帧可复用） |
| Android 系统杀死 VPN Service | Medium | Medium — 隧道中断直到 App 重启 | 前台 Service 通知 + BOOT_COMPLETED 自动启动 + 30s 重试循环 |

---
*Status: DRAFT — 基于已有代码反向梳理。V3s 移植的详细需求见 `v3s-porting.prd.md`。*
