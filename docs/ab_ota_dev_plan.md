# A/B OTA 开发计划 — 当前状态 + 阻塞问题

> 日期: 2026-07-19 | 状态: 规划阶段

---

## 一、已完成功能

| 功能 | 状态 | 说明 |
|------|------|------|
| A/B 分区布局 (4576KB×2) | ✅ | mtdparts 三处一致 |
| SPL flag 检查 → 改 U-Boot | ✅ | flag=0x00→搜改了 mtdblock3→4 |
| U-Boot 硬编码 root= | ✅ | `root=/dev/mtdblock3` 字符串 |
| web_server 升级 | ✅ | dd mtdblock4/3 + slot flag |
| S99 confirmed/retry 回退 | ✅ | 仅覆盖用户空间故障 |
| DHCP 3s + 时间戳 | ✅ | |
| dr_mode=peripheral | ✅ | |
| web_server peek=2048 | ✅ | |
| tmpfs /var/log | ✅ | |

## 二、当前阻塞问题

### P0-1: Kernel panic 后不自动重启

**现象:**
```
rootfs 损坏 → kernel panic → 串口卡在 call trace → 永不自启
→ 需手动断电/短接 FEL 才能恢复
```

**根因:** `sunxi-wdt nowayout=0` 不触发 panic 自启，panic 不是用户空间动作

**解法:** kernel cmdline 加 `panic=5`

**改动量:** U-Boot bootcmd 一行

### P0-2: 重启后无限循环同一坏分区

**现象:**
```
rootfs A 坏了 → panic → 重启 → SPL 又读 slot_flag → 又选 A → 又 panic
```

**根因:** SPL 只能读 SPI NOR，不能写。重启后 slot_flag 没变。S99 没机会跑。

**解法:** SPL 加 `spi0_write_byte()` 写 retry 计数 + retry 判断逻辑

### P1-3: web_server 升级无可视化日志

**现象:** 升级时静默 dd，无法 debug

**解法:** `handleFirmwareUpload` 每步加 `std::cout << "[fw] ..."`

### P1-4: 自动回退无法覆盖 kernel panic

| 故障 | 自动恢复 | 兜底 | 解法 |
|------|---------|------|------|
| web_server 崩溃 | ✅ S99 retry | — | — |
| kernel panic | ❌ (S99 没来得及跑) | 手动 FEL | SPL NOR 写 + retry |
| SPL 损坏 | ❌ (FEL 进不去) | SD 卡救援 | 硬件备份 |

---

## 三、实施计划

### Phase 1: panic=5 自动重启

| 项 | 内容 |
|----|------|
| 改动 | U-Boot bootcmd 加 `panic=5` |
| 测试 | `echo c > /proc/sysrq-trigger` → 5s 后自动重启 |
| 通过标准 | 串口显示 "Kernel panic" → 5s → "U-Boot SPL" |
| 预计 | 15min |

### Phase 2: SPL NOR 写能力

| 项 | 内容 |
|----|------|
| 改动 | `spl_spi_sunxi.c`: `spi0_write_byte()` 16 行 + retry 逻辑 12 行 |
| 写入地址 | 0xFC004-0xFC005 (uboot分区空闲区，距 SPL 1MB+) |
| 测试 | SPL 写测试字节 0xAA→Linux 启动后读回验证 |
| 通过标准 | `dd if=/dev/mtdblock0 bs=1 count=1 skip=1032196 | hexdump -C` → 0xAA |
| 预计 | 1h |

### Phase 3: 全流程集成测试

| 测试 | 操作 | 预期 |
|------|------|------|
| T3.1 正常升级 | Web 上传 v1.4.0 → reboot | kernel cmdline: `mtdblock4`, heartbeat: `1.4.0` |
| T3.2 坏固件回退 | Web 上传坏 rootfs → reboot | 3次 panic→WDT 重启 → 切回旧分区 |
| T3.3 Ping-pong | 在 B 上 Web 升级 → 回到 A | 版本号变化 + slot 交替 |
| T3.4 web 日志可见 | 升级时 `cat /var/log/web_server.log` | 有 `[fw] flashing...` 打印 |

### Phase 4: WDT 双重保险

| 项 | 内容 |
|----|------|
| 改动 | cmdline 加 `sunxi_wdt.nowayout=1 panic=5` |
| 测试 | 与 T3.2 相同 |
| 预计 | 5min |

---

## 四、测试固件版本

| 版本 | 用途 | heartbeat 返回 | 状态 |
|------|------|---------------|------|
| v1.3.1 | 当前稳定版 | `"version":"1.3.1"` | FEL 可刷 |
| v1.4.0 | 升级验证版 | `"version":"1.4.0"` | rootfs_v140.squashfs 已就绪 |
| v1.4.0-bad | 故意损坏版 | — | 待制作: `dd if=/dev/zero of=/tmp/bad.sq bs=1M count=4` |

---

## 五、文件改动清单

| 文件 | Phase 1 | Phase 2 | Phase 3 | Phase 4 |
|------|---------|---------|---------|---------|
| `u-boot/.config` | panic=5 | — | — | nowayout=1 |
| `spl_spi_sunxi.c` | — | spi0_write + retry | — | — |
| `web_server.cpp` | — | — | 升级日志 | — |
| `build_spi_final.py` | — | 初始化retry=FF | — | — |
| `S99tun_nat_hub` | — | — | — | — |

---

## 六、SPL NOR 写安全评估

| 风险 | 评估 | 缓解 |
|------|------|------|
| 写坏 SPL 本体 | 极低 | 写入区 0xFC000+ 距 SPL 0x000000 1MB+ |
| NOR 写时序错误 | 低 | Linux 读回验证 |
| retry 逻辑 bug | 低 | 先单独测试写字节功能 |
| 两分区全坏 | 极低 | SD 卡救援 + FEL 全刷 |
