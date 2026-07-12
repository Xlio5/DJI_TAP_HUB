# TUN_NAT_HUB V3s 完整编译与打包流程

> 从源码到可启动 SD 卡。U-Boot、Kernel、Buildroot **三者独立编译**，手动制作 SD 卡。

---

## 一、总览

```
┌─────────────┐    ┌──────────────┐    ┌──────────────────┐
│   U-Boot    │    │   Kernel     │    │    Buildroot     │
│  单独编译    │    │   单独编译    │    │  只做 rootfs     │
│             │    │              │    │  (外部工具链)     │
└──────┬──────┘    └──────┬───────┘    └────────┬─────────┘
       │                  │                     │
       ▼                  ▼                     ▼
 u-boot-sunxi-       zImage +              rootfs.tar
 with-spl.bin        sun8i-v3s-*.dtb       (含 TUN_NAT_HUB)
       │                  │                     │
       └──────────────────┼─────────────────────┘
                          │
                          ▼
                   SD 卡手动制作
                   dd → fdisk → mkfs → cp → tar xf
                          │
                          ▼
                     可启动 SD 卡 ✅
```

**和之前文档的关键区别：**
- U-Boot 不通过 Buildroot 编译，直接从 Lichee-Pi 仓库
- Kernel 不通过 Buildroot 编译，直接用 lichee-pi 内核仓库
- Buildroot 使用**外部 Linaro 工具链**，只出 rootfs，不管 kernel/U-Boot
- SD 卡是**手动分区制作**，不是 Buildroot 的 genimage

---

## 二、前提：工具链

```bash
# 下载 Linaro GCC 6.3.1 arm-linux-gnueabihf 工具链
cd ~
wget https://releases.linaro.org/components/toolchain/binaries/latest/arm-linux-gnueabihf/gcc-linaro-6.3.1-2017.05-x86_64_arm-linux-gnueabihf.tar.xz
tar xvf gcc-linaro-6.3.1-2017.05-x86_64_arm-linux-gnueabihf.tar.xz
sudo mv gcc-linaro-6.3.1-2017.05-x86_64_arm-linux-gnueabihf /opt/

# 添加到 ~/.bashrc
export PATH=/opt/gcc-linaro-6.3.1-2017.05-x86_64_arm-linux-gnueabihf/bin:$PATH
export ARCH=arm
export CROSS_COMPILE=arm-linux-gnueabihf-

# 验证
source ~/.bashrc
arm-linux-gnueabihf-gcc -v
# 应显示: gcc version 6.3.1 20170109 (Linaro GCC 6.3-2017.02)
```

---

## 三、Step 1：编译 U-Boot

```bash
git clone https://github.com/Lichee-Pi/u-boot.git -b v3s-current
cd u-boot

make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- LicheePi_Zero_defconfig
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j$(nproc)
```

**产物：** `u-boot-sunxi-with-spl.bin`（~400KB）

---

## 四、Step 2：编译 Kernel

```bash
git clone https://github.com/Lichee-Pi/linux.git -b zero-5.2.y --depth 1
cd linux

# 配置
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- licheepi_zero_defconfig

# 检查必须的内核选项（如果菜单里没开）
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- menuconfig
```

必须确保以下选项开启：

```
Device Drivers →
  [*] USB support →
    <M>   USB Gadget Support →
      <M>   USB Gadget Drivers → Serial Gadget (g_serial)
  [*] Network device support →
    <*>   Universal TUN/TAP device driver support

Networking support →
  [*] Networking options →
    [*]   Network packet filtering (Netfilter) →
      <*> IP tables support
      <*>   MASQUERADE target support
      <*>   TCPMSS target support
```

```bash
# 编译
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j$(nproc) zImage
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- dtbs
```

**产物：**
- `arch/arm/boot/zImage`（~5.7MB）
- `arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb`（~13KB）

---

## 五、Step 3：Buildroot 出 rootfs

```bash
cd ~/v3s/buildroot-2024.02

# 清理 Windows PATH（WSL 自动注入了含空格的 PATH）
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

make menuconfig
```

关键配置：

```
Target options →
  Target Architecture = ARM (little endian)
  Target Architecture Variant = cortex-A7
  Target ABI = EABIhf
  Floating point strategy = VFPv4-D16

Toolchain →
  Toolchain type = External toolchain
  Toolchain = Custom toolchain
  Toolchain origin = Pre-installed toolchain
  Toolchain path = /opt/gcc-linaro-6.3.1-2017.05-x86_64_arm-linux-gnueabihf
  External toolchain C library = glibc/eglibc
  [*] Toolchain has C++ support?

System configuration →
  Root password = root
  Init system = BusyBox
  /dev management = Dynamic using devtmpfs + mdev
  Root filesystem overlay directories = board/allwinner/v3s/overlay

Target packages →
  Interpreter languages and scripting →
    [*] python3
  Networking applications →
    [*] iptables

Filesystem images →
  [*] ext2/3/4 root filesystem → ext4
  [*] tar the root filesystem
```

```bash
make -j$(nproc)
```

**产物：** `output/images/rootfs.tar`（~50-150MB）

---

## 六、Step 4：编译 TUN_NAT_HUB daemon

```bash
# 在 TUN_NAT_HUB 目录下
# Windows (Git Bash / WSL 都可以, 用同一个 Linaro 工具链)
rm -rf ubuntu/build_v3s/CMakeCache.txt ubuntu/build_v3s/CMakeFiles
bash scripts/cross_build_v3s.sh
```

**产物：** `ubuntu/build_v3s/usb_tund`（~29KB ARMv7 ELF）

---

## 七、Step 5：制作 SD 卡

插入 SD 卡，假设设备为 `/dev/sdX`。

### 5.1 分区

```bash
sudo fdisk /dev/sdX
# 输入: o          (新建空分区表)
# 输入: n p 1 [回车] +32M   (boot 分区)
# 输入: n p 2 [回车] [回车]  (rootfs 分区)
# 输入: w          (写入并退出)
```

### 5.2 格式化

```bash
sudo mkfs.vfat -n BOOT /dev/sdX1
sudo mkfs.ext4 -L ROOTFS /dev/sdX2
```

### 5.3 烧写 U-Boot（8KB 偏移，关键！）

```bash
sudo dd if=u-boot-sunxi-with-spl.bin of=/dev/sdX bs=1024 seek=8
sync
```

### 5.4 复制文件

```bash
# 挂载
sudo mkdir -p /mnt/{boot,rootfs}
sudo mount /dev/sdX1 /mnt/boot
sudo mount /dev/sdX2 /mnt/rootfs

# 内核 + 设备树 → boot 分区 (FAT32)
sudo cp ~/v3s/linux/arch/arm/boot/zImage /mnt/boot/
sudo cp ~/v3s/linux/arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb /mnt/boot/

# rootfs → rootfs 分区 (ext4)
sudo tar xf ~/v3s/buildroot-2024.02/output/images/rootfs.tar -C /mnt/rootfs/

# TUN_NAT_HUB 应用层文件 → rootfs
sudo cp TUN_NAT_HUB/ubuntu/build_v3s/usb_tund /mnt/rootfs/usr/local/bin/
sudo cp TUN_NAT_HUB/ubuntu/web_panel.py /mnt/rootfs/usr/local/bin/
sudo cp TUN_NAT_HUB/ubuntu/scripts/setup_gadget.sh /mnt/rootfs/usr/local/bin/
sudo cp TUN_NAT_HUB/ubuntu/scripts/setup_nat.sh /mnt/rootfs/usr/local/bin/
sudo cp TUN_NAT_HUB/ubuntu/scripts/S99tun_nat_hub /mnt/rootfs/etc/init.d/

# 确保可执行
sudo chmod +x /mnt/rootfs/usr/local/bin/usb_tund
sudo chmod +x /mnt/rootfs/usr/local/bin/web_panel.py
sudo chmod +x /mnt/rootfs/usr/local/bin/*.sh
sudo chmod +x /mnt/rootfs/etc/init.d/S99tun_nat_hub

# 卸载
sudo umount /mnt/boot /mnt/rootfs
```

### 5.5 U-Boot 环境变量（开机时在 U-Boot 控制台设置一次）

上电后在 U-Boot 倒计时按任意键进入 U-Boot 控制台：

```
=> setenv bootcmd 'fatload mmc 0:1 0x41000000 zImage; fatload mmc 0:1 0x42000000 sun8i-v3s-licheepi-zero-dock.dtb; bootz 0x41000000 - 0x42000000'
=> setenv bootargs 'console=ttyS0,115200 root=/dev/mmcblk0p2 rootwait g_serial.idVendor=0x0BDA g_serial.idProduct=0x8812 g_serial.use_acm=0'
=> saveenv
=> boot
```

> `g_serial.idVendor=0x0BDA g_serial.idProduct=0x8812 g_serial.use_acm=0` 是关键！
> 内核启动时自动加载 g_serial 并伪装 RTL8812AU VID/PID。

---

## 八、Step 6：验证

插 SD 卡上电，串口（115200）观察启动日志：

```
U-Boot SPL 2017.01 ... → U-Boot → Starting kernel ... → rootfs 挂载成功 → login: root
```

```bash
# 串口登录后验证
ps aux | grep -E 'usb_tund|web_panel'     # 两个进程都在
ip addr show tun_hub                        # 10.0.0.1/24
ls -la /dev/ttyGS0                          # g_serial gadget 已创建
wget -q -O - http://127.0.0.1:8080/api/heartbeat  # web_panel 正常
```

插上 DJI RC USB 线，App 显示 USB● + VPN● 双绿 → 完成。

---

## 九、产物对照

| 产物 | 来源 | 大小 | 说明 |
|------|------|------|------|
| `u-boot-sunxi-with-spl.bin` | U-Boot 编译 | ~400KB | dd 到 SD 卡 8KB 偏移 |
| `zImage` | Kernel 编译 | ~5.7MB | 放到 SD 卡 boot 分区 |
| `sun8i-v3s-licheepi-zero-dock.dtb` | Kernel 编译 | ~13KB | 放到 SD 卡 boot 分区 |
| `rootfs.tar` | Buildroot | ~50-150MB | 解压到 SD 卡 rootfs 分区 |
| `usb_tund` | cross_build_v3s.sh | ~29KB | 放到 rootfs /usr/local/bin/ |

---

## 十、量产流程

对于全新 V3s：

```
1. 编译 U-Boot     → u-boot-sunxi-with-spl.bin
2. 编译 Kernel     → zImage + dtb
3. Buildroot       → rootfs.tar
4. cross_build     → usb_tund
5. 插 SD 卡, 按 Step 5 制作        ← 首次需要手动分区
6. 验证 (Step 6)

第二台开始: 用 dd 克隆整张 SD 卡
  sudo dd if=/dev/sdX of=master.img bs=4M
  sudo dd if=master.img of=/dev/sdY bs=4M
```

---

## 十一、日常开发快速部署

```bash
# 改代码 → 编译 → 部署（30 秒）
bash scripts/cross_build_v3s.sh
scp ubuntu/build_v3s/usb_tund root@192.168.144.66:/usr/local/bin/
ssh root@192.168.144.66 "/etc/init.d/S99tun_nat_hub restart"
```

---

## 十二、当前备份文件说明

| 文件 | 用途 |
|------|------|
| `backup/tun_nat_hub_v3s_backup.tar.gz` (41MB) | 应用层 + kernel 快照，**增量更新用** |
| | 含: zImage, dtb, usb_tund, web_panel.py, 脚本, APK |

此备份**不是可启动固件**。缺 U-Boot 和 rootfs。必须配合已装好 Buildroot 系统的 V3s 使用。
