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

## SD 卡刷写 SPI Flash（免 FEL）

**适用场景：** 没有 FEL 工具、不方便短接 MOSI/GND、或批量烧录。

### 原理

SD 卡启动一个最小 Linux → 手动或自动把 `spi_image.bin` 写入 `/dev/mtd0` → 关机拔卡 → SPI Flash 独立启动。

### 制作 SD 卡刷写盘

#### 前置条件

- Linux 主机（WSL 可用）
- SD 卡读卡器 + 一张 ≥128MB 的 microSD 卡
- 已编译好的 U-Boot + kernel + Buildroot rootfs

#### 制作步骤

**方式一：用脚本（推荐）**

```bash
# WSL 中执行，/dev/sdX 是 SD 卡设备名
sudo bash scripts/make_sd_flash.sh /dev/sdb
```

**方式二：手动制作**

```bash
# 1. 分区：32MB FAT16 (type=6) + 剩余 ext4 (type=83)
sudo sfdisk /dev/sdX << 'EOF'
label: dos
size=32M, type=6
type=83
EOF

# 2. 格式化
sudo mkfs.vfat -F 16 -n BOOT /dev/sdX1
sudo mkfs.ext4 -L ROOTFS /dev/sdX2

# 3. 复制 kernel + DTB 到 BOOT 分区
sudo mount /dev/sdX1 /mnt/boot
sudo cp ~/v3s/linux/arch/arm/boot/zImage /mnt/boot/
sudo cp ~/v3s/linux/arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb /mnt/boot/

# 4. 解压 rootfs 到 ROOTFS 分区
sudo mount /dev/sdX2 /mnt/root
sudo tar xf ~/v3s/buildroot-2024.02/output/images/rootfs.tar -C /mnt/root/

# 5. 复制 SPI 镜像到 /root/（刷写用）
sudo cp backup/spi_image.bin /mnt/root/root/

# 6. 写入 U-Boot SPL（让 SD 卡可启动）
sudo dd if=~/v3s/u-boot/u-boot-sunxi-with-spl.bin of=/dev/sdX bs=1024 seek=8

# 7. 卸载
sudo umount /mnt/boot /mnt/root
```

### 用 SD 卡烧录 SPI Flash

1. 插入 SD 卡 → V3s 上电
2. V3s 从 SD 卡启动 Linux（约 8 秒），网口 IP：`192.168.144.66`
3. **SSH 登录**：`ssh root@192.168.144.66`（密码：root）
4. 登录后直接看到 MOTD 提示，执行刷写：

```bash
# 擦除整个 SPI Flash
flash_erase /dev/mtd0 0 0

# 写入 16MB 镜像
dd if=/root/spi_image.bin of=/dev/mtd0 bs=4096

# 校验（前 4 字节应为 "hsqs"）
dd if=/dev/mtd0 bs=1 count=4 skip=$((0x710000)) 2>/dev/null | xxd

# 关机
sync && poweroff
```

5. 拔掉 SD 卡 → 上电 → V3s 从 SPI Flash 启动，版本 v1.4.3

### 批量烧录

将 SD 卡插上 V3s 上电后自动执行烧录：

```bash
# SSH 一键刷写（不关机，手动拔卡重启）
ssh root@192.168.144.66 "flash_erase /dev/mtd0 0 0 && dd if=/root/spi_image.bin of=/dev/mtd0 bs=4096 && sync && echo DONE"
```

烧录完成拔卡 → 下一张 SD 卡 → 下一台 V3s。

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
