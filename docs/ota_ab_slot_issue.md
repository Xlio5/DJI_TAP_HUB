# OTA A/B 槽切换问题（待修复）

> 记录日期: 2026-08-06
> 状态: 待修复（先记录，回头处理）

## 问题

**OTA 的 A/B 槽切换机制在当前固件里不可用。**

### 现象

- web_server 的 `/api/firmware/upload` OTA 上传 rootfs 到 inactive 槽（如 B/mtdblock4），并写 ctl block @ `0xFC000`（`00 ff 00 01 ff 00` = target B, unconfirmed, trial）
- **但 U-Boot bootcmd 硬编码 `root=/dev/mtdblock3`（A 槽）**，SPL/U-Boot 源码里**完全搜不到** `0xFC000` / 槽切换 / fallback 逻辑
- 后果：重启后设备仍从 A 槽启动，**B 槽的 OTA 固件永远不会被加载**

### 证据

```
# U-Boot .config CONFIG_BOOTCOMMAND (硬编码 A 槽)
root=/dev/mtdblock3 rootfstype=squashfs rootwait mtdparts=firmware:1M(uboot),64k(dtb),6M(kernel),4576k(rootfs_a),-(rootfs_b)

# U-Boot 源码全树搜 0xFC000 / 槽切换 —— 无结果
grep -rn '0xFC000' u-boot/  → 只有无关的 drivers

# SPL bin strings —— 无 rootfs/slot/fallback
strings spl/sunxi-spl.bin | grep -iE 'rootfs|slot|0xFC000|fallback'
```

### 影响的代码/产物

- `ubuntu/src/web_server.cpp` OTA 段（写 ctl block @ 0xFC000）
- `ubuntu/scripts/S99tun_nat_hub` 注释提到 "SPL also has NOR-based fallback for kernel panic" —— 但 SPL 里无此逻辑
- `scripts/build_spi_image.py` A/B ctl 区（0xFC000 flag/confirmed/retry/last_slot/boot_cnt）

### 可能的方向（待老大定夺）

1. **U-Boot bootcmd 加槽切换**：bootcmd 先读 ctl block @ 0xFC000，根据 flag 决定 `root=/dev/mtdblock3`（A）还是 `mtdblock4`（B）
2. **SPL 层做 fallback**：SPL 读 ctl block，按 last_slot/retry 决定启动哪个槽（S99 注释描述的但未实现的逻辑）
3. 重新审视是否需要 A/B OTA（若只需 FEL 全量烧录，可简化）

### 关键约束

- bootcmd 是**编译嵌入** U-Boot 的（CONFIG_ENV_IS_NOWHERE），改 bootcmd 需重编 U-Boot
- SPI env 区写的内容不被读取（build_spi_image.py 写的 bootcmd 无效，之前已确认）
