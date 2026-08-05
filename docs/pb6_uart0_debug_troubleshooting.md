# PB6 / UART0 问题排查记录

> 日期: 2026-08-05
> 状态: **进行中** — 已定位根因, 待实施修复方案
> 固件: v1.4.6

## 当前问题

### 问题 1：U-Boot 阶段串口乱码
**现象**：串口软件 115200 下，U-Boot 输出乱码，内核起来后正常（能看到 login 提示）。

### 问题 2：PB6 没接地但误判为 debug 模式
**现象**：PB6 悬空（未接地），但 S99/dji_rc 都检测到接地（PB6_DEBUG=1），UART0 走 debug 串口而不是 SBUS 协议输出。

### 问题 3：内核 bootargs 仍是 921600
**现象**：`Kernel command line: console=ttyS0,921600`，不是期望的 115200。

---

## 已确认的事实

### 1. 设备树 DTB 已正确包含 PB6 上拉
```
spi_image_v146.bin 的 DTB (1MB 处) md5 = 682bde35...（与源码重编一致）
含 pb6 ✓  bias-pull-up ✓  gpio_in ✓
```
- DTS 修改：`sun8i-v3s-licheepi-zero.dts` 加 `pb6_debug_pin` 节点（PB6 gpio_in + bias-pull-up）
- 但**运行时 PB6 仍读 0**（上拉未生效）

### 2. U-Boot env 的根因（关键）
```
U-Boot 嵌入 env (u-boot.bin):
  bootcmd=setenv bootargs console=ttyS0,921600 ...   ← 写死 921600!
  baudrate=115200                                     ← 但 baudrate 115200

CONFIG_ENV_IS_IN_FLASH 未启用  ← 不读 SPI Flash 的 env
```
- U-Boot **不读 SPI Flash 0x7E000 的 env**（我们写的 PB6 bootcmd + 115200 完全没生效）
- U-Boot 用**编译嵌入的 env**：bootcmd 来自 `CONFIG_BOOTCOMMAND` 宏，写死 921600

### 3. 波特率来源梳理
| 层 | 波特率 | 来源 |
|---|---|---|
| SPL 早期 | ? (疑似 921600) | SPL 编译配置 |
| U-Boot proper | 115200 | baudrate env (CONFIG_BAUDRATE=115200 已生效) |
| 内核 console | 921600 | bootcmd 设 bootargs (嵌入 env) |

---

## 已尝试的方案（均未完全解决）

### 尝试 1：改 CONFIG_BAUDRATE 921600→115200
- **做法**：改 `/home/xlong/v3s/u-boot/.config` CONFIG_BAUDRATE=115200，make clean + 重编
- **结果**：U-Boot 自身 baudrate env 变 115200，但 **bootcmd 仍是 921600**（CONFIG_BOOTCOMMAND 没改）
- **未解决**：内核 bootargs 仍 921600

### 尝试 2：build_spi_image.py 写 SPI env (0x7E000)
- **做法**：生成 env 含 `bootcmd=if gpio input 1 6; then console=115200 else console=null`，写入 0x7E000
- **结果**：**完全无效** — 因为 `CONFIG_ENV_IS_IN_FLASH` 未启用，U-Boot 不读 SPI env
- **未解决**

### 尝试 3：DTB 加 PB6 bias-pull-up
- **做法**：DTS 加 `pb6_debug_pin { pins="PB6"; function="gpio_in"; bias-pull-up; }`，重编 DTB
- **结果**：DTB 确认含上拉，但**运行时 PB6 仍读 0**（上拉未生效）
- **疑似**：`function = "gpio_in"` 可能不是 sunxi pinctrl 的正确函数名，pinctrl 申请失败

### 尝试 4：dji_rc PB6 检测 (sysfs → mmap /dev/mem)
- **做法**：先 sysfs，失败改 mmap /dev/mem 读 GPIO 数据寄存器
- **结果**：修复了 sysfs 不可用问题，但**依赖 PB6 实际电平**（上拉未生效时读到 0）

### 尝试 5：S99 devmem 检测 PB6
- **做法**：S99 用 `devmem 0x01C20810` 读 PB6 bit6
- **结果**：检测到 0（接地），但因为上拉未生效，误判

### 尝试 6：改 U-Boot 波特率后 make clean 全量重编
- **做法**：U-Boot make clean + 内核 make clean + DTB 重编
- **结果**：产物确认 CONFIG_BAUDRATE=115200，但 bootcmd 嵌入仍 921600

---

## 根因总结

### U-Boot 乱码 + 内核 921600 的根因
**`CONFIG_ENV_IS_IN_FLASH` 未启用**，导致 U-Boot 使用编译嵌入的 env，而嵌入 env 的 `CONFIG_BOOTCOMMAND` 写死 `console=ttyS0,921600`。

### PB6 误判的根因
DTB 的 `bias-pull-up` 配置**运行时未生效**（可能 `function="gpio_in"` 名称错误，或 pinctrl 未正确应用）。

---

## 已实施的修复方案（2026-08-05）

### 修复 1：dji_rc 运行时寄存器兜底（最终策略）
**改 `pb6_grounded()`**：不再依赖 DTB 上拉，每次检测前主动用 mmap /dev/mem 写寄存器：
- CFG1 强制 PB6 input
- PU0 强制 PB6 pull-up
- 短延时后读 DATA

这样即使 DTB pinctrl 未生效，用户态检测仍可靠（上拉已强制）。

### 修复 2：构建脚本去掉 921600
- `build_spi_final.py` / `build_spi_v145.py`：bootargs 921600 → 115200 + PB6 bootcmd
- `rebuild_full_clean.sh`：不再强制 sed 改回 921600
- S99：不再单独 devmem 读 PB6（交给 dji_rc 统一处理）

### 待验证
- 编译 dji_rc，确认 PB6 诊断打印（CFG1/PU0/DATA）正确
- 镜像字符串检查：产物不再含 `console=ttyS0,921600`
- 实测：PB6 悬空 → 协议模式（上拉生效）；接地 → debug 模式

### 后续优化（非本次救火依赖）
- U-Boot 启用 `CONFIG_ENV_IS_IN_FLASH` + 设 `CONFIG_ENV_OFFSET=0x7E000`，让 SPI env 的 PB6 bootcmd 生效
- 确认 sunxi pinctrl 的 gpio_in function 名（DTB 上拉作为辅助）

---

## 硬件确认

- **PB6 默认上拉**（硬件已定），接地触发 debug
- 板上无外部上拉电阻，需内部上拉（DTB bias-pull-up 或寄存器）

---

## 参考

- 完整方案设计: `docs/pb6_uart0_switch.md`
- 相关提交: `b45133a`, `a31d435`, `f5b1475`, `302f3bf`, `9d207cc`
