# TUN_NAT_HUB v1.4.3 发布说明

> 发布日期: 2026-07-20 | 基于 commit: flash 分支

## 固件文件

| 文件 | 大小 | 用途 |
|------|------|------|
| `backup/rootfs.squashfs` | 4.4 MB | **OTA Web 升级** |
| `backup/rootfs_v143.squashfs` | 4.4 MB | OTA Web 升级（带版本号） |
| `backup/spi_image.bin` | 16 MB | **FEL 全量刷写** |
| `backup/spi_image_v143.bin` | 16 MB | FEL 全量刷写（带版本号） |

## 版本功能

| 功能 | 状态 |
|------|------|
| v1.4.3 版本号 | ✅ |
| A/B OTA ping-pong 升级 | ✅ |
| Web 升级完成后自动重启 | ✅ |
| WDT 双保险 (nowayout=1 + panic=5) | ✅ |
| 内核 cmdline 不再覆盖 root= | ✅ |
| S99 Linux 侧 retry + last_slot 自动回退 | ✅ |
| 坏固件 magic 校验拒绝 | ✅ |

## FEL 刷写（全量重新烧录）

### 前置条件

- Windows 安装 usbipd-win + WSL (Ubuntu)
- WSL 内安装 sunxi-tools (`sunxi-fel`)

### 操作步骤

1. V3s 断电
2. **短接 SPI FLASH MOSI 和 GND** → USB 上电
3. Windows 终端执行：
```powershell
# 绑定并附加到 WSL
usbipd bind -b 1-9 -f
usbipd attach -b 1-9 --wsl

# 刷写 16MB SPI 镜像（耗时约 1-2 分钟）
wsl -u root sunxi-fel spiflash-write 0 backup/spi_image.bin

# 读回校验（应看到 eGON.BT0 启动头）
wsl -u root sunxi-fel spiflash-read 0 64 /tmp/vfy.bin
wsl xxd /tmp/vfy.bin | head -2
```

4. 断开短接，重新上电
5. 待 DHCP 超时（3秒）后访问 `http://192.168.144.66:8080`
6. 页面右上角应显示 **v1.4.3**

### 启动串口输出

```
U-Boot SPL 2026.07-rc5 (Jul 20 2026 - 00:00:00 +0800)
DRAM: 64 MiB
Trying to boot from sunxi SPI

U-Boot 2026.07-rc5 (Jul 20 2026 - 00:00:00 +0800)
...
Hit any key to stop autoboot: 0
Kernel image @ 0x41000000 ...
## Flattened Device Tree blob at 42000000
Starting kernel ...

Welcome to Buildroot
...
[00:00:15] Starting TUN_NAT_HUB v1.4.3...
[00:00:15] confirmed=255 retry=0 last_slot=255
[00:00:15] usb_tund: started
[00:00:15] web_server: started
[00:00:16] Boot confirmed stable
[00:00:16] TUN_NAT_HUB ready
```

## OTA Web 升级（在线更新 rootfs）

### 前置条件

- V3s 已正常启动，`http://192.168.144.66:8080` 可访问

### 操作步骤

1. 浏览器打开 `http://192.168.144.66:8080`
2. 在 **固件升级 (Rootfs)** 区域 → 点击文件选择
3. 选择 `backup/rootfs.squashfs`（或 `rootfs_v143.squashfs`）
4. 点击 **⬆ 升级**
5. **v1.4.3 会自动重启**（约 2 秒后），等待 10 秒
6. 刷新页面，确认版本号改变了

### Ping-pong 验证

从 v1.4.3 升级到其他版本再升级回来，验证 A/B 槽都能正常工作：

| 当前版本 | 上传文件 | 预期 |
|----------|----------|------|
| v1.4.3 (A槽) | `rootfs_v142.squashfs` | 自动重启 → B槽 v1.4.2 |
| v1.4.2 (B槽) | `rootfs_v143.squashfs` | 手动 `reboot` → A槽 v1.4.3 |

> v1.4.2 没有 auto-reboot，上传后需手动运行 `reboot`

## 恢复方法

### 串口 <kbd>f</kbd> 键进 FEL

U-Boot 启动时按任意键进入命令行 → 输入 `f` → 进入 FEL 模式 → 重新刷写

### SD 卡救援

插入 SD 卡启动 → U-Boot 命令行手动引导 kernel → 修复

## S99 自动回退（Linux 层）

当 `confirmed=00, retry>0` 时，S99 启动脚本会自动：

1. 每次启动减 retry
2. 当 retry 归零时，自动切回 `last_slot` 指示的旧分区
3. 重置 confirmed=FF, retry=0

## SPI 分区布局

```
16MB W25Q128 SPI NOR Flash
══════════════════════════════════════════
0x000000  1MB     uboot       SPL+U-Boot+ENV
0x100000  64KB    dtb         Device Tree
0x110000  6MB     kernel      Linux zImage
0x710000  4576KB  rootfs_a    Slot A (活跃)
0xB90000  4576KB  rootfs_b    Slot B (非活跃)
0xFC000   6B      ctl block   A/B OTA 控制
0xFC000+  4680KB  free        OTA 空闲空间
══════════════════════════════════════════

ctl block @ 0xFC000 (6 bytes):
  [0] flag       0xFF=A(mtdblock3), 0x00=B(mtdblock4)
  [1] confirmed  0xFF=stable, 0x00=trial
  [2] retry      remaining trial boots
  [3] version    OTA protocol (0x01)
  [4] last_slot  fallback slot
  [5] boot_cnt   wraps on each boot
```
