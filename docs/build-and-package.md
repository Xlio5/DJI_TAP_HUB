# TUN_NAT_HUB V3s 完整编译与打包流程

> 从源码到可烧录 SD 卡镜像的完整流水线，每个阶段的输入/输出/命令。

---

## 一、总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                        第一阶段：基础设施层                           │
│                       Buildroot 构建 U-Boot + Kernel + Rootfs        │
│                                                                     │
│  输入: buildroot源码 + kernel源码 + defconfig                        │
│  输出: zImage, sun8i-v3s-*.dtb, rootfs.tar, u-boot-sunxi-with-spl.bin│
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        第二阶段：应用层                               │
│                       TUN_NAT_HUB daemon + web_panel                  │
│                                                                     │
│  输入: TUN_NAT_HUB/ubuntu/src/*.cpp                                  │
│  输出: usb_tund (ARMv7 ELF 29KB)                                    │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        第三阶段：整合打包                             │
│                       Overlay → SD 卡镜像                            │
│                                                                     │
│  输入: 第一阶段产物 + 第二阶段产物 + 启动脚本                          │
│  输出: sdcard.img (可直接 dd 烧录)                                   │
│  或: tun_nat_hub_v3s_backup.tar.gz (增量更新包)                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 二、第一阶段：Buildroot 构建基础设施

### 前置

```bash
# 获取 Buildroot
git clone https://github.com/buildroot/buildroot.git
cd buildroot

# 获取 V3s Linux kernel（已配置好 sun8i-v3s 支持）
git clone https://github.com/Lichee-Pi/linux.git ~/v3s/linux
```

### 2.1 Kernel 配置

V3s kernel 必须内置或模块化以下特性：

```
Device Drivers →
  [*] USB support →
    <*>   USB Gadget Support →
      <*>   USB Gadget Drivers →
        <M>   Serial Gadget (g_serial)        ← 关键! USB Bulk 通道
  [*] Network device support →
    <*>   Universal TUN/TAP device driver support    ← 关键! TUN 虚拟网卡

Networking support →
  [*] Networking options →
    [*]   Network packet filtering (Netfilter) →
      <*>   IP tables support (required for filter/masq)
      <*>     MASQUERADE target support
      <*>     TCPMSS target support
```

Kernel 配置文件通常为：

```
~/v3s/linux/arch/arm/configs/sunxi_defconfig
```

修改后手动开启缺失项：

```bash
cd ~/v3s/linux
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- sunxi_defconfig
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- menuconfig   # 勾选上面三项
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- savedefconfig
cp defconfig arch/arm/configs/sunxi_defconfig
```

### 2.2 Buildroot 配置

关键选项（`make menuconfig`）：

```
Target options →
  Target Architecture = ARM (little endian)
  Target Architecture Variant = cortex-A7
  Target ABI = EABIhf
  Floating point strategy = VFPv4-D16

Toolchain →
  C library = glibc (或 uClibc-ng, 两者都行)
  [*] Enable C++ support                          ← daemon 用 C++17

System configuration →
  Root password = root
  /dev management = Dynamic using devtmpfs + mdev
  Path to the permission table = board/allwinner/v3s/device_table.txt
  [*] Install timezone info

Target packages →
  Interpreter languages and scripting →
    [*] python3                                    ← web_panel 依赖
        python3 library = whole python3 (不要 core-only, 缺模块)
  Networking applications →
    [*] iptables                                   ← NAT 转发
  Hardware handling →
    [*] usbutils                                   ← lsusb 调试

Filesystem images →
  [*] ext2/3/4 root filesystem
      ext2/3/4 variant = ext4
  [*] tar the root filesystem                      ← 做 overlay 需要

Kernel →
  [*] Linux Kernel
      Kernel version = Custom Git repository
      URL of custom repository = ~/v3s/linux
      Custom Git tag/commit = (当前 commit hash)
      Kernel configuration = Using an in-tree defconfig file
      Defconfig name = sunxi
      Kernel binary format = zImage
      [*] Build a Device Tree Blob (DTB)
          In-tree Device Tree Source file names = sun8i-v3s-licheepi-zero-dock

Bootloaders →
  [*] U-Boot
      Build system = Kconfig
      U-Boot board name = LicheePi_Zero
      U-Boot Version = Custom Git repository
      URL of custom repository = https://github.com/Lichee-Pi/u-boot.git
      [*] U-Boot needs dtc
```

### 2.3 Buildroot overlay 配置

创建 overlay 目录（第一阶段先留空，第三阶段再填）：

```bash
mkdir -p ~/buildroot/board/allwinner/v3s/overlay/{usr/local/bin,etc/init.d}
```

在 Buildroot `menuconfig` 中：

```
System configuration →
  Root filesystem overlay directories = board/allwinner/v3s/overlay
```

### 2.4 构建

```bash
cd ~/buildroot

# 生成完整配置
make BR2_DEFCONFIG=board/allwinner/v3s/defconfig defconfig

# 构建 (首次约 2-4 小时，后续增量 <10 分钟)
make -j$(nproc)
```

### 第一阶段产物

```
buildroot/output/
├── images/
│   ├── zImage                              ← kernel (ARM 32-bit, ~5.7MB)
│   ├── sun8i-v3s-licheepi-zero-dock.dtb     ← 设备树 (~13KB)
│   ├── rootfs.ext4                          ← 完整 rootfs (50-150MB)
│   ├── rootfs.tar                           ← rootfs 归档
│   └── u-boot-sunxi-with-spl.bin            ← U-Boot + SPL (~400KB)
└── build/
    └── linux-*/                             ← kernel 构建目录
```

---

## 三、第二阶段：应用层编译

### 3.1 编译 daemon (usb_tund)

**输入：** `TUN_NAT_HUB/ubuntu/src/{main.cpp, tun_iface.cpp}`  
**命令：**

```bash
cd TUN_NAT_HUB
bash scripts/cross_build_v3s.sh
```

实际执行的 cmake 命令：

```bash
cd ubuntu/build_v3s
cmake .. \
    -DCMAKE_TOOLCHAIN_FILE=../cmake/toolchain-armv7-linux.cmake \
    -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)
```

工具链：`arm-linux-gnueabihf-g++`（Ubuntu 包 `g++-arm-linux-gnueabihf`）

### 3.2 web_panel.py

**无需编译。** 纯 Python3 标准库，直接使用。

### 3.3 编译 Android APK（可选，打包时附带）

```bash
cd TUN_NAT_HUB/android
./gradlew assembleDebug
```

### 第二阶段产物

| 产物 | 路径 | 大小 | 目标架构 |
|------|------|------|----------|
| **usb_tund** | `ubuntu/build_v3s/usb_tund` | ~29 KB | ARMv7 EABIhf |
| **web_panel.py** | `ubuntu/web_panel.py` | ~39 KB | Python3 (any) |
| app-debug.apk | `android/app/build/outputs/apk/debug/app-debug.apk` | ~5 MB | Android ARM64 |

---

## 四、第三阶段：整合打包

### 方案 A：完整固件（量产用，一台产出多台刷）

把第一阶段和第二阶段产物合并，生成一个 sdcard.img，烧录后即用。

```
┌───────────────────────────────────────────────┐
│              sdcard.img 结构                    │
├───────────────────────────────────────────────┤
│ 前 8KB:   U-Boot SPL (从 u-boot-sunxi-with-spl.bin)  │
│ 扇区 16+:  U-Boot proper                            │
├───────────────────────────────────────────────┤
│ 分区 1: FAT32 (内核 + DTB)                          │
│   ├── zImage                                        │
│   └── sun8i-v3s-licheepi-zero-dock.dtb              │
├───────────────────────────────────────────────┤
│ 分区 2: ext4 (Rootfs)                               │
│   ├── /usr/local/bin/usb_tund        ← daemon      │
│   ├── /usr/local/bin/web_panel.py    ← Web API     │
│   ├── /usr/local/bin/setup_gadget.sh ← g_serial    │
│   ├── /usr/local/bin/setup_nat.sh    ← NAT 规则    │
│   └── /etc/init.d/S99tun_nat_hub     ← 开机自启    │
└───────────────────────────────────────────────┘
```

#### Step A1：生成 sdcard.img

在 Buildroot 里已经自动生成了 `sdcard.img`（前提是配置了正确的分区布局）。

如果没有 `.img`，手动用 genimage 或脚本拼接。Buildroot 通常已有 `board/allwinner/v3s/genimage.cfg`，定义类似：

```
image sdcard.img {
    hdimage {
    }
    partition u-boot {
        in-partition-table = "no"
        image = "u-boot-sunxi-with-spl.bin"
        offset = 8K
        size = 1016K
    }
    partition boot {
        partition-type = 0xC
        bootable = "true"
        files = {
            "zImage",
            "sun8i-v3s-licheepi-zero-dock.dtb",
        }
        size = 32M
    }
    partition rootfs {
        partition-type = 0x83
        image = "rootfs.ext4"
        size = 512M
    }
}
```

#### Step A2：将应用层文件注入 rootfs

```bash
# 方法1: 在 Buildroot make 之前放入 overlay
cp ubuntu/build_v3s/usb_tund ~/buildroot/board/allwinner/v3s/overlay/usr/local/bin/
cp ubuntu/web_panel.py ~/buildroot/board/allwinner/v3s/overlay/usr/local/bin/
cp ubuntu/scripts/setup_gadget.sh ~/buildroot/board/allwinner/v3s/overlay/usr/local/bin/
cp ubuntu/scripts/setup_nat.sh ~/buildroot/board/allwinner/v3s/overlay/usr/local/bin/
cp ubuntu/scripts/S99tun_nat_hub ~/buildroot/board/allwinner/v3s/overlay/etc/init.d/

# 然后再 make
cd ~/buildroot && make
# → output/images/sdcard.img 已包含 TUN_NAT_HUB 文件

# 方法2: 已有 rootfs.ext4，在线挂载注入
mkdir -p /tmp/rootfs
sudo mount -o loop ~/buildroot/output/images/rootfs.ext4 /tmp/rootfs
sudo cp ubuntu/build_v3s/usb_tund /tmp/rootfs/usr/local/bin/
sudo cp ubuntu/web_panel.py /tmp/rootfs/usr/local/bin/
# ...
sudo umount /tmp/rootfs
# 然后用 genimage 重新生成 sdcard.img
```

#### Step A3：烧录

```bash
# Windows: 用 balenaEtcher 或 Win32DiskImager
# Linux:
sudo dd if=output/images/sdcard.img of=/dev/sdX bs=4M status=progress
```

---

### 方案 B：增量更新包（已有系统用）

已有系统 + 只需更新 TUN_NAT_HUB 文件时。

#### Step B1：打包

```bash
cd TUN_NAT_HUB
bash scripts/pack_backup.sh
```

生成 `backup/tun_nat_hub_v3s_backup.tar.gz` (~41MB)：

```
tun_nat_hub_v3s_backup.tar.gz
├── zImage                                     ← 内核
├── sun8i-v3s-licheepi-zero-dock.dtb           ← 设备树
├── usb_tund                                   ← daemon
├── web_panel.py                               ← Web API
├── setup_v3s.sh / v3s_start.sh                ← 启动脚本
├── S99tun_nat_hub                             ← 自启脚本
├── app-debug.apk                              ← Android APK
├── uboot_env.txt                              ← U-Boot 参考参数
└── VERSION.txt                                ← 版本信息
```

#### Step B2：部署到 V3s

```bash
V3S_IP="192.168.144.66"
tar xzf backup/tun_nat_hub_v3s_backup.tar.gz

# 可选：更新内核 (需重启)
scp zImage sun8i-v3s-licheepi-zero-dock.dtb root@$V3S_IP:/boot/

# 更新应用层
scp usb_tund root@$V3S_IP:/usr/local/bin/
scp web_panel.py root@$V3S_IP:/usr/local/bin/
scp setup_v3s.sh root@$V3S_IP:/usr/local/bin/
scp v3s_start.sh root@$V3S_IP:/usr/local/bin/
scp S99tun_nat_hub root@$V3S_IP:/etc/init.d/

ssh root@$V3S_IP "chmod +x /usr/local/bin/*.sh /usr/local/bin/usb_tund /usr/local/bin/web_panel.py"
ssh root@$V3S_IP "/etc/init.d/S99tun_nat_hub restart"
```

---

## 五、完整流水线总结

```
┌──────────────┐
│ Kernel 源码   │──make ARCH=arm sunxi_defconfig──► zImage + DTB
│ ~/v3s/linux  │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Buildroot    │──make──────────────────► u-boot-sunxi-with-spl.bin
│ ~/buildroot  │──make──────────────────► rootfs.ext4 / rootfs.tar
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ TUN_NAT_HUB  │──cross_build_v3s.sh────► usb_tund (ARMv7 29KB)
│ ubuntu/src/  │  (直接可用, 无需编译)─── web_panel.py (39KB)
└──────┬───────┘
       │
       ├─── 量产 ──► overlay → Buildroot make → sdcard.img → dd 烧录
       │
       └─── 增量 ──► pack_backup.sh → backup/*.tar.gz → scp 部署
```

### 一次性量产（5 分钟产出，N 台烧录）

| Step | 命令 | 耗时 |
|------|------|------|
| 编译 kernel | `make -C ~/v3s/linux ARCH=arm ... zImage dtbs` | 5-30 min |
| 编译 Buildroot | `make -C ~/buildroot` | 5 min(增量) |
| 编译 daemon | `bash scripts/cross_build_v3s.sh` | 3 sec |
| 合并到 overlay | `cp` 5 个文件到 overlay 目录 | 1 sec |
| 重新制作 rootfs | `make -C ~/buildroot` | 1 min |
| 制作 SD 卡镜像 | genimage（Buildroot 自动） | 30 sec |
| 烧录 | `dd if=sdcard.img of=/dev/sdX` | 1 min |
| **总耗时** | | **~10 min（增量）/ ~2h（首次）** |

### 产物对照表

| 产物 | 生成者 | 可启动? | 用途 |
|------|--------|---------|------|
| `zImage` | Kernel make | ❌ 需配合 U-Boot + rootfs | kernel 更新 |
| `u-boot-sunxi-with-spl.bin` | Buildroot | ❌ 需配合 kernel + rootfs | 烧录到 SD 卡前 1MB |
| `rootfs.ext4` | Buildroot | ❌ 需配合 U-Boot + kernel | rootfs 分区内容 |
| `sdcard.img` | Buildroot genimage | ✅ 完整可启动 | 量产烧录 |
| `usb_tund` | cross_build_v3s.sh | ❌ 应用层 | 放到 rootfs 的 /usr/local/bin |
| `tun_nat_hub_v3s_backup.tar.gz` | pack_backup.sh | ❌ 仅应用层 + kernel | 已有系统的增量更新 |

---

## 六、开发者工作流

### 日常开发（修改 TUN_NAT_HUB 代码）

```bash
# 1. 改代码
vim ubuntu/src/main.cpp

# 2. 重新编译 daemon（3 秒）
bash scripts/cross_build_v3s.sh

# 3. 快速部署到现有 V3s（30 秒）
scp ubuntu/build_v3s/usb_tund root@192.168.144.66:/usr/local/bin/
ssh root@192.168.144.66 "killall usb_tund; sleep 1; /usr/local/bin/usb_tund > /var/log/usb_tund.log 2>&1 &"

# 4. 验证
ssh root@192.168.144.66 "tail -20 /var/log/usb_tund.log"
```

### 修改 kernel 配置

```bash
cd ~/v3s/linux
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- menuconfig
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j$(nproc) zImage dtbs

# 更新到 V3s
scp arch/arm/boot/zImage root@192.168.144.66:/boot/
scp arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb root@192.168.144.66:/boot/
ssh root@192.168.144.66 "reboot"
```

### 发布新版本（更新包）

```bash
# 确保产物都在
bash scripts/cross_build_v3s.sh
cd android && ./gradlew assembleDebug && cd ..

# 打包
bash scripts/pack_backup.sh

# 产物: backup/tun_nat_hub_v3s_backup.tar.gz
```
