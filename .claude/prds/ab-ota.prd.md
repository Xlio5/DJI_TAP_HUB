# V3s A/B 分区 OTA 在线升级

## Problem

V3s SPI Flash 固件升级需要 FEL 线、SD 卡、串口线，操作繁琐且容易砖。
单分区 squashfs 只读 + MTD 锁住，无法在线写入新固件。已通过 A/B 分区 + SPL 改 U-Boot 解决了"可写"问题，
但升级失败后 kernel panic 不自动重启，也没有验证机制保证写入正确性，缺乏完整的自动回退闭环。

## Evidence

- v1.3.1→v1.4.0 升级时，web_server dd 到 mtdblock3 后数据损坏（`unable to read id index table`），排查 2 小时，最终 FEL 全刷才修复
- v1-v6 内存传值方案全部失败，每次验证 SPL 是否改 U-Boot 需要手动 `printenv bootcmd`
- web_server 升级静默——上传返回"成功"但实际上 B 分区没写入，无日志可查

## Users

- **Primary**: 设备操作者 — 需要不依赖 FEL/SD 卡/串口线完成固件升级
- **Not for**: 不需要增量更新（4MB 全量够用）、不需要进度条（秒传）

## Hypothesis

We believe **A/B 分区 + SPL NOR 写 retry + 自动重启 + rootfs 校验尾** will **实现"上传→重启→自动生效"且"失败自动回退"的闭环 OTA 升级**
for **V3s 设备使用者**。
We'll know we're right when **Web 上传 v1.4.0 → reboot → 自动从 B 分区启动 → heartbeat 返回 1.4.0，且故意上传坏固件后 3 次重启自动切回旧分区**。

## Success Metrics

| Metric | Target | How measured |
|---|---|---|
| OTA 升级成功率 | 100% | Web 上传 v1.4.0 → reboot → `mtdblock4` + `"version":"1.4.0"` |
| 失败自动回退 | 3 次内切回 | 上传坏 rootfs → 观察 3 次 panic→WDT 重启 → 自动切回旧分区 |
| rootfs 校验 | 唯一通过 | dd 写完 → 读回 magic tail `TUN_NAT_HUB` + CRC32 校验 |

## Scope

**MVP** — 让 V3s OTA 升级从一个"需要 FEL 线的硬件操作"变成"浏览器点一下就能完成":

| 优先级 | 功能 | 为什么 |
|--------|------|--------|
| P0 | panic=5 auto-reboot | kernel panic 后必须自己重启 |
| P0 | rootfs 校验尾 (8B magic+CRC) | dd 写完验证完整性 |
| P0 | SPL NOR 写 + retry | 3 次失败自动切回旧分区 |
| P1 | web_server 升级日志 | 每步可查 |
| P1 | 持久化状态日志 | SPI uff 分区空闲 16KB 够用 |

**Out of scope**
- 进度条 — 4MB 秒传，不需要
- Web 手动回滚按钮 — 先让自动回退工作
- 增量更新 — 全量够用

## Delivery Milestones

<!-- Business outcomes, not engineering tasks. /plan turns each into a plan. -->
<!-- Status: pending | in-progress | complete -->

| # | Milestone | Outcome | Status | Plan |
|---|---|---|---|---|
| 1 | panic=5 自动重启 | kernel panic 后 5s 自启 | pending | — |
| 2 | SPL NOR 写 + retry | 3 次失败自动切分区 | pending | — |
| 3 | rootfs 校验尾 | 升级后读回验证 magic+CRC | pending | — |
| 4 | 全流程验证 | 正常升级 + 坏固件回退 | pending | — |

## Open Questions

- [ ] SPL `spi0_write_byte` NOR 时序在 w25q128 上是否直接可用？→ 需写测试字节验证
- [ ] `panic=5` 在当前内核 config 是否生效？→ 需 `echo c > /proc/sysrq-trigger` 测试
- [ ] 校验尾 8 字节放在 squashfs 尾部是否破坏文件系统格式？→ 需测试 `unsquashfs` 校验

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| SPL NOR 写坏本体 | 极低 | 砖 | 写入区距 SPL 1MB+ |
| NOR 写时序不匹配 | 低 | 写不进去 | Linux 读回验证 |
| 校验尾破坏 squashfs | 低 | 无法挂载 | unsquashfs 预测试 |

---
*Status: DRAFT — requirements only. Implementation planning pending via /plan.*
