# 全志 V3s 平台移植 — 产品需求文档

> 来源项目: TUN_NAT_HUB v1.1.0 (RK3588)  
> 目标平台: Allwinner V3s (ARM Cortex-A7, 64MB DDR2)  
> 编制日期: 2026-06-28

## Problem

TUN_NAT_HUB v1.1.0 已在 RK3588 (Rock 5C) 上稳定运行，但 RK3588 物料成本高（~500-800 RMB）、功耗大（10-15W）、体积大（85×56mm 开发板），不适合大规模部署和嵌入式集成。**无人机系统集成商需要一套物料成本 <50 RMB、功耗 <3W、可芯片级嵌入 DJI RC 外壳的配套计算方案。**

## Evidence

- RK3588 (Rock 5C) 方案已验证完整功能链路（USB TUN 隧道 + NAT + RTSP + Web Panel）
- 全志 V3s 是成熟量产芯片（QFP128 封装，SMT 批量数年），IPC 行业广泛使用
- V3s 具备所有必需的硬件外设：USB 2.0 OTG、10/100M 以太网 MAC、64MB DDR2
- LicheePi Zero 开发板已在社区验证 g_serial + TUN 驱动
- Buildroot 已支持 V3s 的完整 BSP

## Users

- **Primary**: 无人机系统集成工程师 — 需要低成本、低功耗的机载配套计算机，通过 USB 为 DJI RC PLUS 2 提供局域网 IP 访问
- **Secondary**: 无人机产品经理/硬件工程师 — 需要可量产、芯片级集成的方案（QFP 封装适合 SMT 批量）
- **Not for**: 现有 RK3588 已满足需求的用户（无需迁移）、需要多路 4K 视频编码的场景（V3s 单核 A7 性能不足）

## Hypothesis

We believe **将 TUN_NAT_HUB 服务端完整移植到全志 V3s 平台（Buildroot + musl + ARMv7 交叉编译）** will **在保持 100% Android 端兼容的前提下，将物料成本降低 10-20x、功耗降低 3-5x** for **需要大规模部署或芯片级集成的无人机系统集成商**.
We'll know we're right when **所有 10 项功能验收测试通过 + 性能指标达标（TCP RTT ≤10ms p50, 吞吐 ≥15Mbps）+ 24h 稳定性无内存泄漏**。

## Success Metrics

| Metric | RK3588 基准 | V3s 目标 | How measured |
|---|---|---|---|
| TCP RTT (p50) | 3-6ms | ≤ 10ms | App "测延迟" 按钮 + nc |
| USB 吞吐量 | 31Mbps | ≥ 15Mbps | iperf 10.0.0.1 ↔ 10.0.0.2 |
| Daemon 内存 | 2-4MB | ≤ 8MB | `free -m` 或 `/proc/pid/status` |
| 系统总内存 | ~500MB | ≤ 32MB | `free` at idle |
| CPU 空载占用 | <1% | <5% | `top -n1` |
| 冷启动到就绪 | <30s | <30s | 断电→daemon ready 计时 |
| 24h VmRSS 波动 | — | ≤ 1MB | `/proc/pid/status` 每小时采样 |
| USB 冷启动识别率 | — | 10/10 次 | 循环断电测试 |
| 功能验收通过率 | — | 10/10 项 | 验收清单逐项打勾 |

## Scope

**MVP** — 以下核心能力在 V3s 上运行，APK 不变：
1. USB g_serial Bulk 通信（VID 0x0BDA, PID 0x8812 伪装不变）
2. TUN 虚拟网卡（tun_hub, 10.0.0.1/24）+ NAT MASQUERADE
3. C++ 守护进程 usb_tund（TUN↔TTY 双向桥接 + 心跳 + TCP ping server）
4. Python Web 配置面板（:8080, 4 Tab, 所有 API）
5. 端口转发 DNAT 管理（App 侧边栏 ↔ V3s iptables）
6. BusyBox init 开机自启

**Out of scope**
- V3s 硬件设计/PCB Layout — 使用 LicheePi Zero 开发板验证，量产转自定义 PCB
- H.264 视频编码复用 — V3s 内置编码器留给后续视频处理功能
- Hub 模式（多客户端） — 当前点对点架构不变
- Lua 重写 Web Panel — 先维持 Python，优化阶段再评估
- Android APK 修改 — 零改动，使用现有 v1.1.0 APK

## Delivery Milestones

| # | Milestone | Outcome | Status | Plan |
|---|---|---|---|---|
| 1 | Phase 0: 环境搭建 | Buildroot 交叉编译环境就绪 + V3s 开发板启动 | **complete** | [v3s-porting.plan.md](../plans/v3s-porting.plan.md) |
| 2 | Phase 1: 核心移植 | usb_tund ARMv7 二进制 + 所有配置脚本适配 | **complete** | — |
| 3 | Phase 2: 集成验证 | DJI RC ↔ V3s USB 联通 + 10 项功能验收通过 | pending | — |
| 4 | Phase 3: 稳定性 + 性能 | 24h 压力测试 + 10 轮冷启动 + 性能对比数据 | pending | — |
| 5 | Phase 4: 文档交付 | V3s 部署手册 + Buildroot defconfig + 交叉编译指南 | pending | — |

## Open Questions

- [ ] **D1**: V3s 开发板选型 — LicheePi Zero + ETH 底板还是自定义 PCB？开发阶段建议 LicheePi Zero，量产转自定义
- [ ] **D2**: Buildroot vs Yocto？建议 Buildroot（社区成熟、镜像小、配置简单）
- [ ] **D3**: 以太网 PHY — RMII + IP101GR 还是 SPI 以太网 (ENC28J60)？建议 RMII + IP101GR（性能好，V3s 原生支持）
- [ ] **D4**: C 库 — musl 还是 uClibc-ng？建议 musl（C++17 兼容性更好）
- [ ] **D5**: 静态链接还是动态链接？建议静态链接 musl（rootfs 无需 C++ 标准库）
- [ ] **D6**: g_serial 驱动在 V3s 的 MUSB 控制器上行为是否与 DWC3 一致？需 Phase 0 验证
- [ ] **D7**: Web Panel 是否后续迁移到 Lua（节约 ~6MB 内存）？先维持 Python，优化阶段评估

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| g_serial 在 MUSB 控制器不兼容 | Medium | High — 核心传输链路断裂 | Phase 0 优先验证；fallback 用 configfs/FunctionFS |
| 64MB 内存不足（daemon + Python + 内核 + 网络栈） | High | Medium — Web Panel 或 daemon 可能 OOM | 裁剪 Buildroot 最小化；Python→Lua 作为降级方案 |
| 以太网 PHY 缺失（部分 V3s 板无板载 PHY） | High | Medium — 无 LAN 口则 NAT 无意义 | 必须选用带 RMII PHY 的板（如 LicheePi Zero + ETH 底板） |
| musl vs glibc 兼容性 | Low | Low — C++17 + POSIX 完全标准 | pthread/网络均为 POSIX，musl 兼容；Phase 1 编译验证 |
| USB OTG ID 引脚未拉低 | Medium | High — USB Device 模式不生效 | 与硬件工程师确认原理图；LicheePi Zero 已默认拉低 |
| Buildroot 内核版本 g_serial 行为差异 | Low | Medium | 参考 LicheePi Zero 社区已验证的内核版本 (5.2+) |

---
*Status: DRAFT — V3s 移植需求文档。实施计划待 `/plan .claude/prds/v3s-porting.prd.md` 生成。*
*详细技术分析见 `docs/PRD-v3s-porting.md`（含引脚表、Buildroot defconfig、CMake toolchain 示例）。*
