# PB6 检测切换 UART0 角色（debug 串口 vs SBUS/CRSF 输出）

> 日期: 2026-08-05
> 固件版本: v1.4.6
> App 版本: v1.3.0

## 背景

V3s 只有 3 个 UART（UART0/UART1/UART2），UART0 原本是内核 console + debug 串口。
为了把 DJI RC 解码数据通过标准 SBUS/CRSF 协议输出，UART0 被释放为协议输出口。
但这导致**无法串口 debug**（启动日志、登录终端都不可用）。

## 方案：PB6 输入引脚检测

利用 **PB6 空闲 GPIO**（未占用），通过硬件接法决定 UART0 角色：

| PB6 状态 | UART0 角色 | 行为 |
|---|---|---|
| **上拉（默认）** | SBUS/CRSF 协议输出 | dji_rc 打开 UART0 按配置输出协议帧 |
| **接地** | debug 串口 | dji_rc 关闭协议输出 + 启动 getty 登录终端 |

硬件要求：**PB6 默认上拉**（内部上拉由 DTB `bias-pull-up` 配置），接地触发 debug。

## 实现

### 1. 设备树（内核 DTB）

`sun8i-v3s-licheepi-zero.dts` 新增 PB6 输入上拉 pinctrl：

```dts
&pio {
	pb6_debug_pin: pb6-debug-pin {
		pins = "PB6";
		function = "gpio_in";
		bias-pull-up;   /* 关键: 默认上拉 */
	};
};

&uart0 {
	pinctrl-0 = <&uart0_pb_pins>, <&pb6_debug_pin>;
	pinctrl-names = "default";
	status = "okay";
};
```

### 2. U-Boot

- **CONFIG_BAUDRATE = 115200**（原 921600），`/home/xlong/v3s/u-boot/.config`
- 编译：`make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf-`
- bootcmd 检测 PB6 决定内核 console：
  ```
  if gpio input 1 6; then setenv bootargs console=ttyS0,115200 ...; else setenv bootargs console=null ...; fi; bootz ...
  ```

### 3. dji_rc（用户态）

- **pb6_grounded()**：`mmap /dev/mem` **运行时主动配置 PB6 寄存器**（最终策略，不依赖 DTB）
  - **CFG1** @0x04：PB6 强制 input（bit24-25=00）
  - **PU0** @0x1C：PB6 强制 pull-up（bit12-13=01）
  - **DATA** @0x10：读 PB6 bit6，0=接地 1=上拉
  - 每次检测前配置寄存器 + 短延时，确保上拉生效，避免浮空误判
- **pb6_auto_switch()**：每 2s 检测，**连续 3 次相同**才切换（防抖，6s 确认）
  - 接地 → debug：关闭协议输出 fd + 启动 getty（`setsid getty -L 115200 ttyS0`）
  - 上拉 → 协议：杀掉 getty + 按配置打开 SBUS/CRSF 输出 fd
- getty 由 dji_rc 统一管理（S99 不再直接启动，避免重复）

### 4. S99 启动脚本

统一启动 dji_rc，由它自己检测 PB6（不再区分启动参数）：

```sh
/usr/local/bin/dji_rc --interval 20 --out-dev /dev/ttyS0 --out-baud auto \
    --crsf-telem 1 --rcmsg-host 10.0.0.2 --rcmsg-port 65530
```

## 关键 bug 修复记录

| Bug | 根因 | 修复 |
|---|---|---|
| S99 not found | S99 是 CRLF 行结尾（git autocrlf），busybox sh 执行失败 | 转 LF |
| PB6 检测 segfault | `printf` 在 `munmap` 后访问悬垂指针 | 先读寄存器+打印，再 munmap |
| PB6 断开仍读 0 | 无内部上拉，浮空输入 | DTB `bias-pull-up` |

## 构建流程（make clean 后全量重编）

```bash
# 1. U-Boot (波特率 115200)
cd /home/xlong/v3s/u-boot && make clean && make -j$(nproc) ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf-

# 2. 内核 DTB + zImage (含 PB6 上拉)
cd /home/xlong/v3s/linux && make clean && make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- zImage && make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- allwinner/sun8i-v3s-licheepi-zero-dock.dtb

# 3. 用户态 (web_server/dji_rc)
bash scripts/build_clean_full_v146.sh   # 编译 + rootfs + 16MB spi_image

# 4. FEL 烧录
sunxi-fel spiflash-write 0 backup/spi_image_v146.bin
```

## 产物

| 文件 | 内容 | md5 |
|---|---|---|
| backup/spi_image_v146.bin | 完整 16MB（U-Boot 115200 + DTB PB6 上拉 + 内核 + rootfs）| `2b1a2503` |
| backup/rootfs_v146.squashfs | OTA 用 rootfs | `6c6b63c2` |
| ubuntu/build_v3s/dji_rc | PB6 自动切换 + SBUS/CRSF（审查修复后）| `3729bcbb` |
| ubuntu/build_v3s/web_server | rc_output 配置 + sbus_std | `c56238ae` |

## 验证

1. **上电 PB6 接地** → UART0 115200 debug 串口（U-Boot + 内核 + getty 全程清晰）
2. **PB6 断开接地** → 自动切协议模式（getty 关闭，UART0 输出 SBUS/CRSF）
3. **再接地** → 自动切回 debug 模式（getty 重启）
4. 切换延迟 ~6s（3 次检测 × 2s 防抖）
