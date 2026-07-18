# A/B OTA 升级 — U-Boot ENV 方案

> 状态: 规划中 | 日期: 2026-07-18

---

## 1. 为什么之前的方案失败了

| 尝试 | 存值位置 | 结果 |
|------|---------|------|
| v1: DRAM 0x43F00000 | 内核后面 | U-Boot 初始化 DRAM 时清零 |
| v2: SRAM 0x00020000 | 低 SRAM | U-Boot BSS 清零 |
| v3: DRAM 0x41600000 | 内核后面更远 | U-Boot 仍然清零 |

**SPL → U-Boot → Linux 三次进程切换，每次都初始化内存。** 通过内存传值不可行。

---

## 2. 正确方案：U-Boot Environment 分区

U-Boot 自带 ENV 持久化机制——编译时指定 ENV 分区位置，启动时从 SPI Flash 读取。

### 当前状态

```
U-Boot: "Loading Environment from nowhere... OK"
        → ENV 未配置，bootcmd 用硬编码
```

### 修改后

```
U-Boot: "Loading Environment from SPI Flash... OK"
        → 读 SPI ENV → rootpart=mtdblock3 → 选择 A 分区
        → 升级后 ENV 改为 rootpart=mtdblock4 → 选择 B 分区
```

### ENV 升级流程

```
Web上传 → 存 rootfs → .pending_flash
    ↓ reboot
S99: dd rootfs → mtdblock4 (空闲分区)
     fw_setenv rootpart /dev/mtdblock4    ← 写 SPI ENV
     fw_setenv bootcmd "..."              ← 更新完整命令
     reboot
    ↓
U-Boot: 读 SPI ENV → rootpart=mtdblock4 → boot B！
    成功启动 → S99 中 fw_setenv 确认标记 → 删除 pending_flash

如果 B 失败 → 进救援模式 → fw_setenv rootpart mtdblock3 → 切回 A
```

---

## 3. 改造清单

### 3.1 U-Boot `.config` — 启用 SPI ENV

```diff
+ CONFIG_ENV_IS_IN_SPI_FLASH=y
+ CONFIG_ENV_OFFSET=0x7E000
+ CONFIG_ENV_SIZE=0x2000   (8KB)
+ CONFIG_ENV_SECT_SIZE=0x1000 (4KB, w25q128 erase block)
- CONFIG_ENV_IS_NOWHERE=y  (当前)
```

### 3.2 `build_spi_final.py`

```diff
- ENV 不是真正的 U-Boot 环境变量 (只是给 bootargs 用的备份)
+ ENV 格式匹配 U-Boot 的 CRC+flag 格式
+ 初始化 bootargs + bootcmd + rootpart=mtdblock3
```

### 3.3 U-Boot CONFIG_BOOTCOMMAND — 简化为读 ENV

```diff
- "setexpr slot *0x41600000; if test ..." (复杂的 A/B 选择逻辑)
+ "run bootcmd_from_env"
  或者直接在 bootcmd 里用 env get rootpart
  实际配置: 保留现有 bootz 逻辑，/dev/mtdblock3 为默认
            升级时 S99 改 ENV → 指向 mtdblock4
```

### 3.4 `S99tun_nat_hub`

```diff
- printf '\x00' | dd of=/dev/mtdblock0 ... (写 SPI 裸扇区)
+ fw_setenv rootpart /dev/mtdblock4   (标准 ENV 写入)
+ fw_printenv → 确认写入成功
+ reboot
```

### 3.5 `SPL` — **完全不需要改**

不再需要 SPL 读取 slot flag。删除此前添加的 `spi0_read_data((void *)0x..., 0xFC000, 4)`。

### 3.6 `fw_printenv`/`fw_setenv` 工具

Buildroot 需要编译 `BR2_PACKAGE_UBOOT_TOOLS=y`，rootfs 中会包含 `/usr/sbin/fw_printenv` 和 `/usr/sbin/fw_setenv`。

配置文件 `/etc/fw_env.config`:
```
# Device    Offset      EnvSize
/dev/mtd0   0x7E000     0x2000
```

---

## 4. 改造对比 — 新方案 vs 旧方案

| 维度 | 旧方案 (DRAM slot flag) | 新方案 (U-Boot ENV) |
|------|------------------------|---------------------|
| SPL 改动 | 需要 (3 行) | **不需要** |
| U-Boot 改动 | bootcmd 条件判断 | **ENV 读取 (标准机制)** |
| 传值方式 | 内存写 → 读 (已被清零) | **SPI Flash 持久化** |
| Linux 端 | dd 裸写 SPI | **fw_setenv (标准工具)** |
| 可靠性 | ❌ 内存被清零 | ✅ **SPI 持久化，永不丢失** |
| 回退 | 写 flag 字节 | **fw_setenv 切回** |
| 复杂度 | 高 | **低 — 标准 U-Boot 机制** |

---

## 5. 实施顺序

| 步骤 | 内容 | 预计 |
|------|------|------|
| S1 | U-Boot 启用 `CONFIG_ENV_IS_IN_SPI_FLASH` + 编译 | 15min |
| S2 | 修正 `build_spi_final.py` ENV 格式 | 10min |
| S3 | Buildroot 编译 `uboot-tools` (fw_setenv) | 10min |
| S4 | S99 改为 fw_setenv | 5min |
| S5 | 全量编译 → FEL 刷入 → 验证 | 30min |
| **总** | | **~1h10min** |

---

## 6. 风险与缓解

| 风险 | 缓解 |
|------|------|
| ENV 写入失败 (SPI NOR 写保护) | S99 检查 fw_setenv 返回值 |
| ENV CRC 错误 | 默认 rootpart=mtdblock3 |
| fw_setenv 工具不在 rootfs | Buildroot 加包 |

---

*文档版本: v1.0 | 下一步: 审查确认 → 实施*
