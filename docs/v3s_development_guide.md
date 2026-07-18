# V3s (LicheePi Zero) 开发工作流

> 基于官方文档与实战总结。最后更新: 2026-07-18

**相关文档:** [A/B 分区 OTA 方案](ab_partition_ota_plan.md)

---

## 1. Boot ROM 启动顺序

```
上电 → BROM (内建)
  ├─ ① SD卡 第16扇区 (offset 8192) 有 eGON 头? → 加载 SPL → 启动
  ├─ ② SPI Flash offset 0 有 eGON 头? → 加载 SPL → 启动
  └─ ③ 都没有 → 自动进 FEL (USB VID_1F3A:PID_EFE8)
```

BROM 检查顺序是 **先 SD 卡，后 SPI Flash**。

---

## 2. FEL 模式 — Allwinner 的"后门"

### 进入方式

| 方式 | 操作 | 适用场景 |
|------|------|---------|
| 自动 | SD卡+SPI 都无有效 eGON → 上电自动进 FEL | 空板/砖板 |
| 短接 SPI MISO | SPI Flash pin 2 (DO/IO1) 短接 GND → 上电 | SPI 有坏数据时强制绕过 |
| SD卡 FEL 镜像 | 写 `fel-sdboot.sunxi` 到 SD 卡 sector 16 → 插入启动 | SPI 正常但需要 FEL |

### w25q128 引脚

```
        ┌───┐
  CS# 1─┤o  ├─8 VCC
  DO  2─┤   ├─7 HOLD   ← 短接 pin2(DO/MISO) 到 pin4(GND) 进 FEL
  WP  3─┤   ├─6 CLK
  GND 4─┤   ├─5 DI
        └───┘
```

### 验证进入 FEL

```bash
lsusb | grep 1f3a:efe8   # 应看到 Allwinner V3s
sudo sunxi-fel version    # 输出芯片版本
```

### sunxi-tools 安装

**必须用 Icenowy 的 spi-rebase 分支！** 主线 sunxi-tools 不支持 V3s SPI Flash。

```bash
git clone https://github.com/Icenowy/sunxi-tools.git
cd sunxi-tools
git checkout -b spi-rebase origin/spi-rebase
make
sudo make install
```

### FEL 常用命令

```bash
# 读 SPI Flash
sunxi-fel spiflash-read 0 0x100 /tmp/dump.bin

# 写 SPI Flash (会先擦除)
sunxi-fel spiflash-write 0 spi_image.bin

# 加载 U-Boot 到 SRAM 执行 (无需 Flash)
sunxi-fel uboot u-boot-sunxi-with-spl.bin
```

---

## 3. SD 卡启动 — 开发阶段推荐方式

### 制作可启动 SD 卡

```bash
# 写 SPL+U-Boot 到第16扇区 (offset 8192, bs=1024 seek=8)
sudo dd if=u-boot-sunxi-with-spl.bin of=/dev/sdX bs=1024 seek=8

# FAT32 分区放文件
mount /dev/sdX1 /mnt/sd
cp zImage sun8i-v3s-licheepi-zero-dock.dtb /mnt/sd/
# rootfs 可放第二个 ext4 分区，或用 initramfs
```

### U-Boot 从 SD 卡启动

```
fatload mmc 0:1 0x41000000 zImage
fatload mmc 0:1 0x42000000 sun8i-v3s-licheepi-zero-dock.dtb
fdt addr 0x42000000
setenv bootargs console=ttyS0,115200 root=/dev/mmcblk0p2 rootwait
bootz 0x41000000 - 0x42000000
```

### SD 卡启动 vs SPI 启动

| | SD 卡 | SPI Flash |
|---|-------|-----------|
| 烧录 | dd 写扇区 + cp 文件 | sunxi-fel 或 U-Boot sf write |
| 开发调试 | 方便 (拔卡改文件) | 不方便 (需 FEL 或 U-Boot 重写) |
| 量产部署 | 不适用 | 适用 (16MB 自包含) |
| 速度 | 快 | 慢但够用 |

**推荐开发流程：SD 卡启动调试 → 最终固件才写 SPI。**

---

## 4. SPI Flash 布局 (16MB w25q128)

| 偏移量 | 大小 | 分区名 | 内容 |
|--------|------|--------|------|
| 0x000000 | 1MB | uboot | SPL + U-Boot |
| 0x07E000 | 8KB | env | U-Boot 环境变量 |
| 0x100000 | 64KB | dtb | Device Tree |
| 0x110000 | 6MB | kernel | Linux zImage |
| 0x710000 | ~5MB | rootfs | squashfs (XZ) |
| 0xB00000+ | ~5MB | - | 预留 OTA |

### U-Boot bootargs

```
console=ttyS0,115200 root=/dev/mtdblock3 rootfstype=squashfs rootwait
mtdparts=firmware:1M(uboot),64k(dtb),6M(kernel),-(rootfs)
g_serial.idVendor=0x0BDA g_serial.idProduct=0x8812 g_serial.use_acm=0
```

### SPL preload 机制

SPL 编译时打补丁，直接从 SPI Flash 预载内核和 DTB 到固定 RAM 地址：
- Kernel: SPI 0x110000 → RAM 0x41000000
- DTB:    SPI 0x100000 → RAM 0x42000000

U-Boot 的 bootcmd 直接 `bootz 0x41000000 - 0x42000000`，不需要 `sf read`。

---

## 5. 全量编译流程

### 5.1 内核

```bash
cd linux
# 关键配置
CONFIG_SQUASHFS=y
CONFIG_SQUASHFS_XZ=y           # XZ 压缩支持
CONFIG_USB_G_SERIAL=y           # g_serial 内置 (不用 .ko)
CONFIG_TUN=y
CONFIG_MTD=y
CONFIG_MTD_SPI_NOR=y
CONFIG_MTD_CMDLINE_PARTS=y
CONFIG_SPI=y
CONFIG_SPI_SUN6I=y
CONFIG_MTD_BLOCK=y

make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j$(nproc) zImage dtbs
```

### 5.2 U-Boot

```bash
cd u-boot
# SPL preload 补丁在 arch/arm/mach-sunxi/spl_spi_sunxi.c
# 更新内核大小后重编

make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- clean
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j$(nproc)
# 输出: spl/sunxi-spl.bin, u-boot.bin, u-boot-sunxi-with-spl.bin
```

### 5.3 rootfs (Buildroot)

```bash
cd buildroot-2024.02
make clean   # 清理
make         # 全量编译

# Overlay: board/allwinner/v3s_overlay/
#   etc/init.d/S99tun_nat_hub    — 启动脚本
#   usr/local/bin/setup_v3s.sh   — TUN/NAT/USB 初始化
#   usr/local/bin/web_server     — 嵌入式 HTTP 面板
#   usr/local/bin/usb_tund       — TUN↔TTY 桥接守护进程
```

### 5.4 拼装 SPI 镜像

```bash
python build_spi_final.py
# → backup/spi_image.bin (16MB)
```

---

## 6. 恢复砖头 V3s (SPI Flash 损坏)

### 方案 A: SD 卡启动（最可靠）

```
1. SD 卡做成可启动盘 (dd bs=1024 seek=8)
2. 插卡上电 → U-Boot 从 SD 卡启动 (SPI 被跳过)
3. U-Boot 里:
   sf probe
   sf erase 0 0x1000000
   fatload mmc 0:1 0x41000000 spi_image.bin
   sf write 0x41000000 0 ${filesize}
4. 关机拔卡 → 纯 SPI 启动
```

### 方案 B: FEL 直写（spi-rebase 版 sunxi-fel）

```
1. 短接 SPI pin2 (DO/MISO) 到 GND → 上电
2. USB OTG 接 PC
3. sunxi-fel spiflash-write 0 spi_image.bin   # 会自动擦除
4. 断电移除短接 → 上电纯 SPI 启动
```

---

## 7. 实战教训

| 教训 | 详情 |
|------|------|
| 永远用 SPI NOR 的 raw /dev/mtd0 写 | `/dev/mtdblock3` 写不触发 NOR 擦除 |
| sunxi-fel 必须用 spi-rebase 分支 | 主线的 spiflash-write 不支持 V3s |
| 编译错误必须停手 | U-Boot make clean 报 Permission denied → 先修权限 |
| FEL 短路是 pin2(DO) 不是 pin1(CS#) | 短错了进不了 FEL |
| SD 卡 SPL 扇区是 offset 8192 (sector 16) | 不是 sector 8 (4096) |
| 所有编译必须同一版本 | 混用不同时间的二进制会导致 squashfs 挂载失败等诡异问题 |

---

## 8. 当前项目构建状态

| 组件 | 日期 | 大小 | 来源 |
|------|------|------|------|
| SPL | 2026-07-18 12:27 | 24KB | U-Boot clean rebuild |
| U-Boot | 2026-07-18 12:27 | 395KB | U-Boot clean rebuild |
| Kernel | 2026-07-18 12:26 | 5.7MB | Linux clean rebuild |
| DTB | 2026-07-18 12:26 | 12.7KB | Linux clean rebuild |
| rootfs | 2026-07-18 12:37 | 4.0MB | Buildroot clean rebuild |
| spi_image.bin | 2026-07-18 | 16MB | 以上全部统一版本 |
