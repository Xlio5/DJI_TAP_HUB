# 平台基线

> 上次更新: 2026-07-23 | 刷写分支: `flash`

本文记录跨层状态快照：各组件当前版本、关键改动、源码位置、工具链。
不重复代码细节——代码即文档。

---

## 一、硬件

| 项目 | 值 |
|------|-----|
| SoC | Allwinner V3s (ARM Cortex-A7) |
| 主板 | LicheePi Zero + Dock |
| Flash | W25Q128 16MB SPI NOR |
| 网口 | RMII 100M (eth0) |
| USB | OTG → g_serial (VID=0x0BDA, PID=0x8812) |

---

## 二、U-Boot

| 项目 | 值 |
|------|-----|
| 版本 | 2026.07-rc5 |
| defconfig | `licheepi_nano_defconfig` |
| 源码 | `/home/xlong/v3s/u-boot/` (git: `master`) |

**关键改动：**
- SPL 预载 kernel + DTB 到 RAM，U-Boot 直接 `bootz`（无需 `sf read`）
- SPL 读 A/B OTA flag @ 0xFC000 → 打补丁 mtdblock3→4
- bootcmd: `console=ttyS0,115200 tun_nat_version=v1.4.3 panic=5 sunxi_wdt.nowayout=1 root=/dev/mtdblock3 rootfstype=squashfs rootwait mtdparts=firmware:1M(uboot),64k(dtb),6M(kernel),4576k(rootfs_a),-(rootfs_b) ...`
- `CONFIG_ENV_IS_NOWHERE=y`（ENV 由 build_spi_final.py 打包进 SPI image）

---

## 三、Kernel

| 项目 | 值 |
|------|-----|
| 版本 | 7.1.0 |
| ARCH | arm |
| 编译器 | `arm-linux-gnueabihf-gcc` 10.5.0 |
| 源码 | `/home/xlong/v3s/linux/` (git: `master`) |

**关键改动：**
- `CONFIG_CMDLINE=""` — 不再追加第二个 `root=`，**U-Boot 全权控制启动分区**
- `CONFIG_CMDLINE_EXTEND=y` — U-Boot 的 bootargs 在前面，内核追加在后面（空串无影响）
- **DTB**: `sun8i-v3s-licheepi-zero-dock.dtb`
  - `&uart0 { status = "okay"; }` — **UART0 (PB8/PB9) 固定 debug console**：内核 `console=ttyS0,115200` + inittab getty（单 getty 独占，勿在 rc 脚本重复拉）
  - `&uart1 { status = "okay"; }` — ttyS1 (PE21/PE22) → DJI-B RC @921600
  - `&uart2 { status = "okay"; }` — ttyS2 (PB0/PB1) → DJI-A RC @115200 + SBUS TX
  - `&i2c0 { status = "okay"; }` — PB6/PB7 (TWI0) → **SC16IS752IPW** (I2C 地址 0x4d, 晶振 1.8432MHz) → `ttySC0/ttySC1` 协议输出口 (SBUS/CRSF)
  - `&spi0 { status = "okay"; }` — W25Q128 SPI NOR
  - `&emac { status = "okay"; }` — 百兆网口

> **UART0 debug 踩坑记录 (2026-08-24, 固件 1.6.39/1.6.40)**：
> 1. 双 getty 抢 ttyS0（inittab respawn + S99 `_respawn_uart0_getty`）→ 登录失效。**修复**：删 S99 getty，inittab 独占。
> 2. `dji_rc aux_tmux_set` 按"每 CFG 管 4 引脚"算 PIO 偏移，V3s 实为 **8 引脚/CFG**，把 `0x28`(PB_CFG1=PB8-15) 当 PB_CFG1(PB4-7) 配 TMUX → **PB8/PB9 被配成 GPIO，UART0 物理断连**（`write()` 成功但字节不到线上）。**修复**：删除 0x28 操作，TMUX PB4/PB5 配置并入 PB_CFG0(0x24)。详见 `docs/SESSION_HANDOFF.md` 顶部。

**重编 DTB：**
```bash
cd /home/xlong/v3s/linux
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- dtbs -j8
```

**重编 zImage：**
```bash
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- zImage -j8
```

---

## 四、Rootfs (Buildroot)

| 项目 | 值 |
|------|-----|
| 版本 | Buildroot 2024.02 |
| libc | glibc 2.38 |
| 编译器 | `arm-buildroot-linux-gnueabihf-g++` (GCC 12.3.0) |
| rootfs | squashfs (xz, ~4.5MB, 只读, 621 inodes) |
| 源码 | `/home/xlong/v3s/buildroot-2024.02/output/target/` |

**关键自定义组件：**

| 二进制 | 源文件 | 大小 | 用途 |
|--------|--------|------|------|
| `web_server` | `ubuntu/src/web_server.cpp` | 1.0MB | 嵌入式 HTTP + HTML 面板 |
| `usb_tund` | `ubuntu/src/main.cpp`, `tun_iface.cpp` | 18KB | TUN/VPN 守护进程 |
| `dji_rc` | `ubuntu/src/dji_rc.cpp` + C 模块 | 18KB | DJI DUML 双路串口解码 + SBUS |

**dji_rc 依赖的纯 C 模块（零改动 from dji_decode）：**
- `duml.c/h` — CRC8/16 表 + 帧同步
- `rc_decode.c/h` — RC/0xAE + SPECIAL/0x02 解码 + 双路融合
- `chmap.c/h` — 16 通道映射 (摇杆→1000-2000µs)
- `sbus.c/h` — SBUS 25 字节帧编码

---

## 五、SPI Flash 分区布局

```
16MB W25Q128 SPI NOR
══════════════════════════════════════
0x000000  1MB     uboot       SPL + U-Boot + ENV
0x100000  64KB    dtb         Device Tree
0x110000  6MB     kernel      Linux zImage
0x710000  4576KB  rootfs_a    Slot A (活跃)
0xB90000  4576KB  rootfs_b    Slot B (OTA)
0xFC000   6B      ctl block   A/B OTA 控制字
0xFC000+  4676KB  free
══════════════════════════════════════

ctl block @ 0xFC000 (6 bytes):
  [0] flag       0xFF=A(mtdblock3), 0x00=B(mtdblock4)
  [1] confirmed  0xFF=stable, 0x00=trial
  [2] retry      remaining trial boots
  [3] version    OTA protocol (0x01)
  [4] last_slot  fallback slot
  [5] boot_cnt   boot counter (wraps)
```

---

## 六、编译命令速查

### web_server（改 HTML 面板或 API）

```bash
# web_server 必须动态链接 (勿加 -static)! rootfs 已有 libstdc++.so.6/libc.so.6,
# 静态链接会让 web_server 达 1MB, rootfs 超 4MB 无法 OTA。动态版 ~86KB (v1.6.48 起)。
# 需链接 rc_map.o + rc_decode.o (RC 输出配置依赖)
/home/xlong/v3s/buildroot-2024.02/output/host/bin/arm-buildroot-linux-gnueabihf-g++ \
    -std=c++17 -Os -s -Wall \
    -o web_server ubuntu/src/web_server.cpp rc_map.o rc_decode.o -lpthread
```

### dji_rc（改 DJI RC 解码）

```bash
GCC=/home/xlong/v3s/buildroot-2024.02/output/host/bin/arm-buildroot-linux-gnueabihf-gcc
GPP=/home/xlong/v3s/buildroot-2024.02/output/host/bin/arm-buildroot-linux-gnueabihf-g++

# 依赖: duml rc_decode chmap sbus rc_map crsf (C) + rc_source_select (C++)
for f in duml rc_decode chmap sbus rc_map crsf; do
    $GCC -O2 -s -c -o /tmp/${f}.o ubuntu/src/${f}.c
done
$GPP -std=c++17 -O2 -s -c -o /tmp/rc_source_select.o ubuntu/src/rc_source_select.cpp
$GPP -std=c++17 -O2 -s -Wall -o dji_rc ubuntu/src/dji_rc.cpp \
    /tmp/duml.o /tmp/rc_decode.o /tmp/chmap.o /tmp/sbus.o /tmp/rc_map.o /tmp/crsf.o /tmp/rc_source_select.o -lpthread
```

### 打包 rootfs

```bash
unsquashfs -d /tmp/rootfs_build backup/rootfs_v143.squashfs
cp web_server dji_rc S99tun_nat_hub /tmp/rootfs_build/usr/local/bin/  # etc
mksquashfs /tmp/rootfs_build backup/rootfs.squashfs -comp xz -noappend -all-root
```

### 构建 SPI 镜像

用 `build_spi_final.py`，或手动 Python 拼接（保留定制的 SPL/U-Boot/DTB/zImage 不变，只换 squashfs）。

---

## 七、部署

| 方式 | 命令 | 文件 |
|------|------|------|
| **OTA Web 升级** | 浏览器 `http://192.168.144.66:8080` → 固件升级 | `backup/rootfs.squashfs` |
| **FEL 全量刷写** | `wsl -u root sunxi-fel spiflash-write 0` | `backup/spi_image.bin` |

详见 [RELEASE.md](RELEASE.md)
