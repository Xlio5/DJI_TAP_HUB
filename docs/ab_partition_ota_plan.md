# TUN_NAT_HUB A/B 分区 OTA 方案

> 状态: 规划中 | 日期: 2026-07-18

---

## 1. 背景

### 当前架构限制

```
16MB SPI NOR (w25q128)
├── uboot:   1MB   (0x000000)  SPL+U-Boot
├── dtb:     64KB  (0x100000)  Device Tree
├── kernel:  6MB   (0x110000)  Linux zImage
└── rootfs:  9.1MB (0x710000)  squashfs (只读) ← 单分区
```

- squashfs 挂载时内核锁 `/dev/mtd0` → 无法 dd 写入
- 无持久化可写存储 → 在线升级闭环无法成立

### 验证结论

- ✅ `dd of=/dev/mtdblock4` 可写（非活跃分区）
- ✅ `dd of=/dev/mtd0 seek=2816` 被锁（rootfs 占用）
- ✅ `dd of=/dev/mtdblock2` 可写（kernel 分区未被 mount）
- 结论: **运行时只能写未挂载的 mtdblock 分区**

---

## 2. A/B 分区布局

```
16MB SPI NOR Flash (w25q128)
═══════════════════════════════════════════════════════════════
偏移量         大小      分区        设备          说明
───────────────────────────────────────────────────────────────
0x000000       1MB      uboot       mtd0/mtdblock0  SPL+U-Boot+ENV
0x07E000       8KB      env         mtd0内          bootargs+bootcmd
0x100000       64KB     dtb         mtd1/mtdblock1  Device Tree
0x110000       6MB      kernel      mtd2/mtdblock2  Linux zImage
0x710000       4608KB   rootfs_a    mtd3/mtdblock3  当前活跃 slot (4.5MB)
0xB90000       4608KB   rootfs_b    mtd4/mtdblock4  非活跃 slot (4.5MB)
0xFFF000       4KB      slot_flag   mtd0 尾部        1字节标志: 0=A, 1=B
═══════════════════════════════════════════════════════════════
```

### mtdparts

```
mtdparts=firmware:1M(uboot),64k(dtb),6M(kernel),4608k(rootfs_a),-(rootfs_b)
```

### 容量分析

| 分区 | 容量 | 当前 rootfs | 余量 |
|------|------|------------|------|
| rootfs_a | 4608KB (4.5MB) | ~4.0MB | ~0.5MB |
| rootfs_b | 4608KB (4.5MB) | — | — |

rootfs 增长空间: ~0.5MB，够用。

---

## 3. 升级流程（全链路）

### A/B 切换逻辑图

```
┌──────────────────────────────────────────────────────────────┐
│                    当前运行 Slot A                            │
│               root=/dev/mtdblock3  flag=0xFF                 │
│                           │                                  │
│                    Web 上传 rootfs                           │
│                   存 /var/log/new_rootfs.sq                    │
│                   设置 .pending_flash                        │
│                   用户点 reboot                               │
│                           │                                  │
│                    ┌──────▼──────┐                           │
│                    │  S99 start  │                           │
│                    │  检测 flag  │                           │
│                    └──────┬──────┘                           │
│                           │                                  │
│              grep /proc/cmdline → "mtdblock3"                │
│              → 当前在 A，升级写入 B                          │
│                           │                                  │
│         ┌─────────────────┼─────────────────┐               │
│         │                 │                 │               │
│    dd → mtdblock4    flag→0x00         reboot               │
│         │                 │                 │               │
│         └─────────────────┼─────────────────┘               │
│                           │                                  │
│                    ┌──────▼──────┐                           │
│                    │ SPL 启动    │                           │
│                    │ 读 0xFC000  │                           │
│                    │ → flag=0x00 │                           │
│                    │ 存 DRAM     │                           │
│                    │ 0x43F00000  │                           │
│                    └──────┬──────┘                           │
│                           │                                  │
│                    ┌──────▼──────┐                           │
│                    │  U-Boot     │                           │
│                    │  setexpr    │                           │
│                    │  slot       │                           │
│                    │  *0x43F00000│                           │
│                    │  = 0x00     │                           │
│                    │             │                           │
│                    │  test -eq 0 │                           │
│                    │    ├─ YES ──► root=/dev/mtdblock4       │
│                    │    └─ NO  ──► root=/dev/mtdblock3       │
│                    │             │                           │
│                    │  bootz      │                           │
│                    └──────┬──────┘                           │
│                           │                                  │
│                    ┌──────▼──────┐                           │
│                    │  现在在 B   │                           │
│                    │  mtdblock4  │                           │
│                    │  flag=0x00  │                           │
│                    └─────────────┘                           │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

```


┌──────────────────────────────────────────────────────────────┐
│                    后续升级（运行 B，回切 A）                  │
│                                                              │
│   当前在 B (mtdblock4, flag=0x00)                            │
│                           │                                  │
│              Web上传 → reboot → S99                          │
│              grep "mtdblock4" → 当前在 B                     │
│                           │                                  │
│         ┌─────────────────┼─────────────────┐               │
│    dd → mtdblock3    flag→0xFF         reboot               │
│         │                 │                 │               │
│         └─────────────────┼─────────────────┘               │
│                           │                                  │
│              SPL→U-Boot: flag=0xFF → mtdblock3 → A!         │
│                                                              │
│    规则: 每次升级，不活跃分区被覆盖，flag 切到新分区          │
│    A→B→A→B→... 来回 ping-pong                                │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### ping-pong 流程图

```
        升级写到B     升级写到A     升级写到B
    A ──────────► B ──────────► A ──────────► B
  mtdblock3     mtdblock4    mtdblock3     mtdblock4
  flag=FF       flag=00      flag=FF       flag=00
```

### 异常恢复

| 异常 | 后果 | 恢复 |
|------|------|------|
| Web 上传中断 | `.pending_flash` 没创建 | 无影响，重新上传 |
| dd 中途断电 | 目标分区半写 | SPL→U-Boot 启动 → root 挂载失败 → **需 SD 卡救援** |
| flag 写入失败 | flag 没切过去 | 下次还是当前分区，重来 |

---

## 4. 升级流程（用户视角）

### 3.1 用户操作

```
Web页面 → 选择 rootfs.squashfs → 点"升级"
       → web_server 存文件到 /var/log (tmpfs)
       → 返回 "已就绪，请重启"
       → 用户手动 reboot (或点击 Web 的重启按钮)
```

### 3.2 系统自动

```
┌─ reboot ──────────────────────────────────────────────────┐
│                                                            │
│ S99 start:                                                 │
│   1. mount -t tmpfs tmpfs /var/log                         │
│   2. [ -f /var/log/.pending_flash ] ?                      │
│      NO  → 正常启动                                        │
│      YES → 进入升级流程 ↓                                  │
│                                                            │
│   3. 读 /dev/mtd0 offset 0xFFF000 1字节:                   │
│      当前在 rootfs_a? → dd /var/log/new_rootfs.sq           │
│                          → /dev/mtdblock4 (rootfs_b)       │
│                     → dd '\x01' → /dev/mtd0 seek=4092      │
│      当前在 rootfs_b? → dd /var/log/new_rootfs.sq           │
│                          → /dev/mtdblock3 (rootfs_a)       │
│                     → dd '\x00' → /dev/mtd0 seek=4092      │
│                                                            │
│   4. rm /var/log/.pending_flash /var/log/new_rootfs.sq     │
│   5. reboot                                                │
│                                                            │
├─ reboot ───────────────────────────────────────────────────┤
│                                                            │
│ SPL start:                                                 │
│   spi0_read_data(0xFFF000) → 读1字节                       │
│   → 存到 EAX/R0 → 传递给 U-Boot                             │
│                                                            │
│ U-Boot bootcmd:                                            │
│   读 scratch register → slot=0? root=mtdblock3:mtdblock4   │
│                                                            │
│ Linux boot:                                                │
│   root=mtdblock3 或 mtdblock4 → 新 rootfs 生效!            │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

### 3.3 回滚

如果升级失败（rootfs_b 无法启动），回退到 SD 卡启动 → U-Boot 手动 `mw` 写 slot flag → 切回。

---

## 4. 代码改造清单

### 4.1 SPL (`spl_spi_sunxi.c`)

**改动:** 在预载 kernel+DTB 之后，多读 1 字节 slot flag。

```c
// 当前代码:
spi0_read_data((void *)0x41000000, 0x110000, 0x5A78B8);  // kernel
spi0_read_data((void *)0x42000000, 0x100000, 0x4000);     // DTB

// 新增:
uint8_t slot_flag;
spi0_read_data(&slot_flag, 0xFFF000, 1);  // 读 slot flag
writel(slot_flag, 0x01C28000 + 0x1C0);     // 存到 scratch register 0x1C0
```

### 4.2 U-Boot bootcmd (`CONFIG_BOOTCOMMAND`)

```bash
setexpr slot 0x1C0;  # 读 scratch register
if test ${slot} -eq 1; then
  setenv bootpart /dev/mtdblock4
else
  setenv bootpart /dev/mtdblock3
fi;
setenv bootargs console=ttyS0,115200 root=${bootpart} rootfstype=squashfs rootwait mtdparts=firmware:1M(uboot),64k(dtb),6M(kernel),4608k(rootfs_a),-(rootfs_b) g_serial.idVendor=0x0BDA g_serial.idProduct=0x8812 g_serial.use_acm=0;
fdt addr 0x42000000;
bootz 0x41000000 - 0x42000000
```

### 4.3 `build_spi_final.py`

- ENV 里 mtdparts 改为含 `rootfs_a` + `rootfs_b`
- 不再需要在 ENV 里写死 root=/dev/mtdblock3
- slot flag @ 0xFFF000 初始化为 `\x00` (A)

### 4.4 S99 (`S99tun_nat_hub`)

```sh
# 0.5 Check pending firmware flash
PENDING=/var/log/.pending_flash
NEW_ROOTFS=/var/log/new_rootfs.sq

if [ -f "$PENDING" ] && [ -f "$NEW_ROOTFS" ]; then
    _ts "FIRMWARE UPGRADE: detecting active slot..."

    # Read current slot flag
    SLOT=$(dd if=/dev/mtd0 bs=1 count=1 skip=10485720 2>/dev/null | hexdump -e '1/1 "%d"')

    if [ "$SLOT" = "0" ] || [ "$SLOT" = "" ]; then
        # Running from A, flash to B
        _ts "A->B: flashing rootfs_b (mtdblock4)..."
        dd if=$NEW_ROOTFS of=/dev/mtdblock4 bs=4096 2>&1
        printf '\x01' | dd of=/dev/mtd0 bs=1 count=1 seek=10485720 2>/dev/null
    else
        # Running from B, flash to A
        _ts "B->A: flashing rootfs_a (mtdblock3)..."
        dd if=$NEW_ROOTFS of=/dev/mtdblock3 bs=4096 2>&1
        printf '\x00' | dd of=/dev/mtd0 bs=1 count=1 seek=10485720 2>/dev/null
    fi

    sync
    rm -f $PENDING $NEW_ROOTFS
    _ts "Firmware flash done — rebooting"
    reboot
fi
```

### 4.5 web_server (`web_server.cpp`)

**不需要额外改动** — 两阶段修复（`/var/log/new_rootfs.sq` + `.pending_flash`）已经做好。

---

## 5. 实施顺序

| 步骤 | 内容 | 验证方式 | 预计时间 |
|------|------|---------|---------|
| **S1** | U-Boot bootcmd 改 A/B 选择逻辑 | 编译 → FEL 刷 → boot 看 root= | 30min |
| **S2** | SPL 读 slot flag | 编译 → FEL 刷 → 手动写 flag → boot | 30min |
| **S3** | build_spi_final.py 更新 mtdparts | 生成 16MB 镜像检查分区 | 10min |
| **S4** | S99 A/B 升级逻辑 | 编译 rootfs → FEL 刷 → Web 上传测试 | 30min |
| **S5** | 全流程集成测试 | Web上传 → reboot → 确认切到新分区 | 30min |
| **总** | | | ~2h |

---

## 6. 风险与边界

| 风险 | 缓解 |
|------|------|
| SPL 裸寄存器传值在不同版本可能失效 | scratch register 地址验证 |
| rootfs 超过 4.5MB | 监控 squashfs 大小 |
| slot flag 被意外擦除 | flag 放在 uboot 分区尾部，不做全 chip erase |
| 升级失败变砖 | 保留 SD 卡启动回滚路径 |

---

## 7. 回滚步骤（升级失败时）

```
1. SD 卡插入 → 上电 → U-Boot
2. fatload mmc 0:1 0x41000000 zImage
   fatload mmc 0:1 0x42000000 dtb
   fdt addr 0x42000000
   setenv bootargs ... root=/dev/mtdblock3 ...  (强制用 A)
   bootz 0x41000000 - 0x42000000
3. 进去后:
   printf '\x00' | dd of=/dev/mtd0 bs=1 count=1 seek=10485720
   重置 slot flag 为 A
```

---

*文档版本: v1.0 | 下一步: 开始 S1 — U-Boot bootcmd 改造*