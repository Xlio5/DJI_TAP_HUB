# TUN_NAT_HUB A/B OTA 升级 — 测试文档

> 版本: v1.0 | 日期: 2026-07-18

---

## 测试环境

| 组件 | 配置 |
|------|------|
| 硬件 | LicheePi Zero (Allwinner V3s) + w25q128 16MB SPI NOR |
| 串口 | COM10 @ 115200 8N1 |
| 烧录 | sunxi-fel (spi-rebase) via FEL mode |
| 网络 | eth0 192.168.144.66/24 |

---

## 测试固件版本

### v1.3.2 (当前最新，含 A/B OTA)

| 分区 | 内容 | 版本标识 |
|------|------|---------|
| rootfs_a (mtdblock3) | 完整系统 | `{"version":"1.3.2"}` |
| rootfs_b (mtdblock4) | 空 | — |

**特征:**
- slot_flag @ 0xFC000 = 0xFF (A)
- S99 带 A/B OTA 升级 ping-pong 逻辑
- DHCP 3s + 时间戳
- web_server peek=2048

### v1.3.3-test (升级功能验证)

与 v1.3.2 代码相同，仅 `#define VERSION "1.3.3-test"`
用于验证 OTA 升级后版本号确实变了。

---

## 测试项目

### T1 — 基础启动 (Slot A)  [P0]

| 步骤 | 操作 | 预期 |
|------|------|------|
| T1.1 | 上电，无 SD 卡 | SPL -> U-Boot -> autoboot |
| T1.2 | - | `root=/dev/mtdblock3` |
| T1.3 | - | DHCP 3s -> 192.168.144.66 |
| T1.4 | - | web_server + usb_tund 自动启动 |
| T1.5 | `wget http://127.0.0.1:8080/api/heartbeat` | `"version":"1.3.2"` |

### T2 — Slot 手动切换  [P0]

| 步骤 | 操作 | 预期 |
|------|------|------|
| T2.1 | 克隆 A 到 B | `dd if=/dev/mtdblock3 of=/dev/mtdblock4 bs=4096` |
| T2.2 | 切到 B | `printf '\x00' \| dd of=/dev/mtdblock0 bs=1 count=1 seek=1032192` |
| T2.3 | `sync && reboot` | |
| T2.4 | 启动 | `cat /proc/cmdline` -> 含 `mtdblock4` |
| T2.5 | 服务正常 | 版本号 1.3.2 (克隆的同一个) |
| T2.6 | 切回 A | `printf '\xFF' \| dd of=/dev/mtdblock0 bs=1 count=1 seek=1032192; sync; reboot` |
| T2.7 | 启动 | `cat /proc/cmdline` -> 含 `mtdblock3` |

### T3 — OTA 升级闭环  [P0]

| 步骤 | 操作 | 预期 |
|------|------|------|
| T3.1 | 确认在 A | `grep mtdblock3 /proc/cmdline` |
| T3.2 | Web 上传 v1.3.3-test rootfs | `http://192.168.144.66:8080/` |
| T3.3 | Web 返回 | `"ok":true,"message":"Rootfs staged..."` |
| T3.4 | `reboot` | |
| T3.5 | S99 日志 | `A->B: flashing rootfs_b (mtdblock4)` |
| T3.6 | 自动重启 | (S99 执行 dd+flag+reboot) |
| T3.7 | U-Boot log | `root=/dev/mtdblock4` |
| T3.8 | 验证版本 | `{"version":"1.3.3-test"}` |
| T3.9 | 分区确认 | `cat /proc/cmdline` -> `mtdblock4` |

### T4 — Ping-pong (B->A)  [P1]

| 步骤 | 操作 | 预期 |
|------|------|------|
| T4.1 | 当前在 B | flag=0x00, mtdblock4 |
| T4.2 | Web 上传 v1.3.2 rootfs | |
| T4.3 | reboot | |
| T4.4 | S99 | `B->A: flashing rootfs_a (mtdblock3)` |
| T4.5 | 启动 | mtdblock3, version 1.3.2 |

### T5 — 坏文件拒绝  [P1]

| 步骤 | 操作 | 预期 |
|------|------|------|
| T5.1 | `dd if=/dev/zero of=/tmp/fake.sq bs=1M count=4` | |
| T5.2 | Web 上传 fake.sq | |
| T5.3 | Web 返回 | `"ok":false,"error":"not a valid squashfs"` |
| T5.4 | 系统 | 正常运行 |

### T6 — 重复上传覆盖  [P2]

| 步骤 | 操作 | 预期 |
|------|------|------|
| T6.1 | Web 上传 v1.3.3-test | OK |
| T6.2 | 不重启，再上传 v1.3.2 | 覆盖 /var/log/new_rootfs.sq |
| T6.3 | reboot | 升级到分区，v1.3.2 生效 |

---

## 回滚步骤

### 升级失败，切回另一个分区

```
# 确认当前在哪个分区
cat /proc/cmdline | grep -o 'mtdblock.'

# 如果跑在 B 不爽，切回 A
printf '\xFF' | dd of=/dev/mtdblock0 bs=1 count=1 seek=1032192
sync && reboot
```

### 两个分区都坏的极端恢复

```
1. FEL 刷入完整 16MB spi_image.bin
2. 或 SD 卡启动救援
```

---

## 通过标准

| 测试 | 条件 | 权重 |
|------|------|------|
| T1 | 正常启动 A | **P0 — 必须** |
| T2 | 手动切换 A<->B | **P0 — 必须** |
| T3 | OTA 闭环升级 | **P0 — 必须** |
| T4 | Ping-pong 来回 | P1 |
| T5 | 坏文件拒绝 | P1 |

**P0 全部通过 = A/B OTA 可用。**
